"""Course, class and chapter schemas (packages/contracts/learning/courses.md).

Course/class separation (courses.md:7-8): `Course` describes content, `Class`
describes a teaching section. `classId` is nullable on assignments/submissions
for S1 single-class demos. Selection (joining a class) is out of scope for M5
and belongs to M1 (courses.md:207-216).
"""

from enum import StrEnum

from pydantic import Field

from app.domains.learning.schemas.common import CamelModel, Page, RequestModel


class Subject(StrEnum):
    """Subject values with display names (courses.md:29-43).

    Clients fall back to the raw string for unknown values (courses.md:44);
    the server rejects unknown values at the schema boundary.
    """

    MATH = "math"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    ENGLISH = "english"
    CS = "cs"
    OTHER = "other"


class CourseResponse(CamelModel):
    """Full course object (courses.md:13-27). `teacherId` is the M1 user id."""

    id: str
    title: str
    description: str | None = None
    subject: Subject
    cover_image_url: str | None = None
    teacher_id: str
    teacher_name: str | None = None
    student_count: int | None = None
    chapter_count: int | None = None
    created_at: str
    updated_at: str


class ClassResponse(CamelModel):
    """Teaching section (courses.md:46-60). `classes` rows are M5-owned,
    access relations are M1-owned (courses.md:59)."""

    id: str
    course_id: str
    title: str
    teacher_id: str
    semester: str | None = None
    student_count: int | None = None
    created_at: str
    updated_at: str


class ChapterResponse(CamelModel):
    """Chapter (courses.md:62-75). `order` is 1-based, unique per course."""

    id: str
    course_id: str
    title: str
    order: int = Field(ge=1)
    description: str | None = None
    document_id: str | None = None
    created_at: str
    updated_at: str


class CourseCreateRequest(RequestModel):
    """Create a course (courses.md:163-178). `teacherId` comes from the
    session, not the request body."""

    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    subject: Subject
    cover_image_url: str | None = None


class ClassCreateRequest(RequestModel):
    """Create a teaching section (courses.md:180-191). `teacherId` is
    session-derived."""

    title: str = Field(min_length=1, max_length=100)
    semester: str | None = None


class ChapterCreateRequest(RequestModel):
    """Add a chapter (courses.md:193-205).

    `order` is server-continued (max + 1); including it yields 422
    VALIDATION_ERROR via `extra="forbid"` (courses.md:195-197).
    """

    title: str = Field(min_length=1, max_length=100)
    description: str | None = None


CourseListResponse = Page[CourseResponse]
ClassListResponse = Page[ClassResponse]
ChapterListResponse = Page[ChapterResponse]
