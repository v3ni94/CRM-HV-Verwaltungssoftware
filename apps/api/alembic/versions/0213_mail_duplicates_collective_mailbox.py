"""Operator 27.09.2026 (mail workspace): duplicates across own mailboxes and collective
mailbox flag. ``mailbox.is_collective`` marks shared addresses (info@, post@, buchhaltung@,
...) and is backfilled by the local part rule of ``mhvp.communication.duplicates``;
``message.duplicate_of_id`` links the copy of a mail in a second mailbox to the leading
copy (kept, hidden from the overview, same ticket and thread). Idempotent.

Revision ID: 0213
Revises: 0212
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0213"
down_revision: str | None = "0212"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with mhvp.communication.duplicates.COLLECTIVE_LOCAL_PARTS.
_COLLECTIVE_REGEX = (
    "^(info|post|buchhaltung|office|kontakt|verwaltung|rechnung|rechnungen|mail|service|"
    "zentrale|hausverwaltung|support|kundenservice|bewerbung|team)([.+-].*)?@"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mailbox"):
        cols = {c["name"] for c in inspector.get_columns("mailbox")}
        if "is_collective" not in cols:
            op.add_column(
                "mailbox",
                sa.Column("is_collective", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
            sql = "UPDATE mailbox SET is_collective = true WHERE lower(address) ~ :rx"
            statement = sa.text(sql)
            op.execute(statement.bindparams(rx=_COLLECTIVE_REGEX))
    if inspector.has_table("message"):
        cols = {c["name"] for c in inspector.get_columns("message")}
        if "duplicate_of_id" not in cols:
            op.add_column(
                "message",
                sa.Column(
                    "duplicate_of_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("message.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        # One inbound row per Message-ID, tenant and mailbox (was: per Message-ID and tenant).
        current = bind.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
            {"n": "uq_message_inbound_header_id"},
        ).scalar()
        if current is None or "mailbox_id" not in str(current):
            if current is not None:
                op.drop_index("uq_message_inbound_header_id", table_name="message")
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX uq_message_inbound_header_id ON message "
                    "(tenant_id, header_message_id, "
                    "coalesce(mailbox_id, '00000000-0000-0000-0000-000000000000'::uuid)) "
                    "WHERE direction = 'in' AND header_message_id IS NOT NULL"
                )
            )
        indexes = {i["name"] for i in inspector.get_indexes("message")}
        if "ix_message_duplicate_of" not in indexes:
            op.create_index(
                "ix_message_duplicate_of",
                "message",
                ["tenant_id", "duplicate_of_id"],
                postgresql_where=sa.text("duplicate_of_id IS NOT NULL"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("message"):
        indexes = {i["name"] for i in inspector.get_indexes("message")}
        if "ix_message_duplicate_of" in indexes:
            op.drop_index("ix_message_duplicate_of", table_name="message")
        # The relaxed unique index (per mailbox) stays: linked copies are kept as evidence and
        # would violate the former index; nothing is deleted on downgrade.
    if inspector.has_table("mailbox"):
        cols = {c["name"] for c in inspector.get_columns("mailbox")}
        if "is_collective" in cols:
            op.drop_column("mailbox", "is_collective")
