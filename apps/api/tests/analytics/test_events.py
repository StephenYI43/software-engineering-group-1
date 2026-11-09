"""学习事件模型：契约校验与规范化。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domains.analytics.events import (
    EventValidationError,
    LearningEvent,
    optional_bool,
    optional_str,
    required_str,
)


def raw_event(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "eventId": "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b",
        "eventType": "assignment_submitted",
        "userId": "user_mock_s01",
        "courseId": "course_mock_c01",
        "occurredAt": "2026-09-16T08:05:00Z",
        "traceId": "req_mock_0001",
        "schemaVersion": "1.0",
        "payload": {"submissionId": "submission_mock_a01"},
    }
    raw.update(overrides)
    return raw


def test_parses_valid_event_and_normalizes_time_to_utc() -> None:
    event = LearningEvent.from_raw(raw_event(occurredAt="2026-09-16T16:05:00+08:00"))

    assert event.occurred_at == datetime(2026, 9, 16, 8, 5, tzinfo=UTC)
    assert event.user_id == "user_mock_s01"
    assert event.payload["submissionId"] == "submission_mock_a01"


def test_accepts_null_course_id() -> None:
    assert LearningEvent.from_raw(raw_event(courseId=None)).course_id is None


def test_rejects_event_id_not_matching_frozen_format() -> None:
    with pytest.raises(EventValidationError):
        LearningEvent.from_raw(raw_event(eventId="event_3f8a2c"))  # 文档占位格式，实现不得照抄


def test_rejects_naive_occurred_at() -> None:
    with pytest.raises(EventValidationError):
        LearningEvent.from_raw(raw_event(occurredAt="2026-09-16T08:05:00"))


def test_rejects_unsupported_schema_version() -> None:
    with pytest.raises(EventValidationError):
        LearningEvent.from_raw(raw_event(schemaVersion="2.0"))


def test_rejects_missing_payload() -> None:
    raw = raw_event()
    del raw["payload"]

    with pytest.raises(EventValidationError):
        LearningEvent.from_raw(raw)


def test_ignores_unknown_fields_for_forward_compatibility() -> None:
    """契约允许新增字段而不破坏旧消费者（learning-events.md 不变量 5）。"""
    event = LearningEvent.from_raw(raw_event(deviceId="device_mock_01"))

    assert event.event_id == "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b"


def test_required_str_returns_value_and_rejects_bad_payload() -> None:
    event = LearningEvent.from_raw(raw_event())

    assert required_str(event.payload, "submissionId", event) == "submission_mock_a01"
    with pytest.raises(EventValidationError):
        required_str(event.payload, "absentKey", event)
    with pytest.raises(EventValidationError):
        required_str({"submissionId": 42}, "submissionId", event)
    with pytest.raises(EventValidationError):
        required_str({"submissionId": ""}, "submissionId", event)


def test_optional_str_handles_null_missing_and_bad_type() -> None:
    event = LearningEvent.from_raw(raw_event())

    assert optional_str({"chapterId": "chapter_mock_c02"}, "chapterId", event) == "chapter_mock_c02"
    assert optional_str({"chapterId": None}, "chapterId", event) is None
    assert optional_str({}, "chapterId", event) is None
    with pytest.raises(EventValidationError):
        optional_str({"chapterId": 7}, "chapterId", event)


def test_optional_bool_handles_null_missing_and_bad_type() -> None:
    event = LearningEvent.from_raw(raw_event())

    assert optional_bool({"isCorrect": True}, "isCorrect", event) is True
    assert optional_bool({"isCorrect": None}, "isCorrect", event) is None
    assert optional_bool({}, "isCorrect", event) is None
    with pytest.raises(EventValidationError):
        optional_bool({"isCorrect": 0}, "isCorrect", event)
