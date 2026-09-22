"""消费编排与读侧组装。

`AnalyticsConsumer` 负责「读一批 → 跳过已处理 → 应用 → 原子提交」；
`AnalyticsService` 负责把聚合状态组装成契约响应。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domains.analytics import aggregation
from app.domains.analytics.cursor import Cursor
from app.domains.analytics.errors import ClassNotFoundError, StoreError, StoreUnavailableError
from app.domains.analytics.events import EventValidationError
from app.domains.analytics.period import Period, PeriodQuery, resolve_period
from app.domains.analytics.ports import (
    AnalyticsStore,
    ClassCourseMapper,
    ClassRoster,
    EventSource,
    StudentRef,
)
from app.domains.analytics.schemas import (
    DURATION_SOURCE_UNAVAILABLE,
    NO_EVENTS_IN_PERIOD,
    ChapterWeakPointResponse,
    ClassOverview,
    Consumption,
    Coverage,
    KnownDuration,
    KnownNumber,
    PeriodResponse,
    QuestionTypeWeakPointResponse,
    StudentOverview,
    StudentPage,
    Summary,
    UnknownNumber,
    WeakPoints,
)
from app.domains.analytics.state import AnalyticsState

DEFAULT_BATCH_SIZE = 500
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 50

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollResult:
    """一轮消费的结果，供日志与走查使用。"""

    read_count: int
    applied_count: int
    skipped_count: int
    cursor: Cursor | None


class AnalyticsConsumer:
    """学习事件消费方（M6 是 `learning_events` 的唯一消费者）。

    一致性规则：整批事件全部应用成功后才提交游标；任何异常都不提交，
    下一轮从头重读本批，重复部分由 `eventId` 账本兜底
    （`packages/contracts/analytics/event-consumption.md`「推进规则」）。

    已知边界：某条事件持续非法（如 payload 违约）会让游标停在该批不动。
    S1 不引入隔离区，需人工核对上游数据后再放行——这属于契约违约的显式暴露，
    而不是被静默少算。
    """

    def __init__(
        self,
        source: EventSource,
        store: AnalyticsStore,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size 必须为正整数")
        self._source = source
        self._store = store
        self._batch_size = batch_size

    def poll_once(self) -> PollResult:
        current = self._store.load()
        batch = self._source.read_after(current.cursor, self._batch_size)
        working = current.clone()

        applied = 0
        skipped = 0
        previous: Cursor | None = None
        for event in batch:
            position = Cursor.of(event)
            # 批次必须按 (occurredAt, eventId) 升序（消费契约硬要求）。
            # 真实 DB 的 ORDER BY 写错会让游标越过未读事件、静默漏算，
            # 这里 fail fast，而不是带病消费。
            if previous is not None and position <= previous:
                raise EventValidationError(
                    f"事件批次未按 (occurredAt, eventId) 升序返回：{event.event_id} 不晚于前一条"
                )
            previous = position

            if working.is_processed(event.event_id):
                skipped += 1
                continue
            working.apply(event)
            applied += 1

        missing_course = sum(1 for event in batch if event.course_id is None)
        if missing_course:
            # 只输出数量，不输出 payload 或用户标识。
            logger.warning("analytics poll: %d 条事件缺 courseId，无法归属任何班级", missing_course)

        latest = max((Cursor.of(event) for event in batch), default=None)
        if latest is not None and (working.cursor is None or latest > working.cursor):
            working.cursor = latest
        self._store.save(working)

        # 游标只输出 occurred_at，避免在日志中泄露用户或事件标识。
        logger.info(
            "analytics poll: read=%d applied=%d skipped=%d cursor=%s",
            len(batch),
            applied,
            skipped,
            working.cursor.occurred_at.isoformat() if working.cursor is not None else None,
        )

        return PollResult(
            read_count=len(batch),
            applied_count=applied,
            skipped_count=skipped,
            cursor=working.cursor,
        )


class AnalyticsService:
    """读侧：把聚合状态与班级花名册组装成交付给 M2 的响应。

    `course_map` 把班级映射到课程（聚合按课程过滤，防止同一学生跨班时串数据）；
    `upstream` 用于计算 consumption 水位，未接入时如实报告 unknown。
    """

    def __init__(
        self,
        *,
        store: AnalyticsStore,
        roster: ClassRoster,
        course_map: ClassCourseMapper,
        upstream: EventSource | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._roster = roster
        self._course_map = course_map
        self._upstream = upstream
        self._clock = clock

    def get_overview(
        self,
        *,
        class_id: str,
        query: PeriodQuery,
        page: int = DEFAULT_PAGE,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> ClassOverview:
        students = self._roster.list_students(class_id)
        if students is None:
            raise ClassNotFoundError

        course_id = self._course_map.course_id_for(class_id)
        now = self._clock()
        period = resolve_period(query, now)
        state = self._load_state()

        student_ids = frozenset(student.user_id for student in students)
        rows = [self._student_row(state, student, period, course_id) for student in students]
        students_with_data = sum(1 for row in rows if row.data_state == "known")
        total = len(rows)
        start = (page - 1) * page_size

        return ClassOverview(
            class_id=class_id,
            course_id=course_id,
            period=self._period_response(period),
            data_through=state.cursor.occurred_at if state.cursor is not None else None,
            generated_at=now,
            consumption=self._consumption(state, period),
            summary=self._summary(rows, students_with_data, course_id),
            weak_points=self._weak_points(state, period, student_ids, course_id),
            students=StudentPage(
                page=page,
                page_size=page_size,
                total=total,
                items=rows[start : start + page_size],
            ),
        )

    def _load_state(self) -> AnalyticsState:
        try:
            return self._store.load()
        except StoreError as error:
            raise StoreUnavailableError() from error

    def _consumption(self, state: AnalyticsState, period: Period) -> Consumption:
        """计算消费水位：游标追平「周期终点与上游水位中较小者」即视为 complete。"""
        if self._upstream is None:
            # 未接入上游事件源：无法判断消费进度，如实报告 unknown。
            return Consumption(data_state="unknown", upstream_watermark=None)
        try:
            watermark = self._upstream.watermark()
        except Exception:
            # 水位暂不可得不代表数据有错，按 unknown 报告而不是把查询打挂。
            logger.warning("analytics consumption: 读取上游水位失败，按 unknown 报告")
            return Consumption(data_state="unknown", upstream_watermark=None)
        if watermark is None:
            # 上游无事件：本域游标无论在哪，都已经处在消费尽头。
            return Consumption(data_state="complete", upstream_watermark=None)
        bound = min(period.end, watermark.occurred_at)
        if state.cursor is not None and state.cursor.occurred_at >= bound:
            return Consumption(data_state="complete", upstream_watermark=watermark.occurred_at)
        return Consumption(data_state="partial", upstream_watermark=watermark.occurred_at)

    def _summary(
        self,
        rows: Sequence[StudentOverview],
        students_with_data: int,
        course_id: str | None,
    ) -> Summary:
        coverage = Coverage(
            student_count=len(rows),
            students_with_data=students_with_data,
            students_without_data=len(rows) - students_with_data,
        )
        # 计数永远是已知数字（statistics-api.md 契约修订「计数 known 0」）：
        # 没有任何可归属事件时是已知的 0，不用 unknown 冒充。
        total_submissions = sum(
            row.submission_count.value
            for row in rows
            if isinstance(row.submission_count, KnownNumber)
        )
        if students_with_data == 0:
            # 时长无法从无事件中推导：周期内没有任何有数据的学生才是 unknown。
            # 班级没有可归属课程时是时长来源不可用，而不是周期内无事件。
            reason = DURATION_SOURCE_UNAVAILABLE if course_id is None else NO_EVENTS_IN_PERIOD
            return Summary(
                total_duration_seconds=UnknownNumber(reason=reason),
                active_student_count=KnownNumber(value=students_with_data),
                submission_count=KnownNumber(value=total_submissions),
                coverage=coverage,
            )

        total_duration = sum(
            row.duration_seconds.value
            for row in rows
            if isinstance(row.duration_seconds, KnownDuration)
        )
        return Summary(
            total_duration_seconds=KnownDuration(
                value=total_duration, algorithm=aggregation.ALGORITHM_SESSION_INFERENCE
            ),
            active_student_count=KnownNumber(value=students_with_data),
            submission_count=KnownNumber(value=total_submissions),
            coverage=coverage,
        )

    def _weak_points(
        self,
        state: AnalyticsState,
        period: Period,
        student_ids: frozenset[str],
        course_id: str | None,
    ) -> WeakPoints:
        if course_id is None:
            # 班级没有可归属课程：无事件可统计，薄弱点列表为空。
            return WeakPoints(by_question_type=[], by_chapter=[])
        return WeakPoints(
            by_question_type=[
                QuestionTypeWeakPointResponse(
                    key=item.key,
                    label=None,
                    error_rate=item.error_rate,
                    sample_size=item.sample_size,
                    insufficient_sample=item.insufficient_sample,
                )
                for item in aggregation.question_type_weak_points(
                    state, period, student_ids, course_id
                )
            ],
            by_chapter=[
                ChapterWeakPointResponse(
                    key=item.key,
                    label=None,
                    mistake_count=item.mistake_count,
                    resolved_count=item.resolved_count,
                    sample_size=item.sample_size,
                    insufficient_sample=item.insufficient_sample,
                )
                for item in aggregation.chapter_weak_points(state, period, student_ids, course_id)
            ],
        )

    def _student_row(
        self,
        state: AnalyticsState,
        student: StudentRef,
        period: Period,
        course_id: str | None,
    ) -> StudentOverview:
        if course_id is None:
            # 班级映射缺失：无任何可归属事件——计数为已知 0、时长来源不可用，
            # coverage 仍由花名册保证真实。
            return StudentOverview(
                user_id=student.user_id,
                display_name=student.display_name,
                data_state="unknown",
                duration_seconds=UnknownNumber(reason=DURATION_SOURCE_UNAVAILABLE),
                submission_count=KnownNumber(value=0),
                weakest_chapter=None,
            )

        has_data = aggregation.has_activity_in_period(state, student.user_id, period, course_id)
        seconds = aggregation.duration_seconds(state, student.user_id, period, course_id)
        submissions = aggregation.submission_count(state, student.user_id, period, course_id)
        weakest = aggregation.weakest_chapter(state, student.user_id, period, course_id)

        return StudentOverview(
            user_id=student.user_id,
            display_name=student.display_name,
            data_state="known" if has_data else "unknown",
            duration_seconds=(
                KnownDuration(value=seconds, algorithm=aggregation.ALGORITHM_SESSION_INFERENCE)
                if seconds is not None
                else UnknownNumber(reason=NO_EVENTS_IN_PERIOD)
            ),
            # 提交数永远是已知数字：无提交就是 0（statistics-api.md「计数 known 0」）。
            submission_count=KnownNumber(value=submissions),
            weakest_chapter=(
                ChapterWeakPointResponse(
                    key=weakest.key,
                    label=None,
                    mistake_count=weakest.mistake_count,
                    resolved_count=weakest.resolved_count,
                    sample_size=weakest.sample_size,
                    insufficient_sample=weakest.insufficient_sample,
                )
                if weakest is not None
                else None
            ),
        )

    def _period_response(self, period: Period) -> PeriodResponse:
        return PeriodResponse(
            period_from=period.start,
            to=period.end,
            timezone=period.timezone.key,
            days=period.days,
        )
