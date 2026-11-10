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
5. 授权人工把 open 置 ``retry_ready`` 时，**授权操作者持久化到隔离行**
   （``resolved_by_user_id``）；重放成功时 ledger + 聚合 + resolved 同事务，
   resolved 的操作者从隔离行读取——worker 重启、并发请求不得串用身份。
   操作者外键 RESTRICT，不靠 SET NULL 破坏已结算记录（#79 decisions.md）。

源事实摘要（``learning-feed-sha256-v1``，#79 decisions.md 2026-11-03 冻结）：

- 字段 ``event_id/event_type/user_id/course_id/class_id/occurred_at/
  recorded_at/trace_id/schema_version/payload`` 全量纳入，含 NULL；
- 两个时间统一转 UTC、固定 6 位小数并以 ``Z`` 结尾（等价时刻的不同时区
  表示摘要一致）；
- 对象键递归排序、UTF-8、``ensure_ascii=False``、JSON 紧凑分隔符、
  禁止 NaN/Infinity；整数保持整数；SHA256 小写 hex。
- 迟到重算时按同协议重新计算并与账本比对，不符抛
  ``SourceFactChanged`` 回滚本轮：不覆盖旧摘要、不重复计数。

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

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.exc import SQLAlchemyError
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

SOURCE_HASH_PROTOCOL = "learning-feed-sha256-v1"
"""源事实摘要协议名（#79 decisions.md 2026-11-03）；算法变更须新建 consumer 版本。"""

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


class SourceFactChanged(RuntimeError):
    """源事实与账本摘要不符（learning-feed-sha256-v1）：本轮回滚，不覆盖旧摘要。"""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"source fact changed for {event_id}: ledger hash mismatch")
        self.event_id = event_id


def new_id(prefix: str) -> str:
    """前缀 + 32 位小写 hex（组内冻结的 ID 格式，不解析 ID 授权）。"""
    return f"{prefix}_{uuid.uuid4().hex}"


def _utc_micros(value: datetime) -> str:
    """等价时刻统一为 UTC 固定 6 位小数（naive 视为 UTC；timestamptz 恒为 aware）。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _source_hash(row: Any) -> str:
    """learning-feed-sha256-v1：feed 行全字段规范化摘要（含 NULL），小写 hex。"""
    canonical: dict[str, Any] = {
        "event_id": row["id"],
        "event_type": row["event_type"],
        "user_id": row["user_id"],
        "course_id": row["course_id"],
        "class_id": row["class_id"],
        "occurred_at": _utc_micros(row["occurred_at"]),
        "recorded_at": None if row["recorded_at"] is None else _utc_micros(row["recorded_at"]),
        "trace_id": row["trace_id"],
        "schema_version": row["schema_version"],
        "payload": row["payload"],
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AnalyticsPgWorker:
    """按协议轮询 ``learning_events`` 并维护账本、隔离与最小日统计。"""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

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
            except SQLAlchemyError as error:
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
        """人工审计后把 open 隔离置 retry_ready，授权操作者持久化到隔离行。

        授权校验由上层调用方负责；resolved 的操作者身份以本行为准，
        worker 重启或并发请求不共享进程变量（#79 decisions.md）。
        """
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
                row.resolved_by_user_id = resolver_user_id
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
                source_hash=_source_hash(row),
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
        重算同时按 learning-feed-sha256-v1 复核每个已入账本事件的源事实：
        不符抛 ``SourceFactChanged`` 回滚本轮，不覆盖旧摘要、不重复计数。
        """
        feed = learning_events_table()
        day_start = datetime.combine(key.metric_date, datetime.min.time(), tzinfo=STATS_TIMEZONE)
        day_end = day_start + timedelta(days=1)
        rows = (
            session.execute(
                select(feed, AnalyticsProcessedEvent.source_hash)
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
            )
            .mappings()
            .all()
        )
        for row in rows:
            if _source_hash(row) != row["source_hash"]:
                raise SourceFactChanged(cast("str", row["id"]))

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
        """重放成功：ledger 已写、聚合已重算，此刻把 retry_ready 置 resolved（同事务）。

        操作者身份从隔离行读取（retry_quarantined 持久化），不取进程变量。
        """
        row = session.execute(
            select(AnalyticsQuarantinedEvent).where(
                AnalyticsQuarantinedEvent.consumer_id == consumer_id,
                AnalyticsQuarantinedEvent.event_id == event_id,
                AnalyticsQuarantinedEvent.status == "retry_ready",
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "resolved"
        row.resolved_at = datetime.now(UTC)

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


def _is_lock_unavailable(error: SQLAlchemyError) -> bool:
    """PostgreSQL 55P03（lock_not_available）：NOWAIT 未立即拿到行锁。

    判断兼容驱动差异：优先异常类名，其次 pgcode，最后消息文本（本地化消息不可靠）。
    """
    original: Any = getattr(error, "orig", None)
    if type(original).__name__.lower() == "locknotavailable":
        return True
    if getattr(original, "pgcode", None) == "55P03":
        return True
    text = str(error).lower()
    return "could not obtain lock" in text or "55p03" in text


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
    "SourceFactChanged",
    "SOURCE_HASH_PROTOCOL",
    "AnalyticsPgWorker",
    "STATS_TIMEZONE",
    "metric_date_of",
    "new_id",
]
