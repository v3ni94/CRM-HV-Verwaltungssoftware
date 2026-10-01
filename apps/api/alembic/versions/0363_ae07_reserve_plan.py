"""AE07 / M24-01, V01-01: reserve plan as own entity and the opening lock switch.

* ``hoa_reserve_plan``: planned contribution (Soll) per reserve and year with economic plan
  and resolution reference and status (draft, resolved, superseded); tax classification only
  as a placeholder with release status (not released).
* ``hoa_reserve_policy``: per tenant switch for changes of the opening balance after a
  calculated statement (locked, logged, four_eyes); no row means locked.
* ``hoa_reserve_opening_change``: log of opening changes (applied, pending, rejected).

Revision ID: 0363
Revises: 0362
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0363"
down_revision: str | None = "0362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("hoa_reserve_plan", "hoa_reserve_policy", "hoa_reserve_opening_change")


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
        "hoa_reserve_plan",
        *_common("hoa_reserve_plan"),
        sa.Column("reserve_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("economic_plan_id", sa.Uuid(), nullable=True),
        sa.Column("planned_contribution", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("resolution_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("tax_classification", sa.String(64), nullable=True),
        sa.Column(
            "tax_classification_status",
            sa.String(16),
            server_default="not_released",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'resolved', 'superseded')",
            name=op.f("ck_hoa_reserve_plan_status"),
        ),
        sa.CheckConstraint(
            "tax_classification_status IN ('not_released', 'released')",
            name=op.f("ck_hoa_reserve_plan_tax_status"),
        ),
        sa.CheckConstraint("year BETWEEN 1990 AND 2100", name=op.f("ck_hoa_reserve_plan_year")),
        sa.CheckConstraint(
            "status = 'draft' OR resolution_id IS NOT NULL",
            name=op.f("ck_hoa_reserve_plan_resolution"),
        ),
        sa.ForeignKeyConstraint(
            ["reserve_id"],
            ["hoa_reserve.id"],
            name=op.f("fk_hoa_reserve_plan_reserve_id_hoa_reserve"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["economic_plan_id"],
            ["economic_plan.id"],
            name=op.f("fk_hoa_reserve_plan_economic_plan_id_economic_plan"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolution_id"],
            ["resolution.id"],
            name=op.f("fk_hoa_reserve_plan_resolution_id_resolution"),
        ),
    )
    op.create_index(
        "ix_hoa_reserve_plan_reserve", "hoa_reserve_plan", ["tenant_id", "reserve_id", "year"]
    )
    op.create_index(
        "uq_hoa_reserve_plan_resolved",
        "hoa_reserve_plan",
        ["tenant_id", "reserve_id", "year"],
        unique=True,
        postgresql_where=sa.text("status = 'resolved'"),
    )
    op.create_table(
        "hoa_reserve_policy",
        *_common("hoa_reserve_policy"),
        sa.Column("opening_lock_mode", sa.String(16), server_default="locked", nullable=False),
        sa.CheckConstraint(
            "opening_lock_mode IN ('locked', 'logged', 'four_eyes')",
            name=op.f("ck_hoa_reserve_policy_mode"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_hoa_reserve_policy_tenant_id")),
    )
    op.create_table(
        "hoa_reserve_opening_change",
        *_common("hoa_reserve_opening_change"),
        sa.Column("reserve_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("changes", JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('applied', 'pending', 'rejected')",
            name=op.f("ck_hoa_reserve_opening_change_status"),
        ),
        sa.ForeignKeyConstraint(
            ["reserve_id"],
            ["hoa_reserve.id"],
            name=op.f("fk_hoa_reserve_opening_change_reserve_id_hoa_reserve"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_hoa_reserve_opening_change_reserve",
        "hoa_reserve_opening_change",
        ["tenant_id", "reserve_id"],
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
