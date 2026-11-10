"""Persist provider identities scoped to their trusted issuer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_external_identities"
down_revision: str | None = "0002_config_schema_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "issuer", "subject"),
        sa.CheckConstraint(
            "provider IN ('github','wechat','school','sms')",
            name=op.f("ck_external_identities_provider"),
        ),
        sa.CheckConstraint(
            "length(btrim(issuer)) > 0 AND length(btrim(subject)) > 0",
            name=op.f("ck_external_identities_identity"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_external_identities_timestamps"),
        ),
    )
    op.create_index("ix_external_identities_user", "external_identities", ["user_id"])


def downgrade() -> None:
    op.drop_table("external_identities")
