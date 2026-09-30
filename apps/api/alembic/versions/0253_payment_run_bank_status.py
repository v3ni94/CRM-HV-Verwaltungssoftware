"""Payment run and direct debit feedback (M15-01 to M15-07, S15-02).

payment_order: payout without invoice (contact bank account, reason) and bank reason code.
payment_bank_config: limits and lead days agreed with the bank (operator input).
direct_debit_order: bank feedback per collection. New tenant tables with RLS (ADR 0002):
bank_status_report (pain.002/camt.054 imports), payment_run_setting, payment_run_preview.

Revision ID: 0253
Revises: 0252
Create Date: 2026-09-30
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0253"
down_revision: str | None = "0252"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(14, 2)
NEW_TABLES = ("bank_status_report", "payment_run_setting", "payment_run_preview")


def _base(table: str) -> list[Any]:
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
            ["tenant_id"], ["tenant.id"], name=f"fk_{table}_tenant_id_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
    ]


def upgrade() -> None:
    op.add_column("payment_order", sa.Column("contact_bank_account_id", sa.Uuid(), nullable=True))
    op.add_column("payment_order", sa.Column("payout_reason", sa.String(32), nullable=True))
    op.add_column(
        "payment_order", sa.Column("bank_status_reason_code", sa.String(8), nullable=True)
    )
    op.create_foreign_key(
        "fk_payment_order_contact_bank_account_id_contact_bank_account",
        "payment_order",
        "contact_bank_account",
        ["contact_bank_account_id"],
        ["id"],
    )
    for name, type_ in (
        ("single_order_limit", MONEY),
        ("daily_limit", MONEY),
        ("dd_lead_days_frst", sa.Integer()),
        ("dd_lead_days_rcur", sa.Integer()),
        ("pre_notification_days", sa.Integer()),
    ):
        op.add_column("payment_bank_config", sa.Column(name, type_, nullable=True))

    op.add_column(
        "direct_debit_order",
        sa.Column("bank_status", sa.String(16), nullable=False, server_default="open"),
    )
    op.add_column("direct_debit_order", sa.Column("bank_status_reason_code", sa.String(8)))
    op.add_column("direct_debit_order", sa.Column("bank_status_reason", sa.String(500)))
    op.add_column("direct_debit_order", sa.Column("collected_amount", MONEY))
    op.add_column("direct_debit_order", sa.Column("bank_transaction_id", sa.Uuid()))
    op.add_column("direct_debit_order", sa.Column("bank_status_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_direct_debit_order_bank_transaction_id_bank_transaction",
        "direct_debit_order",
        "bank_transaction",
        ["bank_transaction_id"],
        ["id"],
    )

    op.create_table(
        "bank_status_report",
        *_base("bank_status_report"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("message_id", sa.String(35), nullable=True),
        sa.Column("original_message_id", sa.String(35), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("tenant_id", "file_sha256", name="uq_bank_status_report_file"),
    )
    op.create_table(
        "payment_run_setting",
        *_base("payment_run_setting"),
        sa.Column(
            "weekly_preview_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.UniqueConstraint("tenant_id", name="uq_payment_run_setting_tenant"),
    )
    op.create_table(
        "payment_run_preview",
        *_base("payment_run_preview"),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_payment_run_preview_tenant_created", "payment_run_preview", ["tenant_id", "created_at"]
    )
    for table in NEW_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in NEW_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_payment_run_preview_tenant_created", table_name="payment_run_preview")
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.drop_constraint(
        "fk_direct_debit_order_bank_transaction_id_bank_transaction",
        "direct_debit_order",
        type_="foreignkey",
    )
    for name in (
        "bank_status_at",
        "bank_transaction_id",
        "collected_amount",
        "bank_status_reason",
        "bank_status_reason_code",
        "bank_status",
    ):
        op.drop_column("direct_debit_order", name)
    for name in (
        "pre_notification_days",
        "dd_lead_days_rcur",
        "dd_lead_days_frst",
        "daily_limit",
        "single_order_limit",
    ):
        op.drop_column("payment_bank_config", name)
    op.drop_constraint(
        "fk_payment_order_contact_bank_account_id_contact_bank_account",
        "payment_order",
        type_="foreignkey",
    )
    for name in ("bank_status_reason_code", "payout_reason", "contact_bank_account_id"):
        op.drop_column("payment_order", name)
