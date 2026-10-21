"""Auth configuration from environment variables with documented demo defaults.

Zero-config startup is a hard requirement (`docs/development.md:21`): a fresh
clone must run `uv run uvicorn app.main:app` and be able to log in without
touching `.env`. The defaults below are synthetic demo values; anything that is
not a course demo must override all three (`docs/code-standards.md:107`).
Malformed configuration fails loud at import time, never silently degrades.
"""

from dataclasses import dataclass

from app.core.auth.accounts import Account, load_accounts

#: Demo-only signing secret. Insecure by design; override via `AUTH_SESSION_SECRET`.
DEFAULT_SESSION_SECRET = "demo-only-session-secret-change-me-before-anything-real"
DEFAULT_SESSION_TTL_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Resolved auth configuration owned by `app/core/auth`."""

    session_secret: str
    session_ttl_seconds: int
    accounts: tuple[Account, ...]


def _env(name: str, default: str) -> str:
    import os

    value = os.environ.get(name)
    return value if value is not None and value != "" else default


def load_auth_settings() -> AuthSettings:
    """Read the environment and validate every branch; raises on misuse."""
    secret = _env("AUTH_SESSION_SECRET", DEFAULT_SESSION_SECRET)
    ttl_raw = _env("AUTH_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
    try:
        ttl = int(ttl_raw)
    except ValueError:
        raise ValueError(f"AUTH_SESSION_TTL_SECONDS must be an integer, got {ttl_raw!r}") from None
    if ttl <= 0:
        raise ValueError(f"AUTH_SESSION_TTL_SECONDS must be positive, got {ttl}")
    accounts = load_accounts(_env("AUTH_SYNTHETIC_ACCOUNTS", ""))
    return AuthSettings(session_secret=secret, session_ttl_seconds=ttl, accounts=accounts)
