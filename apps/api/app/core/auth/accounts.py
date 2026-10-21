"""Synthetic account store for S1 (Issue #45).

Accounts come from the `AUTH_SYNTHETIC_ACCOUNTS` environment variable (a JSON
array) and default to three documented demo identities so a fresh clone can log
in with zero configuration. The repository is public: these are synthetic demo
identities, never real student data (`docs/code-standards.md:103`).

Entry shape: `{"username", "password", "userId", "role", "name"}`. `role` must
be one of student / teacher / admin. Credential comparison is constant-time so
the username/password split does not leak timing.
"""

import hmac
import json
from dataclasses import dataclass
from typing import Any

from app.core.auth.schemas import SessionUser

DEFAULT_SYNTHETIC_ACCOUNTS: tuple[dict[str, str], ...] = (
    {
        "username": "student1",
        "password": "demo-student-1",
        "userId": "user_11111111111111111111111111111111",
        "role": "student",
        "name": "学生甲",
    },
    {
        "username": "student2",
        "password": "demo-student-2",
        "userId": "user_22222222222222222222222222222222",
        "role": "student",
        "name": "学生乙",
    },
    {
        "username": "teacher1",
        "password": "demo-teacher-1",
        "userId": "user_33333333333333333333333333333333",
        "role": "teacher",
        "name": "王老师",
    },
)

_DEFAULT_ACCOUNTS_JSON = json.dumps(DEFAULT_SYNTHETIC_ACCOUNTS, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class Account:
    """One synthetic identity with its demo credential."""

    username: str
    password: str
    session_user: SessionUser


def load_accounts(raw_json: str) -> tuple[Account, ...]:
    """Parse the accounts variable; empty input selects the documented default.

    Raises `ValueError` on any malformed entry so misconfiguration fails loud
    at startup instead of surfacing as a mysterious 401 later.
    """
    raw = raw_json if raw_json != "" else _DEFAULT_ACCOUNTS_JSON
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("AUTH_SYNTHETIC_ACCOUNTS is not valid JSON") from None
    if not isinstance(entries, list):
        raise ValueError("AUTH_SYNTHETIC_ACCOUNTS must be a JSON array")
    return tuple(_parse_entry(entry, index) for index, entry in enumerate(entries))


def _parse_entry(entry: Any, index: int) -> Account:
    if not isinstance(entry, dict):
        raise ValueError(f"AUTH_SYNTHETIC_ACCOUNTS[{index}] must be an object")
    missing = {"username", "password", "userId", "role", "name"} - entry.keys()
    if missing:
        raise ValueError(f"AUTH_SYNTHETIC_ACCOUNTS[{index}] missing fields: {sorted(missing)}")
    username = entry["username"]
    password = entry["password"]
    user_id = entry["userId"]
    role = entry["role"]
    name = entry["name"]
    if not all(isinstance(value, str) and value for value in (username, password, user_id, name)):
        raise ValueError(f"AUTH_SYNTHETIC_ACCOUNTS[{index}] fields must be non-empty strings")
    if role not in ("student", "teacher", "admin"):
        raise ValueError(f"AUTH_SYNTHETIC_ACCOUNTS[{index}] has unknown role {role!r}")
    return Account(
        username=username,
        password=password,
        session_user=SessionUser(user_id=user_id, role=role, name=name),
    )


def verify_credentials(
    accounts: tuple[Account, ...], username: str, password: str
) -> SessionUser | None:
    """Match username/password with constant-time comparison on both fields."""
    for account in accounts:
        if hmac.compare_digest(account.username, username) and hmac.compare_digest(
            account.password, password
        ):
            return account.session_user
    return None
