"""Draft heating statement (M17-02, H02, H04, D25 to D27): ``heating_rule_table`` (CO2 steps
and degree days per tenant, source status "zu prüfen") and ``statement_heating`` (inputs,
consumptions and JSON trace per operating cost statement). Idempotent.

Revision ID: 0162
Revises: 0161
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0162"
down_revision: str | None = "0161"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULES = "heating_rule_table"
HEATING = "statement_heating"
NOW = sa.text("now()")


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _base_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    ]


def upgrade() -> None:
    if not _has_table(RULES):
        op.create_table(
            RULES,
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("rows", postgresql.JSONB(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("review_status", sa.String(length=16), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f(f"fk_{RULES}_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{RULES}")),
            sa.UniqueConstraint("tenant_id", "kind", "valid_from", name=f"uq_{RULES}_kind_valid"),
        )
        for statement in tenant_rls_statements(RULES):
            op.execute(statement)
    if not _has_table(HEATING):
        op.create_table(
            HEATING,
            sa.Column("statement_id", sa.UUID(), nullable=False),
            sa.Column("total_costs", sa.Numeric(14, 2), nullable=True),
            sa.Column("settings", postgresql.JSONB(), nullable=False),
            sa.Column("co2", postgresql.JSONB(), nullable=False),
            sa.Column("consumptions", postgresql.JSONB(), nullable=False),
            sa.Column("unit_totals", postgresql.JSONB(), nullable=False),
            sa.Column("result", postgresql.JSONB(), nullable=True),
            sa.Column("result_hash", sa.String(length=64), nullable=True),
            sa.Column("applied_item_id", sa.UUID(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(
                ["statement_id"],
                ["statement.id"],
                name=op.f(f"fk_{HEATING}_statement_id_statement"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["applied_item_id"],
                ["statement_cost_item.id"],
                name=op.f(f"fk_{HEATING}_applied_item_id_statement_cost_item"),
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f(f"fk_{HEATING}_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{HEATING}")),
            sa.UniqueConstraint("tenant_id", "statement_id", name=f"uq_{HEATING}_statement"),
        )
        for statement in tenant_rls_statements(HEATING):
            op.execute(statement)


def downgrade() -> None:
    for table in (HEATING, RULES):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
