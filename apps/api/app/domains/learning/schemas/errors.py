"""Error response shape and codes for the learning domain.

Structure follows docs/code-standards.md:74-80. Codes and their HTTP mappings
come from packages/contracts/learning/samples/errors.md and the four domain
contracts. `MISTAKE_DUPLICATE` is a non-error 200 response path: it is kept
here so the service layer can reuse the shape without inventing a new one.
"""

from enum import StrEnum

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel


class ErrorCode(StrEnum):
    """Closed set of learning-domain error codes.

    Values are the wire strings clients depend on (courses.md, homework.md,
    mistakes.md, study-plans.md, samples/errors.md). Do not rename without a
    contract change and reviewer sign-off (CONTRIBUTING.md:37).
    """

    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    CLASS_NOT_FOUND = "CLASS_NOT_FOUND"
    CHAPTER_NOT_FOUND = "CHAPTER_NOT_FOUND"
    ASSIGNMENT_NOT_FOUND = "ASSIGNMENT_NOT_FOUND"
    SUBMISSION_NOT_FOUND = "SUBMISSION_NOT_FOUND"
    SUBMISSION_ALREADY_EXISTS = "SUBMISSION_ALREADY_EXISTS"
    SUBMISSION_DRAFT_LOCKED = "SUBMISSION_DRAFT_LOCKED"
    MISTAKE_NOT_FOUND = "MISTAKE_NOT_FOUND"
    MISTAKE_DUPLICATE = "MISTAKE_DUPLICATE"
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    PLAN_ITEM_NOT_FOUND = "PLAN_ITEM_NOT_FOUND"
    REMINDER_NOT_FOUND = "REMINDER_NOT_FOUND"
    TUTORING_TURN_NOT_FOUND = "TUTORING_TURN_NOT_FOUND"
    PLAN_ITEMS_LIMIT_EXCEEDED = "PLAN_ITEMS_LIMIT_EXCEEDED"
    PLAN_DUE_IN_PAST = "PLAN_DUE_IN_PAST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
    RATE_LIMITED = "RATE_LIMITED"


class ErrorResponse(CamelModel):
    """Error body returned on every failure path (code-standards.md:74-80)."""

    code: ErrorCode
    message: str
    request_id: str = Field(alias="requestId")
    details: dict[str, object] = Field(default_factory=dict)
