"""In-memory learning repository.

First concrete driver for the `LearningRepository` protocol. Used by S1 tests
and by the service layer once it lands. Not thread-safe and not persistent:
it is a test/development stand-in until the #48 database plan freezes and a
real migration + driver is added.

ID and timestamp helpers (`new_id`, `now`) are module-level so the service
layer (future) and tests can build rows without depending on a specific driver.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

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


def new_id(prefix: str) -> str:
    """Return `<prefix><32 lowercase hex>` (README.md:65-70).

    `prefix` includes the trailing underscore, e.g. `"course_"`.
    """
    return f"{prefix}{uuid4().hex}"


def now() -> str:
    """UTC ISO 8601 with a trailing `Z` (code-standards.md:55)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_stem(stem: str) -> str:
    """Collapse surrounding/internal whitespace (mistakes.md:207-209)."""
    return " ".join(stem.split())


class InMemoryLearningRepository:
    """Dict-backed implementation of `LearningRepository`.

    Mutating methods return the stored row (or `None` when the target was not
    found) so callers can echo the post-update state back to the client without
    a second lookup.
    """

    def __init__(self) -> None:
        self._courses: dict[str, CourseRow] = {}
        self._classes: dict[str, ClassRow] = {}
        self._chapters: dict[str, ChapterRow] = {}
        self._assignments: dict[str, AssignmentRow] = {}
        self._submissions: dict[str, SubmissionRow] = {}
        self._mistakes: dict[str, MistakeRow] = {}
        self._plans: dict[str, StudyPlanRow] = {}
        self._plan_items: dict[str, PlanItemRow] = {}
        self._reminders: dict[str, ReminderRow] = {}
        self._events: list[LearningEventRow] = []

    # --- courses ---
    def add_course(self, row: CourseRow) -> None:
        self._courses[row.id] = row

    def get_course(self, course_id: str) -> CourseRow | None:
        return self._courses.get(course_id)

    def list_courses(
        self,
        *,
        teacher_id: str | None = None,
        subject: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[CourseRow], int]:
        rows = list(self._courses.values())
        if teacher_id is not None:
            rows = [r for r in rows if r.teacher_id == teacher_id]
        if subject is not None:
            rows = [r for r in rows if r.subject == subject]
        if q is not None:
            needle = q.lower()
            rows = [r for r in rows if needle in r.title.lower()]
        rows.sort(key=lambda r: r.created_at)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    # --- classes ---
    def add_class(self, row: ClassRow) -> None:
        self._classes[row.id] = row

    def get_class(self, class_id: str) -> ClassRow | None:
        return self._classes.get(class_id)

    def list_classes_by_course(self, course_id: str) -> tuple[Sequence[ClassRow], int]:
        rows = [r for r in self._classes.values() if r.course_id == course_id]
        rows.sort(key=lambda r: r.created_at)
        return rows, len(rows)

    # --- chapters ---
    def add_chapter(self, row: ChapterRow) -> None:
        self._chapters[row.id] = row

    def get_chapter(self, chapter_id: str) -> ChapterRow | None:
        return self._chapters.get(chapter_id)

    def list_chapters_by_course(
        self, course_id: str, *, page: int = 1, page_size: int = 50
    ) -> tuple[Sequence[ChapterRow], int]:
        rows = [r for r in self._chapters.values() if r.course_id == course_id]
        rows.sort(key=lambda r: r.order)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def next_chapter_order(self, course_id: str) -> int:
        existing = [r.order for r in self._chapters.values() if r.course_id == course_id]
        return max(existing) + 1 if existing else 1

    # --- assignments ---
    def add_assignment(self, row: AssignmentRow) -> None:
        self._assignments[row.id] = row

    def get_assignment(self, assignment_id: str) -> AssignmentRow | None:
        return self._assignments.get(assignment_id)

    def list_assignments_by_course(
        self, course_id: str, *, published_only: bool = False
    ) -> tuple[Sequence[AssignmentRow], int]:
        rows = [r for r in self._assignments.values() if r.course_id == course_id]
        if published_only:
            rows = [r for r in rows if r.published_at is not None]
        rows.sort(key=lambda r: r.created_at)
        return rows, len(rows)

    # --- submissions ---
    def add_submission(self, row: SubmissionRow) -> None:
        self._submissions[row.id] = row

    def get_submission(self, submission_id: str) -> SubmissionRow | None:
        return self._submissions.get(submission_id)

    def get_submission_by_assignment_student(
        self, assignment_id: str, student_id: str
    ) -> SubmissionRow | None:
        for r in self._submissions.values():
            if r.assignment_id == assignment_id and r.student_id == student_id:
                return r
        return None

    def find_submission_by_idempotency(
        self, assignment_id: str, student_id: str, idempotency_key: str
    ) -> SubmissionRow | None:
        for r in self._submissions.values():
            if (
                r.assignment_id == assignment_id
                and r.student_id == student_id
                and r.idempotency_key == idempotency_key
            ):
                return r
        return None

    def list_submissions_by_assignment(
        self,
        assignment_id: str,
        *,
        graded: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[SubmissionRow], int]:
        rows = [r for r in self._submissions.values() if r.assignment_id == assignment_id]
        if graded is True:
            rows = [r for r in rows if r.graded_at is not None]
        elif graded is False:
            rows = [r for r in rows if r.graded_at is None]
        rows.sort(key=lambda r: r.created_at)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def update_submission_grading(
        self,
        submission_id: str,
        *,
        is_correct: bool,
        score: int | None,
        graded_at: str,
        graded_by: str,
    ) -> SubmissionRow | None:
        row = self._submissions.get(submission_id)
        if row is None:
            return None
        row.is_correct = is_correct
        row.score = score
        row.graded_at = graded_at
        row.graded_by = graded_by
        return row

    # --- mistakes ---
    def add_mistake(self, row: MistakeRow) -> None:
        self._mistakes[row.id] = row

    def get_mistake(self, mistake_id: str) -> MistakeRow | None:
        return self._mistakes.get(mistake_id)

    def find_active_mistake(
        self,
        *,
        student_id: str,
        assignment_id: str | None,
        source_turn_id: str | None,
        normalized_stem: str,
    ) -> MistakeRow | None:
        for r in self._mistakes.values():
            if r.student_id != student_id or r.status != "active":
                continue
            if assignment_id is not None:
                if r.assignment_id != assignment_id:
                    continue
            elif source_turn_id is not None:
                if r.source_turn_id != source_turn_id:
                    continue
            else:
                continue
            if normalize_stem(r.question["stem"]) == normalized_stem:
                return r
        return None

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
    ) -> tuple[Sequence[MistakeRow], int]:
        rows = [r for r in self._mistakes.values() if r.student_id == student_id]
        if status != "all":
            rows = [r for r in rows if r.status == status]
        if course_id is not None:
            rows = [r for r in rows if r.course_id == course_id]
        if chapter_id is not None:
            rows = [r for r in rows if r.chapter_id == chapter_id]
        if source is not None:
            rows = [r for r in rows if r.source == source]
        rows.sort(key=lambda r: r.created_at)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def update_mistake(
        self, mistake_id: str, *, note: str | None = None, status: str | None = None
    ) -> MistakeRow | None:
        row = self._mistakes.get(mistake_id)
        if row is None:
            return None
        if note is not None:
            row.note = note
        if status is not None:
            row.status = status
        return row

    # --- study plans + items ---
    def add_plan(self, plan: StudyPlanRow, items: Sequence[PlanItemRow]) -> None:
        plan.items = list(items)
        self._plans[plan.id] = plan
        for item in plan.items:
            self._plan_items[item.id] = item

    def get_plan(self, plan_id: str) -> StudyPlanRow | None:
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        plan.items = [i for i in self._plan_items.values() if i.plan_id == plan_id]
        plan.items.sort(key=lambda i: i.order)
        return plan

    def list_plans_by_student(
        self,
        student_id: str,
        *,
        course_id: str | None = None,
        status: str = "active",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[StudyPlanRow], int]:
        rows = [r for r in self._plans.values() if r.student_id == student_id]
        if status != "all":
            rows = [r for r in rows if r.status == status]
        if course_id is not None:
            rows = [r for r in rows if r.course_id == course_id]
        rows.sort(key=lambda r: r.created_at)
        total = len(rows)
        start = (page - 1) * page_size
        result = []
        for r in rows[start : start + page_size]:
            r.items = [i for i in self._plan_items.values() if i.plan_id == r.id]
            r.items.sort(key=lambda i: i.order)
            result.append(r)
        return result, total

    def update_plan(
        self,
        plan_id: str,
        *,
        title: str | None = None,
        due_at: str | None = None,
        status: str | None = None,
        updated_at: str,
    ) -> StudyPlanRow | None:
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        if title is not None:
            plan.title = title
        if due_at is not None:
            plan.due_at = due_at
        if status is not None:
            plan.status = status
        plan.updated_at = updated_at
        return plan

    def add_plan_item(self, row: PlanItemRow) -> PlanItemRow | None:
        plan = self._plans.get(row.plan_id)
        if plan is None:
            return None
        self._plan_items[row.id] = row
        return row

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
    ) -> PlanItemRow | None:
        item = self._plan_items.get(item_id)
        if item is None or item.plan_id != plan_id:
            return None
        if content is not None:
            item.content = content
        if status is not None:
            item.status = status
        if due_at is not None:
            item.due_at = due_at
        if order is not None:
            item.order = order
        item.updated_at = updated_at
        return item

    def delete_plan_item(self, plan_id: str, item_id: str) -> bool:
        item = self._plan_items.get(item_id)
        if item is None or item.plan_id != plan_id:
            return False
        del self._plan_items[item_id]
        return True

    # --- reminders ---
    def add_reminder(self, row: ReminderRow) -> None:
        self._reminders[row.id] = row

    def get_reminder(self, reminder_id: str) -> ReminderRow | None:
        return self._reminders.get(reminder_id)

    def list_reminders_by_student(
        self,
        student_id: str,
        *,
        is_read: bool | None = None,
        type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[ReminderRow], int]:
        rows = [r for r in self._reminders.values() if r.student_id == student_id]
        if is_read is not None:
            rows = [r for r in rows if r.is_read == is_read]
        if type is not None:
            rows = [r for r in rows if r.type == type]
        rows.sort(key=lambda r: r.due_at)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    def update_reminder(
        self, reminder_id: str, *, is_read: bool, read_at: str | None
    ) -> ReminderRow | None:
        row = self._reminders.get(reminder_id)
        if row is None:
            return None
        row.is_read = is_read
        row.read_at = read_at
        return row

    # --- learning events (append-only, learning-events.md:148) ---
    def append_event(self, row: LearningEventRow) -> None:
        self._events.append(row)

    def list_events(
        self, *, user_id: str | None = None, limit: int = 100
    ) -> Sequence[LearningEventRow]:
        rows = self._events
        if user_id is not None:
            rows = [r for r in rows if r.user_id == user_id]
        return list(rows[-limit:])
