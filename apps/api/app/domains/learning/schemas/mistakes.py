"""Mistake schemas (packages/contracts/learning/mistakes.md).

Hard rule (mistakes.md:9-27): only wrong submissions and explicit student
marks are collected. The server rejects client-supplied `source=wrong_submission`
with 422; that path is internal-only (mistakes.md:101-104, invariant 1).
"""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel, Page, RequestModel


class MistakeSource(StrEnum):
    """Collection source (mistakes.md:48-55). Closed set of two."""

    WRONG_SUBMISSION = "wrong_submission"
    MANUAL = "manual"


class MistakeStatus(StrEnum):
    """Lifecycle status (mistakes.md:57-66)."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class MistakeQuestionType(StrEnum):
    """Question type stored on the mistake snapshot (mistakes.md:86-94).

    Assignment-sourced mistakes reuse the homework question types; mistakes
    marked from a tutoring turn use `tutoring_question` for free-form text.
    """

    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    PROOF = "proof"
    TUTORING_QUESTION = "tutoring_question"


class MistakeQuestion(CamelModel):
    """Question snapshot at collection time (mistakes.md:68-97).

    A snapshot: later teacher edits to the assignment do not rewrite already
    collected mistakes (mistakes.md:96-97, invariant 4).
    """

    stem: str = Field(max_length=4000)
    question_type: MistakeQuestionType
    options: list[str] | None = None
    attachment_url: str | None = None


class MistakeResponse(CamelModel):
    """Full mistake object (mistakes.md:29-47)."""

    id: str
    student_id: str
    course_id: str
    chapter_id: str | None = None
    assignment_id: str | None = None
    submission_id: str | None = None
    source_turn_id: str | None = None
    source: MistakeSource
    question: MistakeQuestion
    student_answer: dict[str, Any] | str | None = None
    note: str | None = Field(default=None, max_length=500)
    status: MistakeStatus
    created_at: str
    updated_at: str


class MistakeCreateRequest(RequestModel):
    """Student-initiated mark (mistakes.md:100-148).

    `studentId` is session-derived. `source` must be `manual`; the server
    rejects `wrong_submission` from clients (mistakes.md:101-104). The
    dedup key is computed server-side: assignment-scoped
    `(studentId, assignmentId, normalizedStem)`; tutoring-scoped
    `(studentId, sourceTurnId, normalizedStem)` (mistakes.md:150-160).
    """

    course_id: str
    chapter_id: str | None = None
    assignment_id: str | None = None
    submission_id: str | None = None
    source_turn_id: str | None = None
    source: MistakeSource = MistakeSource.MANUAL
    question: MistakeQuestion
    student_answer: dict[str, Any] | str | None = None
    note: str | None = Field(default=None, max_length=500)


class MistakePatchRequest(RequestModel):
    """Student edits a mistake (mistakes.md:183-192).

    Only `note` and `status` are mutable. Physical delete is not implemented;
    `status` moves to `resolved`/`archived` (mistakes.md:194-198).
    """

    note: str | None = Field(default=None, max_length=500)
    status: MistakeStatus | None = None


MistakeListResponse = Page[MistakeResponse]
