"""mailbox_gmail_sync: Gmail history cursor and sync state per mailbox (M20-01).

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mailbox", sa.Column("gmail_history_id", sa.String(length=32), nullable=True))
    op.add_column("mailbox", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mailbox", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailbox", "last_error")
    op.drop_column("mailbox", "last_synced_at")
    op.drop_column("mailbox", "gmail_history_id")
