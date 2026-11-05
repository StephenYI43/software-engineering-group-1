"""Exercise authentication via HTTP against a real disposable PostgreSQL database."""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.auth.dependencies import CurrentPrincipal, require_user
from app.core.auth.external import provider_client
from app.core.db.identities import configure_identity
from app.core.db.identities import main as identity_main
from app.core.db.models import AdminAuditLog, AuthSession, ExternalIdentity, User, UserRole
from app.core.db.repository import PlatformRepository
from app.core.db.seed import seed
from app.core.db.session import Database
from app.core.errors import ApiError
from app.main import create_app

pytestmark = pytest.mark.postgres
STUDENT = "user_" + "1" * 32
OTHER = "user_" + "2" * 32
AUTH = "/api/v1/auth"


def configured_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("AUTH_SESSION_SECRET", "integration-test-only-secret-key-" + "x" * 32)
    monkeypatch.delenv("AUTH_SYNTHETIC_ACCOUNTS", raising=False)
    monkeypatch.setenv(
        "AUTH_EXTERNAL_LOGIN",
        json.dumps(
            {
                "web_origin": "https://learning.example",
                "github": {"client_id": "test", "client_secret": "test-only-secret"},
                "sms": {
                    "account_sid": "AC" + "0" * 32,
                    "service_sid": "VA" + "0" * 32,
                    "auth_token": "test",
                },
            }
        ),
    )
    app = create_app()

    @app.get("/test/identity")
    def current(user: Annotated[CurrentPrincipal, Depends(require_user)]) -> CurrentPrincipal:
        return user

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"id": 42, "role": "admin"})
        if request.url.host == "verify.twilio.com":
            payload = parse_qs(request.content.decode())
            return httpx.Response(
                200,
                json={
                    "to": payload["To"][0],
                    "status": "approved" if payload.get("Code") == ["123456"] else "pending",
                },
            )
        return httpx.Response(200, json={"access_token": "test-only-provider-token"})

    def client():
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            yield http

    app.dependency_overrides[provider_client] = client
    return app


def bind(
    database: Database,
    *,
    provider: str = "github",
    issuer: str = "https://github.com",
    subject: str = "42",
    user_id: str = STUDENT,
    revoke: bool = False,
) -> None:
    with database.sessions.begin() as session:
        configure_identity(
            session,
            provider=provider,
            issuer=issuer,
            subject=subject,
            user_id=user_id,
            revoke=revoke,
        )


def github_login(client: TestClient) -> httpx.Response:
    start = client.post(AUTH + "/oauth/github/start")
    assert start.status_code == 200
    state = parse_qs(urlsplit(start.json()["authorizationUrl"]).query)["state"][0]
    return client.post(AUTH + "/oauth/github/exchange", json={"code": "test-code", "state": state})


def test_binding_session_and_logout_survive_app_restart(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(database)
    bind(database)
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as first:
        response = github_login(first)
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "student"
        token = response.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as restarted:
        assert restarted.get("/test/identity", headers=headers).json()["userId"] == STUDENT
        assert restarted.post(AUTH + "/logout", headers=headers).status_code == 200
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as again:
        assert again.get("/test/identity", headers=headers).status_code == 401
        assert github_login(again).status_code == 200
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ExternalIdentity)) == 1
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(AdminAuditLog)
                .where(
                    AdminAuditLog.action == "session_revoked",
                )
            )
            == 1
        )


def test_unbinding_revokes_sessions_and_cannot_reassign(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(database)
    bind(database)
    bind(database)
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as client:
        token = github_login(client).json()["token"]
        bind(database, revoke=True)
        bind(database, revoke=True)
        assert (
            client.get("/test/identity", headers={"Authorization": "Bearer " + token}).status_code
            == 401
        )
        assert github_login(client).status_code == 401
        with pytest.raises(ValueError, match="another user"):
            bind(database, user_id=OTHER)


def test_database_state_overrides_signed_role(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(database)
    bind(database)
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as client:
        token = github_login(client).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        with database.sessions.begin() as session:
            session.get(User, STUDENT).status = "disabled"
        assert client.get("/test/identity", headers=headers).status_code == 401
        assert github_login(client).status_code == 401
        with database.sessions.begin() as session:
            session.get(User, STUDENT).status = "active"
            session.get(UserRole, (STUDENT, "student")).is_primary = False
            session.flush()
            session.add(UserRole(user_id=STUDENT, role_code="teacher", is_primary=True))
        assert client.get("/test/identity", headers=headers).status_code == 401
        response = github_login(client)
        assert response.json()["user"]["role"] == "teacher"


def test_audit_failure_rolls_back_issued_session(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(database)
    bind(database)

    def fail(*args, **kwargs):
        raise ApiError(503, "AUDIT_UNAVAILABLE", "审计暂不可用")

    monkeypatch.setattr(PlatformRepository, "audit", fail)
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as client:
        assert github_login(client).status_code == 503
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_identity_scope_and_concurrent_conflict(database: Database) -> None:
    seed(database)
    for issuer in ("https://school-a.example", "https://school-b.example"):
        bind(database, provider="school", issuer=issuer, subject="same-subject")
    with database.sessions.begin() as session:
        repo = PlatformRepository(session)
        assert (
            repo.external_user("school", "https://school-a.example", "same-subject").user_id
            == STUDENT
        )
        assert repo.external_user("school", "https://unknown.example", "same-subject") is None

    def race(user_id: str) -> bool:
        try:
            bind(database, user_id=user_id)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(race, (STUDENT, OTHER))) == [False, True]


def test_operator_command_and_invalid_bindings(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed(database)
    command = [
        "identities",
        "--provider",
        "github",
        "--issuer",
        "https://github.com",
        "--subject",
        "4242",
        "--user-id",
        STUDENT,
    ]
    monkeypatch.setattr("sys.argv", command)
    identity_main()
    monkeypatch.setattr("sys.argv", command + ["--revoke"])
    identity_main()
    assert "4242" not in capsys.readouterr().out
    for values in (
        {"provider": "unknown"},
        {"issuer": "https://other.example"},
        {"subject": "some-username"},
    ):
        with pytest.raises(ValueError):
            bind(database, **values)
    with database.sessions.begin() as session:
        session.get(User, OTHER).status = "disabled"
    with pytest.raises(ValueError, match="active local"):
        bind(database, user_id=OTHER)


def test_sms_uses_persisted_binding(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(database)
    phone = "+15550100001"
    bind(database, provider="sms", issuer="phone:e164", subject=phone)
    with TestClient(configured_app(monkeypatch), base_url="https://learning.example") as client:
        assert client.post(AUTH + "/sms/send", json={"phone": phone}).status_code == 204
        result = client.post(AUTH + "/sms/login", json={"phone": phone, "code": "123456"})
        assert result.status_code == 200
        assert (
            client.get(
                "/test/identity",
                headers={
                    "Authorization": "Bearer " + result.json()["token"],
                },
            ).json()["userId"]
            == STUDENT
        )
