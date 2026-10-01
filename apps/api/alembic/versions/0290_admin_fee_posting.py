"""Verwalterhonorar: status cancelled and revenue posting drafts (M13-05, M13-07).

Revision ID: 0290
Revises: 0289
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0290"
down_revision: str | None = "0289"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFIG = "admin_fee_posting_config"
INVOICE = "admin_fee_invoice"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE admin_fee_invoice_status ADD VALUE IF NOT EXISTS 'cancelled'")
    op.execute("UPDATE admin_fee_invoice SET status = 'cancelled' WHERE cancelled_at IS NOT NULL")

    for column in ("payer_entry_id", "manager_entry_id"):
        op.add_column(INVOICE, sa.Column(column, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{INVOICE}_{column}_journal_entry"),
            INVOICE,
            "journal_entry",
            [column],
            ["id"],
        )

    op.create_table(
        CONFIG,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("manager_ledger_id", sa.Uuid(), nullable=False),
        sa.Column("manager_receivable_account_id", sa.Uuid(), nullable=False),
        sa.Column("manager_revenue_account_id", sa.Uuid(), nullable=False),
        sa.Column("manager_vat_account_id", sa.Uuid(), nullable=True),
        sa.Column("payer_expense_account_number", sa.String(6), nullable=False),
        sa.Column("payer_payable_account_number", sa.String(6), nullable=False),
        sa.Column("payer_vat_account_number", sa.String(6), nullable=True),
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
            name=op.f(f"fk_{CONFIG}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_ledger_id"], ["ledger.id"], name=op.f(f"fk_{CONFIG}_manager_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["manager_receivable_account_id"],
            ["ledger_account.id"],
            name=op.f(f"fk_{CONFIG}_manager_receivable_account_id_ledger_account"),
        ),
        sa.ForeignKeyConstraint(
            ["manager_revenue_account_id"],
            ["ledger_account.id"],
            name=op.f(f"fk_{CONFIG}_manager_revenue_account_id_ledger_account"),
        ),
        sa.ForeignKeyConstraint(
            ["manager_vat_account_id"],
            ["ledger_account.id"],
            name=op.f(f"fk_{CONFIG}_manager_vat_account_id_ledger_account"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{CONFIG}")),
        sa.UniqueConstraint("tenant_id", name="uq_admin_fee_posting_config_tenant_id"),
        sa.CheckConstraint(
            "payer_expense_account_number ~ '^[0-9]{6}$' "
            "AND payer_payable_account_number ~ '^[0-9]{6}$' "
            "AND (payer_vat_account_number IS NULL "
            "OR payer_vat_account_number ~ '^[0-9]{6}$')",
            name=op.f(f"ck_{CONFIG}_payer_numbers_six_digits"),
        ),
    )
    for statement in tenant_rls_statements(CONFIG):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(CONFIG):
        op.execute(statement)
    op.drop_table(CONFIG)
    for column in ("manager_entry_id", "payer_entry_id"):
        op.drop_constraint(
            op.f(f"fk_{INVOICE}_{column}_journal_entry"), INVOICE, type_="foreignkey"
        )
        op.drop_column(INVOICE, column)
    # The enum value stays (PostgreSQL cannot drop it); rows fall back to the release state.
    op.execute(
        "UPDATE admin_fee_invoice SET status = CASE WHEN released_at IS NULL THEN 'issued' "
        "ELSE 'released' END::admin_fee_invoice_status WHERE status = 'cancelled'"
    )
