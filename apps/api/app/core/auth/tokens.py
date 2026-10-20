"""Session token issuance, verification and revocation (Issues #45/#48).

When a SessionStore is injected, issuance/revocation are flushed in the caller's
transaction and parsing rechecks persisted account/role/session state. Without
that store the original offline demonstration retains its in-memory behavior.

Tokens are HS256 JWTs issued by this service. The signing secret comes from
`AuthSettings`; its default is a documented demo value that must be replaced
for anything real (`docs/code-standards.md:107`). Revocation is an in-process
deny list keyed by `jti`: it makes logout effective for the single-process
demo but does not survive a restart — the documented S1 limitation; distributed
revocation belongs to a later slice.

`parse` returning `None` is the contract for #16's authorization dependencies:
invalid, expired, tampered or revoked tokens all collapse to "no identity".
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import jwt

from app.core.auth.schemas import SessionUser

_ROLES = ("student", "teacher", "admin")


class SessionStore(Protocol):
    def record(self, jti: str, user: SessionUser, issued_at: int, expires_at: int) -> None: ...
    def is_active(self, jti: str, user: SessionUser) -> bool: ...
    def revoke(self, jti: str) -> None: ...


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A fresh token plus its UTC expiry in ISO 8601."""

    token: str
    expires_at: str


class SessionAuthority:
    """Issues and verifies session tokens with one secret and one TTL."""

    def __init__(self, secret: str, ttl_seconds: int, store: SessionStore | None = None) -> None:
        self._secret = secret
        self._ttl_seconds = ttl_seconds
        self._denied_jtis: set[str] = set()
        self._store = store

    def issue(self, user: SessionUser) -> IssuedSession:
        now = int(time.time())
        expires_at_unix = now + self._ttl_seconds
        jti = uuid.uuid4().hex
        token = jwt.encode(
            {
                "sub": user.user_id,
                "role": user.role,
                "name": user.name,
                "iat": now,
                "exp": expires_at_unix,
                "jti": jti,
            },
            self._secret,
            algorithm="HS256",
        )
        if self._store is not None:
            self._store.record(jti, user, now, expires_at_unix)
        return IssuedSession(
            token=token,
            expires_at=datetime.fromtimestamp(expires_at_unix, tz=UTC).isoformat(),
        )

    def parse(self, token: str) -> SessionUser | None:
        """Return the identity a valid token carries, or `None` if unusable."""
        try:
            claims: dict[str, Any] = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None
        jti = claims.get("jti")
        if isinstance(jti, str) and jti in self._denied_jtis:
            return None
        user_id = claims.get("sub")
        role = claims.get("role")
        name = claims.get("name")
        if not isinstance(user_id, str) or role not in _ROLES or not isinstance(name, str):
            return None
        user = SessionUser(user_id=user_id, role=role, name=name)
        if self._store is not None and (
            not isinstance(jti, str) or not self._store.is_active(jti, user)
        ):
            return None
        return user

    def revoke(self, token: str) -> None:
        """Deny a token by its `jti`. Idempotent; unknown tokens are ignored."""
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
        except jwt.PyJWTError:
            return
        jti = claims.get("jti")
        if isinstance(jti, str):
            if self._store is not None:
                self._store.revoke(jti)
            else:
                self._denied_jtis.add(jti)
