"""ai_fast_table_import: M7 fast path for extract_contacts CSV/XLSX imports (operator
25.09.2026, docs/rules/M7-06.md). Adds the ``map_columns`` AI task and the per-tenant feature
flag ``tenant_settings.ai_fast_table_import`` (default on).

Revision ID: 0067
Revises: 0066
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'map_columns'")
    op.add_column(
        "tenant_settings",
        sa.Column(
            "ai_fast_table_import",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "ai_fast_table_import")
    # Postgres enum values cannot be removed; 'map_columns' stays defined on downgrade.
