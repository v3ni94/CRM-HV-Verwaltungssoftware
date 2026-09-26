"""ledger_account.review_status and review_note (operator decision M10-01 of 26.09.2026):
template rows proposed beyond annex A.1 (rental revenue accounts) carry
``review_status = 'entwurf'`` and the note "Freigabe durch Steuerberatung offen" so the draft
marker stays visible on the ledger accounts created from the template. Existing accounts get
``'none'``. Columns only; the table keeps its RLS policies. No posting behaviour changes,
G1 stays closed.

Revision ID: 0137
Revises: 0136
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0137"
down_revision: str | None = "0136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ledger_account",
        sa.Column("review_status", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column("ledger_account", sa.Column("review_note", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("ledger_account", "review_note")
    op.drop_column("ledger_account", "review_status")
