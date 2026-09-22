"""读侧组装：响应内容与契约样例一致，未知状态不被 0 代替。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.analytics.errors import ClassNotFoundError, StoreError, StoreUnavailableError
from app.domains.analytics.memory import (
    InMemoryAnalyticsStore,
    InMemoryEventSource,
    StaticCourseMap,
    StaticRoster,
)
from app.domains.analytics.period import PeriodQuery
from app.domains.analytics.ports import StudentRef
from app.domains.analytics.schemas import KnownDuration, KnownNumber, UnknownNumber
from app.domains.analytics.service import AnalyticsConsumer, AnalyticsService
from app.domains.analytics.state import AnalyticsState


class BrokenStore:
    def load(self) -> AnalyticsState:
        raise StoreError("database unavailable")

    def save(self, state: AnalyticsState) -> None:
        raise StoreError("database unavailable")


class BrokenUpstream:
    """watermark 读取失败的上游，用于验证 consumption 降级为 unknown。"""

    def read_after(self, cursor: object, limit: int) -> list[object]:
        return []

    def watermark(self) -> object:
        raise StoreError("database unavailable")


def make_service(store, roster, request_time: datetime, course_map) -> AnalyticsService:
    return AnalyticsService(
        store=store, roster=roster, course_map=course_map, clock=lambda: request_time
    )


def test_overview_matches_contract_sample(
    consumed_store, roster, request_time, class_id, course_map, course_id
) -> None:
    overview = make_service(consumed_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert overview.class_id == class_id
    assert overview.course_id == course_id
    assert overview.period.days == 7
    assert overview.period.timezone == "Asia/Shanghai"
    assert overview.data_through == datetime(2026, 9, 16, 9, 20, tzinfo=UTC)
    assert overview.generated_at == request_time
    # service 未接 upstream：consumption 如实报告 unknown
    assert overview.consumption.data_state == "unknown"
    assert overview.consumption.upstream_watermark is None

    assert overview.summary.total_duration_seconds == KnownDuration(
        value=3540, algorithm="session_inference_v1"
    )
    assert overview.summary.active_student_count == KnownNumber(value=2)
    assert overview.summary.submission_count == KnownNumber(value=3)
    assert overview.summary.coverage.student_count == 3
    assert overview.summary.coverage.students_with_data == 2
    assert overview.summary.coverage.students_without_data == 1

    assert overview.students.total == 3
    assert overview.students.page == 1
    assert overview.students.page_size == 50
    rows = {row.user_id: row for row in overview.students.items}
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


def test_student_without_events_reports_unknown_duration_and_known_zero_submissions(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    overview = make_service(consumed_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    row = next(row for row in overview.students.items if row.user_id == "user_mock_s03")

    assert row.data_state == "unknown"
    assert isinstance(row.duration_seconds, UnknownNumber)
    assert row.duration_seconds.reason == "no_events_in_period"
    # 计数 known 0：无提交是已知的 0，不是 unknown
    assert row.submission_count == KnownNumber(value=0)
    assert row.weakest_chapter is None


def test_weak_points_are_grouped_by_dimension(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    overview = make_service(consumed_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert [
        (item.key, item.error_rate, item.sample_size)
        for item in overview.weak_points.by_question_type
    ] == [("single_choice", 0.5, 2), ("short_answer", 1.0, 1)]
    assert [item.key for item in overview.weak_points.by_chapter] == ["chapter_mock_c02"]
    assert overview.weak_points.by_chapter[0].resolved_count == 1
    assert all(item.label is None for item in overview.weak_points.by_question_type)


def test_empty_store_reports_known_zero_counts(
    empty_store, roster, request_time, class_id, course_map
) -> None:
    overview = make_service(empty_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=PeriodQuery()
    )

    assert overview.data_through is None
    assert isinstance(overview.summary.total_duration_seconds, UnknownNumber)
    assert overview.summary.total_duration_seconds.reason == "no_events_in_period"
    # 计数 known 0：没有任何事件也是已知数字
    assert overview.summary.active_student_count == KnownNumber(value=0)
    assert overview.summary.submission_count == KnownNumber(value=0)
    assert overview.summary.coverage.student_count == 3
    assert overview.summary.coverage.students_with_data == 0
    assert overview.summary.coverage.students_without_data == 3
    assert overview.weak_points.by_question_type == []
    assert overview.weak_points.by_chapter == []


def test_unknown_class_is_rejected(consumed_store, roster, request_time, course_map) -> None:
    service = make_service(consumed_store, roster, request_time, course_map)

    with pytest.raises(ClassNotFoundError):
        service.get_overview(class_id="class_mock_other", query=PeriodQuery())


def test_store_failure_becomes_service_unavailable(
    roster, request_time, class_id, course_map
) -> None:
    service = make_service(BrokenStore(), roster, request_time, course_map)

    with pytest.raises(StoreUnavailableError) as error:
        service.get_overview(class_id=class_id, query=PeriodQuery())

    assert error.value.status_code == 503
    assert error.value.code == "ANALYTICS_SOURCE_UNAVAILABLE"


def test_custom_period_is_honoured(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    query = PeriodQuery(period="custom", from_="2026-09-16T00:00:00Z", to="2026-09-17T00:00:00Z")

    overview = make_service(consumed_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=query
    )

    assert overview.period.days == 2
    assert overview.summary.submission_count == KnownNumber(value=3)


def test_period_excluding_all_events_reports_zero_for_consumed_data(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    """已消费事件但周期内无事件：计数是已知的 0，时长才是 unknown。"""
    query = PeriodQuery(period="custom", from_="2026-08-01T00:00:00Z", to="2026-08-02T00:00:00Z")

    overview = make_service(consumed_store, roster, request_time, course_map).get_overview(
        class_id=class_id, query=query
    )

    assert overview.summary.active_student_count == KnownNumber(value=0)
    assert overview.summary.submission_count == KnownNumber(value=0)
    assert overview.summary.coverage.students_without_data == 3
    assert isinstance(overview.summary.total_duration_seconds, UnknownNumber)
    assert overview.summary.total_duration_seconds.reason == "no_events_in_period"


def test_consumption_complete_when_cursor_catches_upstream(
    consumed_store, roster, request_time, class_id, course_map, synthetic_events
) -> None:
    service = AnalyticsService(
        store=consumed_store,
        roster=roster,
        course_map=course_map,
        upstream=InMemoryEventSource(synthetic_events),
        clock=lambda: request_time,
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery())

    assert overview.consumption.data_state == "complete"
    assert overview.consumption.upstream_watermark == datetime(2026, 9, 16, 9, 20, tzinfo=UTC)


def test_consumption_partial_when_cursor_lags_upstream(
    synthetic_events, roster, request_time, class_id, course_map
) -> None:
    """只消费了一部分（store 游标落后于上游水位）：partial。"""
    store = InMemoryAnalyticsStore()
    AnalyticsConsumer(InMemoryEventSource(synthetic_events), store, batch_size=3).poll_once()

    service = AnalyticsService(
        store=store,
        roster=roster,
        course_map=course_map,
        upstream=InMemoryEventSource(synthetic_events),
        clock=lambda: request_time,
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery())

    assert overview.consumption.data_state == "partial"
    assert overview.consumption.upstream_watermark == datetime(2026, 9, 16, 9, 20, tzinfo=UTC)


def test_consumption_complete_when_upstream_is_empty(
    empty_store, roster, request_time, class_id, course_map
) -> None:
    """上游无事件：视为已到消费尽头。"""
    service = AnalyticsService(
        store=empty_store,
        roster=roster,
        course_map=course_map,
        upstream=InMemoryEventSource([]),
        clock=lambda: request_time,
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery())

    assert overview.consumption.data_state == "complete"
    assert overview.consumption.upstream_watermark is None


def test_consumption_unknown_when_upstream_fails(
    empty_store, roster, request_time, class_id, course_map
) -> None:
    service = AnalyticsService(
        store=empty_store,
        roster=roster,
        course_map=course_map,
        upstream=BrokenUpstream(),
        clock=lambda: request_time,
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery())

    assert overview.consumption.data_state == "unknown"
    assert overview.consumption.upstream_watermark is None


def test_same_student_events_do_not_leak_across_classes(event_factory, request_time) -> None:
    """同一学生在两个班级：各班只统计本课程事件，提交数与时长互不串。"""
    roster = StaticRoster(
        {
            "class_mock_c01": [StudentRef(user_id="user_mock_s01", display_name="学生 01")],
            "class_mock_c02": [StudentRef(user_id="user_mock_s01", display_name="学生 01")],
        }
    )
    course_map = StaticCourseMap(
        {"class_mock_c01": "course_mock_c01", "class_mock_c02": "course_mock_c02"}
    )
    events = [
        # c01：一次提交（单事件会话，时长 60s）
        event_factory(
            event_type="assignment_submitted",
            occurred_at="2026-09-16T08:00:00Z",
            payload={"submissionId": "submission_mock_c1", "questionType": "single_choice"},
        ),
        # c02：两次活跃事件（同一会话 300s），无提交
        event_factory(
            event_type="study_plan_saved",
            occurred_at="2026-09-16T08:05:00Z",
            payload={"planId": "plan_mock_x"},
            course_id="course_mock_c02",
        ),
        event_factory(
            event_type="study_plan_saved",
            occurred_at="2026-09-16T08:10:00Z",
            payload={"planId": "plan_mock_y"},
            course_id="course_mock_c02",
        ),
    ]
    store = InMemoryAnalyticsStore()
    AnalyticsConsumer(InMemoryEventSource(events), store).poll_once()

    service = AnalyticsService(
        store=store, roster=roster, course_map=course_map, clock=lambda: request_time
    )

    c01 = service.get_overview(class_id="class_mock_c01", query=PeriodQuery())
    c02 = service.get_overview(class_id="class_mock_c02", query=PeriodQuery())

    assert c01.course_id == "course_mock_c01"
    assert c01.summary.submission_count == KnownNumber(value=1)
    row01 = c01.students.items[0]
    assert row01.submission_count == KnownNumber(value=1)
    assert row01.duration_seconds == KnownDuration(value=60, algorithm="session_inference_v1")

    assert c02.course_id == "course_mock_c02"
    assert c02.summary.submission_count == KnownNumber(value=0)
    row02 = c02.students.items[0]
    assert row02.submission_count == KnownNumber(value=0)
    assert row02.duration_seconds == KnownDuration(value=300, algorithm="session_inference_v1")
    assert row02.data_state == "known"


def test_events_without_course_id_belong_to_no_class(event_factory, request_time) -> None:
    """courseId 为 None 的事件不归属任何班级，两个班都统计不到。"""
    roster = StaticRoster(
        {
            "class_mock_c01": [StudentRef(user_id="user_mock_s01", display_name="学生 01")],
            "class_mock_c02": [StudentRef(user_id="user_mock_s01", display_name="学生 01")],
        }
    )
    course_map = StaticCourseMap(
        {"class_mock_c01": "course_mock_c01", "class_mock_c02": "course_mock_c02"}
    )
    events = [
        event_factory(
            event_type="study_plan_saved",
            occurred_at="2026-09-16T08:00:00Z",
            payload={"planId": "plan_mock_z"},
            course_id=None,
        )
    ]
    store = InMemoryAnalyticsStore()
    AnalyticsConsumer(InMemoryEventSource(events), store).poll_once()

    service = AnalyticsService(
        store=store, roster=roster, course_map=course_map, clock=lambda: request_time
    )

    for class_id in ("class_mock_c01", "class_mock_c02"):
        overview = service.get_overview(class_id=class_id, query=PeriodQuery())
        assert overview.summary.active_student_count == KnownNumber(value=0)
        assert overview.summary.submission_count == KnownNumber(value=0)
        assert isinstance(overview.summary.total_duration_seconds, UnknownNumber)
        assert overview.students.items[0].data_state == "unknown"


def test_missing_course_mapping_reports_null_course_id(
    empty_store, roster, request_time, class_id
) -> None:
    """course_id_for 返回 None：响应 course_id=null、计数 0、时长 unknown。"""
    service = AnalyticsService(
        store=empty_store,
        roster=roster,
        course_map=StaticCourseMap({}),
        clock=lambda: request_time,
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery())

    assert overview.course_id is None
    assert overview.summary.active_student_count == KnownNumber(value=0)
    assert overview.summary.submission_count == KnownNumber(value=0)
    assert isinstance(overview.summary.total_duration_seconds, UnknownNumber)
    assert overview.summary.total_duration_seconds.reason == "duration_source_unavailable"
    assert overview.summary.coverage.student_count == 3
    assert overview.weak_points.by_question_type == []
    assert overview.weak_points.by_chapter == []
    assert overview.students.items[0].submission_count == KnownNumber(value=0)
    assert overview.students.items[0].duration_seconds == UnknownNumber(
        reason="duration_source_unavailable"
    )


def test_students_pagination_slices_rows(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    service = make_service(consumed_store, roster, request_time, course_map)

    first = service.get_overview(class_id=class_id, query=PeriodQuery(), page=1, page_size=2)
    assert first.students.page == 1
    assert first.students.page_size == 2
    assert first.students.total == 3
    assert [row.user_id for row in first.students.items] == ["user_mock_s01", "user_mock_s02"]

    # 默认 pageSize=50 时第 2 页已超出总行数：items 为空但 total 不变
    beyond = service.get_overview(class_id=class_id, query=PeriodQuery(), page=2)
    assert beyond.students.page == 2
    assert beyond.students.page_size == 50
    assert beyond.students.total == 3
    assert beyond.students.items == []
