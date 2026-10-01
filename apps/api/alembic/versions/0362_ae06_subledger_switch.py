"""AE06 (AC01-02): tenant switch to hide written off and reversed items in the sub ledger check.

Revision ID: 0362
Revises: 0361
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0362"
down_revision: str | None = "0361"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_tax_settings",
        sa.Column(
            "subledger_exclude_written_off",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("accounting_tax_settings", "subledger_exclude_written_off")
