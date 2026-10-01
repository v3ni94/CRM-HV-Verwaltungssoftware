"""Factual review of incoming invoices (M14-02, 7.9.1 PUE02): structured links of the invoice
to work order, resolution and economic plan item, quantity and unit price per line, tolerances
per tenant.

Revision ID: 0291
Revises: 0290
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0291"
down_revision: str | None = "0290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTING = "invoice_check_setting"
LINKS = (
    ("work_order_id", "work_order"),
    ("resolution_id", "resolution"),
    ("plan_item_id", "economic_plan_item"),
)


def upgrade() -> None:
    for column, target in LINKS:
        op.add_column("invoice", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_invoice_{column}_{target}"), "invoice", target, [column], ["id"]
        )
    op.add_column("invoice_line", sa.Column("quantity", sa.Numeric(20, 8), nullable=True))
    op.add_column("invoice_line", sa.Column("unit_price", sa.Numeric(20, 8), nullable=True))
    op.create_table(
        SETTING,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("price_tolerance_percent", sa.Numeric(20, 8), server_default="0", nullable=False),
        sa.Column(
            "quantity_tolerance_percent", sa.Numeric(20, 8), server_default="0", nullable=False
        ),
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
            name=op.f("fk_invoice_check_setting_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_check_setting")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_invoice_check_setting_tenant_id")),
    )
    for statement in tenant_rls_statements(SETTING):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(SETTING):
        op.execute(statement)
    op.drop_table(SETTING)
    op.drop_column("invoice_line", "unit_price")
    op.drop_column("invoice_line", "quantity")
    for column, target in reversed(LINKS):
        op.drop_constraint(op.f(f"fk_invoice_{column}_{target}"), "invoice", type_="foreignkey")
        op.drop_column("invoice", column)
