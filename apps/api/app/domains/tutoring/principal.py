"""Who is making the request -- **Mock, and only a Mock.**

The real identity, role and course-access layer is M1's, tracked as #16. Nothing
here replaces it; this is the seam it will be plugged into, so the tutoring
endpoints can be written against a principal today and adopted unchanged
tomorrow. **No behaviour in this file may be relied on for security.**

The one property that is not negotiable, and the reason this is a dependency that
reads nothing from the request rather than a header someone can set: a development
bypass that an *external request can activate* is forbidden outright
(`packages/contracts/platform/README.md:38`). So there is no `X-User-Id`, no
`X-Debug-Principal`, and no config flag that turns one request into somebody else.
Every request is the same synthetic student. The only way to change that is to
replace this provider, which is what #16 will do by binding the real one over it.

There is no FastAPI import here on purpose. The decision is a plain function over
two values, and the router is left to shape the refusal, so the access rule can be
tested without a client and there is exactly one place that decides what a refusal
looks like on the wire.
"""

from dataclasses import dataclass
from typing import Final

__all__ = ["SYNTHETIC_PRINCIPAL", "Principal", "can_reach_course", "get_principal"]


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated caller. **Synthetic in S1.**

    `course_ids` empty would mean "no course scoping at all"; the synthetic
    principal instead names the one course the contracts use in their samples, so
    that the narrowing path is exercised rather than bypassed.
    """

    user_id: str
    roles: tuple[str, ...]
    course_ids: frozenset[str] = frozenset()


#: The single identity S1 serves every request as. The id is deliberately not a
#: plausible real one, and `roles` is empty rather than `("student",)`: inventing
#: a role would suggest an authorisation decision is being made here.
SYNTHETIC_PRINCIPAL: Final[Principal] = Principal(
    user_id="user_synthetic_mock",
    roles=(),
    course_ids=frozenset({"course_b3f1c2d4"}),
)


def get_principal() -> Principal:
    """The S1 stand-in for M1's authentication dependency. **Mock.**

    Takes no parameters, so there is nothing a caller could pass it: no header,
    cookie, token or query parameter can influence the result. Declared as a
    dependency rather than called directly so that swapping in the real provider
    is a one-line change where the router asks for it.
    """

    return SYNTHETIC_PRINCIPAL


def can_reach_course(principal: Principal, course_id: str) -> bool:
    """Whether the principal may narrow a request to this course.

    `courseId` only ever narrows; it can never widen. Without this, a student could
    name any course and have retrieval run against material they were never given.
    """

    return course_id in principal.course_ids
