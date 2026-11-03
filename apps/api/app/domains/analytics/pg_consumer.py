"""真实 PostgreSQL 消费者：反连接账本协议的最小实现（#65 B 批）。

协议（``docs/database-design/decisions.md``「不漏迟到提交的账本协议」，M1 2026-10-24 指令）：

1. 每轮 **READ COMMITTED 新事务**，``FOR UPDATE NOWAIT`` 锁 ``analytics_consumers``
   本行——同一消费者并发轮询立即失败而不是互相等待（调用方下一轮重试即可）；
2. 通过反连接查询「**未进入本 consumer 处理账本、且不在 open 隔离**」的全部已提交
   事件；稳定排序 ``(occurred_at, id)`` 仅用于批次内顺序，**不做任何永久排除水位**
   ——T1 旧事件晚提交仍会在下一轮成为候选；
3. 每个事件在 savepoint 内应用：契约校验 → 账本插入 → 按键重算日统计；
   校验失败用 savepoint 回滚该事件并登记 ``open`` 隔离（不静默跳过）；
4. 整轮原子提交：可证明的结果（其余事件 + 隔离记录）一起落库；
5. 授权人工把 open 置 ``retry_ready`` 后，重放成功时
   **ledger + 聚合 + resolved 同事务**。

边界（如实记录）：

- ``learning_events`` 为 M5 只读表；本消费者不写源事件。
- 事件级校验复用 ``events.LearningEvent``（契约外毒事件进隔离，不推进也不丢弃）。
- 日统计只落 ``known`` 行：重算后无事件的键删除行，无观测是 unknown（读侧合成），
  不用 0 冒充。
- 迟到事件通过「按键整体重算」生效，不按到账顺序追加秒数（``daily.py``）。
- 时长口径 ``session_inference_v1``，时区固定 ``Asia/Shanghai``（列存快照；
  变更时区须新 consumer 版本）。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics import events as ev
from app.domains.analytics.daily import DailyKey, infer_daily_seconds, key_for_event
from app.domains.analytics.pg_models import (
    AnalyticsConsumer,
    AnalyticsDailyMetric,
    AnalyticsProcessedEvent,
    AnalyticsQuarantinedEvent,
    learning_events_table,
)

STATS_TIMEZONE = ZoneInfo("Asia/Shanghai")
"""S1 日界时区快照；变更时区须新 consumer 版本。"""

_METRIC_TZ_COLUMN = "Asia/Shanghai"

_SESSION_SUBMITTED = ev.EventType.ASSIGNMENT_SUBMITTED.value
_SESSION_GRADED = ev.EventType.ASSIGNMENT_GRADED.value


@dataclass(frozen=True)
class PollResult:
    """一轮轮询的可审计结果。"""

    scanned: int
    applied: int
    quarantined: int
    last_observed_at: datetime | None


class ConsumerBusy(RuntimeError):
    """同一 consumer 的另一轮询仍持行锁；本轮放弃，下一轮重试。"""


def new_id(prefix: str) -> str:
    """前缀 + 32 位小写 hex（组内冻结的 ID 格式，不解析 ID 授权）。"""
    return f"{prefix}_{uuid.uuid4().hex}"


def _source_hash(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AnalyticsPgWorker:
    """按协议轮询 ``learning_events`` 并维护账本、隔离与最小日统计。"""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self._last_resolver: str | None = None
        """最近一次 retry_quarantined 的操作者；重放成功时写入 resolved_by。"""

    def poll_once(
        self, consumer_key: str, algorithm_version: str, batch_size: int = 200
    ) -> PollResult:
        """执行一轮完整轮询；整轮原子提交，异常时无部分状态残留。"""
        with self._sessions() as session:
            try:
                with session.begin():
                    consumer = self._lock_consumer(session, consumer_key, algorithm_version)
                    rows = self._candidates(session, consumer.id, batch_size)
                    applied = 0
                    quarantined = 0
                    last_observed: datetime | None = consumer.last_observed_at
                    for row in rows:
                        occurred: datetime = row["occurred_at"]
                        try:
                            with session.begin_nested():
                                self._apply_event(session, consumer, row)
                        except ev.EventValidationError:
                            self._quarantine(session, consumer.id, row["id"], "schema_violation")
                            quarantined += 1
                        else:
                            applied += 1
                            if last_observed is None or occurred > last_observed:
                                last_observed = occurred
                    now = datetime.now(UTC)
                    consumer.last_poll_at = now
                    consumer.last_observed_at = last_observed
                    consumer.processed_count += applied
                    consumer.updated_at = now
                    return PollResult(
                        scanned=len(rows),
                        applied=applied,
                        quarantined=quarantined,
                        last_observed_at=last_observed,
                    )
            except RuntimeError as error:
                if _is_lock_unavailable(error):
                    raise ConsumerBusy(consumer_key) from error
                raise

    def set_consumer_status(self, consumer_key: str, algorithm_version: str, status: str) -> None:
        """注册/启停消费者（管理动作；S1 由部署侧显式调用，不开 HTTP 入口）。"""
        with self._sessions() as session:
            with session.begin():
                consumer = self._lock_consumer(session, consumer_key, algorithm_version)
                consumer.status = status
                consumer.updated_at = datetime.now(UTC)

    def retry_quarantined(
        self, consumer_key: str, algorithm_version: str, event_id: str, resolver_user_id: str
    ) -> bool:
        """人工审计后把 open 隔离置 retry_ready；授权校验由上层调用方负责。"""
        self._last_resolver = resolver_user_id
        with self._sessions() as session:
            with session.begin():
                consumer = self._lock_consumer(session, consumer_key, algorithm_version)
                row = session.execute(
                    select(AnalyticsQuarantinedEvent).where(
                        AnalyticsQuarantinedEvent.consumer_id == consumer.id,
                        AnalyticsQuarantinedEvent.event_id == event_id,
                    )
                ).scalar_one_or_none()
                if row is None:
                    return False
                row.status = "retry_ready"
                return True

    def _lock_consumer(self, session: Session, key: str, version: str) -> AnalyticsConsumer:
        """确保 consumer 行存在并锁行（NOWAIT：并发轮询立即失败，不排队）。"""
        existing = session.execute(
            select(AnalyticsConsumer)
            .where(
                AnalyticsConsumer.consumer_key == key,
                AnalyticsConsumer.algorithm_version == version,
            )
            .with_for_update(nowait=True)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        consumer = AnalyticsConsumer(
            id=new_id("consumer"), consumer_key=key, algorithm_version=version, status="active"
        )
        session.add(consumer)
        session.flush()
        return session.execute(
            select(AnalyticsConsumer)
            .where(AnalyticsConsumer.id == consumer.id)
            .with_for_update(nowait=True)
        ).scalar_one()

    def _candidates(self, session: Session, consumer_id: str, batch_size: int) -> Sequence[Any]:
        """反连接：未入本 consumer 账本且不在 open 隔离的已提交事件，稳定排序取一批。"""
        feed = learning_events_table()
        ledger = select(AnalyticsProcessedEvent.event_id).where(
            AnalyticsProcessedEvent.consumer_id == consumer_id,
            AnalyticsProcessedEvent.event_id == feed.c.id,
        )
        quarantine = select(AnalyticsQuarantinedEvent.event_id).where(
            AnalyticsQuarantinedEvent.consumer_id == consumer_id,
            AnalyticsQuarantinedEvent.status == "open",
            AnalyticsQuarantinedEvent.event_id == feed.c.id,
        )
        result = session.execute(
            select(feed)
            .where(~feed.c.id.in_(ledger), ~feed.c.id.in_(quarantine))
            .order_by(feed.c.occurred_at, feed.c.id)
            .limit(batch_size)
        )
        return result.mappings().all()

    def _apply_event(self, session: Session, consumer: AnalyticsConsumer, row: Any) -> None:
        """单事件应用（在调用方 savepoint 内）；失败抛 ``EventValidationError``。"""
        raw: dict[str, Any] = {
            "eventId": row["id"],
            "eventType": row["event_type"],
            "userId": row["user_id"],
            "courseId": row["course_id"],
            "occurredAt": row["occurred_at"].isoformat(),
            "traceId": row["trace_id"],
            "schemaVersion": row["schema_version"],
            "payload": row["payload"],
        }
        event = ev.LearningEvent.from_raw(raw)
        occurred_at: datetime = row["occurred_at"]

        session.add(
            AnalyticsProcessedEvent(
                consumer_id=consumer.id,
                event_id=row["id"],
                source_hash=_source_hash(raw),
            )
        )
        key = key_for_event(
            student_user_id=event.user_id,
            course_id=event.course_id,
            class_id=row["class_id"],
            occurred_at=occurred_at,
            tz=STATS_TIMEZONE,
        )
        self._recompute_daily(session, consumer.id, key)
        self._resolve_if_retried(session, consumer.id, row["id"])

    def _recompute_daily(self, session: Session, consumer_id: str, key: DailyKey) -> None:
        """对受影响键整体重算：已处理事件集合 → 计数与推断时长 → upsert/删除。

        迟到事件因此不按到账顺序追加：键内统计只取决于「已入账本的事实」，
        与处理顺序无关。重算后无事件的键删除行（无观测 unknown 不落库）。
        """
        feed = learning_events_table()
        day_start = datetime.combine(key.metric_date, datetime.min.time(), tzinfo=STATS_TIMEZONE)
        day_end = day_start + timedelta(days=1)
        rows = session.execute(
            select(feed.c.occurred_at, feed.c.event_type, feed.c.payload)
            .join(
                AnalyticsProcessedEvent,
                (AnalyticsProcessedEvent.event_id == feed.c.id)
                & (AnalyticsProcessedEvent.consumer_id == consumer_id),
            )
            .where(
                feed.c.user_id == key.student_user_id,
                _null_safe(feed.c.course_id, key.course_id),
                _null_safe(feed.c.class_id, key.class_id),
                feed.c.occurred_at >= day_start,
                feed.c.occurred_at < day_end,
            )
            .order_by(feed.c.occurred_at)
        ).all()

        existing = self._find_daily(session, consumer_id, key)
        if not rows:
            if existing is not None:
                session.execute(
                    delete(AnalyticsDailyMetric).where(AnalyticsDailyMetric.id == existing.id)
                )
            return

        submitted: set[str] = set()
        graded_latest: dict[str, bool | None] = {}
        graded_order: list[tuple[datetime, str, bool | None]] = []
        for r in rows:
            payload: dict[str, Any] = r.payload or {}
            submission_id = payload.get("submissionId")
            if (
                r.event_type == _SESSION_SUBMITTED
                and isinstance(submission_id, str)
                and submission_id
            ):
                submitted.add(submission_id)
            elif (
                r.event_type == _SESSION_GRADED and isinstance(submission_id, str) and submission_id
            ):
                is_correct = payload.get("isCorrect")
                graded_order.append(
                    (
                        r.occurred_at,
                        submission_id,
                        is_correct if isinstance(is_correct, bool) else None,
                    )
                )
        # 判分取最新：同一 submissionId 多次判分以 occurredAt 最新为准（统计契约口径）
        for _, submission_id, is_correct in sorted(graded_order, key=lambda item: item[0]):
            graded_latest[submission_id] = is_correct
        wrong = sum(1 for value in graded_latest.values() if value is False)
        sample = sum(1 for value in graded_latest.values() if value is not None)
        study = infer_daily_seconds([r.occurred_at for r in rows])
        data_through = max(r.occurred_at for r in rows)
        now = datetime.now(UTC)

        if existing is None:
            session.add(
                AnalyticsDailyMetric(
                    id=new_id("metric"),
                    consumer_id=consumer_id,
                    student_user_id=key.student_user_id,
                    course_id=key.course_id,
                    class_id=key.class_id,
                    metric_date=key.metric_date,
                    timezone=_METRIC_TZ_COLUMN,
                    study_seconds=study,
                    submission_count=len(submitted),
                    wrong_count=wrong,
                    sample_count=sample,
                    data_state="known",
                    data_through=data_through,
                )
            )
        else:
            existing.study_seconds = study
            existing.submission_count = len(submitted)
            existing.wrong_count = wrong
            existing.sample_count = sample
            existing.data_state = "known"
            existing.data_through = data_through
            existing.updated_at = now

    def _find_daily(
        self, session: Session, consumer_id: str, key: DailyKey
    ) -> AnalyticsDailyMetric | None:
        return session.execute(
            select(AnalyticsDailyMetric).where(
                AnalyticsDailyMetric.consumer_id == consumer_id,
                AnalyticsDailyMetric.student_user_id == key.student_user_id,
                _null_safe(AnalyticsDailyMetric.course_id, key.course_id),
                _null_safe(AnalyticsDailyMetric.class_id, key.class_id),
                AnalyticsDailyMetric.metric_date == key.metric_date,
                AnalyticsDailyMetric.timezone == _METRIC_TZ_COLUMN,
            )
        ).scalar_one_or_none()

    def _resolve_if_retried(self, session: Session, consumer_id: str, event_id: str) -> None:
        """重放成功：ledger 已写、聚合已重算，此刻把 retry_ready 置 resolved（同事务）。"""
        session.execute(
            update(AnalyticsQuarantinedEvent)
            .where(
                AnalyticsQuarantinedEvent.consumer_id == consumer_id,
                AnalyticsQuarantinedEvent.event_id == event_id,
                AnalyticsQuarantinedEvent.status == "retry_ready",
            )
            .values(
                status="resolved",
                resolved_at=datetime.now(UTC),
                resolved_by_user_id=self._last_resolver,
            )
        )

    def _quarantine(
        self, session: Session, consumer_id: str, event_id: str, error_code: str
    ) -> None:
        """登记/累加隔离记录；savepoint 已回滚，本函数在事务主干执行。"""
        row = session.execute(
            select(AnalyticsQuarantinedEvent).where(
                AnalyticsQuarantinedEvent.consumer_id == consumer_id,
                AnalyticsQuarantinedEvent.event_id == event_id,
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            session.add(
                AnalyticsQuarantinedEvent(
                    id=new_id("quarantine"),
                    consumer_id=consumer_id,
                    event_id=event_id,
                    error_code=error_code,
                    status="open",
                    attempts=1,
                    first_failed_at=now,
                    last_failed_at=now,
                )
            )
        else:
            row.status = "open"
            row.attempts += 1
            row.last_failed_at = now
            row.error_code = error_code


def _is_lock_unavailable(error: RuntimeError) -> bool:
    text = str(error).lower()
    return "could not obtain lock" in text or "nowait" in text


def _null_safe(column: Any, value: str | None) -> ColumnElement[bool]:
    """NULL 敏感的等值过滤：值与 NULL 各自成立（唯一键含 NULL 语义）。"""
    if value is None:
        return cast("ColumnElement[bool]", column.is_(None))
    return cast("ColumnElement[bool]", column == value)


def metric_date_of(occurred_at: datetime, tz: ZoneInfo) -> date:
    """事件发生时刻在指定时区日历下的本地日（供测试与读侧复用）。"""
    return occurred_at.astimezone(tz).date()


__all__ = [
    "ConsumerBusy",
    "PollResult",
    "AnalyticsPgWorker",
    "STATS_TIMEZONE",
    "metric_date_of",
    "new_id",
]
