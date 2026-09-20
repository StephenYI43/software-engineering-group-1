"""聚合状态的更新规则：去重、判分优先级与契约外数据的处理。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.analytics.events import EventValidationError


def test_repeated_submission_event_is_counted_once(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T08:05:00Z",
                payload={
                    "submissionId": "submission_mock_a01",
                    "questionType": "single_choice",
                    "isCorrect": False,
                },
            ),
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T09:20:00Z",
                payload={
                    "submissionId": "submission_mock_a01",
                    "questionType": "single_choice",
                    "isCorrect": False,
                },
            ),
        ]
    )

    assert list(state.submissions) == ["submission_mock_a01"]
    assert (
        state.submissions["submission_mock_a01"].occurred_at.hour == 8
    )  # 首次到达的时间决定周期归属


def test_later_judgement_wins(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T08:05:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": False},
            ),
            event_factory(
                event_type="assignment_graded",
                occurred_at="2026-09-16T09:00:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": True},
            ),
        ]
    )

    assert state.judgements["submission_mock_a01"].is_correct is True


def test_stale_judgement_does_not_overwrite_newer_one(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="assignment_graded",
                occurred_at="2026-09-16T09:00:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": True},
            ),
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T08:05:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": False},
            ),
        ]
    )

    assert state.judgements["submission_mock_a01"].is_correct is True


def test_graded_wins_over_submitted_at_the_same_instant(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T08:05:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": False},
            ),
            event_factory(
                event_type="assignment_graded",
                occurred_at="2026-09-16T08:05:00Z",
                payload={"submissionId": "submission_mock_a01", "isCorrect": True},
            ),
        ]
    )

    judgement = state.judgements["submission_mock_a01"]
    assert judgement.is_correct is True
    assert judgement.from_graded_event is True


def test_unjudged_submission_records_no_judgement(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="assignment_submitted",
                occurred_at="2026-09-16T08:12:00Z",
                payload={
                    "submissionId": "submission_mock_a03",
                    "questionType": "short_answer",
                    "isCorrect": None,
                },
            )
        ]
    )

    assert state.judgements == {}
    assert list(state.submissions) == ["submission_mock_a03"]


def test_duplicate_mistake_record_keeps_first_state(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="mistake_recorded",
                occurred_at="2026-09-16T08:30:00Z",
                payload={"mistakeId": "mistake_mock_m01", "chapterId": "chapter_mock_c02"},
            ),
            event_factory(
                event_type="mistake_recorded",
                occurred_at="2026-09-16T08:40:00Z",
                payload={"mistakeId": "mistake_mock_m01", "chapterId": "chapter_mock_c09"},
            ),
        ]
    )

    assert state.mistakes["mistake_mock_m01"].chapter_id == "chapter_mock_c02"


def test_mistake_resolved_marks_record(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="mistake_recorded",
                occurred_at="2026-09-16T08:30:00Z",
                payload={"mistakeId": "mistake_mock_m01", "chapterId": "chapter_mock_c02"},
            ),
            event_factory(
                event_type="mistake_resolved",
                occurred_at="2026-09-16T09:10:00Z",
                payload={"mistakeId": "mistake_mock_m01"},
            ),
        ]
    )

    assert state.mistakes["mistake_mock_m01"].resolved is True


def test_mistake_resolved_without_record_is_ignored(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="mistake_resolved",
                occurred_at="2026-09-16T09:10:00Z",
                payload={"mistakeId": "mistake_mock_unknown"},
            )
        ]
    )

    assert state.mistakes == {}  # 不凭空造出错题


def test_activity_records_every_event_type(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="reminder_triggered",
                occurred_at="2026-09-16T09:15:00Z",
                payload={"reminderId": "reminder_mock_r01", "type": "review"},
            ),
            event_factory(
                event_type="chapter_viewed",
                occurred_at="2026-09-16T09:16:00Z",
                payload={"chapterId": "chapter_mock_c01"},
            ),
        ]
    )

    assert len(state.activity["user_mock_s01"]) == 2
    assert state.submissions == {}
    assert state.judgements == {}


def test_processed_ledger_tracks_event_ids(event_factory, build_state) -> None:
    event = event_factory(
        event_type="study_plan_saved",
        occurred_at="2026-09-16T08:40:00Z",
        payload={"planId": "plan_mock_p01", "itemsCount": 2},
    )
    state = build_state([event])

    assert state.is_processed(event.event_id) is True


def test_payload_contract_violations_raise(event_factory, build_state) -> None:
    with pytest.raises(EventValidationError):
        build_state(
            [
                event_factory(
                    event_type="assignment_submitted",
                    occurred_at="2026-09-16T08:05:00Z",
                    payload={"questionType": "single_choice"},  # 缺 submissionId
                )
            ]
        )

    with pytest.raises(EventValidationError):
        build_state(
            [
                event_factory(
                    event_type="assignment_submitted",
                    occurred_at="2026-09-16T08:05:00Z",
                    payload={"submissionId": "submission_mock_a01", "isCorrect": 0},
                )
            ]
        )

    with pytest.raises(EventValidationError):
        build_state(
            [
                event_factory(
                    event_type="mistake_recorded",
                    occurred_at="2026-09-16T08:30:00Z",
                    payload={"chapterId": "chapter_mock_c02"},  # 缺 mistakeId
                )
            ]
        )


def test_clone_is_independent(event_factory, build_state) -> None:
    state = build_state(
        [
            event_factory(
                event_type="study_plan_saved",
                occurred_at="2026-09-16T08:40:00Z",
                payload={"planId": "plan_mock_p01", "itemsCount": 2},
            )
        ]
    )

    cloned = state.clone()
    cloned.activity["user_mock_s01"].append(datetime(2026, 9, 16, 10, 0, tzinfo=UTC))

    assert len(state.activity["user_mock_s01"]) == 1
