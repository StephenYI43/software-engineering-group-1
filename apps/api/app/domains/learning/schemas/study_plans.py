"""Study plan, plan item and reminder schemas (packages/contracts/learning/study-plans.md).

The `source=tutoring` path depends on M3's `planSuggestion` delivery interface.
Until that lands, the service layer stubs the path to 404 and the PR notes the
Mock (study-plans.md:22-25, AGENTS.md:4). The schema layer accepts both
shapes; conditional validation (`source=tutoring` forbids `items`) is a
service-layer concern, not a schema one.
"""

from enum import StrEnum

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel, Page, RequestModel


class PlanSource(StrEnum):
    """Plan origin (study-plans.md:72-78)."""

    TUTORING = "tutoring"
    MANUAL = "manual"
    IMPORTED = "imported"


class PlanStatus(StrEnum):
    """Plan lifecycle (study-plans.md:80-86)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PlanItemStatus(StrEnum):
    """Plan item lifecycle (study-plans.md:88-96)."""

    PENDING = "pending"
    DONE = "done"


class ReminderType(StrEnum):
    """Reminder type (study-plans.md:218-224).

    `mistake_review_due` is S2; S1 implements only `plan_due`/`assignment_due`
    (study-plans.md:199-202).
    """

    PLAN_DUE = "plan_due"
    ASSIGNMENT_DUE = "assignment_due"
    MISTAKE_REVIEW_DUE = "mistake_review_due"


class PlanItemResponse(CamelModel):
    """Plan item (study-plans.md:88-102).

    `chapter_id` is filled by M5 at save time from `knowledge_point` or the
    student's current chapter; M3 sends `null` (study-plans.md:46-49).
    """

    id: str
    plan_id: str
    content: str = Field(max_length=500)
    order: int = Field(ge=1)
    status: PlanItemStatus
    due_at: str | None = None
    chapter_id: str | None = None
    knowledge_point: str | None = None
    related_mistake_id: str | None = None
    related_assignment_id: str | None = None
    created_at: str
    updated_at: str


class StudyPlanResponse(CamelModel):
    """Full study plan with items (study-plans.md:54-69)."""

    id: str
    student_id: str
    title: str
    course_id: str | None = None
    chapter_id: str | None = None
    source: PlanSource
    source_turn_id: str | None = None
    status: PlanStatus
    items: list[PlanItemResponse]
    due_at: str | None = None
    created_at: str
    updated_at: str


class PlanItemCreateRequest(RequestModel):
    """Add an item to a plan (study-plans.md:187-189). `order` is server-continued."""

    content: str = Field(min_length=1, max_length=500)
    order: int | None = Field(default=None, ge=1)
    due_at: str | None = None
    chapter_id: str | None = None
    knowledge_point: str | None = None
    related_mistake_id: str | None = None
    related_assignment_id: str | None = None


class StudyPlanCreateRequest(RequestModel):
    """Create a plan (study-plans.md:106-167).

    `source=manual` carries `items`; `source=tutoring` carries only
    `source_turn_id` (and optional `title`/`course_id`/`due_at` overrides).
    The schema accepts both; the service layer enforces the conditional rule
    and rejects `items` on a tutoring-sourced request with 422
    (study-plans.md:163-168, errors.md:173-182).
    """

    source: PlanSource
    source_turn_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=100)
    course_id: str | None = None
    chapter_id: str | None = None
    due_at: str | None = None
    items: list[PlanItemCreateRequest] | None = None


class StudyPlanPatchRequest(RequestModel):
    """Edit a plan (study-plans.md:183-185). Only `title`/`due_at`/`status`."""

    title: str | None = Field(default=None, min_length=1, max_length=100)
    due_at: str | None = None
    status: PlanStatus | None = None


class PlanItemPatchRequest(RequestModel):
    """Edit a plan item (study-plans.md:191-193)."""

    content: str | None = Field(default=None, min_length=1, max_length=500)
    status: PlanItemStatus | None = None
    due_at: str | None = None
    order: int | None = Field(default=None, ge=1)


class ReminderResponse(CamelModel):
    """In-app reminder (study-plans.md:204-216).

    Only the server creates reminders (study-plans.md:256-257, invariant 7).
    `read_at` is required once `is_read` is true and cleared on unread
    (study-plans.md:258, invariant 8).
    """

    id: str
    student_id: str
    plan_id: str | None = None
    assignment_id: str | None = None
    type: ReminderType
    title: str = Field(min_length=1, max_length=100)
    body: str | None = Field(default=None, max_length=500)
    due_at: str
    is_read: bool
    created_at: str
    read_at: str | None = None


class ReminderPatchRequest(RequestModel):
    """Mark a reminder read/unread (study-plans.md:233-242)."""

    is_read: bool


StudyPlanListResponse = Page[StudyPlanResponse]
ReminderListResponse = Page[ReminderResponse]
