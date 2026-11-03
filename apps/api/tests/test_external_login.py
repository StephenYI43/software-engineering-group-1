import base64
import hashlib
import json
import time
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.auth.external import provider_client
from app.main import create_app

AUTH = "/api/v1/auth"
PHONE = "+15550100001"
ORIGIN = "https://learning.example"


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    oauth = {"client_id": "demo-client", "client_secret": "demo-secret"}
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-only-session-secret-not-for-deployment")
    monkeypatch.setenv(
        "AUTH_SYNTHETIC_ACCOUNTS",
        json.dumps(
            [
                {
                    "username": "tester",
                    "password": "example-only",
                    "userId": "local",
                    "role": "student",
                    "name": "测试用户",
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "AUTH_EXTERNAL_LOGIN",
        json.dumps(
            {
                "web_origin": ORIGIN,
                "github": oauth,
                "wechat": oauth,
                "school": {
                    **oauth,
                    "issuer": "https://school.example",
                    "authorization_endpoint": "https://school.example/authorize",
                    "token_endpoint": "https://school.example/token",
                    "public_key": public_key.decode(),
                },
                "sms": {
                    "account_sid": "AC" + "0" * 32,
                    "service_sid": "VA" + "0" * 32,
                    "auth_token": "test",
                },
                "bindings": {
                    "github": {"42": "local"},
                    "wechat": {"openid-1": "local"},
                    "school": {"student-1": "local"},
                    "sms": {PHONE: "local"},
                },
            }
        ),
    )
    authorization: dict[str, str] = {}

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.weixin.qq.com":
            assert request.url.params["secret"] == "demo-secret"
            assert request.url.params["appid"] == "demo-client"
            return httpx.Response(200, json={"openid": "openid-1"})
        if request.url.host == "verify.twilio.com":
            fields = parse_qs(request.content.decode())
            assert fields["To"] == [PHONE]
            if request.url.path.endswith("/Verifications"):
                assert fields["Channel"] == ["sms"]
                return httpx.Response(201, json={"to": PHONE, "status": "pending"})
            status = "approved" if fields["Code"] == ["123456"] else "pending"
            return httpx.Response(200, json={"to": PHONE, "status": status})
        if request.url.host == "api.github.com":
            assert request.headers["Authorization"] == "Bearer provider-token"
            return httpx.Response(200, json={"id": 42, "role": "admin"})
        fields = parse_qs(request.content.decode())
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(fields["code_verifier"][0].encode()).digest())
            .decode()
            .rstrip("=")
        )
        assert challenge == authorization["code_challenge"]
        assert fields["redirect_uri"] == [authorization["redirect_uri"]]
        if request.url.host == "github.com":
            return httpx.Response(200, json={"access_token": "provider-token"})
        now = int(time.time())
        claims = {
            "iss": "https://school.example",
            "aud": "demo-client",
            "iat": now,
            "exp": now + 60,
            "sub": "student-1",
            "nonce": authorization["nonce"],
        }
        if fields["code"] == ["wrong-nonce"]:
            claims["nonce"] = "other-flow"
        if fields["code"] == ["wrong-issuer"]:
            claims["iss"] = "https://other.example"
        if fields["code"] == ["wrong-audience"]:
            claims["aud"] = "other-client"
        if fields["code"] == ["expired"]:
            claims["exp"] = now - 1
        signing_key = (
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            if fields["code"] == ["wrong-key"]
            else private_key
        )
        return httpx.Response(
            200,
            json={
                "id_token": jwt.encode(
                    claims,
                    signing_key,
                    algorithm="RS256",
                )
            },
        )

    app = create_app()
    with httpx.Client(transport=httpx.MockTransport(provider)) as upstream:
        app.dependency_overrides[provider_client] = lambda: upstream
        with TestClient(app, base_url=ORIGIN) as client:

            def record_authorization(response: httpx.Response) -> None:
                if not response.request.url.path.endswith("/start"):
                    return
                for key, values in parse_qs(
                    urlsplit(response.json()["authorizationUrl"]).query
                ).items():
                    authorization[key] = values[0]

            client.event_hooks["response"].append(lambda response: response.read())
            client.event_hooks["response"].append(record_authorization)
            yield client


def begin(browser: TestClient, provider: str) -> dict[str, str]:
    response = browser.post(f"{AUTH}/oauth/{provider}/start")
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    return {
        name: values[0]
        for name, values in parse_qs(urlsplit(response.json()["authorizationUrl"]).query).items()
    }


@pytest.mark.parametrize("provider", ["github", "wechat", "school"])
def test_external_oauth_uses_local_role_and_consumes_state(
    browser: TestClient,
    provider: str,
) -> None:
    state = begin(browser, provider)["state"]
    path = f"{AUTH}/oauth/{provider}/exchange"
    payload = {"code": "valid", "state": state}
    with TestClient(browser.app, base_url=ORIGIN) as other_browser:
        assert other_browser.post(path, json=payload).status_code == 401
    assert browser.post(path, json={**payload, "state": "x" * 43}).status_code == 401
    flow = browser.cookies.get("external_login_flow")
    response = browser.post(path, json=payload)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "student"
    token = response.json()["token"]
    assert browser.app.state.session_authority.parse(token).user_id == "local"
    browser.cookies.set("external_login_flow", flow, domain="learning.example", path=AUTH)
    assert browser.post(path, json=payload).status_code == 401


@pytest.mark.parametrize(
    "code", ["wrong-nonce", "wrong-issuer", "wrong-audience", "expired", "wrong-key"]
)
def test_school_rejects_invalid_id_tokens(browser: TestClient, code: str) -> None:
    state = begin(browser, "school")["state"]
    response = browser.post(f"{AUTH}/oauth/school/exchange", json={"code": code, "state": state})
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_sms_requires_binding_and_provider_approval(browser: TestClient) -> None:
    assert browser.post(f"{AUTH}/sms/send", json={"phone": "+15550100002"}).status_code == 204
    assert browser.post(f"{AUTH}/sms/send", json={"phone": PHONE}).status_code == 204
    assert browser.post(f"{AUTH}/sms/send", json={"phone": PHONE}).status_code == 429
    assert (
        browser.post(
            f"{AUTH}/sms/login", json={"phone": "+15550100002", "code": "123456"}
        ).status_code
        == 401
    )
    response = browser.post(f"{AUTH}/sms/login", json={"phone": PHONE, "code": "123456"})
    assert response.status_code == 200
    assert response.json()["user"]["userId"] == "local"


def test_default_methods_and_disabled_oauth() -> None:
    with TestClient(create_app()) as client:
        assert client.get(f"{AUTH}/methods").json() == {"methods": ["password"]}
        assert client.post(f"{AUTH}/oauth/github/start").status_code == 404
