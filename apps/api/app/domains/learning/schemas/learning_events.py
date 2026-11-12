"""Learning event schema published by M5 and consumed by M6.

Public fields `eventId` / `eventType` / `userId` / `occurredAt` / `traceId` /
`schemaVersion` follow docs/code-standards.md:92 and
packages/contracts/learning/learning-events.md. `chapter_viewed` is owned by
M2 and is therefore not in this enum (learning-events.md:50-61).
"""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel


class EventType(StrEnum):
    """Event types M5 publishes (learning-events.md:39-49).

    `chapter_viewed` is deliberately absent: it is a front-end behaviour event
    owned by M2, not M5 (learning-events.md:58-61).
    """

    ASSIGNMENT_SUBMITTED = "assignment_submitted"
    ASSIGNMENT_GRADED = "assignment_graded"
    MISTAKE_RECORDED = "mistake_recorded"
    MISTAKE_RESOLVED = "mistake_resolved"
    STUDY_PLAN_SAVED = "study_plan_saved"
    PLAN_ITEM_COMPLETED = "plan_item_completed"
    REMINDER_TRIGGERED = "reminder_triggered"


class LearningEvent(CamelModel):
    """One append-only learning event row (learning-events.md:22-33).

    `event_id` is server-generated and never accepted from clients
    (learning-events.md:37, invariant 3). `payload` is the per-event-type
    field bag; the closed set of keys per type is documented in the contract
    but not enforced here so M6 can read forward-compat additions.
    """

    event_id: str
    event_type: EventType
    user_id: str
    course_id: str | None = None
    occurred_at: str
    trace_id: str
    schema_version: str = "1.0"
    payload: dict[str, Any] = Field(default_factory=dict)
