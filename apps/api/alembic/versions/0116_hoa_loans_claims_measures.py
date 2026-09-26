"""WEG loans, insurance claims and larger measures (7.8 W10, A59) plus the explained
differences of the cash flow reconciliation on the statement (W04, A60).

Tables hoa_measure, hoa_loan, hoa_loan_item, hoa_measure_financing, hoa_insurance_claim and
hoa_insurance_claim_item carry no balances of their own: every amount becomes a financial fact
only through the referenced journal entry. All tables are tenant tables with RLS (ADR 0002).

Revision ID: 0116
Revises: 0115
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0116"
down_revision: str | None = "0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "hoa_measure",
    "hoa_loan",
    "hoa_loan_item",
    "hoa_measure_financing",
    "hoa_insurance_claim",
    "hoa_insurance_claim_item",
)


def _audit_columns() -> list[sa.Column[Any]]:
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


def _fk(
    table: str, column: str, target: str, ondelete: str | None = None
) -> sa.ForeignKeyConstraint:
    target_table = target.split(".")[0]
    return sa.ForeignKeyConstraint(
        [column],
        [target],
        name=op.f(f"fk_{table}_{column}_{target_table}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "hoa_measure",
        sa.Column("legal_entity_id", sa.UUID(), nullable=False),
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("kind_basis", sa.Text(), nullable=True),
        sa.Column("cost_frame", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("resolution_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_end", sa.Date(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        _fk("hoa_measure", "account_id", "ledger_account.id"),
        _fk("hoa_measure", "ledger_id", "ledger.id"),
        _fk("hoa_measure", "legal_entity_id", "legal_entity.id"),
        _fk("hoa_measure", "resolution_id", "resolution.id"),
        _fk("hoa_measure", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_measure")),
    )
    op.create_table(
        "hoa_loan",
        sa.Column("legal_entity_id", sa.UUID(), nullable=False),
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("lender", sa.String(length=200), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("principal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("interest_rate_percent", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("instalment", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("resolution_id", sa.UUID(), nullable=True),
        sa.Column("measure_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        _fk("hoa_loan", "account_id", "ledger_account.id"),
        _fk("hoa_loan", "ledger_id", "ledger.id"),
        _fk("hoa_loan", "legal_entity_id", "legal_entity.id"),
        _fk("hoa_loan", "measure_id", "hoa_measure.id"),
        _fk("hoa_loan", "resolution_id", "resolution.id"),
        _fk("hoa_loan", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_loan")),
    )
    op.create_table(
        "hoa_loan_item",
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _fk("hoa_loan_item", "journal_entry_id", "journal_entry.id"),
        _fk("hoa_loan_item", "loan_id", "hoa_loan.id", ondelete="CASCADE"),
        _fk("hoa_loan_item", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_loan_item")),
    )
    op.create_table(
        "hoa_measure_financing",
        sa.Column("measure_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("special_levy_id", sa.UUID(), nullable=True),
        sa.Column("loan_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _fk("hoa_measure_financing", "loan_id", "hoa_loan.id"),
        _fk("hoa_measure_financing", "measure_id", "hoa_measure.id", ondelete="CASCADE"),
        _fk("hoa_measure_financing", "special_levy_id", "special_levy.id"),
        _fk("hoa_measure_financing", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_measure_financing")),
    )
    op.create_table(
        "hoa_insurance_claim",
        sa.Column("legal_entity_id", sa.UUID(), nullable=False),
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("damage_date", sa.Date(), nullable=False),
        sa.Column("reported_on", sa.Date(), nullable=True),
        sa.Column("insurer", sa.String(length=200), nullable=True),
        sa.Column("policy_reference", sa.String(length=100), nullable=True),
        sa.Column("claim_number", sa.String(length=100), nullable=True),
        sa.Column("deductible", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("regress_party", sa.String(length=200), nullable=True),
        sa.Column("measure_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_audit_columns(),
        _fk("hoa_insurance_claim", "ledger_id", "ledger.id"),
        _fk("hoa_insurance_claim", "legal_entity_id", "legal_entity.id"),
        _fk("hoa_insurance_claim", "measure_id", "hoa_measure.id"),
        _fk("hoa_insurance_claim", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_insurance_claim")),
    )
    op.create_table(
        "hoa_insurance_claim_item",
        sa.Column("claim_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        _fk("hoa_insurance_claim_item", "claim_id", "hoa_insurance_claim.id", ondelete="CASCADE"),
        _fk("hoa_insurance_claim_item", "contract_id", "contract.id"),
        _fk("hoa_insurance_claim_item", "journal_entry_id", "journal_entry.id"),
        _fk("hoa_insurance_claim_item", "tenant_id", "tenant.id", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_insurance_claim_item")),
    )
    op.add_column(
        "hoa_statement",
        sa.Column(
            "reconciliation_notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_column("hoa_statement", "reconciliation_notes")
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
