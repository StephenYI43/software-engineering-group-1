"""域外依赖的端口（Protocol）。

S1 只有内存实现（`memory.py`）：M5 的 `learning_events` 表与 M1 的鉴权/花名册
接口都还没落地（`packages/contracts/analytics/README.md`「依赖现状」），
此处先把接口定下来，接真实实现时只替换实现类，不改聚合逻辑。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domains.analytics.cursor import Cursor
from app.domains.analytics.events import LearningEvent
from app.domains.analytics.state import AnalyticsState


@dataclass(frozen=True)
class StudentRef:
    """班级花名册中的一名学生。`display_name` 由 M1 的身份接口提供，可为空。"""

    user_id: str
    display_name: str | None = None


class EventSource(Protocol):
    """事件来源。S1 实现是 M5 的 `learning_events` 表（M6 只读）。

    实现必须按 `(occurredAt, eventId)` 升序返回游标之后的事件
    （`packages/contracts/analytics/event-consumption.md`「消费位点」）。
    """

    def read_after(self, cursor: Cursor | None, limit: int) -> Sequence[LearningEvent]:
        """读取 `cursor` 之后最多 `limit` 条事件，升序。`cursor` 为 None 表示从头读。"""
        ...


class AnalyticsStore(Protocol):
    """聚合状态与游标的持久化。

    `save` 必须**原子**写入状态（含游标与已处理事件账本）：实现须在单事务内完成，
    否则失败时可能留下「事件已计入但游标未推进」或反过来的不一致状态。
    """

    def load(self) -> AnalyticsState:
        """读取当前状态；调用方在副本上修改，不得就地改写返回对象的共享引用。"""
        ...

    def save(self, state: AnalyticsState) -> None:
        """原子替换整个状态。"""
        ...


class ClassRoster(Protocol):
    """班级花名册，由 M1 的身份/权限接口提供。

    返回 `None` 表示班级不存在**或**不在该教师授权范围内——两者对外统一 404，
    避免通过状态码枚举他人班级（`statistics-api.md`「权限与错误」）。
    """

    def list_students(self, class_id: str) -> Sequence[StudentRef] | None:
        """列出班级学生；无权限或不存在时返回 None。"""
        ...
