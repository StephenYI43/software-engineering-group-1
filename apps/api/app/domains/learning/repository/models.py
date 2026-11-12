"""Table-row dataclasses for the learning domain.

Mirror the data-model overview in packages/contracts/learning/README.md:105-122
(table list) and the per-contract field tables. Field names are snake_case to
match DB columns (docs/code-standards.md:49) and so response schemas with
`from_attributes=True` can read directly off a row.

Rows deliberately hold plain Python types (str for enums, dict for JSON-shaped
fields). A future DB driver maps its rows to these dataclasses; the in-memory
implementation is the first such driver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CourseRow:
    id: str
    title: str
    description: str | None
    subject: str
    cover_image_url: str | None
    teacher_id: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class ClassRow:
    id: str
    course_id: str
    title: str
    teacher_id: str
    semester: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class ChapterRow:
    id: str
    course_id: str
    title: str
    order: int
    description: str | None
    document_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class AssignmentRow:
    id: str
    course_id: str
    class_id: str | None
    chapter_id: str | None
    title: str
    description: str | None
    question_type: str
    answer_key: dict[str, Any] | None
    max_score: int
    due_at: str | None
    published_at: str | None
    teacher_id: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SubmissionRow:
    id: str
    assignment_id: str
    class_id: str | None
    student_id: str
    answer: dict[str, Any] | str
    is_correct: bool | None
    score: int | None
    graded_at: str | None
    graded_by: str
    idempotency_key: str
    submitted_at: str
    created_at: str


@dataclass(slots=True)
class MistakeRow:
    id: str
    student_id: str
    course_id: str
    chapter_id: str | None
    assignment_id: str | None
    submission_id: str | None
    source_turn_id: str | None
    source: str
    question: dict[str, Any]
    student_answer: dict[str, Any] | str | None
    note: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class StudyPlanRow:
    id: str
    student_id: str
    title: str
    course_id: str | None
    chapter_id: str | None
    source: str
    source_turn_id: str | None
    status: str
    due_at: str | None
    created_at: str
    updated_at: str
    items: list[PlanItemRow] = field(default_factory=list)


@dataclass(slots=True)
class PlanItemRow:
    id: str
    plan_id: str
    content: str
    order: int
    status: str
    due_at: str | None
    chapter_id: str | None
    knowledge_point: str | None
    related_mistake_id: str | None
    related_assignment_id: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class ReminderRow:
    id: str
    student_id: str
    plan_id: str | None
    assignment_id: str | None
    type: str
    title: str
    body: str | None
    due_at: str
    is_read: bool
    created_at: str
    read_at: str | None


@dataclass(slots=True)
class LearningEventRow:
    event_id: str
    event_type: str
    user_id: str
    course_id: str | None
    occurred_at: str
    trace_id: str
    schema_version: str
    payload: dict[str, Any]
