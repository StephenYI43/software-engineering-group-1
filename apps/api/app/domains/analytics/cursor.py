"""消费位点（游标）。

语义见 `packages/contracts/analytics/event-consumption.md`：排序键为
`(occurredAt, eventId)`，`occurredAt` 是主序，`eventId` 只在同一时间戳下作
确定性 tie-breaker（不作为发生顺序的依据）。游标只前进。

序列化时附带 `cursorName`（固定 `analytics_consumption`）与 `updatedAt`
（保存时刻），便于人工排查与多游标存储场景区分；二者只是元数据，
不参与排序与相等比较。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domains.analytics.events import EVENT_ID_PATTERN, EventValidationError, LearningEvent

CURSOR_NAME = "analytics_consumption"
"""游标名称常量：本域只有单一全局消费游标。"""


@dataclass(frozen=True, order=True)
class Cursor:
    """单一全局游标，按 `(occurred_at, event_id)` 排序（字段声明顺序即比较顺序）。

    `updated_at` 是游标保存时刻的元数据，必须 `compare=False`，
    保证排序与相等比较仍只看 `(occurred_at, event_id)`。
    """

    occurred_at: datetime
    event_id: str
    updated_at: datetime | None = field(compare=False, default=None)

    @classmethod
    def of(cls, event: LearningEvent) -> Cursor:
        return cls(occurred_at=event.occurred_at, event_id=event.event_id)

    def to_json(self) -> dict[str, Any]:
        return {
            "lastOccurredAt": self.occurred_at.isoformat(),
            "lastEventId": self.event_id,
            "cursorName": CURSOR_NAME,
            "updatedAt": self.updated_at.isoformat() if self.updated_at is not None else None,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Cursor:
        occurred_at = raw.get("lastOccurredAt")
        event_id = raw.get("lastEventId")
        if not isinstance(occurred_at, str) or not isinstance(event_id, str):
            raise EventValidationError("游标状态必须包含 lastOccurredAt 与 lastEventId 字符串")
        if EVENT_ID_PATTERN.match(event_id) is None:
            raise EventValidationError(f"游标 lastEventId 不是合法事件 ID：{event_id}")
        try:
            parsed = datetime.fromisoformat(occurred_at)
        except ValueError as error:
            raise EventValidationError(
                f"游标 lastOccurredAt 不是合法时间：{occurred_at}"
            ) from error
        if parsed.tzinfo is None:
            raise EventValidationError("游标 lastOccurredAt 必须带时区")
        return cls(occurred_at=parsed, event_id=event_id, updated_at=_parse_updated_at(raw))


def _parse_updated_at(raw: Mapping[str, Any]) -> datetime | None:
    """宽松读取 `updatedAt` 元数据：可缺省，无法解析时忽略（旧游标没有该字段）。"""
    value = raw.get("updatedAt")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
