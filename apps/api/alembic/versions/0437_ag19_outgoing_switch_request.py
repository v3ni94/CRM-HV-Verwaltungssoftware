"""AG19 (AF25-01): target column on auto_posting_switch_request (main or outgoing).

The outgoing automation is switched on only by an approved request (second person, G1).

Revision ID: 0437
Revises: 0436
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0437"
down_revision: str | None = "0436"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "auto_posting_switch_request"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("target", sa.String(length=16), server_default="main", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_auto_posting_switch_request_target"), TABLE, "target IN ('main', 'outgoing')"
    )


def downgrade() -> None:
    # Requests are evidence; outgoing rows keep their decision, only the column goes away.
    op.drop_constraint(op.f("ck_auto_posting_switch_request_target"), TABLE, type_="check")
    op.drop_column(TABLE, "target")
