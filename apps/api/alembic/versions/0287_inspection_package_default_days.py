"""Default validity of inspection packages (P08-04, M25-07): tenant_settings column.

Revision ID: 0287
Revises: 0286
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0287"
down_revision: str | None = "0286"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings", sa.Column("inspection_package_default_days", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "inspection_package_default_days")
