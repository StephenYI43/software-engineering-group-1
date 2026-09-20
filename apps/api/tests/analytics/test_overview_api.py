"""HTTP 层：契约响应形状、缓存头与错误码。

测试自建 FastAPI 应用并注册 M6 的 router 与异常处理器，
等价于 M1 在 app factory 中做的挂载（`main.py` 属 M1，M6 不改）。
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.domains.analytics.errors import AnalyticsError, StoreError
from app.domains.analytics.period import PeriodQuery
from app.domains.analytics.router import UNKNOWN_REQUEST_ID, analytics_error_handler, create_router
from app.domains.analytics.service import AnalyticsService
from app.domains.analytics.state import AnalyticsState

OVERVIEW_PATH = "/api/v1/analytics/classes/{class_id}/overview"
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


def build_client(store, roster, request_time, *, with_request_id: bool = True) -> TestClient:
    app = FastAPI()
    if with_request_id:

        @app.middleware("http")
        async def attach_request_id(request: Request, call_next: Callable) -> object:
            request.state.request_id = TEST_REQUEST_ID
            return await call_next(request)

    service = AnalyticsService(store=store, roster=roster, clock=lambda: request_time)
    app.include_router(create_router(service))
    app.add_exception_handler(AnalyticsError, analytics_error_handler)
    return TestClient(app, raise_server_exceptions=False)


def test_overview_returns_contract_shaped_payload(
    consumed_store, roster, request_time, class_id
) -> None:
    client = build_client(consumed_store, roster, request_time)

    response = client.get(OVERVIEW_PATH.format(class_id=class_id))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["classId"] == class_id
    assert payload["period"] == {
        "from": "2026-09-09T16:00:00Z",
        "to": "2026-09-16T16:00:00Z",
        "timezone": "Asia/Shanghai",
        "days": 7,
    }
    assert payload["dataThrough"] == "2026-09-16T09:20:00Z"
    assert payload["generatedAt"] == "2026-09-17T01:00:00Z"
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


def test_students_and_weak_points_are_camel_case(
    consumed_store, roster, request_time, class_id
) -> None:
    client = build_client(consumed_store, roster, request_time)

    payload = client.get(OVERVIEW_PATH.format(class_id=class_id)).json()

    unknown_student = next(row for row in payload["students"] if row["userId"] == "user_mock_s03")
    assert unknown_student["dataState"] == "unknown"
    assert unknown_student["durationSeconds"] == {
        "state": "unknown",
        "reason": "no_events_in_period",
    }
    assert unknown_student["weakestChapter"] is None

    assert payload["weakPoints"]["byQuestionType"][0] == {
        "key": "single_choice",
        "label": None,
        "errorRate": 0.5,
        "sampleSize": 2,
        "insufficientSample": True,
    }
    assert payload["weakPoints"]["byChapter"][0]["resolvedCount"] == 1


def test_empty_store_returns_unknown_not_zero(empty_store, roster, request_time, class_id) -> None:
    client = build_client(empty_store, roster, request_time)

    payload = client.get(OVERVIEW_PATH.format(class_id=class_id)).json()

    assert payload["dataThrough"] is None
    assert payload["summary"]["totalDurationSeconds"] == {
        "state": "unknown",
        "reason": "no_events_in_period",
    }


def test_unauthorized_class_returns_404_with_request_id(
    consumed_store, roster, request_time
) -> None:
    client = build_client(consumed_store, roster, request_time)

    response = client.get(OVERVIEW_PATH.format(class_id="class_mock_other"))

    assert response.status_code == 404
    assert response.json() == {
        "code": "CLASS_NOT_FOUND",
        "message": "未找到班级",
        "requestId": TEST_REQUEST_ID,
        "details": {},
    }


def test_error_without_request_id_middleware_uses_placeholder(
    consumed_store, roster, request_time
) -> None:
    client = build_client(consumed_store, roster, request_time, with_request_id=False)

    response = client.get(OVERVIEW_PATH.format(class_id="class_mock_other"))

    assert response.json()["requestId"] == UNKNOWN_REQUEST_ID


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
    consumed_store, roster, request_time, class_id, params
) -> None:
    client = build_client(consumed_store, roster, request_time)

    response = client.get(OVERVIEW_PATH.format(class_id=class_id), params=params)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["requestId"] == TEST_REQUEST_ID
    assert body["details"] != {}


def test_custom_period_accepts_from_and_to(consumed_store, roster, request_time, class_id) -> None:
    client = build_client(consumed_store, roster, request_time)

    response = client.get(
        OVERVIEW_PATH.format(class_id=class_id),
        params={"period": "custom", "from": "2026-09-16T00:00:00Z", "to": "2026-09-17T00:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json()["period"]["days"] == 2


def test_store_failure_returns_503(roster, request_time, class_id) -> None:
    client = build_client(FailingStore(), roster, request_time)

    response = client.get(OVERVIEW_PATH.format(class_id=class_id))

    assert response.status_code == 503
    assert response.json() == {
        "code": "ANALYTICS_SOURCE_UNAVAILABLE",
        "message": "统计服务暂时不可用，请稍后重试",
        "requestId": TEST_REQUEST_ID,
        "details": {},
    }


def test_unexpected_error_is_not_swallowed_by_handler(roster, request_time, class_id) -> None:
    """非本域异常必须继续上抛，不被错误处理器伪装成契约错误。"""
    client = build_client(UnexpectedFailureStore(), roster, request_time)

    response = client.get(OVERVIEW_PATH.format(class_id=class_id))

    assert response.status_code == 500


def test_handler_reraises_foreign_exception() -> None:
    request = SimpleNamespace(state=SimpleNamespace(request_id=TEST_REQUEST_ID))

    with pytest.raises(RuntimeError):
        analytics_error_handler(request, RuntimeError("boom"))


def test_openapi_documents_the_endpoint(consumed_store, roster, request_time) -> None:
    client = build_client(consumed_store, roster, request_time)

    schema = client.get("/openapi.json").json()

    assert "/api/v1/analytics/classes/{class_id}/overview" in schema["paths"]


def test_service_requires_period_query_type(consumed_store, roster, request_time, class_id) -> None:
    """服务层只接受结构化的查询对象，HTTP 解析在路由层完成。"""
    service = AnalyticsService(store=consumed_store, roster=roster, clock=lambda: request_time)

    overview = service.get_overview(class_id=class_id, query=PeriodQuery(period="last30d"))

    assert overview.period.days == 30
