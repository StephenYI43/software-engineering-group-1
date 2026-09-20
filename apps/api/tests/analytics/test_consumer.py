"""消费编排：游标推进、幂等重放与失败不推进。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pytest

from app.domains.analytics import aggregation
from app.domains.analytics.cursor import Cursor
from app.domains.analytics.errors import StoreError
from app.domains.analytics.events import EventValidationError, LearningEvent
from app.domains.analytics.memory import InMemoryAnalyticsStore, InMemoryEventSource, StaticRoster
from app.domains.analytics.ports import StudentRef
from app.domains.analytics.service import AnalyticsConsumer
from app.domains.analytics.state import AnalyticsState


class StaleSource:
    """故意返回早于游标的事件，用于验证游标只前进。"""

    def __init__(self, events: Sequence[LearningEvent]) -> None:
        self._events = list(events)

    def read_after(self, cursor: Cursor | None, limit: int) -> Sequence[LearningEvent]:
        return self._events[:limit]


class BrokenStore:
    """读写均失败，用于验证故障不被吞掉。"""

    def load(self) -> AnalyticsState:
        raise StoreError("database unavailable")

    def save(self, state: AnalyticsState) -> None:
        raise StoreError("database unavailable")


def make_consumer(
    events: Sequence[LearningEvent], batch_size: int = 500
) -> tuple[AnalyticsConsumer, InMemoryAnalyticsStore]:
    store = InMemoryAnalyticsStore()
    return AnalyticsConsumer(InMemoryEventSource(events), store, batch_size), store


def test_poll_applies_batch_and_advances_cursor(synthetic_events) -> None:
    consumer, store = make_consumer(synthetic_events)

    result = consumer.poll_once()

    assert (result.read_count, result.applied_count, result.skipped_count) == (11, 11, 0)
    assert result.cursor == Cursor.of(synthetic_events[-1])
    assert store.load().cursor == result.cursor


def test_second_poll_reads_nothing_new(synthetic_events) -> None:
    consumer, _ = make_consumer(synthetic_events)
    consumer.poll_once()

    result = consumer.poll_once()

    assert (result.read_count, result.applied_count, result.skipped_count) == (0, 0, 0)


def test_batch_size_limits_each_poll(synthetic_events) -> None:
    consumer, _ = make_consumer(synthetic_events, batch_size=1)

    results = [consumer.poll_once() for _ in range(3)]

    assert [result.read_count for result in results] == [1, 1, 1]
    assert results[0].cursor == Cursor.of(synthetic_events[0])


def test_replay_after_cursor_reset_does_not_double_count(synthetic_events, last_7_days) -> None:
    """游标回拨后重放：`eventId` 账本兜底，统计不变（消费契约走查第 4 步）。"""
    consumer, store = make_consumer(synthetic_events)
    consumer.poll_once()
    before = aggregation.submission_count(store.load(), "user_mock_s01", last_7_days)

    store.load().cursor = None  # 模拟游标回拨 / 回填重放
    result = consumer.poll_once()
    after = aggregation.submission_count(store.load(), "user_mock_s01", last_7_days)

    assert (result.applied_count, result.skipped_count) == (0, 11)
    assert before == after == 2


def test_failed_batch_does_not_advance_cursor(event_factory) -> None:
    """契约外数据必须让游标停在原地并显式报错，而不是被静默少算。"""
    good = event_factory(
        event_type="study_plan_saved",
        occurred_at="2026-09-16T08:40:00Z",
        payload={"planId": "plan_mock_p01", "itemsCount": 2},
    )
    bad = event_factory(
        event_type="assignment_submitted",
        occurred_at="2026-09-16T09:00:00Z",
        payload={"questionType": "single_choice"},  # 缺 submissionId
    )
    consumer, store = make_consumer([good, bad])

    with pytest.raises(EventValidationError):
        consumer.poll_once()

    assert store.load().cursor is None
    assert store.load().processed_event_ids == set()


def test_store_failure_propagates() -> None:
    consumer = AnalyticsConsumer(InMemoryEventSource([]), BrokenStore())

    with pytest.raises(StoreError):
        consumer.poll_once()


def test_cursor_never_moves_backwards(synthetic_events) -> None:
    store = InMemoryAnalyticsStore()
    consumer = AnalyticsConsumer(InMemoryEventSource(synthetic_events), store)
    consumer.poll_once()
    settled = store.load().cursor
    assert settled is not None

    consumer = AnalyticsConsumer(StaleSource(synthetic_events[:2]), store)
    result = consumer.poll_once()

    assert result.cursor == settled


def test_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError):
        AnalyticsConsumer(InMemoryEventSource([]), InMemoryAnalyticsStore(), batch_size=0)


def test_in_memory_source_returns_events_in_cursor_order(synthetic_events) -> None:
    source = InMemoryEventSource(list(reversed(synthetic_events)))

    first_page = source.read_after(None, 3)
    second_page = source.read_after(Cursor.of(first_page[-1]), 3)

    assert [event.event_id for event in first_page] == [
        event.event_id for event in synthetic_events[:3]
    ]
    assert [event.event_id for event in second_page] == [
        event.event_id for event in synthetic_events[3:6]
    ]


def test_in_memory_store_round_trips_state() -> None:
    store = InMemoryAnalyticsStore()
    state = AnalyticsState(
        cursor=Cursor(occurred_at=datetime(2026, 9, 16, 9, 20), event_id="event_a")
    )

    store.save(state)

    assert store.load() is state


def test_static_roster_hides_unauthorized_classes() -> None:
    roster = StaticRoster(
        {"class_mock_c01": [StudentRef(user_id="user_mock_s01", display_name="合成学生 01")]}
    )

    assert roster.list_students("class_mock_c01") is not None
    assert roster.list_students("class_mock_other") is None
