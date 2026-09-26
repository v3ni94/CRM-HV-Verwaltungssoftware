"""dunning_property_overrides: an object level row of ``dunning_settings`` may leave
``levels``, ``threshold_amount`` and ``interest_enabled`` empty to inherit the tenant default
(M16-10, docs/rules/M16-02.md). The tenant default row (property_id NULL) stays complete; the
API enforces that. The server default of ``interest_enabled`` is dropped so that an explicit
NULL (inherit) is stored as NULL and not replaced by ``false``. No data changes: existing
rows keep their values.

Revision ID: 0078
Revises: 0074
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("dunning_settings", "levels", existing_type=sa.JSON(), nullable=True)
    op.alter_column(
        "dunning_settings", "threshold_amount", existing_type=sa.Numeric(14, 2), nullable=True
    )
    op.alter_column(
        "dunning_settings",
        "interest_enabled",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # The table forces row level security (ADR 0002); without a tenant context the owner would
    # update no rows and the NOT NULL constraints below would fail. Lift the force for the fix.
    op.execute("ALTER TABLE dunning_settings NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE dunning_settings SET levels = '[]'::jsonb WHERE levels IS NULL")
    op.execute("UPDATE dunning_settings SET threshold_amount = 0 WHERE threshold_amount IS NULL")
    op.execute(
        "UPDATE dunning_settings SET interest_enabled = false WHERE interest_enabled IS NULL"
    )
    op.alter_column(
        "dunning_settings",
        "interest_enabled",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    op.alter_column(
        "dunning_settings", "threshold_amount", existing_type=sa.Numeric(14, 2), nullable=False
    )
    op.alter_column("dunning_settings", "levels", existing_type=sa.JSON(), nullable=False)
    op.execute("ALTER TABLE dunning_settings FORCE ROW LEVEL SECURITY")
