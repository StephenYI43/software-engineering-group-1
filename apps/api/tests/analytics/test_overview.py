"""读侧组装：响应内容与契约样例一致，未知状态不被 0 代替。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.analytics.errors import ClassNotFoundError, StoreError, StoreUnavailableError
from app.domains.analytics.period import PeriodQuery
from app.domains.analytics.schemas import KnownDuration, KnownNumber, UnknownNumber
from app.domains.analytics.service import AnalyticsService
from app.domains.analytics.state import AnalyticsState


class BrokenStore:
    def load(self) -> AnalyticsState:
        raise StoreError("database unavailable")

    def save(self, state: AnalyticsState) -> None:
        raise StoreError("database unavailable")


def make_service(store, roster, request_time: datetime) -> AnalyticsService:
    return AnalyticsService(store=store, roster=roster, clock=lambda: request_time)


def test_overview_matches_contract_sample(consumed_store, roster, request_time, class_id) -> None:
    overview = make_service(consumed_store, roster, request_time).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert overview.class_id == class_id
    assert overview.period.days == 7
    assert overview.period.timezone == "Asia/Shanghai"
    assert overview.data_through == datetime(2026, 9, 16, 9, 20, tzinfo=UTC)
    assert overview.generated_at == request_time

    assert overview.summary.total_duration_seconds == KnownDuration(
        value=3540, algorithm="session_inference_v1"
    )
    assert overview.summary.active_student_count == KnownNumber(value=2)
    assert overview.summary.submission_count == KnownNumber(value=3)
    assert overview.summary.coverage.student_count == 3
    assert overview.summary.coverage.students_with_data == 2
    assert overview.summary.coverage.students_without_data == 1

    rows = {row.user_id: row for row in overview.students}
    assert rows["user_mock_s01"].duration_seconds == KnownDuration(
        value=1680, algorithm="session_inference_v1"
    )
    assert rows["user_mock_s01"].submission_count == KnownNumber(value=2)
    assert rows["user_mock_s01"].weakest_chapter is not None
    assert rows["user_mock_s02"].duration_seconds == KnownDuration(
        value=1860, algorithm="session_inference_v1"
    )
    assert rows["user_mock_s02"].weakest_chapter is None  # 本周期无错题，不是未知
    assert rows["user_mock_s02"].data_state == "known"


def test_student_without_events_is_unknown_not_zero(
    consumed_store, roster, request_time, class_id
) -> None:
    overview = make_service(consumed_store, roster, request_time).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    row = next(row for row in overview.students if row.user_id == "user_mock_s03")

    assert row.data_state == "unknown"
    assert isinstance(row.duration_seconds, UnknownNumber)
    assert row.duration_seconds.reason == "no_events_in_period"
    assert isinstance(row.submission_count, UnknownNumber)
    assert row.weakest_chapter is None


def test_weak_points_are_grouped_by_dimension(
    consumed_store, roster, request_time, class_id
) -> None:
    overview = make_service(consumed_store, roster, request_time).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert [
        (item.key, item.error_rate, item.sample_size)
        for item in overview.weak_points.by_question_type
    ] == [("single_choice", 0.5, 2), ("short_answer", 1.0, 1)]
    assert [item.key for item in overview.weak_points.by_chapter] == ["chapter_mock_c02"]
    assert overview.weak_points.by_chapter[0].resolved_count == 1
    assert all(item.label is None for item in overview.weak_points.by_question_type)


def test_empty_store_reports_unknown_everywhere(
    empty_store, roster, request_time, class_id
) -> None:
    overview = make_service(empty_store, roster, request_time).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert overview.data_through is None
    assert isinstance(overview.summary.total_duration_seconds, UnknownNumber)
    assert isinstance(overview.summary.active_student_count, UnknownNumber)
    assert isinstance(overview.summary.submission_count, UnknownNumber)
    assert overview.summary.coverage.student_count == 3
    assert overview.summary.coverage.students_with_data == 0
    assert overview.summary.coverage.students_without_data == 3
    assert overview.weak_points.by_question_type == []
    assert overview.weak_points.by_chapter == []


def test_unknown_class_is_rejected(consumed_store, roster, request_time) -> None:
    service = make_service(consumed_store, roster, request_time)

    with pytest.raises(ClassNotFoundError):
        service.get_overview(class_id="class_mock_other", query=PeriodQuery())


def test_store_failure_becomes_service_unavailable(roster, request_time, class_id) -> None:
    service = make_service(BrokenStore(), roster, request_time)

    with pytest.raises(StoreUnavailableError) as error:
        service.get_overview(class_id=class_id, query=PeriodQuery())

    assert error.value.status_code == 503
    assert error.value.code == "ANALYTICS_SOURCE_UNAVAILABLE"


def test_custom_period_is_honoured(consumed_store, roster, request_time, class_id) -> None:
    query = PeriodQuery(period="custom", from_="2026-09-16T00:00:00Z", to="2026-09-17T00:00:00Z")

    overview = make_service(consumed_store, roster, request_time).get_overview(
        class_id=class_id, query=query
    )

    assert overview.period.days == 2
    assert overview.summary.submission_count == KnownNumber(value=3)


def test_period_excluding_all_events_reports_zero_for_consumed_data(
    consumed_store, roster, request_time, class_id
) -> None:
    """已消费事件但周期内无事件：这是已知的 0，而不是未知。"""
    query = PeriodQuery(period="custom", from_="2026-08-01T00:00:00Z", to="2026-08-02T00:00:00Z")

    overview = make_service(consumed_store, roster, request_time).get_overview(
        class_id=class_id, query=query
    )

    assert overview.summary.active_student_count == KnownNumber(value=0)
    assert overview.summary.submission_count == KnownNumber(value=0)
    assert overview.summary.coverage.students_without_data == 3
    assert isinstance(overview.summary.total_duration_seconds, KnownDuration)
    assert overview.summary.total_duration_seconds.value == 0
