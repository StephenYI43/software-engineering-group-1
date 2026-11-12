"""In-memory repository tests for the learning domain.

Mock 鉴权，待 #16: `student_id` / `teacher_id` are fixed test strings passed
directly into rows. The repository has no notion of a session; the service
layer will inject the authenticated user once #16 lands.

These tests cover the data-access invariants the contract relies on:
idempotency key lookup (homework.md:128-162), mistake dedup keys
(mistakes.md:150-160), graded=true|false filtering (homework.md:210-221) and
append-only events (learning-events.md:148).
"""

from collections.abc import Sequence
from typing import Any

from app.domains.learning.repository import (
    AssignmentRow,
    ChapterRow,
    ClassRow,
    CourseRow,
    InMemoryLearningRepository,
    LearningEventRow,
    MistakeRow,
    PlanItemRow,
    ReminderRow,
    StudyPlanRow,
    SubmissionRow,
    new_id,
    normalize_stem,
    now,
)

STUDENT = "user_student_1"
TEACHER = "user_teacher_1"
COURSE = "course_b3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6"


# --- helpers ---------------------------------------------------------------


def _course(teacher: str = TEACHER, **overrides: Any) -> CourseRow:
    base: dict[str, Any] = {
        "id": new_id("course_"),
        "title": "高等数学（上）",
        "description": None,
        "subject": "math",
        "cover_image_url": None,
        "teacher_id": teacher,
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return CourseRow(**base)


def _chapter(course_id: str, order: int, **overrides: Any) -> ChapterRow:
    base: dict[str, Any] = {
        "id": new_id("chapter_"),
        "course_id": course_id,
        "title": f"第{order}章",
        "order": order,
        "description": None,
        "document_id": None,
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return ChapterRow(**base)


def _assignment(course_id: str, **overrides: Any) -> AssignmentRow:
    base: dict[str, Any] = {
        "id": new_id("assignment_"),
        "course_id": course_id,
        "class_id": None,
        "chapter_id": None,
        "title": "习题 1",
        "description": None,
        "question_type": "single_choice",
        "answer_key": {"options": ["A"]},
        "max_score": 10,
        "due_at": None,
        "published_at": now(),
        "teacher_id": TEACHER,
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return AssignmentRow(**base)


def _submission(assignment_id: str, student: str = STUDENT, **overrides: Any) -> SubmissionRow:
    base: dict[str, Any] = {
        "id": new_id("submission_"),
        "assignment_id": assignment_id,
        "class_id": None,
        "student_id": student,
        "answer": {"options": ["A"]},
        "is_correct": None,
        "score": None,
        "graded_at": None,
        "graded_by": "auto",
        "idempotency_key": new_id("idem_"),
        "submitted_at": now(),
        "created_at": now(),
    }
    base.update(overrides)
    return SubmissionRow(**base)


def _mistake(student: str = STUDENT, **overrides: Any) -> MistakeRow:
    base: dict[str, Any] = {
        "id": new_id("mistake_"),
        "student_id": student,
        "course_id": COURSE,
        "chapter_id": None,
        "assignment_id": "assignment_1",
        "submission_id": None,
        "source_turn_id": None,
        "source": "manual",
        "question": {"stem": "求极限", "questionType": "short_answer", "options": None},
        "student_answer": None,
        "note": None,
        "status": "active",
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return MistakeRow(**base)


def _plan(student: str = STUDENT, **overrides: Any) -> StudyPlanRow:
    base: dict[str, Any] = {
        "id": new_id("plan_"),
        "student_id": student,
        "title": "复习计划",
        "course_id": COURSE,
        "chapter_id": None,
        "source": "manual",
        "source_turn_id": None,
        "status": "active",
        "due_at": None,
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return StudyPlanRow(**base)


def _item(plan_id: str, order: int, **overrides: Any) -> PlanItemRow:
    base: dict[str, Any] = {
        "id": new_id("plan_item_"),
        "plan_id": plan_id,
        "content": f"项 {order}",
        "order": order,
        "status": "pending",
        "due_at": None,
        "chapter_id": None,
        "knowledge_point": None,
        "related_mistake_id": None,
        "related_assignment_id": None,
        "created_at": now(),
        "updated_at": now(),
    }
    base.update(overrides)
    return PlanItemRow(**base)


# --- courses / classes / chapters ------------------------------------------


def test_course_add_get_list() -> None:
    repo = InMemoryLearningRepository()
    c1 = _course(title="高数上", subject="math")
    c2 = _course(title="大学物理", subject="physics")
    repo.add_course(c1)
    repo.add_course(c2)

    assert repo.get_course(c1.id) is c1
    assert repo.get_course("missing") is None

    all_rows, total = repo.list_courses()
    assert total == 2
    assert {r.id for r in all_rows} == {c1.id, c2.id}

    math_rows, math_total = repo.list_courses(subject="math")
    assert math_total == 1
    assert math_rows[0].id == c1.id

    q_rows, q_total = repo.list_courses(q="物理")
    assert q_total == 1
    assert q_rows[0].id == c2.id

    page_rows, _ = repo.list_courses(page=1, page_size=1)
    assert len(page_rows) == 1


def test_class_list_by_course() -> None:
    repo = InMemoryLearningRepository()
    cls = ClassRow(
        id=new_id("class_"),
        course_id=COURSE,
        title="高数 A 班",
        teacher_id=TEACHER,
        semester="2026-fall",
        created_at=now(),
        updated_at=now(),
    )
    repo.add_class(cls)
    rows, total = repo.list_classes_by_course(COURSE)
    assert total == 1
    assert rows[0].id == cls.id
    assert repo.get_class(cls.id) is cls


def test_chapter_order_continues_from_max() -> None:
    repo = InMemoryLearningRepository()
    assert repo.next_chapter_order(COURSE) == 1
    repo.add_chapter(_chapter(COURSE, 1))
    repo.add_chapter(_chapter(COURSE, 3))
    assert repo.next_chapter_order(COURSE) == 4


def test_chapter_list_paginates_and_sorts_by_order() -> None:
    repo = InMemoryLearningRepository()
    for i in range(1, 61):
        repo.add_chapter(_chapter(COURSE, i))
    page1, total = repo.list_chapters_by_course(COURSE, page=1, page_size=50)
    assert total == 60
    assert len(page1) == 50
    assert page1[0].order == 1
    assert page1[-1].order == 50
    page2, _ = repo.list_chapters_by_course(COURSE, page=2, page_size=50)
    assert len(page2) == 10
    assert page2[0].order == 51


# --- assignments / submissions --------------------------------------------


def test_assignment_published_filter() -> None:
    repo = InMemoryLearningRepository()
    pub = _assignment(COURSE, published_at=now())
    draft = _assignment(COURSE, published_at=None)
    repo.add_assignment(pub)
    repo.add_assignment(draft)
    all_rows, all_total = repo.list_assignments_by_course(COURSE)
    assert all_total == 2
    pub_rows, pub_total = repo.list_assignments_by_course(COURSE, published_only=True)
    assert pub_total == 1
    assert pub_rows[0].id == pub.id


def test_submission_idempotency_and_assignment_student_lookup() -> None:
    repo = InMemoryLearningRepository()
    a = _assignment(COURSE)
    repo.add_assignment(a)
    sub = _submission(a.id, idempotency_key="idem_x")
    repo.add_submission(sub)

    found = repo.find_submission_by_idempotency(a.id, STUDENT, "idem_x")
    assert found is sub
    assert repo.find_submission_by_idempotency(a.id, STUDENT, "other") is None

    by_student = repo.get_submission_by_assignment_student(a.id, STUDENT)
    assert by_student is sub
    assert repo.get_submission_by_assignment_student(a.id, "user_other") is None


def test_submission_list_graded_filter_and_pagination() -> None:
    repo = InMemoryLearningRepository()
    a = _assignment(COURSE)
    repo.add_assignment(a)
    s1 = _submission(a.id, graded_at=None)
    s2 = _submission(a.id, graded_at=now(), is_correct=False, score=4)
    s3 = _submission(a.id, graded_at=now(), is_correct=True, score=10)
    repo.add_submission(s1)
    repo.add_submission(s2)
    repo.add_submission(s3)

    all_rows, all_total = repo.list_submissions_by_assignment(a.id)
    assert all_total == 3

    ungraded, ungraded_total = repo.list_submissions_by_assignment(a.id, graded=False)
    assert ungraded_total == 1
    assert ungraded[0].id == s1.id

    graded, graded_total = repo.list_submissions_by_assignment(a.id, graded=True)
    assert graded_total == 2
    assert {r.id for r in graded} == {s2.id, s3.id}

    page, _ = repo.list_submissions_by_assignment(a.id, page=1, page_size=2)
    assert len(page) == 2


def test_submission_update_grading() -> None:
    repo = InMemoryLearningRepository()
    a = _assignment(COURSE)
    repo.add_assignment(a)
    sub = _submission(a.id)
    repo.add_submission(sub)
    ts = now()
    updated = repo.update_submission_grading(
        sub.id, is_correct=False, score=5, graded_at=ts, graded_by="teacher"
    )
    assert updated is not None
    assert updated.is_correct is False
    assert updated.score == 5
    assert updated.graded_by == "teacher"
    assert (
        repo.update_submission_grading(
            "missing", is_correct=True, score=1, graded_at=ts, graded_by="auto"
        )
        is None
    )


# --- mistakes --------------------------------------------------------------


def test_mistake_dedup_assignment_scoped() -> None:
    repo = InMemoryLearningRepository()
    a = _assignment(COURSE)
    repo.add_assignment(a)
    m = _mistake(
        assignment_id=a.id, question={"stem": "  求极限  lim ", "questionType": "short_answer"}
    )
    repo.add_mistake(m)

    stem_key = normalize_stem("求极限 lim")
    found = repo.find_active_mistake(
        student_id=STUDENT,
        assignment_id=a.id,
        source_turn_id=None,
        normalized_stem=stem_key,
    )
    assert found is m
    # different stem -> no match
    assert (
        repo.find_active_mistake(
            student_id=STUDENT,
            assignment_id=a.id,
            source_turn_id=None,
            normalized_stem="另一题",
        )
        is None
    )
    # other student -> no match
    assert (
        repo.find_active_mistake(
            student_id="user_other",
            assignment_id=a.id,
            source_turn_id=None,
            normalized_stem=stem_key,
        )
        is None
    )


def test_mistake_dedup_tutoring_scoped() -> None:
    repo = InMemoryLearningRepository()
    m = _mistake(
        assignment_id=None,
        source_turn_id="turn_1",
        question={"stem": "ε-δ 定义", "questionType": "tutoring_question"},
    )
    repo.add_mistake(m)
    found = repo.find_active_mistake(
        student_id=STUDENT,
        assignment_id=None,
        source_turn_id="turn_1",
        normalized_stem=normalize_stem("ε-δ 定义"),
    )
    assert found is m


def test_mistake_list_filters_and_status_all() -> None:
    repo = InMemoryLearningRepository()
    repo.add_mistake(_mistake(status="active", source="manual"))
    repo.add_mistake(_mistake(status="resolved", source="wrong_submission"))
    repo.add_mistake(_mistake(status="active", source="wrong_submission"))

    active, active_total = repo.list_mistakes_by_student(STUDENT)
    assert active_total == 2

    all_rows, all_total = repo.list_mistakes_by_student(STUDENT, status="all")
    assert all_total == 3

    wrong, wrong_total = repo.list_mistakes_by_student(STUDENT, source="wrong_submission")
    assert wrong_total == 1

    other, _ = repo.list_mistakes_by_student("user_other")
    assert len(other) == 0


def test_mistake_update_note_and_status() -> None:
    repo = InMemoryLearningRepository()
    m = _mistake()
    repo.add_mistake(m)
    updated = repo.update_mistake(m.id, note="已复习", status="resolved")
    assert updated is not None
    assert updated.note == "已复习"
    assert updated.status == "resolved"
    assert repo.update_mistake("missing", note="x") is None


# --- study plans + items ---------------------------------------------------


def test_plan_add_with_items_and_get_assembles_items() -> None:
    repo = InMemoryLearningRepository()
    plan = _plan()
    items = [_item(plan.id, 2), _item(plan.id, 1)]
    repo.add_plan(plan, items)

    got = repo.get_plan(plan.id)
    assert got is not None
    assert [i.order for i in got.items] == [1, 2]
    assert repo.get_plan("missing") is None


def test_plan_list_by_student_filters_and_paginates() -> None:
    repo = InMemoryLearningRepository()
    p1 = _plan(status="active", course_id=COURSE)
    p2 = _plan(status="archived", course_id=COURSE)
    p3 = _plan(status="active", course_id="course_other")
    for p in (p1, p2, p3):
        repo.add_plan(p, [])
    active, active_total = repo.list_plans_by_student(STUDENT)
    assert active_total == 2
    course_rows, course_total = repo.list_plans_by_student(STUDENT, course_id=COURSE)
    assert course_total == 1
    assert course_rows[0].id == p1.id
    page, _ = repo.list_plans_by_student(STUDENT, page=1, page_size=1)
    assert len(page) == 1


def test_plan_update_fields() -> None:
    repo = InMemoryLearningRepository()
    plan = _plan()
    repo.add_plan(plan, [])
    ts = now()
    updated = repo.update_plan(plan.id, title="新标题", status="completed", updated_at=ts)
    assert updated is not None
    assert updated.title == "新标题"
    assert updated.status == "completed"
    assert updated.updated_at == ts
    assert repo.update_plan("missing", updated_at=ts) is None


def test_plan_item_crud() -> None:
    repo = InMemoryLearningRepository()
    plan = _plan()
    repo.add_plan(plan, [])
    item = _item(plan.id, 1)
    added = repo.add_plan_item(item)
    assert added is item
    # add_plan_item to unknown plan returns None
    assert repo.add_plan_item(_item("plan_missing", 1)) is None

    ts = now()
    patched = repo.update_plan_item(plan.id, item.id, content="改", status="done", updated_at=ts)
    assert patched is not None
    assert patched.content == "改"
    assert patched.status == "done"
    # mismatched plan_id -> None
    assert repo.update_plan_item("plan_other", item.id, updated_at=ts) is None

    assert repo.delete_plan_item(plan.id, item.id) is True
    assert repo.delete_plan_item(plan.id, item.id) is False
    assert repo.get_plan(plan.id) is not None


# --- reminders -------------------------------------------------------------


def test_reminder_crud_and_filters() -> None:
    repo = InMemoryLearningRepository()
    r1 = ReminderRow(
        id=new_id("reminder_"),
        student_id=STUDENT,
        plan_id=None,
        assignment_id="assignment_1",
        type="assignment_due",
        title="作业截止",
        body=None,
        due_at="2026-09-22T23:59:00Z",
        is_read=False,
        created_at=now(),
        read_at=None,
    )
    r2 = ReminderRow(
        id=new_id("reminder_"),
        student_id=STUDENT,
        plan_id="plan_1",
        assignment_id=None,
        type="plan_due",
        title="计划截止",
        body=None,
        due_at="2026-09-20T23:59:00Z",
        is_read=True,
        created_at=now(),
        read_at="2026-09-19T08:00:00Z",
    )
    repo.add_reminder(r1)
    repo.add_reminder(r2)

    assert repo.get_reminder(r1.id) is r1
    all_rows, total = repo.list_reminders_by_student(STUDENT)
    assert total == 2
    # sorted by due_at ascending -> r2 (09-20) before r1 (09-22)
    assert all_rows[0].id == r2.id

    unread, unread_total = repo.list_reminders_by_student(STUDENT, is_read=False)
    assert unread_total == 1
    assert unread[0].id == r1.id

    typed, typed_total = repo.list_reminders_by_student(STUDENT, type="plan_due")
    assert typed_total == 1

    updated = repo.update_reminder(r1.id, is_read=True, read_at="2026-09-19T10:00:00Z")
    assert updated is not None
    assert updated.is_read is True
    assert updated.read_at == "2026-09-19T10:00:00Z"
    assert repo.update_reminder("missing", is_read=True, read_at=None) is None


# --- learning events --------------------------------------------------------


def test_event_append_only_and_list_filters() -> None:
    repo = InMemoryLearningRepository()
    e1 = LearningEventRow(
        event_id=new_id("event_"),
        event_type="assignment_submitted",
        user_id=STUDENT,
        course_id=COURSE,
        occurred_at=now(),
        trace_id="req_1",
        schema_version="1.0",
        payload={"submissionId": "submission_1"},
    )
    e2 = LearningEventRow(
        event_id=new_id("event_"),
        event_type="mistake_recorded",
        user_id="user_other",
        course_id=None,
        occurred_at=now(),
        trace_id="req_2",
        schema_version="1.0",
        payload={"mistakeId": "mistake_1"},
    )
    repo.append_event(e1)
    repo.append_event(e2)

    all_events: Sequence[LearningEventRow] = repo.list_events()
    assert len(all_events) == 2
    mine = repo.list_events(user_id=STUDENT)
    assert len(mine) == 1
    assert mine[0].event_type == "assignment_submitted"
    limited = repo.list_events(limit=1)
    assert len(limited) == 1


# --- id / time / stem helpers ----------------------------------------------


def test_new_id_prefix_and_hex_length() -> None:
    cid = new_id("course_")
    assert cid.startswith("course_")
    assert len(cid.removeprefix("course_")) == 32
    assert cid.removeprefix("course_").islower()
    assert new_id("plan_") != new_id("plan_")


def test_now_is_iso_zulu() -> None:
    ts = now()
    assert ts.endswith("Z")
    assert "T" in ts


def test_normalize_stem_collapses_whitespace() -> None:
    assert normalize_stem("  求   极限  ") == "求 极限"
    assert normalize_stem("\t求极限\n") == "求极限"
