from typing import Annotated

import pytest
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient

from app.core.auth.accounts import load_accounts
from app.core.auth.dependencies import (
    CurrentPrincipal,
    require_course_access,
    require_owner,
    require_teacher,
    require_user,
)
from app.core.auth.summaries import resolve_user_summaries
from app.main import create_app


def test_identity_role_and_resource_isolation() -> None:
    accounts = load_accounts("")
    first, second, teacher = (account.session_user for account in accounts)
    allowed = {(first.user_id, "student", "math"), (teacher.user_id, "teacher", "math")}
    app = create_app(course_access=lambda uid, role, cid: (uid, role, cid) in allowed)

    @app.get("/test/teacher")
    def teacher_only(user: Annotated[CurrentPrincipal, Depends(require_teacher)]) -> str:
        return user.user_id

    @app.get("/test/owners/{owner_id}")
    def owner_only(owner_id: str, user: Annotated[CurrentPrincipal, Depends(require_user)]) -> str:
        require_owner(user, owner_id)
        return user.user_id

    @app.get("/test/courses/{course_id}")
    def course_only(user: Annotated[CurrentPrincipal, Depends(require_course_access)]) -> str:
        return user.user_id

    with TestClient(app) as client:

        def login(username: str, password: str) -> dict[str, str]:
            result = client.post(
                "/api/v1/auth/login", json={"username": username, "password": password}
            )
            assert result.status_code == 200
            return {"Authorization": "Bearer " + result.json()["token"]}

        first_headers = login("student1", "demo-student-1")
        second_headers = login("student2", "demo-student-2")
        teacher_headers = login("teacher1", "demo-teacher-1")
        assert client.get("/test/teacher").status_code == 401
        assert client.get("/test/teacher", headers=first_headers).status_code == 403
        assert client.get("/test/teacher", headers=teacher_headers).json() == teacher.user_id
        assert (
            client.get(f"/test/owners/{second.user_id}", headers=first_headers).status_code == 404
        )
        assert client.get(f"/test/owners/{first.user_id}", headers=first_headers).status_code == 200
        assert client.get("/test/courses/math", headers=first_headers).json() == first.user_id
        assert client.get("/test/courses/math", headers=second_headers).status_code == 404
        assert client.get("/test/courses/other", headers=teacher_headers).status_code == 404
        assert client.post("/api/v1/auth/logout", headers=first_headers).status_code == 200
        revoked = client.get("/test/courses/math", headers=first_headers)
        assert revoked.status_code == 401
        assert revoked.json()["code"] == "INVALID_TOKEN"
        assert revoked.headers["www-authenticate"] == "Bearer"


def test_missing_course_provider_fails_closed() -> None:
    app = create_app()

    @app.get("/test/courses/{course_id}")
    def course_only(user: Annotated[CurrentPrincipal, Depends(require_course_access)]) -> str:
        return user.user_id

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "student1", "password": "demo-student-1"}
        )
        response = client.get(
            "/test/courses/math", headers={"Authorization": "Bearer " + login.json()["token"]}
        )
        assert response.status_code == 503


def test_summary_excludes_unauthorized_profiles() -> None:
    accounts = load_accounts("")
    first, second, teacher = (account.session_user for account in accounts)
    summaries = resolve_user_summaries(
        [first.user_id, second.user_id, teacher.user_id],
        authorized_ids={first.user_id, teacher.user_id},
        accounts=accounts,
    )
    assert [item.model_dump(by_alias=True) for item in summaries] == [
        {"studentId": first.user_id, "name": first.name, "studentNumber": "DEMO-001"}
    ]


def test_error_envelopes_and_redaction(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    @app.get("/test/limited")
    def limited() -> None:
        raise HTTPException(429, "synthetic private data", headers={"Retry-After": "3"})

    @app.get("/test/broken")
    def broken() -> None:
        raise RuntimeError("synthetic private data")

    with TestClient(app) as client:
        limited_response = client.get("/test/limited")
        assert limited_response.headers["retry-after"] == "3"
        for response, status, code in [
            (limited_response, 429, "RATE_LIMITED"),
            (client.get("/test/broken"), 500, "INTERNAL_ERROR"),
            (client.get("/absent"), 404, "NOT_FOUND"),
            (
                client.post("/api/v1/auth/login", json={"password": ["synthetic private data"]}),
                422,
                "VALIDATION_ERROR",
            ),
        ]:
            assert response.status_code == status
            body = response.json()
            assert set(body) == {"code", "message", "requestId", "details"}
            assert body["code"] == code
            assert body["requestId"] == response.headers["x-request-id"]
            assert "synthetic private data" not in response.text
        assert "Unhandled API exception request_id=req_" in caplog.text
        assert "synthetic private data" not in caplog.text
