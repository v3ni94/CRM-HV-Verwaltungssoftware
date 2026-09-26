"""mail_review_fixes: soft deleted mailboxes keep their messages bound (review 26.09.2026,
M12) and the Gmail thread id of inbound mails as a threading fallback (M7).

Revision ID: 0126
Revises: 0125
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0126"
down_revision: str | None = "0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mailbox", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("gmail_thread_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_message_gmail_thread", "message", ["tenant_id", "gmail_thread_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_message_gmail_thread", table_name="message")
    op.drop_column("message", "gmail_thread_id")
    op.drop_column("mailbox", "deleted_at")
