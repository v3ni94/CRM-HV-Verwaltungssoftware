"""AG02 / GAC-05: leading system per ledger, property, process kind and valid-from date.

``ledger_leading_switch`` holds requested, approved and rejected switches (second person,
G1 for the platform as leading system). Tenant table with RLS (ADR 0002).

Revision ID: 0420
Revises: 0419
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0420"
down_revision: str | None = "0419"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ledger_leading_switch"


def upgrade() -> None:
    op.create_table(
        TABLE,
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
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("leading_system", sa.String(16), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'requested'")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('receivable_posting', 'dunning', 'direct_debit', 'payment_order')",
            name="kind_valid",
        ),
        sa.CheckConstraint("leading_system IN ('immoware24', 'mhvp')", name="leading_valid"),
        sa.CheckConstraint("status IN ('requested', 'approved', 'rejected')", name="status_valid"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledger.id"],
            name=op.f(f"fk_{TABLE}_ledger_id_ledger"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f(f"fk_{TABLE}_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(
        "ix_ledger_leading_switch_lookup", TABLE, ["tenant_id", "ledger_id", "kind", "valid_from"]
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_ledger_leading_switch_lookup", table_name=TABLE)
    op.drop_table(TABLE)
