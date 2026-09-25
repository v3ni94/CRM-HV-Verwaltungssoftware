"""portal_role_permissions: per tenant configurable portal permission set per CRM system role
(operator decision 25.09.2026, M2-08 entschieden, docs/rules/M2-07.md). Adds the JSON override
column on tenant_settings; the catalogue and the built in defaults live in code
(mhvp.portal.staff_access), only the tenant's overrides are persisted.

Revision ID: 0056
Revises: 0055

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "portal_role_permissions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "portal_role_permissions")
