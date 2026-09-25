"""mail_suggestions: KI-Vorschläge je Mail und Playbooks aus geschlossenen Tickets (M20
Übernahme aus dem Immoware Hub).

Revision ID: 0041
Revises: 0040

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("playbook",)
ENUMS: tuple[str, ...] = ()


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column("suggestion", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "message",
        sa.Column("suggestion_status", sa.String(length=16), nullable=False, server_default="none"),
    )
    op.create_table(
        "playbook",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("reply_template", sa.Text(), nullable=True),
        sa.Column("source_ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_ticket_id"],
            ["ticket.id"],
            name=op.f("fk_playbook_source_ticket_id_ticket"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_playbook_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playbook")),
        sa.UniqueConstraint("tenant_id", "title", name="uq_playbook_title"),
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("playbook")
    op.drop_column("message", "suggestion_status")
    op.drop_column("message", "suggestion")
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
