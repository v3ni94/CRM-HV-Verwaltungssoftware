"""deadline_types: tenant catalogue of deadline types, user created deadline entries with a
responsible person and property checklists (rule WS-01; handbook gaps Verwalterwechsel row 1,
Mieterwechsel row 3, Mieterhöhung rows 2 and 3).

All three tables are tenant tables with RLS via mhvp.core.db.rls.tenant_rls_statements()
(ADR 0002). The three system types (Verwalterwechsel, Kautionsabrechnung, Mieterhöhung) are
seeded lazily per tenant by ``mhvp.workspace.deadlines.ensure_system_types`` without a
duration; no duration and no legal deadline is written by this migration.

Revision ID: 0230
Revises: 0223
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0230"
down_revision: str | None = "0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("deadline_type", "deadline_entry", "property_checklist")


def _audit(table: str) -> list[sa.SchemaItem]:
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
        "deadline_type",
        sa.Column("code", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("responsible_role", sa.String(length=63), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_audit("deadline_type"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_deadline_type_code"),
    )

    op.create_table(
        "deadline_entry",
        sa.Column("type_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("trigger_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("due_computed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("responsible_user_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by", sa.UUID(), nullable=True),
        *_audit("deadline_entry"),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["deadline_type.id"],
            name=op.f("fk_deadline_entry_type_id_deadline_type"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["app_user.id"],
            name=op.f("fk_deadline_entry_responsible_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_deadline_entry_property_id_property"),
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_deadline_entry_due", "deadline_entry", ["tenant_id", "status", "due_on"])
    op.create_index(
        "ix_deadline_entry_source", "deadline_entry", ["tenant_id", "source_type", "source_id"]
    )

    op.create_table(
        "property_checklist",
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        *_audit("property_checklist"),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_checklist_property_id_property"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_property_checklist_property", "property_checklist", ["tenant_id", "property_id"]
    )
    op.create_index(
        "uq_property_checklist_open",
        "property_checklist",
        ["tenant_id", "property_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("uq_property_checklist_open", table_name="property_checklist")
    op.drop_index("ix_property_checklist_property", table_name="property_checklist")
    op.drop_table("property_checklist")
    op.drop_index("ix_deadline_entry_source", table_name="deadline_entry")
    op.drop_index("ix_deadline_entry_due", table_name="deadline_entry")
    op.drop_table("deadline_entry")
    op.drop_table("deadline_type")
