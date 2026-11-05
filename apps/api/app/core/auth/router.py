"""Login and logout routes with a shared v1 error envelope."""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from app.core.auth.accounts import Account, verify_credentials
from app.core.auth.context import auth_context
from app.core.auth.schemas import LoginRequest, LoginResponse, LogoutResponse
from app.core.auth.settings import AuthSettings
from app.core.errors import ApiError


def create_auth_router(settings: AuthSettings) -> APIRouter:
    """Build the auth router against one resolved settings snapshot."""
    accounts: tuple[Account, ...] = settings.accounts
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    def login(payload: LoginRequest, request: Request) -> LoginResponse:
        with auth_context(request) as context:
            user = (
                context.repository.authenticate(payload.username, payload.password)
                if context.repository is not None
                else verify_credentials(accounts, payload.username, payload.password)
            )
            if user is None:
                raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
            return context.issue(user)

    @router.post("/logout", response_model=LogoutResponse)
    def logout(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> LogoutResponse:
        token = bearer_token(authorization)
        if token is None:
            raise ApiError(401, "TOKEN_REQUIRED", "缺少登录凭证")
        with auth_context(request) as context:
            context.authority.revoke(token)
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
