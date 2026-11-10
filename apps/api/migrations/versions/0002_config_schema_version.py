"""Reject missing, null, and non-string configuration schema versions."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_config_schema_version"
down_revision: str | None = "0001_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "system_config_versions"
_CHECK_NAME = "ck_system_config_versions_schema_version"
_STRICT_CHECK = """(value -> 'schemaVersion') IS NOT DISTINCT FROM '"1.0"'::jsonb"""
_OLD_CHECK = "value ? 'schemaVersion' AND value ->> 'schemaVersion' = '1.0'"


def _replace_check(expression: str) -> None:
    op.drop_constraint(op.f(_CHECK_NAME), _TABLE, type_="check")
    op.create_check_constraint(op.f(_CHECK_NAME), _TABLE, expression)


def upgrade() -> None:
    # PostgreSQL validates existing rows and rolls the revision back on a violation.
    # Do not guess a version or rewrite the contents of a historical configuration.
    _replace_check(_STRICT_CHECK)


def downgrade() -> None:
    _replace_check(_OLD_CHECK)
