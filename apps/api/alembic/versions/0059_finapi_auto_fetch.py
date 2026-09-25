"""finapi_auto_fetch: M11-finapi Stage 2 (docs/plans/M11-finapi.md), operator decision
25.09.2026. Adds the per tenant "scheduled daily fetch" flag, default off, so a signed off
tenant can opt into automatic fetch without changing the manual-click path.

Revision ID: 0059
Revises: 0058

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002); this migration
only adds a column to an existing tenant table, so RLS is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finapi_tenant_config",
        sa.Column("auto_fetch_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("finapi_tenant_config", "auto_fetch_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("finapi_tenant_config", "auto_fetch_enabled")
