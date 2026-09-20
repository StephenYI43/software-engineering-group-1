"""消费编排与读侧组装。

`AnalyticsConsumer` 负责「读一批 → 跳过已处理 → 应用 → 原子提交」；
`AnalyticsService` 负责把聚合状态组装成契约响应。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domains.analytics import aggregation
from app.domains.analytics.cursor import Cursor
from app.domains.analytics.errors import ClassNotFoundError, StoreError, StoreUnavailableError
from app.domains.analytics.period import Period, PeriodQuery, resolve_period
from app.domains.analytics.ports import AnalyticsStore, ClassRoster, EventSource, StudentRef
from app.domains.analytics.schemas import (
    NO_EVENTS_IN_PERIOD,
    ChapterWeakPointResponse,
    ClassOverview,
    Coverage,
    KnownDuration,
    KnownNumber,
    PeriodResponse,
    QuestionTypeWeakPointResponse,
    StudentOverview,
    Summary,
    UnknownNumber,
    WeakPoints,
)
from app.domains.analytics.state import AnalyticsState

DEFAULT_BATCH_SIZE = 500


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
        for event in batch:
            if working.is_processed(event.event_id):
                skipped += 1
                continue
            working.apply(event)
            applied += 1

        latest = max((Cursor.of(event) for event in batch), default=None)
        if latest is not None and (working.cursor is None or latest > working.cursor):
            working.cursor = latest
        self._store.save(working)

        return PollResult(
            read_count=len(batch),
            applied_count=applied,
            skipped_count=skipped,
            cursor=working.cursor,
        )


class AnalyticsService:
    """读侧：把聚合状态与班级花名册组装成交付给 M2 的响应。"""

    def __init__(
        self,
        *,
        store: AnalyticsStore,
        roster: ClassRoster,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._roster = roster
        self._clock = clock

    def get_overview(self, *, class_id: str, query: PeriodQuery) -> ClassOverview:
        students = self._roster.list_students(class_id)
        if students is None:
            raise ClassNotFoundError

        now = self._clock()
        period = resolve_period(query, now)
        state = self._load_state()

        student_ids = frozenset(student.user_id for student in students)
        rows = [self._student_row(state, student, period) for student in students]
        students_with_data = sum(1 for row in rows if row.data_state == "known")

        return ClassOverview(
            class_id=class_id,
            period=self._period_response(period),
            data_through=state.cursor.occurred_at if state.cursor is not None else None,
            generated_at=now,
            summary=self._summary(state, period, rows, students_with_data),
            weak_points=self._weak_points(state, period, student_ids),
            students=rows,
        )

    def _load_state(self) -> AnalyticsState:
        try:
            return self._store.load()
        except StoreError as error:
            raise StoreUnavailableError() from error

    def _summary(
        self,
        state: AnalyticsState,
        period: Period,
        rows: Sequence[StudentOverview],
        students_with_data: int,
    ) -> Summary:
        coverage = Coverage(
            student_count=len(rows),
            students_with_data=students_with_data,
            students_without_data=len(rows) - students_with_data,
        )
        if state.cursor is None:
            # 尚未消费任何事件：全班都是未知，不能用 0 冒充（statistics-api.md）
            unknown = UnknownNumber(reason=NO_EVENTS_IN_PERIOD)
            return Summary(
                total_duration_seconds=unknown,
                active_student_count=unknown,
                submission_count=unknown,
                coverage=coverage,
            )

        total_duration = sum(
            row.duration_seconds.value
            for row in rows
            if isinstance(row.duration_seconds, KnownDuration)
        )
        total_submissions = sum(
            row.submission_count.value
            for row in rows
            if isinstance(row.submission_count, KnownNumber)
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
        self, state: AnalyticsState, period: Period, student_ids: frozenset[str]
    ) -> WeakPoints:
        return WeakPoints(
            by_question_type=[
                QuestionTypeWeakPointResponse(
                    key=item.key,
                    label=None,
                    error_rate=item.error_rate,
                    sample_size=item.sample_size,
                    insufficient_sample=item.insufficient_sample,
                )
                for item in aggregation.question_type_weak_points(state, period, student_ids)
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
                for item in aggregation.chapter_weak_points(state, period, student_ids)
            ],
        )

    def _student_row(
        self, state: AnalyticsState, student: StudentRef, period: Period
    ) -> StudentOverview:
        has_data = aggregation.has_activity_in_period(state, student.user_id, period)
        seconds = aggregation.duration_seconds(state, student.user_id, period)
        submissions = aggregation.submission_count(state, student.user_id, period)
        weakest = aggregation.weakest_chapter(state, student.user_id, period)

        return StudentOverview(
            user_id=student.user_id,
            display_name=student.display_name,
            data_state="known" if has_data else "unknown",
            duration_seconds=(
                KnownDuration(value=seconds, algorithm=aggregation.ALGORITHM_SESSION_INFERENCE)
                if seconds is not None
                else UnknownNumber(reason=NO_EVENTS_IN_PERIOD)
            ),
            submission_count=(
                KnownNumber(value=submissions)
                if submissions is not None
                else UnknownNumber(reason=NO_EVENTS_IN_PERIOD)
            ),
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
