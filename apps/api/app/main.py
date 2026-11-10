"""Platform authentication with optional PostgreSQL persistence."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from app.core.auth.dependencies import CourseAccess
from app.core.auth.external import create_external_router
from app.core.auth.router import create_auth_router
from app.core.auth.settings import load_auth_settings
from app.core.auth.tokens import SessionAuthority
from app.core.db.session import Database, load_database_url
from app.core.errors import ApiError, error_response, install_error_handlers
from app.core.request_id import create_request_id


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["learning-assistant-api"] = "learning-assistant-api"
    request_id: str = Field(serialization_alias="requestId")


def create_app(*, course_access: CourseAccess | None = None) -> FastAPI:
    url = load_database_url()
    database = Database(url) if url is not None else None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if database is not None:
                database.close()

    application = FastAPI(
        title="大学生辅助学习 AI 数字人系统 API",
        version="0.1.0",
        description="Platform login, authorization and optional PostgreSQL persistence.",
        lifespan=lifespan,
    )
    # Fail loud on auth misconfiguration before serving any request.
    settings = load_auth_settings()
    application.state.database = database
    application.state.auth_settings = settings
    authority = SessionAuthority(settings.session_secret, settings.session_ttl_seconds)
    application.state.session_authority = authority
    application.state.course_access = course_access
    application.include_router(create_auth_router(settings))
    application.include_router(create_external_router(settings, persistent=database is not None))
    install_error_handlers(application)

    @application.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError) -> Response:
        return error_response(request, ApiError(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用"))

    @application.middleware("http")
    async def attach_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = create_request_id()
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger(__name__).error(
                "Unhandled API exception request_id=%s", request.state.request_id
            )
            response = error_response(request, ApiError(500, "INTERNAL_ERROR", "服务暂不可用"))
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/auth/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["platform"])
    async def health(request: Request, response: Response) -> HealthResponse:
        """Report process liveness only; this does not test external dependencies."""
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(request_id=request.state.request_id)

    return application


app = create_app()
