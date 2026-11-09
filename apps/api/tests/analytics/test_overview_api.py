"""HTTP 层：契约响应形状、缓存头与错误码。

测试自建 FastAPI 应用并注册 M6 的 router 与异常处理器，
等价于 M1 在 app factory 中做的挂载（`main.py` 属 M1，M6 不改）。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.domains.analytics.errors import AnalyticsError, StoreError
from app.domains.analytics.period import PeriodQuery
from app.domains.analytics.router import analytics_error_handler, create_router, fallback_request_id
from app.domains.analytics.service import AnalyticsService
from app.domains.analytics.state import AnalyticsState

OVERVIEW_PATH = "/api/v1/analytics/classes/{classId}/overview"
TEST_REQUEST_ID = "req_test_0001"


class UnexpectedFailureStore:
    """抛出非本域异常，验证错误处理器不吞异常。"""

    def load(self) -> AnalyticsState:
        raise RuntimeError("store exploded")

    def save(self, state: AnalyticsState) -> None:
        raise RuntimeError("store exploded")


class FailingStore:
    """存储故障，按契约转成 503。"""

    def load(self) -> AnalyticsState:
        raise StoreError("database unavailable")

    def save(self, state: AnalyticsState) -> None:
        raise StoreError("database unavailable")


def build_client(
    store, roster, request_time: datetime, course_map, *, with_request_id: bool = True
) -> TestClient:
    app = FastAPI()
    if with_request_id:

        @app.middleware("http")
        async def attach_request_id(request: Request, call_next: Callable) -> object:
            request.state.request_id = TEST_REQUEST_ID
            return await call_next(request)

    service = AnalyticsService(
        store=store, roster=roster, course_map=course_map, clock=lambda: request_time
    )
    app.include_router(create_router(service))
    app.add_exception_handler(AnalyticsError, analytics_error_handler)
    return TestClient(app, raise_server_exceptions=False)


def test_overview_returns_contract_shaped_payload(
    consumed_store, roster, request_time, class_id, course_map, course_id
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["classId"] == class_id
    assert payload["courseId"] == course_id
    assert payload["period"] == {
        "from": "2026-09-09T16:00:00Z",
        "to": "2026-09-16T16:00:00Z",
        "timezone": "Asia/Shanghai",
        "days": 7,
    }
    assert payload["dataThrough"] == "2026-09-16T09:20:00Z"
    assert payload["generatedAt"] == "2026-09-17T01:00:00Z"
    # service 未接 upstream：consumption 如实报告 unknown
    assert payload["consumption"] == {"dataState": "unknown", "upstreamWatermark": None}
    assert payload["summary"]["totalDurationSeconds"] == {
        "state": "known",
        "value": 3540,
        "algorithm": "session_inference_v1",
    }
    assert payload["summary"]["activeStudentCount"] == {"state": "known", "value": 2}
    assert payload["summary"]["submissionCount"] == {"state": "known", "value": 3}
    assert payload["summary"]["coverage"] == {
        "studentCount": 3,
        "studentsWithData": 2,
        "studentsWithoutData": 1,
    }
    assert payload["students"] == {
        "page": 1,
        "pageSize": 50,
        "total": 3,
        "items": payload["students"]["items"],
    }
    assert len(payload["students"]["items"]) == 3


def test_students_and_weak_points_are_camel_case(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    payload = client.get(OVERVIEW_PATH.format(classId=class_id)).json()

    unknown_student = next(
        row for row in payload["students"]["items"] if row["userId"] == "user_mock_s03"
    )
    assert unknown_student["dataState"] == "unknown"
    assert unknown_student["durationSeconds"] == {
        "state": "unknown",
        "reason": "no_events_in_period",
    }
    # 计数 known 0：无提交是已知的 0
    assert unknown_student["submissionCount"] == {"state": "known", "value": 0}
    assert unknown_student["weakestChapter"] is None

    assert payload["weakPoints"]["byQuestionType"][0] == {
        "key": "single_choice",
        "label": None,
        "errorRate": 0.5,
        "sampleSize": 2,
        "insufficientSample": True,
    }
    assert payload["weakPoints"]["byChapter"][0]["resolvedCount"] == 1


def test_students_pagination_parameters_are_honoured(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id), params={"page": 2, "pageSize": 2})

    assert response.status_code == 200
    students = response.json()["students"]
    assert students["page"] == 2
    assert students["pageSize"] == 2
    assert students["total"] == 3
    assert len(students["items"]) == 1  # 3 行取 [2:4] 只剩 1 行


def test_students_beyond_last_page_returns_empty_items(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    payload = client.get(
        OVERVIEW_PATH.format(classId=class_id), params={"page": 99, "pageSize": 50}
    ).json()

    assert payload["students"]["page"] == 99
    assert payload["students"]["total"] == 3
    assert payload["students"]["items"] == []


def test_empty_store_returns_known_zero_counts(
    empty_store, roster, request_time, class_id, course_map
) -> None:
    client = build_client(empty_store, roster, request_time, course_map)

    payload = client.get(OVERVIEW_PATH.format(classId=class_id)).json()

    assert payload["dataThrough"] is None
    assert payload["summary"]["totalDurationSeconds"] == {
        "state": "unknown",
        "reason": "no_events_in_period",
    }
    # 计数 known 0：没有事件也是已知数字
    assert payload["summary"]["activeStudentCount"] == {"state": "known", "value": 0}
    assert payload["summary"]["submissionCount"] == {"state": "known", "value": 0}


def test_unauthorized_class_returns_404_with_request_id(
    consumed_store, roster, request_time, course_map
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId="class_mock_other"))

    assert response.status_code == 404
    assert response.json() == {
        "code": "CLASS_NOT_FOUND",
        "message": "未找到班级",
        "requestId": TEST_REQUEST_ID,
        "details": {},
    }


def test_error_without_request_id_middleware_generates_fallback(
    consumed_store, roster, request_time, course_map
) -> None:
    """未接入 requestId 中间件时兜底生成 `req_` + 32 位十六进制的合法格式。"""
    client = build_client(consumed_store, roster, request_time, course_map, with_request_id=False)

    response = client.get(OVERVIEW_PATH.format(classId="class_mock_other"))

    request_id = response.json()["requestId"]
    assert re.fullmatch(r"req_[0-9a-f]{32}", request_id)


def test_fallback_request_id_is_unique_and_well_formed() -> None:
    first = fallback_request_id()
    second = fallback_request_id()

    assert re.fullmatch(r"req_[0-9a-f]{32}", first)
    assert first != second


@pytest.mark.parametrize(
    "params",
    [
        {"period": "lastYear"},
        {"period": "custom"},
        {"period": "custom", "from": "2026-09-17T00:00:00Z", "to": "2026-09-15T00:00:00Z"},
        {"period": "last7d", "timezone": "Mars/Olympus"},
    ],
)
def test_invalid_parameters_return_422(
    consumed_store, roster, request_time, class_id, course_map, params
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id), params=params)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["requestId"] == TEST_REQUEST_ID
    assert body["details"] != {}


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"pageSize": 0},
        {"pageSize": 201},
    ],
)
def test_pagination_bounds_are_enforced_by_query_constraints(
    consumed_store, roster, request_time, class_id, course_map, params
) -> None:
    """page/pageSize 边界由 router 的 Query 约束（1—200）在进入服务层前拦下。

    该校验走 FastAPI 默认的 RequestValidationError 路径，响应体不是本域错误契约形状。
    """
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id), params=params)

    assert response.status_code == 422


def test_custom_period_accepts_from_and_to(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    response = client.get(
        OVERVIEW_PATH.format(classId=class_id),
        params={"period": "custom", "from": "2026-09-16T00:00:00Z", "to": "2026-09-17T00:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["period"]["days"] == 2


def test_store_failure_returns_503(roster, request_time, class_id, course_map) -> None:
    client = build_client(FailingStore(), roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id))

    assert response.status_code == 503
    assert response.json() == {
        "code": "ANALYTICS_SOURCE_UNAVAILABLE",
        "message": "统计服务暂时不可用，请稍后重试",
        "requestId": TEST_REQUEST_ID,
        "details": {},
    }


def test_unexpected_error_is_not_swallowed_by_handler(
    roster, request_time, class_id, course_map
) -> None:
    """非本域异常必须继续上抛，不被错误处理器伪装成契约错误。"""
    client = build_client(UnexpectedFailureStore(), roster, request_time, course_map)

    response = client.get(OVERVIEW_PATH.format(classId=class_id))

    assert response.status_code == 500


def test_handler_reraises_foreign_exception() -> None:
    request = SimpleNamespace(state=SimpleNamespace(request_id=TEST_REQUEST_ID))

    with pytest.raises(RuntimeError):
        analytics_error_handler(request, RuntimeError("boom"))


def test_openapi_documents_the_endpoint(consumed_store, roster, request_time, course_map) -> None:
    client = build_client(consumed_store, roster, request_time, course_map)

    schema = client.get("/openapi.json").json()

    assert "/api/v1/analytics/classes/{classId}/overview" in schema["paths"]


def test_service_requires_period_query_type(
    consumed_store, roster, request_time, class_id, course_map
) -> None:
    """服务层只接受结构化的查询对象，HTTP 解析在路由层完成。"""
    service = AnalyticsService(
        store=consumed_store, roster=roster, course_map=course_map, clock=lambda: request_time
    )

    overview = service.get_overview(class_id=class_id, query=PeriodQuery(period="last30d"))

    assert overview.period.days == 30
