"""AE11: correction reason, basis and resolution on hoa_statement (P02).

Revision ID: 0367
Revises: 0366
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0367"
down_revision: str | None = "0366"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hoa_statement", sa.Column("correction_reason", sa.String(32)))
    op.add_column("hoa_statement", sa.Column("correction_basis", sa.Text()))
    op.add_column(
        "hoa_statement",
        sa.Column(
            "correction_resolution_id",
            sa.Uuid(),
            sa.ForeignKey("resolution.id"),
        ),
    )


def downgrade() -> None:
    op.drop_column("hoa_statement", "correction_resolution_id")
    op.drop_column("hoa_statement", "correction_basis")
    op.drop_column("hoa_statement", "correction_reason")
