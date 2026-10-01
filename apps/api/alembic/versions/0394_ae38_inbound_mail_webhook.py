"""AE38 / M20-04: inbound webhook for classified mails of the legacy mail program.

* ``inbound_mail_source``: source of the deliveries per tenant (name, encrypted HMAC secret,
  switch ``active`` default on, mailbox binding, ``auto_ticket`` default on = decided rule
  25.09.2026). Unique per tenant and name.
* ``inbound_mail_event``: idempotency record, unique per source and ``event_id``; holds the
  hash of the canonical payload, the link to message and ticket and the replay counter, but
  no mail content.

Both tables are tenant tables with RLS (ADR 0002).

Revision ID: 0394
Revises: 0393
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0394"
down_revision: str | None = "0393"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("inbound_mail_source", "inbound_mail_event")


def _common(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.create_table(
        "inbound_mail_source",
        *_common("inbound_mail_source"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("secret", sa.LargeBinary(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mailbox_id", sa.Uuid(), nullable=True),
        sa.Column("auto_ticket", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["mailbox_id"],
            ["mailbox.id"],
            name=op.f("fk_inbound_mail_source_mailbox_id_mailbox"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id", "name", name=op.f("uq_inbound_mail_source_tenant_id_name")
        ),
    )
    op.create_table(
        "inbound_mail_event",
        *_common("inbound_mail_event"),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("message_created", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["inbound_mail_source.id"],
            name=op.f("fk_inbound_mail_event_source_id_inbound_mail_source"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["message.id"],
            name=op.f("fk_inbound_mail_event_message_id_message"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
            name=op.f("fk_inbound_mail_event_ticket_id_ticket"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "source_id", "event_id", name=op.f("uq_inbound_mail_event_source_id_event_id")
        ),
    )
    op.create_index(
        "ix_inbound_mail_event_source_created",
        "inbound_mail_event",
        ["tenant_id", "source_id", "created_at"],
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_inbound_mail_event_source_created", table_name="inbound_mail_event")
    op.drop_table("inbound_mail_event")
    op.drop_table("inbound_mail_source")
