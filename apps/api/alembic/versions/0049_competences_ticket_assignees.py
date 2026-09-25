"""competences_ticket_assignees: member competences, ticket topic and multi-assignee, mailbox
archive-on-done setting, invoice forwarding and competence catalogue settings (M19/M20, operator
decisions 25.09.2026, docs/integrations/mail-optimierung.md).

Deviation note (rule 0.1.11 / task instructions): the task named down_revision "0049" with a base
revision "0050"; the actual head found in this branch was "0048" (0049/0050 do not exist yet), so
this migration is filed as "0049" on top of "0048" as instructed for that case.

Revision ID: 0049
Revises: 0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Membership: Kompetenzen ------------------------------------------------------------
    op.add_column(
        "membership",
        sa.Column(
            "competences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # TenantSettings: Kompetenzkatalog-Erweiterung und Rechnungs-Weiterleitung ------------
    op.add_column(
        "tenant_settings",
        sa.Column(
            "competence_catalogue_extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "invoice_forwarding",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Ticket / TicketTemplate: Thema, Kontakt-Link ---------------------------------------
    op.add_column("ticket_template", sa.Column("topic", sa.String(length=32), nullable=True))
    op.add_column("ticket", sa.Column("topic", sa.String(length=32), nullable=True))
    op.add_column(
        "ticket",
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contact.id"),
            nullable=True,
        ),
    )

    # ticket_assignee ----------------------------------------------------------------------
    op.create_table(
        "ticket_assignee",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ticket.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("ticket_id", "user_id", name="uq_ticket_assignee"),
    )
    for statement in tenant_rls_statements("ticket_assignee"):
        op.execute(statement)

    # Mailbox: "Erledigt archiviert Mail" ---------------------------------------------------
    op.add_column(
        "mailbox",
        sa.Column("archive_on_ticket_done", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "mailbox",
        sa.Column("archive_scope_missing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("mailbox", "archive_scope_missing")
    op.drop_column("mailbox", "archive_on_ticket_done")
    for statement in drop_tenant_rls_statements("ticket_assignee"):
        op.execute(statement)
    op.drop_table("ticket_assignee")
    op.drop_column("ticket", "contact_id")
    op.drop_column("ticket", "topic")
    op.drop_column("ticket_template", "topic")
    op.drop_column("tenant_settings", "invoice_forwarding")
    op.drop_column("tenant_settings", "competence_catalogue_extra")
    op.drop_column("membership", "competences")
