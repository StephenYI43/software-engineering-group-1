"""Shared v1 error envelope. Only explicitly public fields reach the client."""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException


class ApiError(Exception):
    """A domain error with a public code and message."""

    def __init__(
        self, status: int, code: str, message: str, *, headers: Mapping[str, str] | None = None
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


def error_response(request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        headers=error.headers,
        content={
            "code": error.code,
            "message": error.message,
            "requestId": request.state.request_id,
            "details": {},
        },
    )


_HTTP_ERRORS = {
    401: ("TOKEN_REQUIRED", "请登录"),
    403: ("FORBIDDEN", "无权执行此操作"),
    404: ("NOT_FOUND", "未找到资源"),
    405: ("METHOD_NOT_ALLOWED", "请求方法不受支持"),
    422: ("VALIDATION_ERROR", "请求参数不合法"),
    429: ("RATE_LIMITED", "请求过于频繁"),
    503: ("SERVICE_UNAVAILABLE", "服务暂不可用"),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def domain_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if exc.status_code in (204, 304) or exc.status_code < 200:
            return Response(status_code=exc.status_code, headers=exc.headers)
        fallback = (
            ("INTERNAL_ERROR", "服务暂不可用")
            if exc.status_code >= 500
            else ("REQUEST_FAILED", "请求失败")
        )
        code, message = _HTTP_ERRORS.get(exc.status_code, fallback)
        return error_response(
            request, ApiError(exc.status_code, code, message, headers=exc.headers)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, ApiError(422, "VALIDATION_ERROR", "请求参数不合法"))
