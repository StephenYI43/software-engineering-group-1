"""成长报告快照服务（#65 C 批第一批）。

契约：``packages/contracts/analytics/report-api.md``（数据结构与快照语义冻结稿）。
表结构：``pg_models.AnalyticsReportSnapshot`` / ``ReportJob``（#79 DDL 表 5-38/39）。

事务边界：所有方法以 ``session.begin()`` 开启整段事务，repository 语义——
不自行 commit，失败整批回滚。幂等检查、任务创建与快照生成在同一事务内完成。

边界（如实记录）：

- 本批无 worker 队列：``create_job`` 在同一事务内同步生成快照，
  任务 queued → succeeded 瞬时完成，不伪造 running/started_at。
- 授权最小实现：student 仅本人报告；teacher/admin 全部放行。
  真实 ACL（教师仅当前有效授课班级、admin 显式管理范围）等 M1 #84 底座。
- 目标（学生/班级）存在性由 FK RESTRICT 保证，服务层不代查 M1/M5 身份表；
  FK 冲突的 404/422 映射在路由批接入时统一处理。
- ``reason`` / 重放操作者的持久审计在 M1 #84 审计域接入，本批不造新表。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domains.analytics.errors import AnalyticsError, InvalidQueryError
from app.domains.analytics.pg_consumer import STATS_TIMEZONE, new_id
from app.domains.analytics.pg_models import (
    AnalyticsConsumer,
    AnalyticsDailyMetric,
    AnalyticsQuarantinedEvent,
    AnalyticsReportSnapshot,
    ReportJob,
)

_CONSUMER_KEY = "teacher-overview"
"""报告快照的数据源 consumer（与 B 批日统计 consumer 同源）。"""

_CONSUMER_VERSION = "v1"

_SNAPSHOT_TZ_COLUMN = "Asia/Shanghai"
"""日统计快照的日界时区列值（B 批固定；其余时区属 S2 增量）。"""

_DURATION_ALGORITHM = "session_inference_v1"
_METRICS_SCHEMA_VERSION = "1.0"

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SORT_WHITELIST = frozenset({"created_at", "-created_at"})
_QUARANTINED_STATUS_WHITELIST = frozenset({"open", "retry_ready", "resolved"})
_ROLES = frozenset({"student", "teacher", "admin"})

_MAX_PAGE = 1000
_MAX_PAGE_SIZE = 100
_MAX_REASON_LENGTH = 300


class ReportIdempotencyConflictError(AnalyticsError):
    """同一 actor 的幂等键对应了不同报告参数（路由映射 409 / 业务码 20002）。"""

    def __init__(self) -> None:
        super().__init__(409, "IDEMPOTENCY_KEY_CONFLICT", "相同幂等键已用于不同的报告参数")


class ReportForbiddenError(AnalyticsError):
    """角色禁止（403 / 业务码 20011）：学生只能请求本人报告；隔离区仅管理员。"""

    def __init__(self) -> None:
        super().__init__(403, "REPORT_FORBIDDEN", "无权执行该报告操作")


class ReportNotFoundError(AnalyticsError):
    """报告不存在或越权（统一 404 防枚举 / 业务码 20001）。"""

    def __init__(self) -> None:
        super().__init__(404, "REPORT_NOT_FOUND", "未找到报告")


class ReportJobNotFoundError(AnalyticsError):
    """报告任务不存在或越权（统一 404 防枚举 / 业务码 20001）。"""

    def __init__(self) -> None:
        super().__init__(404, "REPORT_JOB_NOT_FOUND", "未找到报告任务")


class QuarantinedEventNotFoundError(AnalyticsError):
    """隔离事件不存在或超出管理范围（业务码 20001）。"""

    def __init__(self) -> None:
        super().__init__(404, "QUARANTINED_EVENT_NOT_FOUND", "未找到隔离事件")


@dataclass(frozen=True)
class ReportActor:
    """最小 actor 形状（#84 鉴权底座接入前由调用方显式构造）。"""

    user_id: str
    role: str

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"未知角色: {self.role}")


@dataclass(frozen=True)
class JobView:
    """Job 的服务层视图（wire 形状见契约「Job」；路由批负责 camelCase 封套）。"""

    job_id: str
    status: str
    is_mock: bool
    result_id: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class ReportView:
    """LearningReport 的服务层视图。"""

    report_id: str
    student_user_id: str | None
    class_id: str | None
    period_start: datetime
    period_end: datetime
    data_through: datetime | None
    duration_seconds: dict[str, Any]
    knowledge_points: list[Any]
    suggestions: list[Any]
    generated_at: datetime


@dataclass(frozen=True)
class ReportJobOutcome:
    """create_job 的返回：任务状态与（成功时）报告快照。"""

    job: JobView
    report: ReportView | None


@dataclass(frozen=True)
class QuarantinedView:
    """QuarantinedEvent 的服务层视图（只含引用与脱敏原因）。"""

    quarantine_id: str
    event_id: str
    consumer_id: str
    error_code: str
    status: str
    attempts: int
    first_failed_at: datetime
    last_failed_at: datetime


@dataclass(frozen=True)
class ReportListPage:
    items: list[ReportView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class QuarantinedListPage:
    items: list[QuarantinedView]
    total: int
    page: int
    page_size: int


def _metric_known(value: int) -> dict[str, Any]:
    return {"state": "known", "value": value, "algorithm": _DURATION_ALGORITHM}


def _metric_unknown(reason: str) -> dict[str, Any]:
    return {"state": "unknown", "reason": reason}


def _job_view(job: ReportJob) -> JobView:
    return JobView(
        job_id=job.id,
        status=job.status,
        is_mock=False,  # 真实 PG 聚合，非模拟执行
        result_id=job.report_id,
        error_code=job.error_code,
        created_at=job.created_at,
        # report_jobs 无 started_at 列；同步生成路径不伪造 running 阶段
        started_at=None,
        finished_at=job.finished_at,
    )


def _report_view(snapshot: AnalyticsReportSnapshot) -> ReportView:
    metrics: dict[str, Any] = snapshot.metrics
    return ReportView(
        report_id=snapshot.id,
        student_user_id=snapshot.student_user_id,
        class_id=snapshot.class_id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        data_through=snapshot.data_through,
        duration_seconds=metrics["durationSeconds"],
        knowledge_points=list(metrics.get("knowledgePoints", [])),
        suggestions=list(metrics.get("suggestions", [])),
        generated_at=snapshot.generated_at,
    )


def _quarantined_view(row: AnalyticsQuarantinedEvent) -> QuarantinedView:
    return QuarantinedView(
        quarantine_id=row.id,
        event_id=row.event_id,
        consumer_id=row.consumer_id,
        error_code=row.error_code,
        status=row.status,
        attempts=row.attempts,
        first_failed_at=row.first_failed_at,
        last_failed_at=row.last_failed_at,
    )


def _null_eq(column: Any, value: str | None) -> Any:
    """NULL 敏感的等值过滤（快照自然键含 NULL；与 pg_consumer._null_safe 同义）。"""
    if value is None:
        return column.is_(None)
    return column == value


def _validate_page(page: int, page_size: int) -> tuple[int, int]:
    problems: list[str] = []
    if not 1 <= page <= _MAX_PAGE:
        problems.append("page 范围 1—1000")
    if not 1 <= page_size <= _MAX_PAGE_SIZE:
        problems.append("page_size 范围 1—100")
    if problems:
        raise InvalidQueryError({"pagination": "；".join(problems)})
    return page, page_size


def _validate_sort(sort: str) -> str:
    if sort not in _SORT_WHITELIST:
        raise InvalidQueryError({"sort": "仅允许 created_at / -created_at"})
    return sort


class ReportPgService:
    """成长报告快照服务：幂等建任务、同事务快照生成、查询与隔离区管理。"""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    # ------------------------------------------------------------------ 创建

    def create_job(
        self,
        *,
        actor: ReportActor,
        student_user_id: str | None,
        class_id: str | None,
        period_start: datetime,
        period_end: datetime,
        timezone: str,
        idempotency_key: str,
    ) -> ReportJobOutcome:
        """创建报告任务并同步生成快照（R02 语义；同事务，repository 不 commit）。

        幂等：同 (requested_by, idempotency_key) 已存在时——参数一致返回既有
        Job，参数不一致抛 ``ReportIdempotencyConflictError``（路由映射 409）。
        换参比较只覆盖 report_jobs 持久化的字段（目标 + 周期）；timezone 本批
        固定 ``Asia/Shanghai`` 且不入库，不参与比较。

        目标（学生/班级）存在性由 FK RESTRICT 保证；目标不存在时事务以
        IntegrityError 失败整批回滚（路由批统一映射 404/422）。
        """
        self._validate_target(student_user_id, class_id)
        self._validate_period(period_start, period_end)
        self._validate_timezone(timezone)
        self._validate_idempotency_key(idempotency_key)
        if actor.role == "student" and (class_id is not None or student_user_id != actor.user_id):
            # 学生只可指定本人（api.md R02 资源权限；403 = 业务码 20011）
            raise ReportForbiddenError()

        with self._sessions() as session:
            with session.begin():
                consumer = self._ensure_consumer(session)
                existing = session.execute(
                    select(ReportJob).where(
                        ReportJob.requested_by_user_id == actor.user_id,
                        ReportJob.idempotency_key == idempotency_key,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if not _same_request(
                        existing, student_user_id, class_id, period_start, period_end
                    ):
                        raise ReportIdempotencyConflictError()
                    return ReportJobOutcome(
                        job=_job_view(existing),
                        report=self._load_report_view(session, existing.report_id),
                    )

                job = ReportJob(
                    id=new_id("job"),
                    requested_by_user_id=actor.user_id,
                    student_user_id=student_user_id,
                    class_id=class_id,
                    consumer_id=consumer.id,
                    period_start=period_start,
                    period_end=period_end,
                    status="queued",
                    idempotency_key=idempotency_key,
                    created_at=datetime.now(UTC),
                )
                session.add(job)
                session.flush()

                snapshot = self._generate_snapshot(
                    session,
                    consumer.id,
                    student_user_id=student_user_id,
                    class_id=class_id,
                    period_start=period_start,
                    period_end=period_end,
                )
                job.status = "succeeded"
                job.report_id = snapshot.id
                job.finished_at = datetime.now(UTC)
                return ReportJobOutcome(job=_job_view(job), report=_report_view(snapshot))

    # ------------------------------------------------------------------ 读取

    def get_report(self, *, report_id: str, actor: ReportActor) -> ReportView:
        """读取报告快照（R04 语义）。学生仅本人；越权与不存在统一 404。"""
        with self._sessions() as session:
            with session.begin():
                snapshot = session.get(AnalyticsReportSnapshot, report_id)
                if snapshot is None or (
                    actor.role == "student" and snapshot.student_user_id != actor.user_id
                ):
                    raise ReportNotFoundError()
                return _report_view(snapshot)

    def get_job(self, *, job_id: str, actor: ReportActor) -> JobView:
        """查询报告任务（R03 语义）。学生仅本人创建或以本人为目标的任务。"""
        with self._sessions() as session:
            with session.begin():
                job = session.get(ReportJob, job_id)
                if job is None or (
                    actor.role == "student"
                    and job.requested_by_user_id != actor.user_id
                    and job.student_user_id != actor.user_id
                ):
                    raise ReportJobNotFoundError()
                return _job_view(job)

    def list_reports(
        self,
        *,
        actor: ReportActor,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
    ) -> ReportListPage:
        """授权成长报告列表（R05 语义）。学生仅本人；teacher/admin 本批全部放行。"""
        page, page_size = _validate_page(page, page_size)
        sort_key = _validate_sort(sort)
        with self._sessions() as session:
            with session.begin():
                stmt = select(AnalyticsReportSnapshot)
                if actor.role == "student":
                    stmt = stmt.where(AnalyticsReportSnapshot.student_user_id == actor.user_id)
                total = int(
                    session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
                )
                # sort 白名单映射 ORM（created_at → 快照 generated_at），以 id 稳定排序
                order_col = AnalyticsReportSnapshot.generated_at
                stmt = stmt.order_by(
                    order_col.asc() if sort_key == "created_at" else order_col.desc(),
                    AnalyticsReportSnapshot.id,
                )
                rows = (
                    session.execute(stmt.limit(page_size).offset((page - 1) * page_size))
                    .scalars()
                    .all()
                )
                return ReportListPage(
                    items=[_report_view(row) for row in rows],
                    total=total,
                    page=page,
                    page_size=page_size,
                )

    # --------------------------------------------------------------- 隔离区

    def list_quarantined(
        self,
        *,
        actor: ReportActor,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "-created_at",
    ) -> QuarantinedListPage:
        """查询脱敏隔离事件（R06 语义，仅 admin；只返回引用与脱敏原因）。"""
        if actor.role != "admin":
            raise ReportForbiddenError()
        page, page_size = _validate_page(page, page_size)
        sort_key = _validate_sort(sort)
        if status is not None and status not in _QUARANTINED_STATUS_WHITELIST:
            raise InvalidQueryError({"status": "仅允许 open / retry_ready / resolved"})
        with self._sessions() as session:
            with session.begin():
                stmt = select(AnalyticsQuarantinedEvent)
                if status is not None:
                    stmt = stmt.where(AnalyticsQuarantinedEvent.status == status)
                total = int(
                    session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
                )
                # sort 白名单键 created_at → 首次失败时间（隔离行的创建时刻）
                order_col = AnalyticsQuarantinedEvent.first_failed_at
                stmt = stmt.order_by(
                    order_col.asc() if sort_key == "created_at" else order_col.desc(),
                    AnalyticsQuarantinedEvent.id,
                )
                rows = (
                    session.execute(stmt.limit(page_size).offset((page - 1) * page_size))
                    .scalars()
                    .all()
                )
                return QuarantinedListPage(
                    items=[_quarantined_view(row) for row in rows],
                    total=total,
                    page=page,
                    page_size=page_size,
                )

    def replay_quarantined(
        self, *, quarantine_id: str, reason: str, actor: ReportActor, idempotency_key: str
    ) -> QuarantinedView:
        """授权重放隔离事件（R07 语义，仅 admin）：置 retry_ready，不改源事件。

        置位语义与 ``AnalyticsPgWorker.retry_quarantined`` 等价（open/retry_ready/
        resolved 均可再次置位），由 worker 下一轮轮询重放；重放成功时
        ledger + 聚合 + resolved 同事务（B 批已实现）。

        审计边界：``reason`` 与操作者的**持久**审计在 M1 #84 审计域接入——
        本批不造新表，reason 仅做格式校验（长度 1—300），不入库；
        ``idempotency_key`` 同理仅校验格式，登记与冲突检测随 #84 落地。
        B 批 worker 的 resolved_by 为 worker 实例内存（``_last_resolver``），
        跨实例「重放成功」路径依赖 #84 落地持久审计后修复（如实记录）。
        """
        if actor.role != "admin":
            raise ReportForbiddenError()
        if not 1 <= len(reason) <= _MAX_REASON_LENGTH:
            raise InvalidQueryError({"reason": "长度 1—300"})
        self._validate_idempotency_key(idempotency_key)
        with self._sessions() as session:
            with session.begin():
                row = session.get(AnalyticsQuarantinedEvent, quarantine_id)
                if row is None:
                    raise QuarantinedEventNotFoundError()
                row.status = "retry_ready"
                return _quarantined_view(row)

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _ensure_consumer(session: Session) -> AnalyticsConsumer:
        """报告数据源 consumer（teacher-overview/v1）：存在则复用，缺失则注册。

        参照 ``pg_consumer._lock_consumer`` 的 ensure 语义；报告路径只读聚合，
        无需 NOWAIT 行锁。并发首建依赖 (consumer_key, algorithm_version) 唯一
        约束：冲突方收到 IntegrityError（不吞异常，调用方重试即可）。
        """
        existing = session.execute(
            select(AnalyticsConsumer).where(
                AnalyticsConsumer.consumer_key == _CONSUMER_KEY,
                AnalyticsConsumer.algorithm_version == _CONSUMER_VERSION,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        consumer = AnalyticsConsumer(
            id=new_id("consumer"),
            consumer_key=_CONSUMER_KEY,
            algorithm_version=_CONSUMER_VERSION,
            status="active",
        )
        session.add(consumer)
        session.flush()
        return consumer

    @staticmethod
    def _generate_snapshot(
        session: Session,
        consumer_id: str,
        *,
        student_user_id: str | None,
        class_id: str | None,
        period_start: datetime,
        period_end: datetime,
    ) -> AnalyticsReportSnapshot:
        """生成或复用报告快照（调用方事务内）。

        - (consumer, 目标, 周期) 命中既有快照则直接复用：快照是生成时刻的
          不可变事实，本批不做刷新（S2 再定刷新策略）；
        - duration_seconds：窗口内（Asia/Shanghai 日界）纳入 known 行的
          study_seconds 求和；窗口内无任何已知观测 → unknown(no_events_in_period)，
          不用 0 冒充（沿用 statistics-api.md S1 / MetricNumber 语义）；
        - data_through：纳入行的最新 data_through（最新事件发生时间）；
        - knowledge_points / suggestions 本批恒 []（受控词表未定义，S2 增量）。
        """
        first_day = period_start.astimezone(STATS_TIMEZONE).date()
        # 半开区间 [start, end)：end 恰为某日零点时该日不计入
        last_day = (period_end - timedelta(microseconds=1)).astimezone(STATS_TIMEZONE).date()
        stmt = select(AnalyticsDailyMetric).where(
            AnalyticsDailyMetric.consumer_id == consumer_id,
            AnalyticsDailyMetric.timezone == _SNAPSHOT_TZ_COLUMN,
            AnalyticsDailyMetric.metric_date >= first_day,
            AnalyticsDailyMetric.metric_date <= last_day,
        )
        if student_user_id is not None:
            stmt = stmt.where(AnalyticsDailyMetric.student_user_id == student_user_id)
        elif class_id is not None:
            stmt = stmt.where(AnalyticsDailyMetric.class_id == class_id)
        else:  # _validate_target 已保证恰好一个目标；到此属于编程错误
            raise ValueError("报告目标缺失")
        rows = session.execute(stmt).scalars().all()

        seconds = [row.study_seconds for row in rows if row.study_seconds is not None]
        throughs = [row.data_through for row in rows if row.data_through is not None]
        duration = (
            _metric_known(sum(seconds)) if seconds else _metric_unknown("no_events_in_period")
        )
        data_through = max(throughs) if throughs else None
        sample_count = (
            1 if student_user_id is not None else len({row.student_user_id for row in rows})
        )
        metrics = {
            "schemaVersion": _METRICS_SCHEMA_VERSION,
            "durationSeconds": duration,
            "knowledgePoints": [],
            "suggestions": [],
        }

        existing = session.execute(
            select(AnalyticsReportSnapshot).where(
                AnalyticsReportSnapshot.consumer_id == consumer_id,
                _null_eq(AnalyticsReportSnapshot.student_user_id, student_user_id),
                _null_eq(AnalyticsReportSnapshot.class_id, class_id),
                AnalyticsReportSnapshot.period_start == period_start,
                AnalyticsReportSnapshot.period_end == period_end,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        snapshot = AnalyticsReportSnapshot(
            id=new_id("report"),
            consumer_id=consumer_id,
            student_user_id=student_user_id,
            class_id=class_id,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics,
            sample_count=sample_count,
            data_through=data_through,
            generated_at=datetime.now(UTC),
        )
        session.add(snapshot)
        session.flush()
        return snapshot

    def _load_report_view(self, session: Session, report_id: str | None) -> ReportView | None:
        if report_id is None:
            return None
        snapshot = session.get(AnalyticsReportSnapshot, report_id)
        return None if snapshot is None else _report_view(snapshot)

    @staticmethod
    def _validate_target(student_user_id: str | None, class_id: str | None) -> None:
        if (student_user_id is None) == (class_id is None):
            raise InvalidQueryError({"target": "studentUserId 与 classId 必须恰好提供一个"})

    @staticmethod
    def _validate_period(period_start: datetime, period_end: datetime) -> None:
        problems: list[str] = []
        if period_start.tzinfo is None or period_end.tzinfo is None:
            problems.append("periodStart/periodEnd 必须为带时区的 UTC 时间")
        elif period_end <= period_start:
            problems.append("periodEnd 必须晚于 periodStart")
        if problems:
            raise InvalidQueryError({"period": "；".join(problems)})

    @staticmethod
    def _validate_timezone(timezone: str) -> None:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise InvalidQueryError({"timezone": "非法 IANA 时区"}) from error
        if timezone != _SNAPSHOT_TZ_COLUMN:
            # 日统计按 Asia/Shanghai 快照落库（B 批固定）；其余时区属 S2 增量
            raise InvalidQueryError({"timezone": "本批报告快照仅支持 Asia/Shanghai"})

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> None:
        if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
            raise InvalidQueryError({"idempotencyKey": "长度 1—128，仅允许字母数字与 . _ : -"})


def _same_request(
    job: ReportJob,
    student_user_id: str | None,
    class_id: str | None,
    period_start: datetime,
    period_end: datetime,
) -> bool:
    """同键换参判定：比较 report_jobs 持久化的目标与周期字段。"""
    return (
        job.student_user_id == student_user_id
        and job.class_id == class_id
        and job.period_start == period_start
        and job.period_end == period_end
    )


__all__ = [
    "QuarantinedEventNotFoundError",
    "QuarantinedListPage",
    "QuarantinedView",
    "ReportActor",
    "ReportForbiddenError",
    "ReportIdempotencyConflictError",
    "ReportJobNotFoundError",
    "ReportJobOutcome",
    "ReportListPage",
    "ReportNotFoundError",
    "ReportPgService",
    "ReportView",
    "JobView",
]
