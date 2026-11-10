"""Create avatar configuration versions and user preferences.

Revision number is provisional pending M5's single-chain registration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_media_preferences"
down_revision: str | None = "0003_external_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avatar_config_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("config_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column(
            "created_by_user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("config_key", "version"),
        sa.CheckConstraint("length(id) > 0", name=op.f("ck_avatar_config_versions_id_nonempty")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_avatar_config_versions_version")),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')", name=op.f("ck_avatar_config_versions_status")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(config) = 'object' AND "
            """(config -> 'schemaVersion') IS NOT DISTINCT FROM '"1.0"'::jsonb""",
            name=op.f("ck_avatar_config_versions_config_schema"),
        ),
    )
    op.create_index(
        "uq_avatar_config_active",
        "avatar_config_versions",
        ["config_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "avatar_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "config_version_id",
            sa.String(64),
            sa.ForeignKey("avatar_config_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("auto_play", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("volume", sa.Numeric(3, 2), server_default=sa.text("1.00"), nullable=False),
        sa.Column("speech_rate", sa.Numeric(3, 2), server_default=sa.text("1.00"), nullable=False),
        sa.Column(
            "subtitles_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(id) > 0", name=op.f("ck_avatar_profiles_id_nonempty")),
        sa.CheckConstraint("volume BETWEEN 0 AND 1", name=op.f("ck_avatar_profiles_volume")),
        sa.CheckConstraint(
            "speech_rate BETWEEN 0.5 AND 2", name=op.f("ck_avatar_profiles_speech_rate")
        ),
        sa.CheckConstraint("updated_at >= created_at", name=op.f("ck_avatar_profiles_timestamps")),
    )
    op.create_index(
        "ix_avatar_profiles_config_version_id", "avatar_profiles", ["config_version_id"]
    )


def downgrade() -> None:
    op.drop_table("avatar_profiles")
    op.drop_table("avatar_config_versions")
