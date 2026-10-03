"""AO07 / GAK-106: tenant switch direct_debit_creator_may_not_approve (default off).

Revision ID: 0458
Revises: 0457
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0458"
down_revision: str | None = "0457"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "direct_debit_creator_may_not_approve",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "direct_debit_creator_may_not_approve")
