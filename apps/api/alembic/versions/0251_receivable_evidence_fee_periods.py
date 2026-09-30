"""Receivable evidence and difference items, fee invoice periods and corrections (M13).

receivable_item: contract version, applied payment plan, start of validity, reason and source
document of the applied amount (7.5 evidence), and the difference to an already posted item
(plan changed after posting). admin_fee_invoice: service period with one invoice per setting
and period, kind (invoice or credit note), corrected invoice, release and cancellation trail.

Revision ID: 0251
Revises: 0250
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0251"
down_revision: str | None = "0250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("receivable_item", sa.Column("contract_version", sa.Integer(), nullable=True))
    op.add_column(
        "receivable_item",
        sa.Column("payment_schedule_id", UUID, sa.ForeignKey("payment_schedule.id"), nullable=True),
    )
    op.add_column("receivable_item", sa.Column("basis_valid_from", sa.Date(), nullable=True))
    op.add_column("receivable_item", sa.Column("basis_reason", sa.String(32), nullable=True))
    op.add_column("receivable_item", sa.Column("basis_document_id", UUID, nullable=True))
    op.add_column(
        "receivable_item",
        sa.Column(
            "difference_of_item_id", UUID, sa.ForeignKey("receivable_item.id"), nullable=True
        ),
    )
    op.add_column(
        "receivable_item", sa.Column("difference_amount", sa.Numeric(14, 2), nullable=True)
    )

    op.add_column("admin_fee_invoice", sa.Column("period_start", sa.Date(), nullable=True))
    op.add_column("admin_fee_invoice", sa.Column("period_end", sa.Date(), nullable=True))
    op.add_column(
        "admin_fee_invoice",
        sa.Column("kind", sa.String(16), nullable=False, server_default="invoice"),
    )
    op.add_column(
        "admin_fee_invoice",
        sa.Column(
            "corrects_invoice_id", UUID, sa.ForeignKey("admin_fee_invoice.id"), nullable=True
        ),
    )
    op.add_column("admin_fee_invoice", sa.Column("released_at", TS, nullable=True))
    op.add_column("admin_fee_invoice", sa.Column("released_by", UUID, nullable=True))
    op.add_column("admin_fee_invoice", sa.Column("cancelled_at", TS, nullable=True))
    op.add_column("admin_fee_invoice", sa.Column("cancelled_by", UUID, nullable=True))
    op.add_column("admin_fee_invoice", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.create_index(
        "uq_admin_fee_invoice_period",
        "admin_fee_invoice",
        ["tenant_id", "fee_setting_id", "period_start"],
        unique=True,
        postgresql_where=sa.text(
            "kind = 'invoice' AND cancelled_at IS NULL AND period_start IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_admin_fee_invoice_period", table_name="admin_fee_invoice")
    for column in (
        "cancel_reason",
        "cancelled_by",
        "cancelled_at",
        "released_by",
        "released_at",
        "corrects_invoice_id",
        "kind",
        "period_end",
        "period_start",
    ):
        op.drop_column("admin_fee_invoice", column)
    for column in (
        "difference_amount",
        "difference_of_item_id",
        "basis_document_id",
        "basis_reason",
        "basis_valid_from",
        "payment_schedule_id",
        "contract_version",
    ):
        op.drop_column("receivable_item", column)
