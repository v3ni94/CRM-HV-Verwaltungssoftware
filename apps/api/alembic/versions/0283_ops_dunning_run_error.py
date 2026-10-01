"""Dunning run error status (M9-01): error text on dunning_run.

Revision ID: 0283
Revises: 0282
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0283"
down_revision: str | None = "0282"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dunning_run", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dunning_run", "error")
