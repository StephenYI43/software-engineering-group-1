"""Shared schema primitives for the learning domain.

Camel-case aliasing follows docs/code-standards.md:55 (snake_case Python in,
camelCase JSON out). Pagination shape follows docs/code-standards.md:71
(`items` / `total` / `page` / `pageSize`).
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: snake_case Python attributes, camelCase JSON aliases."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class RequestModel(CamelModel):
    """Request bodies reject unknown fields.

    Forbidden inputs (`isCorrect` on a submission, `gradedBy` on a grading
    patch, `order` on a chapter create, `items` on a `source=tutoring` plan)
    surface as 422 VALIDATION_ERROR at the schema boundary, matching
    packages/contracts/learning/samples/errors.md.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class PageParams(CamelModel):
    """Pagination query parameters (docs/code-standards.md:71)."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class Page[T](CamelModel):
    """Paginated list response: items/total/page/pageSize.

    `items` may be empty but is never null (courses.md:117).
    """

    items: Sequence[T]
    total: int
    page: int
    page_size: int
