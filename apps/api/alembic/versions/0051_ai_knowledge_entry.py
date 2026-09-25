"""ai_knowledge_entry: AI knowledge base per tenant and optionally per property (Welle 3 item
14). Entries are manually curated (source ``manual``) or learned from a correction of a mail
preparation (source ``learned``); they are read only context for AI runs, never posted or
sent automatically (rule 0.1.6).

Revision ID: 0051
Revises: 0050

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("ai_knowledge_entry",)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    ai_knowledge_kind = sa.Enum(
        "filing_rule", "workflow", "correction", "fact", name="ai_knowledge_kind"
    )
    ai_knowledge_source = sa.Enum("manual", "learned", name="ai_knowledge_source")

    op.create_table(
        "ai_knowledge_entry",
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("kind", ai_knowledge_kind, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source", ai_knowledge_source, nullable=False, server_default=sa.text("'manual'")
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_ai_knowledge_entry_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_ai_knowledge_entry_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_knowledge_entry")),
    )
    op.create_index(
        "ix_ai_knowledge_entry_property_id", "ai_knowledge_entry", ["property_id"]
    )
    op.create_index(
        "ix_ai_knowledge_entry_tenant_property",
        "ai_knowledge_entry",
        ["tenant_id", "property_id"],
    )
    op.create_index(
        "ix_ai_knowledge_entry_tenant_kind", "ai_knowledge_entry", ["tenant_id", "kind"]
    )

    for table in TENANT_TABLES:
        for stmt in tenant_rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for stmt in drop_tenant_rls_statements(table):
            op.execute(stmt)
    op.drop_index("ix_ai_knowledge_entry_tenant_kind", table_name="ai_knowledge_entry")
    op.drop_index("ix_ai_knowledge_entry_tenant_property", table_name="ai_knowledge_entry")
    op.drop_index("ix_ai_knowledge_entry_property_id", table_name="ai_knowledge_entry")
    op.drop_table("ai_knowledge_entry")
    sa.Enum(name="ai_knowledge_source").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="ai_knowledge_kind").drop(op.get_bind(), checkfirst=True)
