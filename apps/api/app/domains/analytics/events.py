"""学习事件输入模型（M6 消费侧）。

字段与语义依据 M5 的 `packages/contracts/learning/learning-events.md`
（PR #26，未合并）：六公共字段 `eventId` / `eventType` / `userId` / `courseId` /
`occurredAt` / `traceId` / `schemaVersion` 加 `payload`。

本模块只做输入校验与规范化，不做聚合。校验失败抛 `EventValidationError`，
**不静默跳过**：少算和错算一样有害，且静默跳过会掩盖上游契约违约
（`docs/code-standards.md:63`「不吞异常」）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

EVENT_ID_PATTERN = re.compile(r"^event_[0-9a-f]{32}$")
"""`eventId` 格式：`event_` 加 UUIDv4 的 32 位小写十六进制（M1 冻结口径）。"""

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})
"""S1 支持的 `schemaVersion`；新增版本需同步消费逻辑。"""


class EventType(StrEnum):
    """M5 发布侧的事件类型；`chapter_viewed` 由 M2 发布。"""

    ASSIGNMENT_SUBMITTED = "assignment_submitted"
    ASSIGNMENT_GRADED = "assignment_graded"
    MISTAKE_RECORDED = "mistake_recorded"
    MISTAKE_RESOLVED = "mistake_resolved"
    STUDY_PLAN_SAVED = "study_plan_saved"
    PLAN_ITEM_COMPLETED = "plan_item_completed"
    REMINDER_TRIGGERED = "reminder_triggered"
    CHAPTER_VIEWED = "chapter_viewed"


class EventValidationError(ValueError):
    """事件不符合契约，无法安全参与聚合。"""


class LearningEvent(BaseModel):
    """一条学习事件。

    `extra="ignore"`：契约允许新增字段而不破坏旧消费者
    （learning-events.md 不变量 5），因此未知字段忽略而非报错。
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True, extra="ignore")

    event_id: str = Field(alias="eventId")
    event_type: EventType = Field(alias="eventType")
    user_id: str = Field(alias="userId")
    course_id: str | None = Field(alias="courseId")
    occurred_at: datetime = Field(alias="occurredAt")
    trace_id: str = Field(alias="traceId")
    schema_version: str = Field(alias="schemaVersion")
    payload: dict[str, Any]

    @field_validator("event_id")
    @classmethod
    def _check_event_id(cls, value: str) -> str:
        if not EVENT_ID_PATTERN.match(value):
            raise ValueError("eventId 必须为 event_ 加 32 位小写十六进制")
        return value

    @field_validator("occurred_at")
    @classmethod
    def _normalize_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurredAt 必须是带时区的 UTC ISO 8601")
        return value.astimezone(UTC)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(f"不支持的 schemaVersion：{value}")
        return value

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> LearningEvent:
        """从已解析的 JSON 对象构造事件，校验失败时抛 `EventValidationError`。"""
        try:
            return cls.model_validate(dict(raw))
        except ValidationError as error:
            raise EventValidationError(str(error)) from error


def required_str(payload: Mapping[str, Any], key: str, event: LearningEvent) -> str:
    """读取 payload 中的必填字符串字段。

    契约外数据（类型不符、缺失）一律报错而不是猜测，
    否则统计会在无人察觉的情况下偏小。
    """
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise EventValidationError(f"{event.event_type} 事件的 payload.{key} 必须是非空字符串")
    return value


def optional_str(payload: Mapping[str, Any], key: str, event: LearningEvent) -> str | None:
    """读取 payload 中的可选字符串字段；缺失或为 null 返回 None。"""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise EventValidationError(
            f"{event.event_type} 事件的 payload.{key} 必须是非空字符串或 null"
        )
    return value


def optional_bool(payload: Mapping[str, Any], key: str, event: LearningEvent) -> bool | None:
    """读取 payload 中的可选布尔字段；缺失或为 null 返回 None（如主观题未判分）。"""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise EventValidationError(f"{event.event_type} 事件的 payload.{key} 必须是布尔值或 null")
    return value
