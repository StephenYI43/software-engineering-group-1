from uuid import UUID

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_live_and_correlated() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "service", "requestId"}
    assert data["status"] == "ok"
    assert data["service"] == "learning-assistant-api"
    request_id = data["requestId"]
    assert request_id.startswith("req_")
    assert UUID(hex=request_id.removeprefix("req_")).version == 4
    assert response.headers["x-request-id"] == request_id
    assert response.headers["cache-control"] == "no-store"


def test_request_ids_are_distinct_and_server_owned() -> None:
    with TestClient(create_app()) as client:
        first = client.get("/api/v1/health", headers={"X-Request-ID": "untrusted-client-value"})
        second = client.get("/api/v1/health")
    assert first.json()["requestId"] != "untrusted-client-value"
    assert first.json()["requestId"] != second.json()["requestId"]


def test_unknown_route_is_not_a_successful_health_response() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/not-implemented")
    assert response.status_code == 404
    assert response.headers["x-request-id"].startswith("req_")
