"""analytics 域的异常。

`AnalyticsError` 可 1:1 映射为契约错误响应（`docs/code-standards.md:73`）；
`StoreError` 表示存储层故障，读侧转成 503，**不允许**用部分或伪造数字代替
（`packages/contracts/analytics/statistics-api.md`「权限与错误」）。
"""

from __future__ import annotations

from typing import Any


class AnalyticsError(Exception):
    """可直接转成契约错误响应的领域异常。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}


class ClassNotFoundError(AnalyticsError):
    """班级不存在或不在教师授权范围内（统一 404，避免枚举）。"""

    def __init__(self) -> None:
        super().__init__(404, "CLASS_NOT_FOUND", "未找到班级")


class InvalidQueryError(AnalyticsError):
    """查询参数不合法。"""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__(422, "VALIDATION_FAILED", "统计周期参数不合法", details)


class StoreUnavailableError(AnalyticsError):
    """聚合数据源不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "ANALYTICS_SOURCE_UNAVAILABLE", "统计服务暂时不可用，请稍后重试")


class StoreError(Exception):
    """存储层读写故障（数据库不可用、连接中断等）。"""
