"""读侧聚合：会话推断时长、薄弱点、提交数去重。

期望值与 `packages/contracts/analytics/samples/01-class-overview-ok.json` 一致，
即「样例事件 → 页面数字可推导」的后端侧验证。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domains.analytics import aggregation
from app.domains.analytics.period import Period
from app.domains.analytics.state import AnalyticsState

SHANGHAI = ZoneInfo("Asia/Shanghai")
STUDENTS = frozenset({"user_mock_s01", "user_mock_s02", "user_mock_s03"})
COURSE = "course_mock_c01"


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 16, hour, minute, tzinfo=UTC)


def test_lone_event_counts_the_session_minimum() -> None:
    assert aggregation.session_seconds([at(8, 30)], SHANGHAI) == aggregation.SESSION_MIN_SECONDS


def test_gap_at_threshold_stays_in_one_session() -> None:
    times = [at(8, 0), at(8, 0) + aggregation.SESSION_GAP_THRESHOLD]

    assert aggregation.session_seconds(times, SHANGHAI) == 900


def test_gap_beyond_threshold_splits_sessions() -> None:
    times = [at(8, 0), at(8, 0) + aggregation.SESSION_GAP_THRESHOLD + timedelta(minutes=1)]

    assert aggregation.session_seconds(times, SHANGHAI) == 2 * aggregation.SESSION_MIN_SECONDS


def test_long_session_is_capped_at_the_maximum() -> None:
    """同一会话内连续事件（间隔均不超过阈值）跨 1 小时以上时触发上限。

    注意 `[08:00, 10:00]` 这类相邻事件间隔超过会话阈值，会被切成两个会话，
    不构成上限用例。
    """
    times = [at(8, 0) + timedelta(minutes=10 * step) for step in range(8)]  # 08:00 → 09:10

    assert aggregation.session_seconds(times, SHANGHAI) == aggregation.SESSION_MAX_SECONDS


def test_session_spanning_local_midnight_is_split_by_day() -> None:
    """Shanghai 日界：15:50Z 属于 23:50（16 日），16:10Z 属于 00:10（17 日）。"""
    times = [datetime(2026, 9, 16, 15, 50, tzinfo=UTC), datetime(2026, 9, 16, 16, 10, tzinfo=UTC)]

    assert aggregation.session_seconds(times, SHANGHAI) == 2 * aggregation.SESSION_MIN_SECONDS


def test_duration_matches_contract_sample(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    assert (
        aggregation.duration_seconds(aggregated_state, "user_mock_s01", last_7_days, course_id)
        == 1680
    )
    assert (
        aggregation.duration_seconds(aggregated_state, "user_mock_s02", last_7_days, course_id)
        == 1860
    )


def test_student_without_events_has_unknown_duration(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    assert (
        aggregation.has_activity_in_period(
            aggregated_state, "user_mock_s03", last_7_days, course_id
        )
        is False
    )
    assert (
        aggregation.duration_seconds(aggregated_state, "user_mock_s03", last_7_days, course_id)
        is None
    )


def test_events_outside_period_do_not_count(
    aggregated_state: AnalyticsState, request_time: datetime, course_id: str
) -> None:
    from app.domains.analytics.period import PeriodQuery, resolve_period

    past = resolve_period(
        PeriodQuery(period="custom", from_="2026-08-01T00:00:00Z", to="2026-08-02T00:00:00Z"),
        request_time,
    )

    assert aggregation.duration_seconds(aggregated_state, "user_mock_s01", past, course_id) is None


def test_submission_count_deduplicates_by_submission_id(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    """样例第 11 条与第 1 条 `submissionId` 相同，提交数不得变为 2 次以上。"""
    assert (
        aggregation.submission_count(aggregated_state, "user_mock_s01", last_7_days, course_id) == 2
    )
    assert (
        aggregation.submission_count(aggregated_state, "user_mock_s02", last_7_days, course_id) == 1
    )
    # 计数 known 0：无提交是已知的 0
    assert (
        aggregation.submission_count(aggregated_state, "user_mock_s03", last_7_days, course_id) == 0
    )


def test_course_filter_excludes_other_courses(
    event_factory, build_state, last_7_days: Period
) -> None:
    """同一用户在两个课程各有事件：course 过滤后互不可见。"""
    events = [
        event_factory(
            event_type="assignment_submitted",
            occurred_at="2026-09-16T08:00:00Z",
            payload={"submissionId": "submission_mock_c1", "questionType": "single_choice"},
        ),
        event_factory(
            event_type="study_plan_saved",
            occurred_at="2026-09-16T09:00:00Z",
            payload={"planId": "plan_mock_x"},
            course_id="course_mock_c02",
        ),
    ]
    state = build_state(events)

    assert aggregation.submission_count(state, "user_mock_s01", last_7_days, COURSE) == 1
    assert aggregation.submission_count(state, "user_mock_s01", last_7_days, "course_mock_c02") == 0
    assert aggregation.duration_seconds(state, "user_mock_s01", last_7_days, COURSE) == 60
    assert (
        aggregation.duration_seconds(state, "user_mock_s01", last_7_days, "course_mock_c02") == 60
    )


def test_question_type_weak_points_match_contract_sample(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    items = aggregation.question_type_weak_points(
        aggregated_state, last_7_days, STUDENTS, course_id
    )

    assert [(item.key, item.error_rate, item.sample_size) for item in items] == [
        ("single_choice", 0.5, 2),
        ("short_answer", 1.0, 1),
    ]
    assert all(item.insufficient_sample for item in items)  # 样本量均低于 MIN_SAMPLE_SIZE


def test_weak_points_put_insufficient_samples_last(
    event_factory, build_state, last_7_days: Period, course_id: str
) -> None:
    """样本量 1、错误率 100% 的章节不得因错误率霸榜（教师端原型已提出该风险）。"""
    events = [
        event_factory(
            event_type="assignment_graded",
            occurred_at="2026-09-16T08:00:00Z",
            payload={
                "submissionId": f"submission_mock_n{index}",
                "isCorrect": False,
                "questionType": "frequent",
            },
        )
        for index in range(aggregation.MIN_SAMPLE_SIZE)
    ]
    events.append(
        event_factory(
            event_type="assignment_graded",
            occurred_at="2026-09-16T08:30:00Z",
            payload={
                "submissionId": "submission_mock_lonely",
                "isCorrect": False,
                "questionType": "rare",
            },
        )
    )
    state = build_state(events)

    items = aggregation.question_type_weak_points(
        state, last_7_days, frozenset({"user_mock_s01"}), course_id
    )

    assert [item.key for item in items] == ["frequent", "rare"]
    assert items[0].insufficient_sample is False
    assert items[1].insufficient_sample is True


def test_question_type_weak_points_ignore_other_classes_and_users(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    items = aggregation.question_type_weak_points(
        aggregated_state, last_7_days, frozenset({"user_mock_s03"}), course_id
    )

    assert items == []


def test_unjudged_submission_is_excluded_from_error_rate(
    event_factory, build_state, last_7_days: Period, course_id: str
) -> None:
    """主观题未判分不代表答错，不能进分母。"""
    events = [
        event_factory(
            event_type="assignment_submitted",
            occurred_at="2026-09-16T08:00:00Z",
            payload={
                "submissionId": "submission_mock_pending",
                "questionType": "short_answer",
                "isCorrect": None,
            },
        )
    ]
    state = build_state(events)

    assert (
        aggregation.question_type_weak_points(
            state, last_7_days, frozenset({"user_mock_s01"}), course_id
        )
        == []
    )
    assert aggregation.submission_count(state, "user_mock_s01", last_7_days, course_id) == 1


def test_missing_question_type_is_grouped_under_unknown(
    event_factory, build_state, last_7_days: Period, course_id: str
) -> None:
    events = [
        event_factory(
            event_type="assignment_graded",
            occurred_at="2026-09-16T08:00:00Z",
            payload={"submissionId": "submission_mock_no_type", "isCorrect": False},
        )
    ]
    state = build_state(events)

    items = aggregation.question_type_weak_points(
        state, last_7_days, frozenset({"user_mock_s01"}), course_id
    )

    assert [item.key for item in items] == [aggregation.UNKNOWN_KEY]


def test_chapter_weak_points_match_contract_sample(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    items = aggregation.chapter_weak_points(aggregated_state, last_7_days, STUDENTS, course_id)

    assert len(items) == 1
    assert (items[0].key, items[0].mistake_count, items[0].resolved_count) == (
        "chapter_mock_c02",
        1,
        1,
    )


def test_weakest_chapter_is_none_without_mistakes(
    aggregated_state: AnalyticsState, last_7_days: Period, course_id: str
) -> None:
    assert (
        aggregation.weakest_chapter(aggregated_state, "user_mock_s01", last_7_days, course_id)
        is not None
    )
    assert (
        aggregation.weakest_chapter(aggregated_state, "user_mock_s02", last_7_days, course_id)
        is None
    )


def test_weakest_chapter_prefers_more_mistakes(
    event_factory, build_state, last_7_days: Period, course_id: str
) -> None:
    events = [
        event_factory(
            event_type="mistake_recorded",
            occurred_at=f"2026-09-16T08:0{index}:00Z",
            payload={"mistakeId": f"mistake_mock_b{index}", "chapterId": "chapter_mock_heavy"},
        )
        for index in range(2)
    ]
    events.append(
        event_factory(
            event_type="mistake_recorded",
            occurred_at="2026-09-16T08:30:00Z",
            payload={"mistakeId": "mistake_mock_light", "chapterId": "chapter_mock_light"},
        )
    )
    state = build_state(events)

    weakest = aggregation.weakest_chapter(state, "user_mock_s01", last_7_days, course_id)

    assert weakest is not None
    assert weakest.key == "chapter_mock_heavy"
