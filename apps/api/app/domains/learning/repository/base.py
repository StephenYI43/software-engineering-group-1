"""Driver-neutral repository protocol for the learning domain.

A concrete DB-backed implementation will satisfy this protocol; the in-memory
implementation in `in_memory.py` is the first one and what the S1 tests use.
Service-layer business rules (auth from #16, M3 planSuggestion fetching,
event publish-or-skip on idempotent hits) sit above this protocol and are not
its concern: the repository only stores and queries rows.

List methods return `(rows, total)` so the caller can assemble a `Page` with
the correct `total` even when the page slice is a window. `list_*` filters
that depend on auth (e.g. "courses the current student can see") are not here:
they belong to the service layer once #16 lands.
"""

from collections.abc import Sequence
from typing import Protocol

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


class LearningRepository(Protocol):
    """Aggregate repository for all learning-domain tables.

    Each table is owned by M5 and not shared with other domains
    (code-standards.md:33). Cross-domain reads go through public service
    functions or events, not direct table access.
    """

    # --- courses (courses.md) ---
    def add_course(self, row: CourseRow) -> None: ...
    def get_course(self, course_id: str) -> CourseRow | None: ...
    def list_courses(
        self,
        *,
        teacher_id: str | None = None,
        subject: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[CourseRow], int]: ...

    # --- classes (courses.md) ---
    def add_class(self, row: ClassRow) -> None: ...
    def get_class(self, class_id: str) -> ClassRow | None: ...
    def list_classes_by_course(self, course_id: str) -> tuple[Sequence[ClassRow], int]: ...

    # --- chapters (courses.md) ---
    def add_chapter(self, row: ChapterRow) -> None: ...
    def get_chapter(self, chapter_id: str) -> ChapterRow | None: ...
    def list_chapters_by_course(
        self, course_id: str, *, page: int = 1, page_size: int = 50
    ) -> tuple[Sequence[ChapterRow], int]: ...
    def next_chapter_order(self, course_id: str) -> int:
        """Next `order` value for a new chapter (max(existing) + 1, or 1)."""

    # --- assignments (homework.md) ---
    def add_assignment(self, row: AssignmentRow) -> None: ...
    def get_assignment(self, assignment_id: str) -> AssignmentRow | None: ...
    def list_assignments_by_course(
        self, course_id: str, *, published_only: bool = False
    ) -> tuple[Sequence[AssignmentRow], int]: ...

    # --- submissions (homework.md) ---
    def add_submission(self, row: SubmissionRow) -> None: ...
    def get_submission(self, submission_id: str) -> SubmissionRow | None: ...
    def get_submission_by_assignment_student(
        self, assignment_id: str, student_id: str
    ) -> SubmissionRow | None: ...
    def find_submission_by_idempotency(
        self, assignment_id: str, student_id: str, idempotency_key: str
    ) -> SubmissionRow | None: ...
    def list_submissions_by_assignment(
        self,
        assignment_id: str,
        *,
        graded: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[SubmissionRow], int]: ...
    def update_submission_grading(
        self,
        submission_id: str,
        *,
        is_correct: bool,
        score: int | None,
        graded_at: str,
        graded_by: str,
    ) -> SubmissionRow | None: ...

    # --- mistakes (mistakes.md) ---
    def add_mistake(self, row: MistakeRow) -> None: ...
    def get_mistake(self, mistake_id: str) -> MistakeRow | None: ...
    def find_active_mistake(
        self,
        *,
        student_id: str,
        assignment_id: str | None,
        source_turn_id: str | None,
        normalized_stem: str,
    ) -> MistakeRow | None: ...
    def list_mistakes_by_student(
        self,
        student_id: str,
        *,
        course_id: str | None = None,
        chapter_id: str | None = None,
        source: str | None = None,
        status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[MistakeRow], int]: ...
    def update_mistake(
        self, mistake_id: str, *, note: str | None = None, status: str | None = None
    ) -> MistakeRow | None: ...

    # --- study plans + items (study-plans.md) ---
    def add_plan(self, plan: StudyPlanRow, items: Sequence[PlanItemRow]) -> None: ...
    def get_plan(self, plan_id: str) -> StudyPlanRow | None: ...
    def list_plans_by_student(
        self,
        student_id: str,
        *,
        course_id: str | None = None,
        status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[StudyPlanRow], int]: ...
    def update_plan(
        self,
        plan_id: str,
        *,
        title: str | None = None,
        due_at: str | None = None,
        status: str | None = None,
        updated_at: str,
    ) -> StudyPlanRow | None: ...
    def add_plan_item(self, row: PlanItemRow) -> PlanItemRow | None: ...
    def update_plan_item(
        self,
        plan_id: str,
        item_id: str,
        *,
        content: str | None = None,
        status: str | None = None,
        due_at: str | None = None,
        order: int | None = None,
        updated_at: str,
    ) -> PlanItemRow | None: ...
    def delete_plan_item(self, plan_id: str, item_id: str) -> bool: ...

    # --- reminders (study-plans.md) ---
    def add_reminder(self, row: ReminderRow) -> None: ...
    def get_reminder(self, reminder_id: str) -> ReminderRow | None: ...
    def list_reminders_by_student(
        self,
        student_id: str,
        *,
        is_read: bool | None = None,
        type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[ReminderRow], int]: ...
    def update_reminder(
        self, reminder_id: str, *, is_read: bool, read_at: str | None
    ) -> ReminderRow | None: ...

    # --- learning events (learning-events.md) ---
    def append_event(self, row: LearningEventRow) -> None: ...
    def list_events(
        self, *, user_id: str | None = None, limit: int = 100
    ) -> Sequence[LearningEventRow]: ...
