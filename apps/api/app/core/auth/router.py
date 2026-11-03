"""Login and logout routes with a shared v1 error envelope."""

from typing import Annotated

from fastapi import APIRouter, Header

from app.core.auth.accounts import Account, verify_credentials
from app.core.auth.schemas import LoginRequest, LoginResponse, LogoutResponse
from app.core.auth.settings import AuthSettings
from app.core.auth.tokens import SessionAuthority
from app.core.errors import ApiError


def create_auth_router(settings: AuthSettings, authority: SessionAuthority) -> APIRouter:
    """Build the auth router against one resolved settings snapshot."""
    accounts: tuple[Account, ...] = settings.accounts
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    def login(payload: LoginRequest) -> LoginResponse:
        user = verify_credentials(accounts, payload.username, payload.password)
        if user is None:
            raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
        issued = authority.issue(user)
        return LoginResponse(token=issued.token, expires_at=issued.expires_at, user=user)

    @router.post("/logout", response_model=LogoutResponse)
    def logout(
        authorization: Annotated[str | None, Header()] = None,
    ) -> LogoutResponse:
        token = bearer_token(authorization)
        if token is None:
            raise ApiError(401, "TOKEN_REQUIRED", "缺少登录凭证")
        authority.revoke(token)
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
