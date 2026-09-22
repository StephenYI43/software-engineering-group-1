"""Wire schemas for login/logout and the session identity they carry (Issue #45).

Wire fields are camelCase per `docs/code-standards.md:48`; Python attributes are
snake_case and map through `serialization_alias`. The role set mirrors the
platform contract (`packages/contracts/platform/README.md`): student / teacher /
admin, never free text.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["student", "teacher", "admin"]


class SessionUser(BaseModel):
    """The verified identity every authenticated request carries."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(serialization_alias="userId")
    role: Role
    name: str


class LoginRequest(BaseModel):
    """Credentials submitted by the client. Plaintext over the wire is a known
    S1 scope limitation; nothing here is real student data."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    """A fresh session token plus the identity it carries."""

    model_config = ConfigDict(populate_by_name=True)

    token: str
    token_type: Literal["bearer"] = Field(default="bearer", serialization_alias="tokenType")
    expires_at: str = Field(serialization_alias="expiresAt")
    user: SessionUser


class LogoutResponse(BaseModel):
    """Logout is idempotent: revoking an unknown token is still a success, and
    the response never reveals whether the token was previously valid."""

    revoked: bool
