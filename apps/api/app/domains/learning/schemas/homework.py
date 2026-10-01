"""Homework schemas: assignment, submission, grading (packages/contracts/learning/homework.md).

Key invariants surfaced at the schema boundary:
- `answerKey` is absent from the student view (not null) to prevent existence
  probing (homework.md:46-58, invariant 1).
- `gradedBy` is server-derived and never accepted on a request body
  (homework.md:71, invariant 8).
- `studentId` on a submission is the stable M1 user id; names/student numbers
  are composed into `StudentSummary` at response time, never persisted
  (homework.md:79-90, invariant 9).
"""

from enum import StrEnum
from typing import Any

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel, Page, RequestModel


class QuestionType(StrEnum):
    """Assignment question types (homework.md:28-37).

    `single_choice`/`multiple_choice`/`fill_blank` are auto-graded against
    `answerKey`; `short_answer`/`proof` require teacher grading. The
    `tutoring_question` variant lives in mistakes.py for mistake snapshots
    sourced from M3 free-form text.
    """

    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    PROOF = "proof"


class AnswerKey(CamelModel):
    """Teacher-side answer key (homework.md:46-53). Never returned to students."""

    options: list[str] | None = None
    acceptable_blanks: list[str] | None = None


class AssignmentResponse(CamelModel):
    """Teacher view of an assignment (homework.md:9-26). `answerKey` retained."""

    id: str
    course_id: str
    class_id: str | None = None
    chapter_id: str | None = None
    title: str
    description: str | None = None
    question_type: QuestionType
    answer_key: AnswerKey | None = None
    max_score: int = Field(ge=1)
    due_at: str | None = None
    published_at: str | None = None
    teacher_id: str
    created_at: str
    updated_at: str


class AssignmentStudentView(CamelModel):
    """Student view of an assignment (homework.md:122-126).

    `answer_key` is omitted entirely (not null) so clients cannot probe whether
    a key exists (homework.md:55-57, invariant 1). Draft assignments
    (`published_at` is null) are not visible to students (homework.md:288).
    """

    id: str
    course_id: str
    class_id: str | None = None
    chapter_id: str | None = None
    title: str
    description: str | None = None
    question_type: QuestionType
    max_score: int = Field(ge=1)
    due_at: str | None = None
    published_at: str | None = None
    teacher_id: str
    created_at: str
    updated_at: str


class AssignmentCreateRequest(RequestModel):
    """Publish an assignment (homework.md:94-114). `teacherId` is session-derived."""

    class_id: str | None = None
    chapter_id: str | None = None
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=8000)
    question_type: QuestionType
    answer_key: AnswerKey | None = None
    max_score: int = Field(ge=1)
    due_at: str | None = None
    published_at: str | None = None


class StudentSummary(CamelModel):
    """Composed student summary for the teacher grading list (homework.md:79-90).

    Not persisted on `submissions`; assembled at response time from M1 profile
    to avoid name drift.
    """

    student_id: str
    name: str | None = None
    student_number: str | None = None


class SubmissionResponse(CamelModel):
    """Full submission object (homework.md:59-77).

    `graded_by` is server-written (`auto`/`teacher`/`ai_assisted`); `isCorrect`
    cannot regress to null once set (homework.md:282-284, invariant 4).
    """

    id: str
    assignment_id: str
    class_id: str | None = None
    student_id: str
    answer: dict[str, Any] | str
    is_correct: bool | None = None
    score: int | None = None
    graded_at: str | None = None
    graded_by: str
    idempotency_key: str = Field(max_length=128)
    submitted_at: str
    created_at: str


class SubmissionListItem(CamelModel):
    """One row in the teacher's grading list (homework.md:210-250).

    Includes the composed `student_summary`; `answer_key` is irrelevant here
    (it lives on the assignment, not the submission).
    """

    id: str
    assignment_id: str
    student_id: str
    student_summary: StudentSummary
    answer: dict[str, Any] | str
    is_correct: bool | None = None
    score: int | None = None
    graded_at: str | None = None
    graded_by: str
    submitted_at: str
    created_at: str


class SubmissionCreateRequest(RequestModel):
    """Student submission (homework.md:128-162).

    `studentId` is session-derived; `isCorrect`/`score`/`gradedAt`/`gradedBy`
    are server-derived. Any of those in the body hit `extra="forbid"` and
    return 422 (homework.md:289, invariant 8).
    """

    answer: dict[str, Any] | str
    idempotency_key: str = Field(min_length=1, max_length=128)


class GradingPatchRequest(RequestModel):
    """Teacher grading patch (homework.md:254-272).

    `gradedBy` is server-derived from the session role; including it yields
    422 via `extra="forbid"` (homework.md:289, invariant 8).
    """

    is_correct: bool
    score: int | None = Field(default=None, ge=0)


class SubmissionStatusResponse(CamelModel):
    """`GET /api/v1/assignments/{id}/submissions/me` body (homework.md:183-206).

    Returns `{"submission": null}` when the student has not submitted yet
    (200, not 404). Cross-user access still returns 404 (errors.md:32-46).
    """

    submission: SubmissionResponse | None = None


AssignmentListResponse = Page[AssignmentStudentView]
SubmissionListResponse = Page[SubmissionListItem]
