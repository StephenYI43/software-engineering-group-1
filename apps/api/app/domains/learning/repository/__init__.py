"""Repository package for the learning domain.

Re-exports the in-memory driver and the protocol so the service layer and
tests can depend on the abstraction (`LearningRepository`) rather than the
concrete class.
"""

from app.domains.learning.repository.base import LearningRepository
from app.domains.learning.repository.in_memory import (
    InMemoryLearningRepository,
    new_id,
    normalize_stem,
    now,
)
from app.domains.learning.repository.models import (
    AssignmentRow,
    ChapterRow,
    ClassRow,
    CourseRow,
    LearningEventRow,
    MistakeRow,
    PlanItemRow,
    ReminderRow,
    StudyPlanRow,
    SubmissionRow,
)

__all__ = [
    "AssignmentRow",
    "ChapterRow",
    "ClassRow",
    "CourseRow",
    "InMemoryLearningRepository",
    "LearningEventRow",
    "LearningRepository",
    "MistakeRow",
    "PlanItemRow",
    "ReminderRow",
    "StudyPlanRow",
    "SubmissionRow",
    "new_id",
    "normalize_stem",
    "now",
]
