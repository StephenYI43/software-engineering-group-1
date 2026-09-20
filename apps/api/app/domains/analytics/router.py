"""M6 → M2 统计查询接口的路由。

契约见 `packages/contracts/analytics/statistics-api.md`。

挂载由 M1 协调（`docs/team-plan.md:27`）：M6 提供 `create_router` 与
`analytics_error_handler`，M1 在 app factory 中注册两者
（`apps/api/app/main.py` 属 M1，M6 不直接改公共入口）。

错误响应统一为 `{code, message, requestId, details}`（`docs/code-standards.md:73`），
`requestId` 取自 M1 的 requestId 中间件；未接入时用占位值，正常路径不会出现。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from app.domains.analytics.errors import AnalyticsError
from app.domains.analytics.period import DEFAULT_TIMEZONE, PERIOD_LAST_7_DAYS, PeriodQuery
from app.domains.analytics.schemas import ClassOverview
from app.domains.analytics.service import AnalyticsService

UNKNOWN_REQUEST_ID = "unknown"
"""未接入 requestId 中间件时的占位符。"""


def create_router(service: AnalyticsService) -> APIRouter:
    """构造 analytics 路由。`service` 由 app factory 注入。"""
    router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

    @router.get("/classes/{class_id}/overview", response_model=ClassOverview)
    def get_class_overview(
        class_id: str,
        response: Response,
        period: str = Query(PERIOD_LAST_7_DAYS, description="统计周期：last7d / last30d / custom"),
        from_: str | None = Query(None, alias="from", description="period=custom 时必填"),
        to: str | None = Query(None, description="period=custom 时必填"),
        timezone: str = Query(DEFAULT_TIMEZONE, description="IANA 时区名，决定按日聚合的日界"),
    ) -> ClassOverview:
        """读取授权班级的统计概览。无数据返回 unknown，不是错误。"""
        response.headers["Cache-Control"] = "no-store"
        query = PeriodQuery(period=period, from_=from_, to=to, timezone=timezone)
        return service.get_overview(class_id=class_id, query=query)

    return router


def analytics_error_handler(request: Request, error: Exception) -> JSONResponse:
    """把 `AnalyticsError` 转成契约错误响应。非本域异常原样抛出，不被吞掉。"""
    if not isinstance(error, AnalyticsError):
        raise error
    request_id = getattr(request.state, "request_id", None) or UNKNOWN_REQUEST_ID
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "requestId": request_id,
            "details": error.details,
        },
    )
