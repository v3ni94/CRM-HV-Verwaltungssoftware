"""broker_tenant_config.settings: provider specific configuration with no shared column
(M28-02). For flowfact: schema_rental/schema_sale, the FLOWFACT schema name per listing kind.

Revision ID: 0247
Revises: 0246
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0247"
down_revision: str | None = "0246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "broker_tenant_config",
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("broker_tenant_config", "settings")
