"""端口的内存实现，供测试与无数据库时的本地演示使用。

**不是生产实现**：`learning_events` 表与鉴权接口就绪后，替换为真实的
`EventSource`（读 M5 的表）与 `AnalyticsStore`（写 analytics 域自己的表），
本域聚合逻辑不变。内存实现每次进程重启后状态归零。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from app.domains.analytics.cursor import Cursor
from app.domains.analytics.events import LearningEvent
from app.domains.analytics.ports import StudentRef
from app.domains.analytics.state import AnalyticsState


class InMemoryEventSource:
    """按 `(occurredAt, eventId)` 升序保存事件的简单来源。"""

    def __init__(self, events: Iterable[LearningEvent] = ()) -> None:
        self._events = sorted(events, key=Cursor.of)

    def read_after(self, cursor: Cursor | None, limit: int) -> Sequence[LearningEvent]:
        remaining = [event for event in self._events if cursor is None or Cursor.of(event) > cursor]
        return remaining[:limit]


class InMemoryAnalyticsStore:
    """把聚合状态整体放在内存中。

    `load` 返回当前状态对象，调用方必须先 `clone()` 再修改；`save` 原子替换。
    """

    def __init__(self, state: AnalyticsState | None = None) -> None:
        self._state = state if state is not None else AnalyticsState()

    def load(self) -> AnalyticsState:
        return self._state

    def save(self, state: AnalyticsState) -> None:
        self._state = state


class StaticRoster:
    """按班级 ID 返回固定花名册；不在表中的班级视为不存在或未授权。

    真实实现应改为查询 M1 的鉴权/花名册接口，并保证「未授权」与「不存在」
    在返回值上不可区分（统一 404，`statistics-api.md`「权限与错误」）。
    """

    def __init__(self, classes: Mapping[str, Sequence[StudentRef]]) -> None:
        self._classes = {class_id: tuple(students) for class_id, students in classes.items()}

    def list_students(self, class_id: str) -> Sequence[StudentRef] | None:
        return self._classes.get(class_id)
