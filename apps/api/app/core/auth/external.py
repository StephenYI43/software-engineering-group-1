"""Optional external login endpoints and single-process flow state."""

import base64
import hashlib
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from os import getenv
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.auth.context import auth_context
from app.core.auth.providers import (
    OAuthConfig,
    Provider,
    SchoolConfig,
    SmsConfig,
    authorization_url,
    exchange_subject,
    invalid_credentials,
    protect_wechat_logs,
    verify_sms,
)
from app.core.auth.schemas import LoginResponse, SessionUser
from app.core.auth.settings import DEFAULT_SESSION_SECRET, AuthSettings
from app.core.errors import ApiError

type Method = Literal["password", "sms", "github", "wechat", "school"]
type Phone = Annotated[str, Field(pattern=r"^\+[1-9][0-9]{7,14}$")]
_PROVIDERS: tuple[Provider, ...] = ("github", "wechat", "school")
_FLOW_COOKIE = "external_login_flow"
_FLOW_TTL = 300
_AUTH_PATH = "/api/v1/auth"


class ExternalConfig(BaseModel):
    web_origin: str
    github: OAuthConfig | None = None
    wechat: OAuthConfig | None = None
    school: SchoolConfig | None = None
    sms: SmsConfig | None = None
    bindings: dict[Literal["sms", "github", "wechat", "school"], dict[str, str]] = Field(
        default_factory=dict
    )

    @field_validator("web_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
            or value != f"{url.scheme}://{url.netloc}"
            or (
                url.scheme != "https"
                and (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"})
            )
        ):
            raise ValueError("web_origin must be an HTTPS origin or a loopback HTTP origin")
        return value

    def oauth(self, provider: Provider) -> OAuthConfig:
        config = {"github": self.github, "wechat": self.wechat, "school": self.school}[provider]
        if config is None:
            raise method_unavailable()
        return config

    def redirect_uri(self, provider: Provider) -> str:
        return f"{self.web_origin}/login/{provider}"

    def issuer(self, provider: Literal["sms", "github", "wechat", "school"]) -> str:
        if provider == "school" and self.school is not None:
            return self.school.issuer
        if provider == "wechat" and self.wechat is not None:
            return f"wechat:{self.wechat.client_id}"
        return "phone:e164" if provider == "sms" else "https://github.com"


class MethodsResponse(BaseModel):
    methods: list[Method]


class AuthorizationResponse(BaseModel):
    authorization_url: str = Field(serialization_alias="authorizationUrl")


class OAuthExchange(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class SmsSend(BaseModel):
    phone: Phone


class SmsLogin(SmsSend):
    code: str = Field(pattern=r"^[0-9]{4,10}$")


@dataclass(frozen=True, slots=True)
class OAuthFlow:
    provider: Provider
    state: str
    verifier: str
    nonce: str
    expires_at: float


class LoginAttempts:
    def __init__(self) -> None:
        self.flows: dict[str, OAuthFlow] = {}
        self.sms_limits: dict[tuple[str, bool], float] = {}
        self.lock = Lock()

    def start(self, provider: Provider) -> tuple[str, OAuthFlow]:
        now = monotonic()
        flow = OAuthFlow(
            provider,
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            now + _FLOW_TTL,
        )
        flow_id = secrets.token_urlsafe(32)
        with self.lock:
            self.flows = {key: value for key, value in self.flows.items() if value.expires_at > now}
            if len(self.flows) >= 1024:
                raise ApiError(429, "RATE_LIMITED", "操作过于频繁，请稍后重试")
            self.flows[flow_id] = flow
        return flow_id, flow

    def consume(self, flow_id: str, provider: Provider, state: str) -> OAuthFlow:
        with self.lock:
            flow = self.flows.get(flow_id)
            if (
                flow is None
                or flow.provider != provider
                or flow.expires_at <= monotonic()
                or not secrets.compare_digest(flow.state, state)
            ):
                raise invalid_credentials()
            del self.flows[flow_id]
        return flow

    def throttle_sms(self, phone: str, sending: bool) -> None:
        now = monotonic()
        key = (phone, sending)
        with self.lock:
            if self.sms_limits.get(key, 0) > now:
                raise ApiError(429, "RATE_LIMITED", "操作过于频繁，请稍后重试")
            self.sms_limits[key] = now + (60 if sending else 3)


def method_unavailable() -> ApiError:
    return ApiError(404, "LOGIN_METHOD_UNAVAILABLE", "该登录方式未启用")


def load_external_config(
    settings: AuthSettings, *, persistent: bool = False
) -> ExternalConfig | None:
    raw = getenv("AUTH_EXTERNAL_LOGIN")
    if not raw:
        return None
    if (
        settings.session_secret == DEFAULT_SESSION_SECRET
        or len(settings.session_secret.encode()) < 32
        or (not persistent and not getenv("AUTH_SYNTHETIC_ACCOUNTS"))
    ):
        raise ValueError(
            "external login requires a private session key and explicit local accounts"
        )
    try:
        config = ExternalConfig.model_validate_json(raw)
    except ValidationError:
        raise ValueError("AUTH_EXTERNAL_LOGIN configuration is invalid") from None
    if persistent:
        if any(config.bindings.values()):
            raise ValueError(
                "database mode requires stored identity bindings; clear config bindings"
            )
        return config
    user_ids = {account.session_user.user_id for account in settings.accounts}
    if len(user_ids) != len(settings.accounts) or any(
        not subject or user_id not in user_ids
        for bindings in config.bindings.values()
        for subject, user_id in bindings.items()
    ):
        raise ValueError("AUTH_EXTERNAL_LOGIN bindings must reference unique local accounts")
    return config


def provider_client() -> Iterator[httpx.Client]:
    # WeChat sends credentials in query parameters; do not emit outbound request URLs.
    with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
        yield client


def create_external_router(
    settings: AuthSettings,
    *,
    persistent: bool = False,
) -> APIRouter:
    config = load_external_config(settings, persistent=persistent)
    if config is not None and config.wechat is not None:
        protect_wechat_logs()
    attempts = LoginAttempts()
    users = {account.session_user.user_id: account.session_user for account in settings.accounts}
    router = APIRouter(prefix=_AUTH_PATH, tags=["auth"])

    def enabled() -> ExternalConfig:
        if config is None:
            raise method_unavailable()
        return config

    def linked_user(
        request: Request, method: Literal["sms", "github", "wechat", "school"], subject: str
    ) -> SessionUser | None:
        with auth_context(request) as context:
            if context.repository is not None:
                return context.repository.external_user(method, enabled().issuer(method), subject)
        user_id = enabled().bindings.get(method, {}).get(subject)
        return users.get(user_id) if user_id is not None else None

    def login_response(
        request: Request,
        method: Literal["sms", "github", "wechat", "school"],
        subject: str,
    ) -> LoginResponse:
        with auth_context(request) as context:
            user = (
                context.repository.external_user(method, enabled().issuer(method), subject)
                if context.repository is not None
                else linked_user(request, method, subject)
            )
            if user is None:
                raise invalid_credentials()
            return context.issue(user)

    @router.get("/methods")
    def methods() -> MethodsResponse:
        result: list[Method] = ["password"] if persistent or settings.accounts else []
        if config is not None:
            result.extend(provider for provider in _PROVIDERS if getattr(config, provider))
            if config.sms is not None:
                result.append("sms")
        return MethodsResponse(methods=result)

    @router.post("/oauth/{provider}/start")
    def start(provider: Provider, response: Response) -> AuthorizationResponse:
        external = enabled()
        provider_config = external.oauth(provider)
        flow_id, flow = attempts.start(provider)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest())
        response.set_cookie(
            _FLOW_COOKIE,
            flow_id,
            max_age=_FLOW_TTL,
            httponly=True,
            secure=external.web_origin.startswith("https://"),
            samesite="lax",
            path=_AUTH_PATH,
        )
        return AuthorizationResponse(
            authorization_url=authorization_url(
                provider,
                provider_config,
                external.redirect_uri(provider),
                flow.state,
                challenge.decode().rstrip("="),
                flow.nonce,
            )
        )

    @router.post("/oauth/{provider}/exchange")
    def exchange(
        request: Request,
        provider: Provider,
        payload: OAuthExchange,
        response: Response,
        client: Annotated[httpx.Client, Depends(provider_client)],
        flow_id: Annotated[str, Cookie(alias=_FLOW_COOKIE)] = "",
    ) -> LoginResponse:
        external = enabled()
        provider_config = external.oauth(provider)
        flow = attempts.consume(flow_id, provider, payload.state)
        subject = exchange_subject(
            client,
            provider,
            provider_config,
            external.redirect_uri(provider),
            payload.code,
            flow.verifier,
            flow.nonce,
        )
        result = login_response(request, provider, subject)
        response.delete_cookie(_FLOW_COOKIE, path=_AUTH_PATH)
        return result

    @router.post("/sms/send", status_code=204)
    def send(
        request: Request,
        payload: SmsSend,
        client: Annotated[httpx.Client, Depends(provider_client)],
    ) -> None:
        sms = enabled().sms
        if sms is None:
            raise method_unavailable()
        if linked_user(request, "sms", payload.phone) is not None:
            attempts.throttle_sms(payload.phone, sending=True)
            verify_sms(client, sms, payload.phone)

    @router.post("/sms/login")
    def sms_login(
        request: Request,
        payload: SmsLogin,
        client: Annotated[httpx.Client, Depends(provider_client)],
    ) -> LoginResponse:
        sms = enabled().sms
        if sms is None:
            raise method_unavailable()
        user = linked_user(request, "sms", payload.phone)
        if user is None:
            raise invalid_credentials()
        attempts.throttle_sms(payload.phone, sending=False)
        verify_sms(client, sms, payload.phone, payload.code)
        return login_response(request, "sms", payload.phone)

    return router
