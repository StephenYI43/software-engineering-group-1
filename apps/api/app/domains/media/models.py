"""Media configuration and per-user preferences."""

from datetime import datetime
from decimal import Decimal
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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class AvatarConfigVersion(Base):
    __tablename__ = "avatar_config_versions"
    __table_args__ = (
        UniqueConstraint("config_key", "version"),
        CheckConstraint("length(id) > 0", name="id_nonempty"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("status IN ('draft','active','retired')", name="status"),
        CheckConstraint(
            "jsonb_typeof(config) = 'object' AND "
            """(config -> 'schemaVersion') IS NOT DISTINCT FROM '"1.0"'::jsonb""",
            name="config_schema",
        ),
        Index(
            "uq_avatar_config_active",
            "config_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), server_default="draft")
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AvatarProfile(Base):
    __tablename__ = "avatar_profiles"
    __table_args__ = (
        CheckConstraint("length(id) > 0", name="id_nonempty"),
        CheckConstraint("volume BETWEEN 0 AND 1", name="volume"),
        CheckConstraint("speech_rate BETWEEN 0.5 AND 2", name="speech_rate"),
        CheckConstraint("updated_at >= created_at", name="timestamps"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    config_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("avatar_config_versions.id", ondelete="RESTRICT"), index=True
    )
    auto_play: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    volume: Mapped[Decimal] = mapped_column(Numeric(3, 2), server_default=text("1.00"))
    speech_rate: Mapped[Decimal] = mapped_column(Numeric(3, 2), server_default=text("1.00"))
    subtitles_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
