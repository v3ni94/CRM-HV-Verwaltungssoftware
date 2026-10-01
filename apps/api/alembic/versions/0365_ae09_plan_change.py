"""AE09 (M24-08, P07-01, M12-L2): plan change within the year, difference of posted months.

* ``hoa_plan_change_setting``: per tenant variant, default ``notice`` (no row means notice).
* ``hoa_plan_difference``: draft claim or credit per contract, component and posted month;
  approval needs gate G4 and a second person, nothing is posted.

Revision ID: 0365
Revises: 0364
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0365"
down_revision: str | None = "0364"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("hoa_plan_change_setting", "hoa_plan_difference")


def _common(table: str) -> list[sa.SchemaItem]:
    return [
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
        "hoa_plan_change_setting",
        *_common("hoa_plan_change_setting"),
        sa.Column("mode", sa.String(16), server_default="notice", nullable=False),
        sa.CheckConstraint(
            "mode IN ('notice', 'due_now', 'next_instalment')",
            name=op.f("ck_hoa_plan_change_setting_mode"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_hoa_plan_change_setting_tenant_id")),
    )
    op.create_table(
        "hoa_plan_difference",
        *_common("hoa_plan_difference"),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("payment_type_code", sa.String(63), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("posted_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("new_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("difference", sa.Numeric(14, 2), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("proposed_due", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('due_now', 'next_instalment')", name=op.f("ck_hoa_plan_difference_mode")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name=op.f("ck_hoa_plan_difference_status"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["economic_plan.id"],
            name=op.f("fk_hoa_plan_difference_plan_id_economic_plan"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["unit.id"], name=op.f("fk_hoa_plan_difference_unit_id_unit")
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_hoa_plan_difference_contract_id_contract"),
        ),
        sa.UniqueConstraint(
            "plan_id",
            "contract_id",
            "payment_type_code",
            "period_month",
            name="uq_hoa_plan_difference_month",
        ),
    )
    op.create_index("ix_hoa_plan_difference_plan", "hoa_plan_difference", ["tenant_id", "plan_id"])
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
