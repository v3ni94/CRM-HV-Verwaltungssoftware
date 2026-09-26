"""M20-03 Direktversand von Ticketantworten (operator decision 26.09.2026):
membership.reply_approval_required/_reason/_until (per member flag, default false),
tenant_settings.ticket_reply_approval_all (emergency brake, default false),
message.author_approval_required/_reason (flag at drafting time). Columns only; the tenant
tables keep their RLS policies.

Revision ID: 0129
Revises: 0128
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0129"
down_revision: str | None = "0128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "membership",
        sa.Column(
            "reply_approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("membership", sa.Column("reply_approval_reason", sa.String(32), nullable=True))
    op.add_column("membership", sa.Column("reply_approval_until", sa.Date(), nullable=True))
    op.add_column(
        "tenant_settings",
        sa.Column(
            "ticket_reply_approval_all",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "message",
        sa.Column(
            "author_approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("message", sa.Column("author_approval_reason", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("message", "author_approval_reason")
    op.drop_column("message", "author_approval_required")
    op.drop_column("tenant_settings", "ticket_reply_approval_all")
    op.drop_column("membership", "reply_approval_until")
    op.drop_column("membership", "reply_approval_reason")
    op.drop_column("membership", "reply_approval_required")
