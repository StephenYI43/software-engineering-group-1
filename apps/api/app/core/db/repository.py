"""Platform data access only: no commits and no public role-grant endpoints."""

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.auth.schemas import SessionUser
from app.core.db.models import AdminAuditLog, AuthSession, User, UserProfile, UserRole
from app.core.db.passwords import hash_password, verify_password

_DUMMY_HASH = hash_password("synthetic-timing-placeholder")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class PlatformRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def authenticate(self, username: str, password: str) -> SessionUser | None:
        normalized = username.strip().lower()
        row = self.session.execute(
            select(User, UserProfile, UserRole)
            .join(UserProfile, UserProfile.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                User.username_key == normalized,
                User.status == "active",
                UserRole.is_primary.is_(True),
                UserRole.revoked_at.is_(None),
            )
        ).one_or_none()
        # Both unknown-user and wrong-password paths run one expensive KDF.
        stored = row[0].password_hash if row is not None else _DUMMY_HASH
        valid = verify_password(password, stored)
        if row is None or not valid:
            return None
        user, profile, role = row
        return SessionUser(user_id=user.id, role=role.role_code, name=profile.display_name)

    def audit(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        target_type: str,
        target_id: str | None,
        request_id: str,
        result: str = "succeeded",
        details: dict[str, Any] | None = None,
    ) -> None:
        summary = details or {}
        allowed = {"schemaVersion", "changedFields", "reasonCode"}
        if set(summary) - allowed or (summary and summary.get("schemaVersion") != "1.0"):
            raise ValueError("Audit details must use the versioned summary whitelist")
        if "changedFields" in summary and (
            not isinstance(summary["changedFields"], list)
            or len(summary["changedFields"]) > 50
            or any(not isinstance(v, str) or len(v) > 100 for v in summary["changedFields"])
        ):
            raise ValueError("Invalid changedFields")
        if "reasonCode" in summary and (
            not isinstance(summary["reasonCode"], str) or len(summary["reasonCode"]) > 64
        ):
            raise ValueError("Invalid reasonCode")
        self.session.add(
            AdminAuditLog(
                id=new_id("audit"),
                actor_user_id=actor_user_id,
                actor_type="user" if actor_user_id else "system",
                action=action,
                target_type=target_type,
                target_id=target_id,
                result=result,
                request_id=request_id,
                details=summary,
            )
        )
        self.session.flush()


class DatabaseSessionStore:
    """Used by SessionAuthority inside a caller-owned Session/transaction."""

    def __init__(self, session: Session, request_id: str) -> None:
        self.session = session
        self.request_id = request_id

    @staticmethod
    def _digest(jti: str) -> str:
        return hashlib.sha256(jti.encode()).hexdigest()

    def record(self, jti: str, user: SessionUser, issued_at: int, expires_at: int) -> None:
        if re.fullmatch(r"[0-9a-f]{32}", jti) is None:
            raise ValueError("Invalid session identifier")
        # Recheck identity under a row lock before issuing a token. A login must
        # not sign a token from stale role/disabled-account data.
        active = self.session.execute(
            select(UserRole)
            .join(User, User.id == UserRole.user_id)
            .where(
                User.id == user.user_id,
                User.status == "active",
                UserRole.role_code == user.role,
                UserRole.is_primary.is_(True),
                UserRole.revoked_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if active is None:
            raise ValueError("Account authorization changed during login")
        self.session.add(
            AuthSession(
                id=new_id("authsess"),
                jti_digest=self._digest(jti),
                user_id=user.user_id,
                role_code=user.role,
                issued_at=datetime.fromtimestamp(issued_at, UTC),
                expires_at=datetime.fromtimestamp(expires_at, UTC),
                request_id=self.request_id,
            )
        )
        self.session.flush()

    def is_active(self, jti: str, user: SessionUser) -> bool:
        return (
            self.session.execute(
                select(AuthSession.id)
                .join(User, User.id == AuthSession.user_id)
                .join(
                    UserRole,
                    (UserRole.user_id == User.id) & (UserRole.role_code == AuthSession.role_code),
                )
                .where(
                    AuthSession.jti_digest == self._digest(jti),
                    AuthSession.user_id == user.user_id,
                    AuthSession.role_code == user.role,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > datetime.now(UTC),
                    User.status == "active",
                    UserRole.is_primary.is_(True),
                    UserRole.revoked_at.is_(None),
                )
            ).scalar_one_or_none()
            is not None
        )

    def revoke(self, jti: str) -> None:
        row = self.session.execute(
            update(AuthSession)
            .where(AuthSession.jti_digest == self._digest(jti), AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoke_reason="logout")
            .returning(AuthSession.id, AuthSession.user_id)
        ).one_or_none()
        if row is not None:
            PlatformRepository(self.session).audit(
                actor_user_id=row.user_id,
                action="session_revoked",
                target_type="auth_sessions",
                target_id=row.id,
                request_id=self.request_id,
            )
        self.session.flush()
