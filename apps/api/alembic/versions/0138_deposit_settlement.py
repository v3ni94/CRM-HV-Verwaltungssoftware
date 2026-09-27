"""Deposit settlement drafts and reference interest rates (rule M5-02, operator decision
26.09.2026): ``deposit_interest_reference_rate`` (rate per year, maintained by the tenant) and
``deposit_settlement`` (settlement draft per deposit: interest mode, interest per year,
deductions, payout amount). Records only, no postings. Tenant tables with RLS (ADR 0002).

Revision ID: 0138
Revises: 0137
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0138"
down_revision: str | None = "0137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RATES = "deposit_interest_reference_rate"
SETTLEMENT = "deposit_settlement"
_MODES = ("individual", "reference_rate", "none")
_STATUSES = ("draft", "released")


def upgrade() -> None:
    postgresql.ENUM(*_MODES, name="deposit_interest_mode").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(*_STATUSES, name="deposit_settlement_status").create(
        op.get_bind(), checkfirst=True
    )
    # create_type=False: the types exist already, create_table must not create them again.
    mode = postgresql.ENUM(*_MODES, name="deposit_interest_mode", create_type=False)
    status = postgresql.ENUM(*_STATUSES, name="deposit_settlement_status", create_type=False)

    op.create_table(
        RATES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Numeric(8, 5), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_deposit_interest_reference_rate_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_interest_reference_rate")),
        sa.UniqueConstraint(
            "tenant_id", "year", name=op.f("uq_deposit_interest_reference_rate_tenant_id_year")
        ),
    )
    for statement in tenant_rls_statements(RATES):
        op.execute(statement)

    op.create_table(
        SETTLEMENT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("deposit_id", sa.Uuid(), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("interest_mode", mode, nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("interest_years", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("deductions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("principal_paid", sa.Numeric(14, 2), nullable=False),
        sa.Column("offsets_recorded", sa.Numeric(14, 2), nullable=False),
        sa.Column("payouts_recorded", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_recorded", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("deductions_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("payout_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("number", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_deposit_settlement_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deposit_id"],
            ["deposit.id"],
            name=op.f("fk_deposit_settlement_deposit_id_deposit"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposit_settlement")),
    )
    op.create_index(
        op.f("ix_deposit_settlement_deposit_id"), SETTLEMENT, ["deposit_id"], unique=False
    )
    for statement in tenant_rls_statements(SETTLEMENT):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(SETTLEMENT):
        op.execute(statement)
    op.drop_index(op.f("ix_deposit_settlement_deposit_id"), table_name=SETTLEMENT)
    op.drop_table(SETTLEMENT)
    for statement in drop_tenant_rls_statements(RATES):
        op.execute(statement)
    op.drop_table(RATES)
    postgresql.ENUM(name="deposit_settlement_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="deposit_interest_mode").drop(op.get_bind(), checkfirst=True)
