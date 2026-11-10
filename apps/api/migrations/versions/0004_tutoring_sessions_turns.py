"""Tutoring sessions and turns, plus version registries used by those turns.

course_id is stored as a nullable string without a foreign key: the courses table
is not in this slice, and this revision must not invent a placeholder table.
session id format is intentionally not tightened to sess_ + 32 hex; create-session
HTTP is also out of scope.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_tutoring_sessions_turns"
down_revision: str | None = "0003_external_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("series", sa.String(64), nullable=False),
        sa.Column("version_label", sa.String(64), nullable=False),
        sa.Column("template_path", sa.String(255), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_versions")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_prompt_versions_created_by_user_id_users")),
        sa.UniqueConstraint("series", "version_label", name=op.f("uq_prompt_versions_series")),
        sa.CheckConstraint(
            "id ~ '^promptver_[0-9a-f]{32}$'", name=op.f("ck_prompt_versions_id_format")
        ),
        sa.CheckConstraint("length(btrim(series)) > 0", name=op.f("ck_prompt_versions_series")),
        sa.CheckConstraint(
            "length(btrim(version_label)) > 0", name=op.f("ck_prompt_versions_version_label")
        ),
        sa.CheckConstraint(
            "template_path ~ '^ai/prompts/[^/]+\\.md$'",
            name=op.f("ck_prompt_versions_template_path"),
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_prompt_versions_content_sha256")
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')", name=op.f("ck_prompt_versions_status")
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND retired_at IS NOT NULL AND activated_at IS NULL)",
            name=op.f("ck_prompt_versions_lifecycle"),
        ),
    )
    op.create_index(
        "uq_prompt_versions_active",
        "prompt_versions",
        ["series"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_prompt_versions_series_status", "prompt_versions", ["series", "status"])

    op.create_table(
        "model_config_versions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column(
            "config_key", sa.String(64), server_default="tutoring_default", nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Numeric(6, 2), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_config_versions")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_model_config_versions_created_by_user_id_users")),
        sa.UniqueConstraint("config_key", "version", name=op.f("uq_model_config_versions_config_key")),
        sa.CheckConstraint(
            "id ~ '^modelcfg_[0-9a-f]{32}$'", name=op.f("ck_model_config_versions_id_format")
        ),
        sa.CheckConstraint(
            "length(btrim(config_key)) > 0", name=op.f("ck_model_config_versions_config_key")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_model_config_versions_positive_version")),
        sa.CheckConstraint(
            "length(btrim(provider)) > 0", name=op.f("ck_model_config_versions_provider")
        ),
        sa.CheckConstraint(
            "length(btrim(model_name)) BETWEEN 1 AND 100",
            name=op.f("ck_model_config_versions_model_name"),
        ),
        sa.CheckConstraint(
            "(provider = 'mock') = is_mock", name=op.f("ck_model_config_versions_mock_consistency")
        ),
        sa.CheckConstraint(
            "temperature >= 0 AND temperature <= 2",
            name=op.f("ck_model_config_versions_temperature"),
        ),
        sa.CheckConstraint(
            "max_output_tokens > 0", name=op.f("ck_model_config_versions_max_output_tokens")
        ),
        sa.CheckConstraint(
            "timeout_seconds > 0", name=op.f("ck_model_config_versions_timeout_seconds")
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','retired')", name=op.f("ck_model_config_versions_status")
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND retired_at IS NULL) OR "
            "(status = 'active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR "
            "(status = 'retired' AND retired_at IS NOT NULL AND activated_at IS NULL)",
            name=op.f("ck_model_config_versions_lifecycle"),
        ),
    )
    op.create_index(
        "uq_model_config_versions_active",
        "model_config_versions",
        ["config_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_model_config_versions_config_key_status",
        "model_config_versions",
        ["config_key", "status"],
    )

    op.create_table(
        "tutoring_sessions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("student_user_id", sa.String(64), nullable=False),
        sa.Column("course_id", sa.String(64), nullable=True),
        sa.Column("current_stage", sa.String(16), server_default="thought", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tutoring_sessions")),
        sa.ForeignKeyConstraint(["student_user_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_tutoring_sessions_student_user_id_users")),
        sa.CheckConstraint("length(btrim(id)) > 0", name=op.f("ck_tutoring_sessions_id_present")),
        sa.CheckConstraint(
            "current_stage IN ('thought','hint','step','summary')",
            name=op.f("ck_tutoring_sessions_current_stage"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_tutoring_sessions_timestamps")
        ),
    )
    op.create_index(
        "ix_tutoring_sessions_student_updated",
        "tutoring_sessions",
        ["student_user_id", "updated_at"],
    )
    op.create_index("ix_tutoring_sessions_course_id", "tutoring_sessions", ["course_id"])

    op.create_table(
        "tutoring_turns",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("student_content", sa.Text(), nullable=False),
        sa.Column("assistant_content", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("is_complete", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("has_evidence", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("emotion", sa.String(16), nullable=True),
        sa.Column("action", sa.String(16), nullable=True),
        sa.Column(
            "follow_ups",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{\"schemaVersion\":\"1.0\",\"items\":[]}'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_version_id", sa.String(64), nullable=False),
        sa.Column("model_config_version_id", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("abort_reason", sa.String(32), nullable=True),
        sa.Column("error_code", sa.String(32), nullable=True),
        sa.Column("error_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tutoring_turns")),
        sa.ForeignKeyConstraint(["session_id"], ["tutoring_sessions.id"], ondelete="CASCADE", name=op.f("fk_tutoring_turns_session_id_tutoring_sessions")),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="RESTRICT", name=op.f("fk_tutoring_turns_prompt_version_id_prompt_versions")),
        sa.ForeignKeyConstraint(
            ["model_config_version_id"], ["model_config_versions.id"], ondelete="RESTRICT",
            name=op.f("fk_tutoring_turns_model_config_version_id_model_config_versions"),
        ),
        sa.UniqueConstraint("session_id", "seq", name=op.f("uq_tutoring_turns_session_id")),
        sa.CheckConstraint("id ~ '^turn_[0-9a-f]{32}$'", name=op.f("ck_tutoring_turns_id_format")),
        sa.CheckConstraint("seq > 0", name=op.f("ck_tutoring_turns_seq")),
        sa.CheckConstraint(
            "request_id ~ '^req_[0-9a-f]{32}$'", name=op.f("ck_tutoring_turns_request_format")
        ),
        sa.CheckConstraint(
            "char_length(student_content) BETWEEN 1 AND 2000",
            name=op.f("ck_tutoring_turns_student_content"),
        ),
        sa.CheckConstraint(
            "stage IN ('thought','hint','step','summary')", name=op.f("ck_tutoring_turns_stage")
        ),
        sa.CheckConstraint(
            "status IN ('active','completed','aborted')", name=op.f("ck_tutoring_turns_status")
        ),
        sa.CheckConstraint(
            "(status = 'completed') = is_complete",
            name=op.f("ck_tutoring_turns_complete_consistency"),
        ),
        sa.CheckConstraint(
            "(status = 'active') = (settled_at IS NULL)",
            name=op.f("ck_tutoring_turns_settled_state"),
        ),
        sa.CheckConstraint(
            "settled_at IS NULL OR settled_at >= created_at",
            name=op.f("ck_tutoring_turns_settled_timestamp"),
        ),
        sa.CheckConstraint(
            "(status = 'aborted') = (abort_reason IS NOT NULL)",
            name=op.f("ck_tutoring_turns_abort_reason_state"),
        ),
        sa.CheckConstraint(
            "abort_reason IS NULL OR abort_reason IN "
            "('client_stop','client_disconnect','model_error','retrieval_error','server_restart')",
            name=op.f("ck_tutoring_turns_abort_reason"),
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR status = 'aborted'",
            name=op.f("ck_tutoring_turns_error_code_state"),
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('MODEL_OUTPUT_INVALID','MODEL_REFUSED','MODEL_TIMEOUT',"
            "'RETRIEVAL_UNAVAILABLE','TURN_ABORTED')",
            name=op.f("ck_tutoring_turns_error_code"),
        ),
        sa.CheckConstraint(
            "error_reason IS NULL OR error_code IS NOT NULL",
            name=op.f("ck_tutoring_turns_error_reason"),
        ),
        sa.CheckConstraint(
            "abort_reason NOT IN ('model_error','retrieval_error') OR error_code IS NOT NULL",
            name=op.f("ck_tutoring_turns_failure_error_code"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR (assistant_content IS NOT NULL "
            "AND emotion IS NOT NULL AND action IS NOT NULL)",
            name=op.f("ck_tutoring_turns_completed_payload"),
        ),
        sa.CheckConstraint(
            "emotion IS NULL OR emotion IN ('neutral','encouraging','thinking','celebrating')",
            name=op.f("ck_tutoring_turns_emotion"),
        ),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('idle','nod','point','write')",
            name=op.f("ck_tutoring_turns_action"),
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name=op.f("ck_tutoring_turns_input_tokens")
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_tutoring_turns_output_tokens"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name=op.f("ck_tutoring_turns_duration_ms")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(follow_ups) = 'object'", name=op.f("ck_tutoring_turns_follow_ups_object")
        ),
        sa.CheckConstraint(
            """(follow_ups -> 'schemaVersion') IS NOT DISTINCT FROM '"1.0"'::jsonb""",
            name=op.f("ck_tutoring_turns_follow_ups_schema"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(follow_ups -> 'items') = 'array' "
            "AND jsonb_array_length(follow_ups -> 'items') <= 3",
            name=op.f("ck_tutoring_turns_follow_ups_items"),
        ),
    )
    op.create_index(
        "uq_tutoring_turns_active_session",
        "tutoring_turns",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_tutoring_turns_prompt_version_id", "tutoring_turns", ["prompt_version_id"])
    op.create_index(
        "ix_tutoring_turns_model_config_version_id",
        "tutoring_turns",
        ["model_config_version_id"],
    )
    op.create_index("ix_tutoring_turns_status_created", "tutoring_turns", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("tutoring_turns")
    op.drop_table("tutoring_sessions")
    op.drop_table("model_config_versions")
    op.drop_table("prompt_versions")
