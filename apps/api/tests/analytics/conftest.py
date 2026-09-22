"""analytics 测试的公共夹具。

固定事件集与 M6 教师端 S0 交付物
`docs/prototypes/samples/learning-events-synthetic.jsonl` 同源（11 条合成事件），
此处复制一份是为了让后端测试不依赖 docs 目录（该文件已合并进 main；
后端测试保留一份独立副本，避免跨目录依赖）。
两处若出现差异，以本文件为准并同步更新 S0 样例。
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.domains.analytics.events import LearningEvent
from app.domains.analytics.memory import (
    InMemoryAnalyticsStore,
    InMemoryEventSource,
    StaticCourseMap,
    StaticRoster,
)
from app.domains.analytics.period import Period, PeriodQuery, resolve_period
from app.domains.analytics.ports import StudentRef
from app.domains.analytics.service import AnalyticsConsumer
from app.domains.analytics.state import AnalyticsState

FIXTURES = Path(__file__).parent / "fixtures"

REQUEST_TIME = datetime(2026, 9, 17, 1, 0, tzinfo=UTC)
"""查询时刻，取 `2026-09-17T09:00+08:00`，与契约样例 `generatedAt` 一致。"""


def load_events(name: str = "learning-events-synthetic.jsonl") -> list[LearningEvent]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [LearningEvent.from_raw(json.loads(line)) for line in lines if line.strip()]


@pytest.fixture
def request_time() -> datetime:
    """查询时刻，取 `2026-09-17T09:00+08:00`，与契约样例 `generatedAt` 一致。"""
    return REQUEST_TIME


@pytest.fixture
def synthetic_events() -> list[LearningEvent]:
    return load_events()


@pytest.fixture
def aggregated_state(synthetic_events: list[LearningEvent]) -> Iterator[AnalyticsState]:
    state = AnalyticsState()
    for event in synthetic_events:
        state.apply(event)
    yield state


@pytest.fixture
def last_7_days(request_time: datetime) -> Period:
    return resolve_period(PeriodQuery(period="last7d"), request_time)


@pytest.fixture
def event_factory() -> Callable[..., LearningEvent]:
    """构造合法事件，`eventId` 顺序确定，便于断言去重与排序行为。"""
    counter = itertools.count(1)

    def make(
        *,
        event_type: str,
        occurred_at: str,
        payload: dict[str, Any],
        user_id: str = "user_mock_s01",
        course_id: str | None = "course_mock_c01",
    ) -> LearningEvent:
        return LearningEvent.from_raw(
            {
                "eventId": f"event_{next(counter):032x}",
                "eventType": event_type,
                "userId": user_id,
                "courseId": course_id,
                "occurredAt": occurred_at,
                "traceId": "req_mock_test",
                "schemaVersion": "1.0",
                "payload": payload,
            }
        )

    return make


@pytest.fixture
def build_state() -> Callable[[Sequence[LearningEvent]], AnalyticsState]:
    def build(events: Sequence[LearningEvent]) -> AnalyticsState:
        state = AnalyticsState()
        for event in events:
            state.apply(event)
        return state

    return build


CLASS_ID = "class_mock_c01"
COURSE_ID = "course_mock_c01"


@pytest.fixture
def class_id() -> str:
    return CLASS_ID


@pytest.fixture
def course_id() -> str:
    return COURSE_ID


@pytest.fixture
def course_map() -> StaticCourseMap:
    """class_mock_c01 → course_mock_c01；其他班级映射缺失。"""
    return StaticCourseMap({CLASS_ID: COURSE_ID})


@pytest.fixture
def roster() -> StaticRoster:
    """合成班级花名册：s03 全程无事件，用于验证「未知不是 0」。"""
    return StaticRoster(
        {
            CLASS_ID: [
                StudentRef(user_id="user_mock_s01", display_name="合成学生 01"),
                StudentRef(user_id="user_mock_s02", display_name="合成学生 02"),
                StudentRef(user_id="user_mock_s03", display_name="合成学生 03"),
            ]
        }
    )


@pytest.fixture
def consumed_store(synthetic_events: list[LearningEvent]) -> InMemoryAnalyticsStore:
    """已消费完全部合成事件的状态（含游标）。"""
    store = InMemoryAnalyticsStore()
    AnalyticsConsumer(InMemoryEventSource(synthetic_events), store).poll_once()
    return store


@pytest.fixture
def empty_store() -> InMemoryAnalyticsStore:
    """尚未消费任何事件的状态。"""
    return InMemoryAnalyticsStore()
