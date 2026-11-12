"""Schema-layer tests for the learning domain.

Mock 鉴权，待 #16: `student_id` / `teacher_id` are fixed test strings injected
directly into models. No session resolution is exercised here; once #16 lands
the service layer will populate these from the authenticated session before
constructing responses.
"""

import pytest
from pydantic import ValidationError

from app.domains.learning.schemas import (
    AssignmentStudentView,
    ChapterCreateRequest,
    CourseResponse,
    ErrorCode,
    EventType,
    GradingPatchRequest,
    MistakeSource,
    Page,
    StudyPlanCreateRequest,
    SubmissionCreateRequest,
    SubmissionStatusResponse,
)
from app.domains.learning.schemas.courses import Subject
from app.domains.learning.schemas.homework import QuestionType
from app.domains.learning.schemas.mistakes import MistakeQuestionType


def _course(**overrides: object) -> CourseResponse:
    base = {
        "id": "course_1",
        "title": "高等数学（上）",
        "description": None,
        "subject": Subject.MATH,
        "cover_image_url": None,
        "teacher_id": "user_teacher_1",
        "teacher_name": None,
        "student_count": None,
        "chapter_count": None,
        "created_at": "2026-09-10T08:00:00Z",
        "updated_at": "2026-09-10T08:00:00Z",
    }
    base.update(overrides)
    return CourseResponse(**base)  # type: ignore[arg-type]


def test_course_response_serializes_camel_case() -> None:
    dumped = _course().model_dump(by_alias=True)
    assert set(dumped) == {
        "id",
        "title",
        "description",
        "subject",
        "coverImageUrl",
        "teacherId",
        "teacherName",
        "studentCount",
        "chapterCount",
        "createdAt",
        "updatedAt",
    }
    assert dumped["teacherId"] == "user_teacher_1"
    assert dumped["subject"] == "math"


def test_request_model_forbids_server_derived_fields() -> None:
    # isCorrect/score/gradedAt/gradedBy are server-derived (homework.md invariant 8)
    with pytest.raises(ValidationError):
        SubmissionCreateRequest(answer={"options": ["A"]}, idempotencyKey="idem_1", isCorrect=True)


def test_grading_patch_forbids_graded_by() -> None:
    # gradedBy is server-derived from the session role (homework.md:254-272)
    with pytest.raises(ValidationError):
        GradingPatchRequest(isCorrect=True, score=10, gradedBy="teacher")


def test_chapter_create_forbids_order() -> None:
    # order is server-continued (courses.md:195-197)
    with pytest.raises(ValidationError):
        ChapterCreateRequest(title="第一章", order=1)


def test_assignment_student_view_has_no_answer_key() -> None:
    # answerKey must be absent (not null) on the student view (homework.md:55-57)
    view = AssignmentStudentView(
        id="assignment_1",
        course_id="course_1",
        class_id=None,
        chapter_id=None,
        title="习题 1",
        description=None,
        question_type=QuestionType.SINGLE_CHOICE,
        max_score=10,
        due_at=None,
        published_at="2026-09-10T08:00:00Z",
        teacher_id="user_teacher_1",
        created_at="2026-09-10T08:00:00Z",
        updated_at="2026-09-10T08:00:00Z",
    )
    assert "answer_key" not in AssignmentStudentView.model_fields
    assert "answerKey" not in view.model_dump(by_alias=True)


def test_submission_status_response_allows_null() -> None:
    # GET /submissions/me returns {"submission": null} when not submitted
    # (homework.md:200-206)
    body = SubmissionStatusResponse(submission=None)
    assert body.model_dump(by_alias=True)["submission"] is None


def test_study_plan_tutoring_request_omits_items() -> None:
    # source=tutoring carries only sourceTurnId (study-plans.md:139-148)
    req = StudyPlanCreateRequest(source="tutoring", source_turn_id="turn_1")
    assert req.items is None
    assert req.source_turn_id == "turn_1"


def test_mistake_source_is_closed_set_of_two() -> None:
    assert {m.value for m in MistakeSource} == {"wrong_submission", "manual"}


def test_event_type_omits_chapter_viewed() -> None:
    # chapter_viewed is owned by M2, not M5 (learning-events.md:58-61)
    assert "chapter_viewed" not in {e.value for e in EventType}


def test_error_code_contract_values() -> None:
    assert ErrorCode.COURSE_NOT_FOUND.value == "COURSE_NOT_FOUND"
    assert ErrorCode.MISTAKE_DUPLICATE.value == "MISTAKE_DUPLICATE"
    assert ErrorCode.TUTORING_TURN_NOT_FOUND.value == "TUTORING_TURN_NOT_FOUND"
    assert ErrorCode.PLAN_ITEMS_LIMIT_EXCEEDED.value == "PLAN_ITEMS_LIMIT_EXCEEDED"


def test_mistake_question_type_includes_tutoring_question() -> None:
    assert "tutoring_question" in {q.value for q in MistakeQuestionType}


def test_populate_by_name_accepts_snake_case() -> None:
    # CamelModel accepts both alias and snake_case name (populate_by_name=True)
    req = SubmissionCreateRequest(answer={"options": ["A"]}, idempotency_key="idem_2")
    assert req.idempotency_key == "idem_2"


def test_page_generic_holds_typed_items() -> None:
    page: Page[CourseResponse] = Page(items=[_course()], total=1, page=1, page_size=20)
    dumped = page.model_dump(by_alias=True)
    assert dumped["pageSize"] == 20
    assert dumped["items"][0]["teacherId"] == "user_teacher_1"
