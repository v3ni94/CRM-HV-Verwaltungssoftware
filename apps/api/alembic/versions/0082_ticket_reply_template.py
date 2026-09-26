"""ticket_reply_template: vorgefertigte Antworten je Mandant für Tickets (operator 26.09.2026):
Name, Betreff, Text mit Platzhaltern, Thema aus dem Kompetenzkatalog und Standardanhänge als
Dokumentverweise. Versand nur über den bestehenden Antwortweg und nach Bestätigung.

Revision ID: 0082
Revises: 0080

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0082"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ticket_reply_template"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=32), nullable=True),
        sa.Column(
            "attachment_document_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=f"fk_{TABLE}_tenant_id_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ticket_reply_template_name"),
    )
    for stmt in tenant_rls_statements(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in drop_tenant_rls_statements(TABLE):
        op.execute(stmt)
    op.drop_table(TABLE)
