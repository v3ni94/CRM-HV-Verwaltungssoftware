"""AE15: tenant switch for advances still open at statement issue (D24, AC10-01).

Revision ID: 0371
Revises: 0370
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0371"
down_revision: str | None = "0370"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "statement_advance_rule",
        sa.Column("open_advance_mode", sa.String(32), nullable=False, server_default="info_only"),
    )
    op.create_check_constraint(
        "open_advance_mode",
        "statement_advance_rule",
        "open_advance_mode IN ('info_only', 'offset_reversal', 'balance_against_due')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_statement_advance_rule_open_advance_mode"),
        "statement_advance_rule",
        type_="check",
    )
    op.drop_column("statement_advance_rule", "open_advance_mode")
