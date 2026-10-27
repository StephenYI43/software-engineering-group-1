"""Pydantic schemas for the learning domain.

snake_case Python attributes, camelCase JSON aliases (docs/code-standards.md:55).
Request bodies forbid unknown fields so forbidden inputs such as `isCorrect` on
a submission or `gradedBy` on a grading patch are rejected as 422 at the
schema boundary, matching packages/contracts/learning/samples/errors.md.
"""

from app.domains.learning.schemas.common import CamelModel, Page, PageParams, RequestModel
from app.domains.learning.schemas.courses import (
    ChapterCreateRequest,
    ChapterResponse,
    ClassCreateRequest,
    ClassResponse,
    CourseCreateRequest,
    CourseResponse,
    Subject,
)
from app.domains.learning.schemas.errors import ErrorCode, ErrorResponse
from app.domains.learning.schemas.homework import (
    AnswerKey,
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentStudentView,
    GradingPatchRequest,
    QuestionType,
    StudentSummary,
    SubmissionCreateRequest,
    SubmissionResponse,
    SubmissionStatusResponse,
)
from app.domains.learning.schemas.learning_events import EventType, LearningEvent
from app.domains.learning.schemas.mistakes import (
    MistakeCreateRequest,
    MistakePatchRequest,
    MistakeQuestion,
    MistakeQuestionType,
    MistakeResponse,
    MistakeSource,
    MistakeStatus,
)
from app.domains.learning.schemas.study_plans import (
    PlanItemCreateRequest,
    PlanItemPatchRequest,
    PlanItemResponse,
    PlanItemStatus,
    PlanSource,
    PlanStatus,
    ReminderPatchRequest,
    ReminderResponse,
    ReminderType,
    StudyPlanCreateRequest,
    StudyPlanPatchRequest,
    StudyPlanResponse,
)

__all__ = [
    "AnswerKey",
    "AssignmentCreateRequest",
    "AssignmentResponse",
    "AssignmentStudentView",
    "CamelModel",
    "ChapterCreateRequest",
    "ChapterResponse",
    "ClassCreateRequest",
    "ClassResponse",
    "CourseCreateRequest",
    "CourseResponse",
    "ErrorCode",
    "ErrorResponse",
    "EventType",
    "GradingPatchRequest",
    "LearningEvent",
    "MistakeCreateRequest",
    "MistakePatchRequest",
    "MistakeQuestion",
    "MistakeQuestionType",
    "MistakeResponse",
    "MistakeSource",
    "MistakeStatus",
    "Page",
    "PageParams",
    "PlanItemCreateRequest",
    "PlanItemPatchRequest",
    "PlanItemResponse",
    "PlanItemStatus",
    "PlanSource",
    "PlanStatus",
    "QuestionType",
    "ReminderPatchRequest",
    "ReminderResponse",
    "ReminderType",
    "RequestModel",
    "StudentSummary",
    "SubmissionCreateRequest",
    "SubmissionResponse",
    "SubmissionStatusResponse",
    "Subject",
    "StudyPlanCreateRequest",
    "StudyPlanPatchRequest",
    "StudyPlanResponse",
]
