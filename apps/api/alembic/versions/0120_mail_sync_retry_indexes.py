"""Gmail sync retry queue and ticket/mail indexes (review 26.09.2026, H1, M2, M4).

``mailbox_sync_retry`` remembers Gmail messages whose ingest failed so the next sync tries them
again (tenant table with RLS, ADR 0002). Indexes on ``message`` (ticket, thread, mailbox and
status), ``ticket`` (status and number, assignee), ``ticket_comment``, ``ticket_event`` and
``work_order`` (ticket), plus the partial unique index that deduplicates inbound mails per
Message-ID and tenant.

Revision ID: 0120
Revises: 0119
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0120"
down_revision: str | None = "0119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETRY = "mailbox_sync_retry"

INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_message_ticket", "message", ["tenant_id", "ticket_id"]),
    ("ix_message_thread", "message", ["tenant_id", "thread_id"]),
    ("ix_message_mailbox_status", "message", ["tenant_id", "mailbox_id", "status"]),
    ("ix_ticket_status_number", "ticket", ["tenant_id", "status", "number"]),
    ("ix_ticket_assignee", "ticket", ["tenant_id", "assignee_user_id"]),
    ("ix_ticket_comment_ticket", "ticket_comment", ["tenant_id", "ticket_id"]),
    ("ix_ticket_event_ticket", "ticket_event", ["tenant_id", "ticket_id"]),
    ("ix_work_order_ticket", "work_order", ["tenant_id", "ticket_id"]),
]


def upgrade() -> None:
    op.create_table(
        RETRY,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_mailbox_sync_retry_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["mailbox_id"],
            ["mailbox.id"],
            name=op.f("fk_mailbox_sync_retry_mailbox_id_mailbox"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mailbox_sync_retry")),
        sa.UniqueConstraint("mailbox_id", "gmail_message_id", name="uq_mailbox_sync_retry_message"),
    )
    for statement in tenant_rls_statements(RETRY):
        op.execute(statement)
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)
    op.create_index(
        "uq_message_inbound_header_id",
        "message",
        ["tenant_id", "header_message_id"],
        unique=True,
        postgresql_where=sa.text("direction = 'in' AND header_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_message_inbound_header_id", table_name="message")
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    for statement in drop_tenant_rls_statements(RETRY):
        op.execute(statement)
    op.drop_table(RETRY)
