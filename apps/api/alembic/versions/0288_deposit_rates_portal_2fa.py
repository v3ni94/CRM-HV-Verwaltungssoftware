"""Deposit interest rate history and yearly interest drafts (B15), portal second factor policy
per tenant (B20).

Revision ID: 0288
Revises: 0287
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0288"
down_revision: str | None = "0287"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RATES = "deposit_interest_rate"
DRAFTS = "deposit_interest_draft"


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
    ]


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE needs an autocommit block (same as the other enum extensions).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE deposit_interest_mode ADD VALUE IF NOT EXISTS 'deposit_rates'")

    op.create_table(
        RATES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("deposit_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(8, 5), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_deposit_interest_rate_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deposit_id"],
            ["deposit.id"],
            name=op.f("fk_deposit_interest_rate_deposit_id_deposit"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_interest_rate")),
        sa.UniqueConstraint(
            "deposit_id", "valid_from", name=op.f("uq_deposit_interest_rate_deposit_id_valid_from")
        ),
    )
    for statement in tenant_rls_statements(RATES):
        op.execute(statement)

    op.create_table(
        DRAFTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("deposit_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Numeric(8, 5), nullable=True),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("movement_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'discarded')",
            name=op.f("ck_deposit_interest_draft_deposit_interest_draft_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_deposit_interest_draft_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deposit_id"],
            ["deposit.id"],
            name=op.f("fk_deposit_interest_draft_deposit_id_deposit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["movement_id"],
            ["deposit_movement.id"],
            name=op.f("fk_deposit_interest_draft_movement_id_deposit_movement"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_interest_draft")),
        sa.UniqueConstraint(
            "deposit_id", "year", name=op.f("uq_deposit_interest_draft_deposit_id_year")
        ),
    )
    for statement in tenant_rls_statements(DRAFTS):
        op.execute(statement)

    op.add_column(
        "tenant_settings",
        sa.Column(
            "portal_second_factor",
            sa.String(length=16),
            server_default="account_choice",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_tenant_settings_portal_second_factor_values"),
        "tenant_settings",
        "portal_second_factor IN ('account_choice', 'required')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_tenant_settings_portal_second_factor_values"), "tenant_settings", type_="check"
    )
    op.drop_column("tenant_settings", "portal_second_factor")
    for statement in drop_tenant_rls_statements(DRAFTS):
        op.execute(statement)
    op.drop_table(DRAFTS)
    for statement in drop_tenant_rls_statements(RATES):
        op.execute(statement)
    op.drop_table(RATES)
    # The enum value 'deposit_rates' stays (PostgreSQL cannot drop enum values); no row uses it
    # after the tables are gone only if no settlement was created with it.
