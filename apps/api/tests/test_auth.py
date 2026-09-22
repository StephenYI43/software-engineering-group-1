"""Tests for login/logout and the session token lifecycle (Issue #45).

Covers the three default synthetic accounts, the hand-rolled error envelope,
token round-trip / expiry / tampering / revocation, and the fail-loud settings
branches. The shared error wrapper is out of scope here (Issue #46): 422
responses still use FastAPI's default shape, which these tests pin as-is.
"""

import json
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.auth.accounts import Account, load_accounts, verify_credentials
from app.core.auth.schemas import SessionUser
from app.core.auth.settings import load_auth_settings
from app.core.auth.tokens import SessionAuthority
from app.main import create_app

#: Long enough for HS256 without PyJWT's short-key warning.
_SECRET = "test-secret-0123456789abcdef0123456789abcdef"

_STUDENT = SessionUser(
    user_id="user_11111111111111111111111111111111", role="student", name="学生甲"
)


def _client() -> TestClient:
    return TestClient(create_app())


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


# --- accounts: documented defaults ---


def test_default_store_has_three_synthetic_accounts() -> None:
    accounts = load_accounts("")
    assert [(a.username, a.session_user.role) for a in accounts] == [
        ("student1", "student"),
        ("student2", "student"),
        ("teacher1", "teacher"),
    ]


def test_verify_credentials_matches_exact_username_and_password() -> None:
    accounts = load_accounts("")
    assert verify_credentials(accounts, "student1", "demo-student-1") == _STUDENT
    assert verify_credentials(accounts, "student1", "wrong") is None
    assert verify_credentials(accounts, "student1x", "demo-student-1") is None


def test_load_accounts_fails_loud_on_bad_input() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        load_accounts("{")
    with pytest.raises(ValueError, match="must be a JSON array"):
        load_accounts('{"username": "x"}')
    with pytest.raises(ValueError, match="must be an object"):
        load_accounts("[1]")
    with pytest.raises(ValueError, match="missing fields"):
        load_accounts('[{"username": "x"}]')
    with pytest.raises(ValueError, match="non-empty strings"):
        load_accounts(
            json.dumps(
                [
                    {
                        "username": "",
                        "password": "p",
                        "userId": "user_1",
                        "role": "student",
                        "name": "n",
                    }
                ]
            )
        )
    with pytest.raises(ValueError, match="unknown role"):
        load_accounts(
            json.dumps(
                [
                    {
                        "username": "x",
                        "password": "p",
                        "userId": "user_1",
                        "role": "root",
                        "name": "n",
                    }
                ]
            )
        )


# --- settings: zero-config default and fail-loud branches ---


def test_settings_default_to_demo_values_without_env() -> None:
    settings = load_auth_settings()
    assert settings.session_ttl_seconds == 86_400
    assert [a.username for a in settings.accounts] == ["student1", "student2", "teacher1"]


def test_settings_reject_invalid_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "abc")
    with pytest.raises(ValueError, match="must be an integer"):
        load_auth_settings()
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "0")
    with pytest.raises(ValueError, match="must be positive"):
        load_auth_settings()


def test_settings_accept_custom_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SESSION_SECRET", "custom-secret")
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv(
        "AUTH_SYNTHETIC_ACCOUNTS",
        json.dumps(
            [
                {
                    "username": "u1",
                    "password": "p1",
                    "userId": "user_44444444444444444444444444444444",
                    "role": "admin",
                    "name": "管理员",
                }
            ],
            ensure_ascii=False,
        ),
    )
    settings = load_auth_settings()
    assert settings.session_secret == "custom-secret"
    assert settings.session_ttl_seconds == 60
    assert [a.username for a in settings.accounts] == ["u1"]


# --- login route ---


def test_login_returns_bearer_session_for_each_default_account() -> None:
    with _client() as client:
        for username, password, user_id, role in [
            ("student1", "demo-student-1", "user_11111111111111111111111111111111", "student"),
            ("student2", "demo-student-2", "user_22222222222222222222222222222222", "student"),
            ("teacher1", "demo-teacher-1", "user_33333333333333333333333333333333", "teacher"),
        ]:
            response = _login(client, username, password)
            assert response.status_code == 200
            data = response.json()
            assert set(data) == {"token", "tokenType", "expiresAt", "user"}
            assert data["tokenType"] == "bearer"
            assert data["token"]
            assert data["expiresAt"].endswith("+00:00")
            assert data["user"] == {
                "userId": user_id,
                "role": role,
                "name": data["user"]["name"],
            }


def test_login_failures_share_one_401_envelope() -> None:
    with _client() as client:
        wrong_password = _login(client, "student1", "wrong")
        unknown_user = _login(client, "ghost", "demo-student-1")
        for response in (wrong_password, unknown_user):
            assert response.status_code == 401
            data = response.json()
            assert set(data) == {"code", "message", "requestId", "details"}
            assert data["code"] == "INVALID_CREDENTIALS"
            assert data["message"] == "用户名或密码错误"
            assert data["details"] == {}
            assert data["requestId"] == response.headers["x-request-id"]
        # 防枚举：两种失败返回同一文案，仅 requestId 不同
        assert wrong_password.json()["message"] == unknown_user.json()["message"]


def test_login_validates_request_body() -> None:
    with _client() as client:
        response = client.post("/api/v1/auth/login", json={"username": "student1"})
    assert response.status_code == 422


def test_custom_accounts_env_drives_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AUTH_SYNTHETIC_ACCOUNTS",
        json.dumps(
            [
                {
                    "username": "u1",
                    "password": "p1",
                    "userId": "user_44444444444444444444444444444444",
                    "role": "admin",
                    "name": "管理员",
                }
            ],
            ensure_ascii=False,
        ),
    )
    with _client() as client:
        assert _login(client, "u1", "p1").status_code == 200
        assert _login(client, "student1", "demo-student-1").status_code == 401


# --- session token lifecycle ---


def _crafted_token(secret: str, **overrides: Any) -> str:
    claims: dict[str, Any] = {
        "sub": "user_11111111111111111111111111111111",
        "role": "student",
        "name": "学生甲",
        "iat": 1,
        "exp": 4102444800,
        "jti": "test-jti",
    }
    claims.update(overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


def test_issued_token_round_trips_to_the_same_user() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    issued = authority.issue(_STUDENT)
    assert authority.parse(issued.token) == _STUDENT


def test_tampered_token_is_rejected() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    issued = authority.issue(_STUDENT)
    assert authority.parse(issued.token + "x") is None
    assert authority.parse(issued.token[:-1]) is None


def test_expired_token_is_rejected() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=-1)
    issued = authority.issue(_STUDENT)
    assert authority.parse(issued.token) is None


def test_revoked_token_is_rejected_and_revocation_is_idempotent() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    issued = authority.issue(_STUDENT)
    authority.revoke(issued.token)
    authority.revoke(issued.token)
    assert authority.parse(issued.token) is None


def test_token_with_invalid_claims_is_rejected() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    assert authority.parse(_crafted_token(_SECRET, role="hacker")) is None
    assert authority.parse(_crafted_token(_SECRET, sub=123)) is None
    assert authority.parse(_crafted_token(_SECRET, name=None)) is None


def test_token_with_non_string_jti_is_rejected_by_claim_validation() -> None:
    """PyJWT refuses non-string registered claims at decode time, so a token
    whose `jti` is not a string is unusable — `parse` collapses it to `None`
    like any other invalid token."""
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    assert authority.parse(_crafted_token(_SECRET, jti=123)) is None


def test_revoke_ignores_unusable_tokens() -> None:
    authority = SessionAuthority(secret=_SECRET, ttl_seconds=3600)
    authority.revoke("not-a-token")
    authority.revoke(_crafted_token("wrong-secret-0123456789abcdef0123456789abcdef"))


# --- logout route ---


def test_logout_revokes_and_is_idempotent() -> None:
    with _client() as client:
        token = _login(client, "student1", "demo-student-1").json()["token"]
        first = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        second = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200
    assert first.json() == {"revoked": True}
    assert second.json() == {"revoked": True}


def test_logout_without_usable_token_returns_401() -> None:
    with _client() as client:
        assert client.post("/api/v1/auth/logout").status_code == 401
        malformed = client.post("/api/v1/auth/logout", headers={"Authorization": "Basic abc"})
        assert malformed.status_code == 401
        assert malformed.json()["code"] == "TOKEN_REQUIRED"


def test_logout_with_unknown_token_still_succeeds() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/auth/logout", headers={"Authorization": "Bearer not-a-real-token"}
        )
    assert response.status_code == 200
    assert response.json() == {"revoked": True}


# --- account dataclass surface (kept small on purpose) ---


def test_account_is_frozen_identity_with_credential() -> None:
    account = Account(username="u", password="p", session_user=_STUDENT)
    assert account.session_user == _STUDENT
