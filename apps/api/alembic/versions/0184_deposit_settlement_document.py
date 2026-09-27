"""Deposit settlement letter (Kautionsabrechnung als PDF, M5-02 follow up): links the
generated, stored draft document to its ``deposit_settlement`` row so the CRM can show and
open it. No booking, no payment, no receivable (G1/G3 unaffected).

Revision ID: 0184
Revises: 0183
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0184"
down_revision: str | None = "0183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "deposit_settlement"
COLUMN = "document_id"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if TABLE not in _inspector().get_table_names():
        return
    columns = {c["name"] for c in _inspector().get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("document.id", ondelete="SET NULL"),
            ),
        )


def downgrade() -> None:
    if TABLE not in _inspector().get_table_names():
        return
    columns = {c["name"] for c in _inspector().get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)
