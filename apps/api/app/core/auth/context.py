"""Share one transaction for authentication, session writes and auditing."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import Request

from app.core.auth.schemas import LoginResponse, SessionUser
from app.core.auth.settings import AuthSettings
from app.core.auth.tokens import SessionAuthority
from app.core.db.repository import DatabaseSessionStore, PlatformRepository
from app.core.db.session import Database


@dataclass
class AuthContext:
    authority: SessionAuthority
    repository: PlatformRepository | None
    request_id: str

    def issue(self, user: SessionUser) -> LoginResponse:
        issued = self.authority.issue(user)
        if self.repository is not None:
            self.repository.audit(
                actor_user_id=user.user_id,
                action="session_issued",
                target_type="users",
                target_id=user.user_id,
                request_id=self.request_id,
            )
        return LoginResponse(token=issued.token, expires_at=issued.expires_at, user=user)


@contextmanager
def auth_context(request: Request) -> Iterator[AuthContext]:
    database: Database | None = request.app.state.database
    request_id: str = request.state.request_id
    if database is None:
        yield AuthContext(request.app.state.session_authority, None, request_id)
        return
    settings: AuthSettings = request.app.state.auth_settings
    # Commit before the handler returns its response. Any failure rolls back both
    # the session and audit entry rather than returning an unusable credential.
    with database.sessions.begin() as session:
        yield AuthContext(
            SessionAuthority(
                settings.session_secret,
                settings.session_ttl_seconds,
                DatabaseSessionStore(session, request_id),
            ),
            PlatformRepository(session),
            request_id,
        )
