"""IMAP fetch cursor on the mailbox (M20-01, decision 5 a).

* ``mailbox.imap_uidvalidity``: UIDVALIDITY of the INBOX the stored ``last_uid`` belongs to.
* ``mailbox.reply_style``: style rules for AI reply drafts (M20-02), the default mailbox
  applies tenant wide.
* ``mailbox.last_uid``: widened to BIGINT, IMAP UIDs are unsigned 32 bit values.

Revision ID: 0261
Revises: 0260
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0261"
down_revision: str | None = "0260"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mailbox", sa.Column("imap_uidvalidity", sa.BigInteger(), nullable=True))
    op.add_column(
        "mailbox",
        sa.Column(
            "reply_style",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column(
        "mailbox",
        "last_uid",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "mailbox",
        "last_uid",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.drop_column("mailbox", "reply_style")
    op.drop_column("mailbox", "imap_uidvalidity")
