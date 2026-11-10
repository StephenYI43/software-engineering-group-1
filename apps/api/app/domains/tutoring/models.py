"""Tutoring persistence models (M3). Inherit the single platform Base."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("series", "version_label"),
        CheckConstraint("id ~ '^promptver_[0-9a-f]{32}$'", name="id_format"),
        CheckConstraint("length(btrim(series)) > 0", name="series"),
        CheckConstraint("length(btrim(version_label)) > 0", name="version_label"),
        CheckConstraint(
            "template_path ~ '^ai/prompts/[^/]+\\.md$'",
            name="template_path",
        ),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256"),
        CheckConstraint("status IN ('draft','active','retired')", name="status"),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND retired_at IS NOT NULL AND activated_at IS NULL)",
            name="lifecycle",
        ),
        Index(
            "uq_prompt_versions_active",
            "series",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_prompt_versions_series_status", "series", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series: Mapped[str] = mapped_column(String(64))
    version_label: Mapped[str] = mapped_column(String(64))
    template_path: Mapped[str] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelConfigVersion(Base):
    __tablename__ = "model_config_versions"
    __table_args__ = (
        UniqueConstraint("config_key", "version"),
        CheckConstraint("id ~ '^modelcfg_[0-9a-f]{32}$'", name="id_format"),
        CheckConstraint("length(btrim(config_key)) > 0", name="config_key"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("length(btrim(provider)) > 0", name="provider"),
        CheckConstraint("length(btrim(model_name)) BETWEEN 1 AND 100", name="model_name"),
        CheckConstraint("(provider = 'mock') = is_mock", name="mock_consistency"),
        CheckConstraint("temperature >= 0 AND temperature <= 2", name="temperature"),
        CheckConstraint("max_output_tokens > 0", name="max_output_tokens"),
        CheckConstraint("timeout_seconds > 0", name="timeout_seconds"),
        CheckConstraint("status IN ('draft','active','retired')", name="status"),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND retired_at IS NOT NULL AND activated_at IS NULL)",
            name="lifecycle",
        ),
        Index(
            "uq_model_config_versions_active",
            "config_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_model_config_versions_config_key_status", "config_key", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(64), server_default="tutoring_default")
    version: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str] = mapped_column(String(100))
    is_mock: Mapped[bool] = mapped_column(Boolean)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2))
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[float] = mapped_column(Numeric(6, 2))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TutoringSession(Base):
    __tablename__ = "tutoring_sessions"
    __table_args__ = (
        CheckConstraint("length(btrim(id)) > 0", name="id_present"),
        CheckConstraint(
            "current_stage IN ('thought','hint','step','summary')",
            name="current_stage",
        ),
        CheckConstraint("updated_at >= created_at", name="timestamps"),
        Index("ix_tutoring_sessions_student_updated", "student_user_id", "updated_at"),
        Index("ix_tutoring_sessions_course_id", "course_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT")
    )
    # Nullable and without FK until the courses table exists (M5). Do not invent a stub table.
    course_id: Mapped[str | None] = mapped_column(String(64))
    current_stage: Mapped[str] = mapped_column(String(16), server_default="thought")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TutoringTurn(Base):
    __tablename__ = "tutoring_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        CheckConstraint("id ~ '^turn_[0-9a-f]{32}$'", name="id_format"),
        CheckConstraint("seq > 0", name="seq"),
        CheckConstraint("request_id ~ '^req_[0-9a-f]{32}$'", name="request_format"),
        CheckConstraint(
            "char_length(student_content) BETWEEN 1 AND 2000",
            name="student_content",
        ),
        CheckConstraint("stage IN ('thought','hint','step','summary')", name="stage"),
        CheckConstraint("status IN ('active','completed','aborted')", name="status"),
        CheckConstraint("(status = 'completed') = is_complete", name="complete_consistency"),
        CheckConstraint("(status = 'active') = (settled_at IS NULL)", name="settled_state"),
        CheckConstraint(
            "settled_at IS NULL OR settled_at >= created_at",
            name="settled_timestamp",
        ),
        CheckConstraint(
            "(status = 'aborted') = (abort_reason IS NOT NULL)",
            name="abort_reason_state",
        ),
        CheckConstraint(
            "abort_reason IS NULL OR abort_reason IN "
            "('client_stop','client_disconnect','model_error','retrieval_error','server_restart')",
            name="abort_reason",
        ),
        CheckConstraint("error_code IS NULL OR status = 'aborted'", name="error_code_state"),
        CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('MODEL_OUTPUT_INVALID','MODEL_REFUSED','MODEL_TIMEOUT',"
            "'RETRIEVAL_UNAVAILABLE','TURN_ABORTED')",
            name="error_code",
        ),
        CheckConstraint("error_reason IS NULL OR error_code IS NOT NULL", name="error_reason"),
        CheckConstraint(
            "abort_reason NOT IN ('model_error','retrieval_error') OR error_code IS NOT NULL",
            name="failure_error_code",
        ),
        CheckConstraint(
            "status <> 'completed' OR (assistant_content IS NOT NULL "
            "AND emotion IS NOT NULL AND action IS NOT NULL)",
            name="completed_payload",
        ),
        CheckConstraint(
            "emotion IS NULL OR emotion IN ('neutral','encouraging','thinking','celebrating')",
            name="emotion",
        ),
        CheckConstraint(
            "action IS NULL OR action IN ('idle','nod','point','write')",
            name="action",
        ),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="input_tokens"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="output_tokens"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_ms"),
        CheckConstraint("jsonb_typeof(follow_ups) = 'object'", name="follow_ups_object"),
        CheckConstraint(
            """(follow_ups -> 'schemaVersion') IS NOT DISTINCT FROM '"1.0"'::jsonb""",
            name="follow_ups_schema",
        ),
        CheckConstraint(
            "jsonb_typeof(follow_ups -> 'items') = 'array' "
            "AND jsonb_array_length(follow_ups -> 'items') <= 3",
            name="follow_ups_items",
        ),
        Index(
            "uq_tutoring_turns_active_session",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_tutoring_turns_prompt_version_id", "prompt_version_id"),
        Index("ix_tutoring_turns_model_config_version_id", "model_config_version_id"),
        Index("ix_tutoring_turns_status_created", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tutoring_sessions.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(36))
    student_content: Mapped[str] = mapped_column(Text)
    assistant_content: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="active")
    is_complete: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_mock: Mapped[bool] = mapped_column(Boolean)
    has_evidence: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    emotion: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str | None] = mapped_column(String(16))
    follow_ups: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{\"schemaVersion\":\"1.0\",\"items\":[]}'::jsonb")
    )
    prompt_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    model_config_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("model_config_versions.id", ondelete="RESTRICT")
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    abort_reason: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(32))
    error_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
