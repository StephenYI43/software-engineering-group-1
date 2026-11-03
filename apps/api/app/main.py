"""Platform API; DATABASE_URL opts into persistent accounts and sessions."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from app.core.auth.router import create_auth_router
from app.core.auth.settings import load_auth_settings
from app.core.db.session import Database, load_database_url
from app.core.request_id import create_request_id


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["learning-assistant-api"] = "learning-assistant-api"
    request_id: str = Field(serialization_alias="requestId")


def create_app() -> FastAPI:
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
        description="Platform authentication with optional PostgreSQL persistence.",
        lifespan=lifespan,
    )
    application.state.database = database
    # Fail loud on auth misconfiguration before serving any request.
    application.include_router(create_auth_router(load_auth_settings(), database))

    @application.exception_handler(OperationalError)
    async def database_error(request: Request, error: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "message": "数据库暂时不可用",
                "requestId": request.state.request_id,
                "details": {},
            },
        )

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
