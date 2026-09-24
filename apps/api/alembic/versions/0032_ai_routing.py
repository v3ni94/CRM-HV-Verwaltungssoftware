"""ai_routing: provider strategy per tenant (M7-02).

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "ai_routing", sa.String(length=24), nullable=False, server_default="anthropic_first"
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "ai_routing")
