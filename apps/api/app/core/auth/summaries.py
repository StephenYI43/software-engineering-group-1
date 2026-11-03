"""Minimal student projections for callers with an authorized roster."""

from collections.abc import Iterable, Set

from pydantic import BaseModel, Field

from app.core.auth.accounts import Account


class StudentSummary(BaseModel):
    student_id: str = Field(serialization_alias="studentId")
    name: str
    student_number: str | None = Field(serialization_alias="studentNumber")


def resolve_user_summaries(
    user_ids: Iterable[str], *, authorized_ids: Set[str], accounts: Iterable[Account]
) -> list[StudentSummary]:
    """Resolve demo profiles only inside a server-authorized roster."""
    requested = authorized_ids & set(user_ids)
    return [
        StudentSummary(
            student_id=account.session_user.user_id,
            name=account.session_user.name,
            student_number=account.student_number,
        )
        for account in accounts
        if account.session_user.user_id in requested and account.session_user.role == "student"
    ]
