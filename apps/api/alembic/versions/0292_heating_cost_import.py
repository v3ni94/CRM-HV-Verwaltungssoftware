"""Heating cost import of the metering service (M17-09, 6.5 heating_cost_import, H01).

Revision ID: 0292
Revises: 0291
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0292"
down_revision: str | None = "0291"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

T = "heating_cost_import"


def _fk(column: str, target: str, ondelete: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{T}_{column}_{target}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        T,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("provider_contact_id", sa.Uuid(), nullable=True),
        sa.Column("provider_name", sa.String(200), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("document_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("co2", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("user_mapping", jsonb, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("rows", jsonb, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("csv_meta", jsonb, nullable=True),
        sa.Column("status", sa.String(16), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("check_result", jsonb, nullable=True),
        sa.Column("duplicate_ack_reason", sa.Text(), nullable=True),
        sa.Column("checked_by", sa.Uuid(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_item_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        _fk("tenant_id", "tenant", "RESTRICT"),
        _fk("property_id", "property"),
        _fk("statement_id", "statement", "SET NULL"),
        _fk("document_id", "document"),
        _fk("provider_contact_id", "contact"),
        _fk("applied_item_id", "statement_cost_item", "SET NULL"),
        sa.CheckConstraint(
            "status IN ('draft', 'checked', 'applied')", name=op.f(f"ck_{T}_status")
        ),
        sa.CheckConstraint("period_from <= period_to", name=op.f(f"ck_{T}_period")),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{T}")),
    )
    op.create_index(
        "ix_heating_cost_import_property_period",
        T,
        ["tenant_id", "property_id", "period_from"],
    )
    for statement in tenant_rls_statements(T):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(T):
        op.execute(statement)
    op.drop_index("ix_heating_cost_import_property_period", table_name=T)
    op.drop_table(T)
