"""Outbound requests for explicitly configured identity providers."""

import logging
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator

from app.core.errors import ApiError

type Provider = Literal["github", "wechat", "school"]
_WECHAT_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"


class _WeChatLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # HTTPX logs the whole URL at INFO. This endpoint requires a secret in the query.
        return _WECHAT_TOKEN_URL not in record.getMessage()


def protect_wechat_logs() -> None:
    logger = logging.getLogger("httpx")
    if not any(isinstance(item, _WeChatLogFilter) for item in logger.filters):
        logger.addFilter(_WeChatLogFilter())


class OAuthConfig(BaseModel):
    client_id: str = Field(min_length=1)
    client_secret: SecretStr


class SchoolConfig(OAuthConfig):
    issuer: str
    authorization_endpoint: HttpUrl
    token_endpoint: HttpUrl
    public_key: str

    @field_validator("public_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        key = load_pem_public_key(value.encode())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("school requires an RSA public key of at least 2048 bits")
        return value

    @field_validator("issuer")
    @classmethod
    def validate_issuer(cls, issuer: str) -> str:
        cls.require_https(HttpUrl(issuer))
        return issuer

    @field_validator("authorization_endpoint", "token_endpoint")
    @classmethod
    def require_https(cls, url: HttpUrl) -> HttpUrl:
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise ValueError(
                "school endpoints require HTTPS without credentials, query or fragment"
            )
        return url


class SmsConfig(BaseModel):
    account_sid: str = Field(pattern=r"^AC[0-9a-fA-F]{32}$")
    service_sid: str = Field(pattern=r"^VA[0-9a-fA-F]{32}$")
    auth_token: SecretStr


def invalid_credentials() -> ApiError:
    return ApiError(401, "INVALID_CREDENTIALS", "登录凭证无效或账号未绑定")


def upstream_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = client.request(method, url, **kwargs)
        if response.status_code == 429:
            raise ApiError(429, "RATE_LIMITED", "操作过于频繁，请稍后重试")
        if response.status_code >= 500 or 300 <= response.status_code < 400:
            raise ApiError(503, "PROVIDER_UNAVAILABLE", "登录服务暂不可用")
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise ApiError(503, "PROVIDER_UNAVAILABLE", "登录服务暂不可用") from None
    if not isinstance(data, dict):
        raise ApiError(503, "PROVIDER_UNAVAILABLE", "登录服务暂不可用")
    if response.status_code in (401, 403):
        raise ApiError(503, "PROVIDER_UNAVAILABLE", "登录服务暂不可用")
    if response.is_error:
        raise invalid_credentials()
    return data


def authorization_url(
    provider: Provider,
    config: OAuthConfig,
    redirect_uri: str,
    state: str,
    challenge: str,
    nonce: str,
) -> str:
    query = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider == "wechat":
        query.pop("client_id")
        query.pop("code_challenge")
        query.pop("code_challenge_method")
        query.update(appid=config.client_id, scope="snsapi_login")
        return f"https://open.weixin.qq.com/connect/qrconnect?{urlencode(query)}#wechat_redirect"
    if isinstance(config, SchoolConfig):
        query.update(scope="openid", nonce=nonce)
        return f"{config.authorization_endpoint}?{urlencode(query)}"
    return f"https://github.com/login/oauth/authorize?{urlencode(query)}"


def exchange_subject(
    client: httpx.Client,
    provider: Provider,
    config: OAuthConfig,
    redirect_uri: str,
    code: str,
    verifier: str,
    nonce: str,
) -> str:
    secret = config.client_secret.get_secret_value()
    if provider == "wechat":
        data = upstream_json(
            client,
            "GET",
            _WECHAT_TOKEN_URL,
            params={
                "appid": config.client_id,
                "secret": secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        subject = data.get("openid") if not data.get("errcode") else None
    elif isinstance(config, SchoolConfig):
        data = upstream_json(
            client,
            "POST",
            str(config.token_endpoint),
            auth=(config.client_id, secret),
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        subject = school_subject(config, data.get("id_token"), nonce)
    else:
        data = upstream_json(
            client,
            "POST",
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": config.client_id,
                "client_secret": secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token or not token.isascii():
            raise invalid_credentials()
        profile = upstream_json(
            client,
            "GET",
            "https://api.github.com/user",
            headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
        )
        github_id = profile.get("id")
        subject = str(github_id) if type(github_id) is int and github_id > 0 else None
    if not isinstance(subject, str) or not subject:
        raise invalid_credentials()
    return subject


def school_subject(config: SchoolConfig, token: object, nonce: str) -> object:
    if not isinstance(token, str):
        raise invalid_credentials()
    try:
        claims = jwt.decode(
            token,
            config.public_key,
            algorithms=["RS256"],
            audience=config.client_id,
            issuer=config.issuer,
            options={"require": ["exp", "iat", "sub", "nonce"], "strict_aud": True},
        )
    except jwt.InvalidTokenError:
        raise invalid_credentials() from None
    if claims.get("nonce") != nonce or claims.get("azp", config.client_id) != config.client_id:
        raise invalid_credentials()
    return claims.get("sub")


def verify_sms(
    client: httpx.Client, config: SmsConfig, phone: str, code: str | None = None
) -> None:
    endpoint = "Verifications" if code is None else "VerificationCheck"
    data = {"To": phone, "Channel": "sms"} if code is None else {"To": phone, "Code": code}
    result = upstream_json(
        client,
        "POST",
        f"https://verify.twilio.com/v2/Services/{config.service_sid}/{endpoint}",
        auth=(config.account_sid, config.auth_token.get_secret_value()),
        data=data,
    )
    if result.get("to") != phone or result.get("status") != (
        "pending" if code is None else "approved"
    ):
        raise invalid_credentials()
