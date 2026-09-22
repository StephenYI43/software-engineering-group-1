"""消费位点：排序键与序列化。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.analytics.cursor import Cursor
from app.domains.analytics.events import EventValidationError, LearningEvent


def test_sorts_by_occurred_at_then_event_id() -> None:
    earlier = Cursor(occurred_at=datetime(2026, 9, 16, 8, 5, tzinfo=UTC), event_id="event_b")
    later_same_instant = Cursor(
        occurred_at=datetime(2026, 9, 16, 8, 5, tzinfo=UTC), event_id="event_c"
    )
    later = Cursor(occurred_at=datetime(2026, 9, 16, 8, 6, tzinfo=UTC), event_id="event_a")

    assert earlier < later_same_instant < later


def test_round_trips_through_json(synthetic_events: list[LearningEvent]) -> None:
    cursor = Cursor.of(synthetic_events[0])

    restored = Cursor.from_json(cursor.to_json())

    assert restored == cursor
    assert restored.updated_at is None
    assert cursor.to_json()["cursorName"] == "analytics_consumption"
    assert cursor.to_json()["updatedAt"] is None


def test_round_trips_updated_at_metadata(synthetic_events: list[LearningEvent]) -> None:
    saved_at = datetime(2026, 9, 17, 1, 5, tzinfo=UTC)
    base = Cursor.of(synthetic_events[0])
    persisted = Cursor(occurred_at=base.occurred_at, event_id=base.event_id, updated_at=saved_at)

    restored = Cursor.from_json(persisted.to_json())

    assert restored.updated_at == saved_at
    # 元数据不参与相等比较：与无 updated_at 的同位置游标相等
    assert restored == base


def test_tolerates_missing_or_broken_metadata() -> None:
    """cursorName/updatedAt 宽松处理：可缺省，updatedAt 非法时忽略。"""
    raw = {
        "lastOccurredAt": "2026-09-16T08:05:00+00:00",
        "lastEventId": "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b",
        "updatedAt": "not-a-time",
    }

    restored = Cursor.from_json(raw)

    assert restored.updated_at is None


def test_rejects_incomplete_cursor_state() -> None:
    with pytest.raises(EventValidationError):
        Cursor.from_json({"lastEventId": "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b"})


def test_rejects_malformed_last_event_id() -> None:
    with pytest.raises(EventValidationError):
        Cursor.from_json(
            {"lastOccurredAt": "2026-09-16T08:05:00+00:00", "lastEventId": "evt_bogus"}
        )


def test_rejects_unparsable_cursor_time() -> None:
    with pytest.raises(EventValidationError):
        Cursor.from_json(
            {
                "lastOccurredAt": "not-a-time",
                "lastEventId": "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b",
            }
        )


def test_rejects_naive_cursor_time() -> None:
    with pytest.raises(EventValidationError):
        Cursor.from_json(
            {
                "lastOccurredAt": "2026-09-16T08:05:00",
                "lastEventId": "event_5f1e2a3b4c5d4e6f8a7b6c5d4e3f2a1b",
            }
        )


def test_cursor_of_event_uses_event_identity() -> None:
    event = LearningEvent.from_raw(
        {
            "eventId": "event_0123456789ab4def8123456789abcdef",
            "eventType": "mistake_resolved",
            "userId": "user_mock_s01",
            "courseId": None,
            "occurredAt": "2026-09-16T09:10:00Z",
            "traceId": "req_mock_0008",
            "schemaVersion": "1.0",
            "payload": {"mistakeId": "mistake_mock_m01"},
        }
    )

    assert Cursor.of(event) == Cursor(
        occurred_at=datetime(2026, 9, 16, 9, 10, tzinfo=UTC),
        event_id="event_0123456789ab4def8123456789abcdef",
    )
