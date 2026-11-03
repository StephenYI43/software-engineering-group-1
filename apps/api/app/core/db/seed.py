"""Explicit, idempotent synthetic development seed. Never runs on app startup."""

import argparse
import os

from sqlalchemy import select

from app.core.auth.accounts import DEFAULT_SYNTHETIC_ACCOUNTS
from app.core.db.models import Role, SystemConfigVersion, User, UserProfile, UserRole
from app.core.db.passwords import hash_password
from app.core.db.repository import PlatformRepository, new_id
from app.core.db.session import Database, load_database_url
from app.core.request_id import create_request_id

_ADMIN = {
    "username": "admin1",
    "password": "demo-admin-1",
    "userId": "user_44444444444444444444444444444444",
    "role": "admin",
    "name": "合成管理员",
}


def seed(database: Database) -> None:
    """No overwrites: reruns preserve IDs, passwords, roles and audit history."""
    with database.sessions.begin() as session:
        # Serialize concurrent seed runs within this database.
        from sqlalchemy import text

        session.execute(text("SELECT pg_advisory_xact_lock(480069)"))
        for code, name in (("student", "学生"), ("teacher", "教师"), ("admin", "管理员")):
            if session.get(Role, code) is None:
                session.add(Role(code=code, name=name))
        session.flush()
        for account in (*DEFAULT_SYNTHETIC_ACCOUNTS, _ADMIN):
            if session.get(User, account["userId"]) is not None:
                continue
            session.add(
                User(
                    id=account["userId"],
                    username=account["username"],
                    username_key=account["username"].lower(),
                    password_hash=hash_password(account["password"]),
                )
            )
            session.flush()
            session.add(
                UserProfile(
                    user_id=account["userId"],
                    display_name=account["name"],
                    student_number=(
                        f"DEMO-{account['username']}" if account["role"] == "student" else None
                    ),
                )
            )
            session.add(
                UserRole(
                    user_id=account["userId"],
                    role_code=account["role"],
                    is_primary=True,
                )
            )
            PlatformRepository(session).audit(
                actor_user_id=None,
                action="synthetic_user_created",
                target_type="users",
                target_id=account["userId"],
                request_id=create_request_id(),
            )
        for key, value in (
            (
                "upload_limits",
                {
                    "schemaVersion": "1.0",
                    "maxUploadBytes": 10485760,
                    "allowedMimeTypes": ["application/pdf"],
                },
            ),
            ("session_policy", {"schemaVersion": "1.0", "sessionTtlSeconds": 86400}),
        ):
            if (
                session.scalar(
                    select(SystemConfigVersion.id).where(SystemConfigVersion.config_key == key)
                )
                is None
            ):
                session.add(
                    SystemConfigVersion(
                        id=new_id("syscfg"),
                        config_key=key,
                        version=1,
                        value=value,
                    )
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-development", action="store_true", required=True)
    parser.parse_args()
    if os.getenv("APP_ENV", "development") != "development":
        raise SystemExit("Synthetic seed is restricted to APP_ENV=development")
    url = load_database_url()
    if url is None:
        raise SystemExit("DATABASE_URL is required")
    database = Database(url)
    try:
        seed(database)
    finally:
        database.close()
    print("Synthetic development seed completed (idempotent; no credentials logged).")


if __name__ == "__main__":
    main()
