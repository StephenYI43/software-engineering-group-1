"""消费位点（游标）。

语义见 `packages/contracts/analytics/event-consumption.md`：排序键为
`(occurredAt, eventId)`，`occurredAt` 是主序，`eventId` 只在同一时间戳下作
确定性 tie-breaker（不作为发生顺序的依据）。游标只前进。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domains.analytics.events import EventValidationError, LearningEvent


@dataclass(frozen=True, order=True)
class Cursor:
    """单一全局游标，按 `(occurred_at, event_id)` 排序（字段声明顺序即比较顺序）。"""

    occurred_at: datetime
    event_id: str

    @classmethod
    def of(cls, event: LearningEvent) -> Cursor:
        return cls(occurred_at=event.occurred_at, event_id=event.event_id)

    def to_json(self) -> dict[str, str]:
        return {
            "lastOccurredAt": self.occurred_at.isoformat(),
            "lastEventId": self.event_id,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Cursor:
        occurred_at = raw.get("lastOccurredAt")
        event_id = raw.get("lastEventId")
        if not isinstance(occurred_at, str) or not isinstance(event_id, str):
            raise EventValidationError("游标状态必须包含 lastOccurredAt 与 lastEventId 字符串")
        try:
            parsed = datetime.fromisoformat(occurred_at)
        except ValueError as error:
            raise EventValidationError(
                f"游标 lastOccurredAt 不是合法时间：{occurred_at}"
            ) from error
        if parsed.tzinfo is None:
            raise EventValidationError("游标 lastOccurredAt 必须带时区")
        return cls(occurred_at=parsed, event_id=event_id)
