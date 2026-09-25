"""mail_forwarding (M32): forwarding of company invoices to the invoicing mailbox.
Configuration per tenant, forwarding stamp per message.

Revision ID: 0041
Revises: 0040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column(
            "mail_forwarding",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    # Default only backfills existing rows; the application sets the value.
    op.alter_column("tenant_settings", "mail_forwarding", server_default=None)
    op.add_column("message", sa.Column("forwarded_to", sa.String(length=320)))
    op.add_column("message", sa.Column("forwarded_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("message", "forwarded_at")
    op.drop_column("message", "forwarded_to")
    op.drop_column("tenant_settings", "mail_forwarding")
