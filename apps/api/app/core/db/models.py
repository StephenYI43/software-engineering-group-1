"""Platform tables only. Domain owners register their models in metadata.py."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("id ~ '^user_[0-9a-f]{32}$'", name="id_format"),
        CheckConstraint("username ~ '^[A-Za-z0-9_.-]{1,64}$'", name="username_format"),
        CheckConstraint("username_key = lower(username)", name="username_key"),
        CheckConstraint("status IN ('active','disabled')", name="status"),
        CheckConstraint("updated_at >= created_at", name="timestamps"),
        Index("ix_users_status", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    username_key: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint("length(btrim(display_name)) BETWEEN 1 AND 100", name="name"),
        CheckConstraint(
            "student_number IS NULL OR length(student_number) > 0", name="student_number"
        ),
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    student_number: Mapped[str | None] = mapped_column(String(32), unique=True)
    major: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("code IN ('student','teacher','admin')", name="code"),)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        CheckConstraint("revoked_at IS NULL OR revoked_at >= granted_at", name="timestamps"),
        CheckConstraint("NOT is_primary OR revoked_at IS NULL", name="primary_active"),
        Index("uq_user_roles_primary", "user_id", unique=True, postgresql_where=text("is_primary")),
        Index("ix_user_roles_role_user", "role_code", "user_id"),
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(
        String(16), ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    granted_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("jti_digest ~ '^[0-9a-f]{64}$'", name="digest_format"),
        CheckConstraint("expires_at > issued_at", name="expiry"),
        CheckConstraint("request_id ~ '^req_[0-9a-f]{32}$'", name="request_format"),
        CheckConstraint(
            "(revoked_at IS NULL AND revoke_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoke_reason IS NOT NULL AND revoke_reason IN "
            "('logout','admin_revoke','role_changed','password_changed'))",
            name="revocation",
        ),
        Index("ix_auth_sessions_user_expiry", "user_id", "expires_at"),
        Index("ix_auth_sessions_expiry", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    jti_digest: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="RESTRICT"))
    role_code: Mapped[str] = mapped_column(
        String(16), ForeignKey("roles.code", ondelete="RESTRICT")
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(36))


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user','system')", name="actor_type"),
        CheckConstraint("result IN ('succeeded','failed','denied')", name="result"),
        CheckConstraint("request_id ~ '^req_[0-9a-f]{32}$'", name="request_format"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
        Index("ix_admin_audit_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_admin_audit_target_time", "target_type", "target_id", "occurred_at"),
        Index("ix_admin_audit_request", "request_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(String(16), server_default="user")
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SystemConfigVersion(Base):
    __tablename__ = "system_config_versions"
    __table_args__ = (
        UniqueConstraint("config_key", "version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("status IN ('draft','active','retired')", name="status"),
        CheckConstraint("jsonb_typeof(value) = 'object'", name="value_object"),
        CheckConstraint(
            "value ? 'schemaVersion' AND value ->> 'schemaVersion' = '1.0'",
            name="schema_version",
        ),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL) OR "
            "(status <> 'draft' AND activated_at IS NOT NULL)",
            name="activation",
        ),
        Index(
            "uq_system_config_active",
            "config_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
