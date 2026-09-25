"""mail_approval: Vier-Augen-Freigabe für ausgehende E-Mails (M20).

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message", sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("message", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("message", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("rejection_note", sa.Text(), nullable=True))
    op.add_column("message", sa.Column("gmail_message_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("message", "gmail_message_id")
    op.drop_column("message", "rejection_note")
    op.drop_column("message", "approved_at")
    op.drop_column("message", "approved_by")
    op.drop_column("message", "submitted_at")
    op.drop_column("message", "submitted_by")
