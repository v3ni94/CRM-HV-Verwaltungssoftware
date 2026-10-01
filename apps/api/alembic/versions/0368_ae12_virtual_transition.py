"""AE12: transition date for the enabling resolution of virtual meetings (tenant_settings).

Revision ID: 0368
Revises: 0367
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0368"
down_revision: str | None = "0367"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings", sa.Column("hoa_virtual_basis_transition_date", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "hoa_virtual_basis_transition_date")
