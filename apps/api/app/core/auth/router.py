"""Login and logout routes (Issue #45).

These routes hand-roll the error envelope (`docs/code-standards.md:74-80`)
because the shared error wrapper is not implemented yet (Issue #46); the inline
envelope will migrate to that wrapper once #46 lands. Login failures never
distinguish "unknown username" from "wrong password" so the endpoint does not
become a user-enumeration oracle.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.core.auth.accounts import Account, verify_credentials
from app.core.auth.schemas import LoginRequest, LoginResponse, LogoutResponse
from app.core.auth.settings import AuthSettings
from app.core.auth.tokens import SessionAuthority
from app.core.db.repository import DatabaseSessionStore, PlatformRepository
from app.core.db.session import Database


def create_auth_router(settings: AuthSettings, database: Database | None = None) -> APIRouter:
    """Build the auth router against one resolved settings snapshot."""
    authority = SessionAuthority(
        secret=settings.session_secret, ttl_seconds=settings.session_ttl_seconds
    )
    accounts: tuple[Account, ...] = settings.accounts
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    def login(payload: LoginRequest, request: Request) -> LoginResponse | JSONResponse:
        if database is not None:
            with database.sessions.begin() as session:
                user = PlatformRepository(session).authenticate(payload.username, payload.password)
                if user is None:
                    return error_response(request, 401, "INVALID_CREDENTIALS", "用户名或密码错误")
                persistent = SessionAuthority(
                    settings.session_secret,
                    settings.session_ttl_seconds,
                    DatabaseSessionStore(session, request.state.request_id),
                )
                issued = persistent.issue(user)
                PlatformRepository(session).audit(
                    actor_user_id=user.user_id,
                    action="session_issued",
                    target_type="users",
                    target_id=user.user_id,
                    request_id=request.state.request_id,
                )
                result = LoginResponse(token=issued.token, expires_at=issued.expires_at, user=user)
            return result
        user = verify_credentials(accounts, payload.username, payload.password)
        if user is None:
            return error_response(request, 401, "INVALID_CREDENTIALS", "用户名或密码错误")
        issued = authority.issue(user)
        return LoginResponse(token=issued.token, expires_at=issued.expires_at, user=user)

    @router.post("/logout", response_model=LogoutResponse)
    def logout(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> LogoutResponse | JSONResponse:
        token = bearer_token(authorization)
        if token is None:
            return error_response(request, 401, "TOKEN_REQUIRED", "缺少登录凭证")
        if database is None:
            authority.revoke(token)
        else:
            with database.sessions.begin() as session:
                SessionAuthority(
                    settings.session_secret,
                    settings.session_ttl_seconds,
                    DatabaseSessionStore(session, request.state.request_id),
                ).revoke(token)
        return LogoutResponse(revoked=True)

    return router


def bearer_token(authorization: str | None) -> str | None:
    """Extract the token from a `Bearer <token>` header; `None` when unusable."""
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token == "":
        return None
    return token


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    """Hand-rolled error envelope; to be replaced by the #46 shared wrapper."""
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "requestId": request.state.request_id,
            "details": {},
        },
    )
