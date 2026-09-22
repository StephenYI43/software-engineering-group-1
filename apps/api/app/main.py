"""S0 liveness API plus S1 login/logout (Issue #45). No database yet."""

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

from app.core.auth.router import create_auth_router
from app.core.auth.settings import load_auth_settings
from app.core.request_id import create_request_id


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["learning-assistant-api"] = "learning-assistant-api"
    request_id: str = Field(serialization_alias="requestId")


def create_app() -> FastAPI:
    application = FastAPI(
        title="大学生辅助学习 AI 数字人系统 API",
        version="0.1.0",
        description="S0 development skeleton plus S1 auth; no database or learning data yet.",
    )
    # Fail loud on auth misconfiguration before serving any request.
    application.include_router(create_auth_router(load_auth_settings()))

    @application.middleware("http")
    async def attach_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = create_request_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["platform"])
    async def health(request: Request, response: Response) -> HealthResponse:
        """Report process liveness only; this does not test external dependencies."""
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(request_id=request.state.request_id)

    return application


app = create_app()
