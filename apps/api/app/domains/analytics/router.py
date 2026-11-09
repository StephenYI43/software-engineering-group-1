"""M6 → M2 统计查询接口的路由。

契约见 `packages/contracts/analytics/statistics-api.md`。

挂载由 M1 协调（`docs/team-plan.md:27`）：M6 提供 `create_router` 与
`analytics_error_handler`，M1 在 app factory 中注册两者
（`apps/api/app/main.py` 属 M1，M6 不直接改公共入口）。

`create_router` 只接收 `AnalyticsService`；service 依赖的 `upstream`
与 `course_map` 同样由 M1 的 app factory 组装注入，路由层不感知。

错误响应统一为 `{code, message, requestId, details}`（`docs/code-standards.md:73`），
`requestId` 取自 M1 的 requestId 中间件；未接入时兜底生成 `req_` + 随机 UUID——
正常路径不会出现，但出现时也保持契约要求的合法格式。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from app.domains.analytics.errors import AnalyticsError
from app.domains.analytics.period import DEFAULT_TIMEZONE, PERIOD_LAST_7_DAYS, PeriodQuery
from app.domains.analytics.schemas import ClassOverview
from app.domains.analytics.service import AnalyticsService


def fallback_request_id() -> str:
    """未接入 requestId 中间件时的兜底 ID：`req_` 加随机 UUID 的十六进制。"""
    return f"req_{uuid.uuid4().hex}"


def create_router(service: AnalyticsService) -> APIRouter:
    """构造 analytics 路由。`service` 由 app factory 注入。"""
    router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

    @router.get("/classes/{classId}/overview", response_model=ClassOverview)
    def get_class_overview(
        classId: str,
        response: Response,
        period: str = Query(PERIOD_LAST_7_DAYS, description="统计周期：last7d / last30d / custom"),
        from_: str | None = Query(None, alias="from", description="period=custom 时必填"),
        to: str | None = Query(None, description="period=custom 时必填"),
        timezone: str = Query(DEFAULT_TIMEZONE, description="IANA 时区名，决定按日聚合的日界"),
        page: int = Query(1, ge=1, description="students 页码，从 1 起"),
        page_size: int = Query(
            50, alias="pageSize", ge=1, le=200, description="students 每页人数，1—200"
        ),
    ) -> ClassOverview:
        """读取授权班级的统计概览。无数据返回 unknown，不是错误。"""
        response.headers["Cache-Control"] = "no-store"
        query = PeriodQuery(period=period, from_=from_, to=to, timezone=timezone)
        return service.get_overview(class_id=classId, query=query, page=page, page_size=page_size)

    return router


def analytics_error_handler(request: Request, error: Exception) -> JSONResponse:
    """把 `AnalyticsError` 转成契约错误响应。非本域异常原样抛出，不被吞掉。"""
    if not isinstance(error, AnalyticsError):
        raise error
    request_id = getattr(request.state, "request_id", None) or fallback_request_id()
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "requestId": request_id,
            "details": error.details,
        },
    )
