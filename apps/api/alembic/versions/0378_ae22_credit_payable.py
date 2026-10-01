"""AE22 / P04-04, Q01-01, M15-07: payables from statement credits, tenant switch (default off).

* ``credit_payable_setting``: one row per tenant, no row means mode ``off``.
* ``credit_payable``: proposal, release and withdrawal of one payable per source.
* ``journal_entry_kind`` gains ``credit_reclass`` (variant reclass: posting creates the payable
  on the creditor line only). An enum value cannot be dropped; the downgrade keeps it.

Revision ID: 0378
Revises: 0377
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0378"
down_revision: str | None = "0377"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("credit_payable_setting", "credit_payable")
NUMBER = "IS NULL OR {0} ~ '^[0-9]{{6}}$'"


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
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE journal_entry_kind ADD VALUE IF NOT EXISTS 'credit_reclass'")

    op.create_table(
        "credit_payable_setting",
        *_common("credit_payable_setting"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="off"),
        sa.Column("four_eyes_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("creditor_account_number", sa.String(6), nullable=True),
        sa.Column("owner_debit_account_number", sa.String(6), nullable=True),
        sa.Column("deposit_debit_account_number", sa.String(6), nullable=True),
        sa.CheckConstraint(
            "mode IN ('off', 'subledger', 'reclass')",
            name=op.f("ck_credit_payable_setting_mode"),
        ),
        *[
            sa.CheckConstraint(
                f"{column} {NUMBER.format(column)}",
                name=op.f(f"ck_credit_payable_setting_{column}"),
            )
            for column in (
                "creditor_account_number",
                "owner_debit_account_number",
                "deposit_debit_account_number",
            )
        ],
        sa.UniqueConstraint("tenant_id", name="uq_credit_payable_setting_tenant"),
    )

    op.create_table(
        "credit_payable",
        *_common("credit_payable"),
        sa.Column("ledger_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("source_entry_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("variant", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("payout_reason", sa.String(24), nullable=False),
        sa.Column("open_item_id", sa.Uuid(), nullable=True),
        sa.Column("reclass_entry_id", sa.Uuid(), nullable=True),
        sa.Column("reversal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("released_by", sa.Uuid(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.Uuid(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdraw_reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_credit_payable_amount_positive")),
        sa.CheckConstraint(
            "source_type IN ('rent_statement', 'owner_statement', 'deposit_settlement')",
            name=op.f("ck_credit_payable_source_type"),
        ),
        sa.CheckConstraint(
            "variant IN ('subledger', 'reclass')", name=op.f("ck_credit_payable_variant")
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'released', 'withdrawn')",
            name=op.f("ck_credit_payable_status"),
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"], ["ledger.id"], name=op.f("fk_credit_payable_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f("fk_credit_payable_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_credit_payable_source_entry_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["open_item_id"],
            ["open_item.id"],
            name=op.f("fk_credit_payable_open_item_id_open_item"),
        ),
        sa.ForeignKeyConstraint(
            ["reclass_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_credit_payable_reclass_entry_id_journal_entry"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_credit_payable_reversal_entry_id_journal_entry"),
        ),
    )
    op.create_index(
        "ix_credit_payable_tenant_ledger", "credit_payable", ["tenant_id", "ledger_id"]
    )
    op.create_index(
        "uq_credit_payable_active_source",
        "credit_payable",
        ["tenant_id", "source_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'withdrawn'"),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    # The enum value credit_reclass stays (PostgreSQL cannot drop an enum value); entries of
    # that kind would otherwise lose their meaning.
