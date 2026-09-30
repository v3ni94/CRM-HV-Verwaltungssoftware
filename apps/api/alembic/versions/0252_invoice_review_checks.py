"""Incoming invoice checks, creditor plans and e-invoice evidence (M14, 7.9.1, 7.11).

invoice: service contract and original invoice (credit note), PÜ01 mandatory data (place,
issuer tax data, attachments), PÜ03 amounts (stated discount, prepayment, retention) and tax
markers (reverse charge, construction withholding, input tax). invoice_review: delegation and
structured scope (PÜ05). recurring_invoice_plan: contract link, order reference, VAT rate,
anchor day and end. receipt_draft: e-invoice profile, stored validation result, SHA-256 of
the received file and its structured part, hybrid deviations (S02, S03).

Revision ID: 0252
Revises: 0251
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0252"
down_revision: str | None = "0251"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
MONEY = sa.Numeric(14, 2)
RATE = sa.Numeric(20, 8)
EMPTY = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.add_column(
        "invoice",
        sa.Column("service_contract_id", UUID, sa.ForeignKey("service_contract.id"), nullable=True),
    )
    op.add_column(
        "invoice",
        sa.Column(
            "recurring_plan_id", UUID, sa.ForeignKey("recurring_invoice_plan.id"), nullable=True
        ),
    )
    op.add_column(
        "invoice",
        sa.Column("reference_invoice_id", UUID, sa.ForeignKey("invoice.id"), nullable=True),
    )
    op.add_column("invoice", sa.Column("service_place", sa.String(200), nullable=True))
    op.add_column("invoice", sa.Column("issuer_vat_id", sa.String(20), nullable=True))
    op.add_column("invoice", sa.Column("issuer_tax_number", sa.String(30), nullable=True))
    op.add_column(
        "invoice",
        sa.Column("attachment_document_ids", JSONB, nullable=False, server_default=EMPTY),
    )
    op.add_column("invoice", sa.Column("discount_amount", MONEY, nullable=True))
    op.add_column("invoice", sa.Column("prepaid_amount", MONEY, nullable=True))
    op.add_column("invoice", sa.Column("retention_amount", MONEY, nullable=True))
    op.add_column(
        "invoice",
        sa.Column("reverse_charge", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "invoice",
        sa.Column(
            "construction_withholding",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("invoice", sa.Column("input_tax_deductible", sa.Boolean(), nullable=True))

    op.add_column("invoice_review", sa.Column("delegated_by", UUID, nullable=True))
    op.add_column("invoice_review", sa.Column("delegation_reason", sa.Text(), nullable=True))
    op.add_column(
        "invoice_review",
        sa.Column("reviewed_items", JSONB, nullable=False, server_default=EMPTY),
    )

    op.add_column(
        "recurring_invoice_plan",
        sa.Column("service_contract_id", UUID, sa.ForeignKey("service_contract.id"), nullable=True),
    )
    op.add_column(
        "recurring_invoice_plan", sa.Column("order_reference", sa.String(100), nullable=True)
    )
    op.add_column(
        "recurring_invoice_plan",
        sa.Column("vat_percent", RATE, nullable=False, server_default=sa.text("0")),
    )
    op.add_column("recurring_invoice_plan", sa.Column("anchor_day", sa.Integer(), nullable=True))
    op.add_column("recurring_invoice_plan", sa.Column("ended_at", sa.Date(), nullable=True))

    op.add_column("receipt_draft", sa.Column("e_invoice_profile", sa.String(300), nullable=True))
    op.add_column("receipt_draft", sa.Column("validation", JSONB, nullable=True))
    op.add_column("receipt_draft", sa.Column("original_sha256", sa.String(64), nullable=True))
    op.add_column("receipt_draft", sa.Column("structured_sha256", sa.String(64), nullable=True))
    op.add_column("receipt_draft", sa.Column("structured_name", sa.String(200), nullable=True))
    op.add_column(
        "receipt_draft",
        sa.Column("hybrid_deviations", JSONB, nullable=False, server_default=EMPTY),
    )


def downgrade() -> None:
    for column in (
        "hybrid_deviations",
        "structured_name",
        "structured_sha256",
        "original_sha256",
        "validation",
        "e_invoice_profile",
    ):
        op.drop_column("receipt_draft", column)
    for column in (
        "ended_at",
        "anchor_day",
        "vat_percent",
        "order_reference",
        "service_contract_id",
    ):
        op.drop_column("recurring_invoice_plan", column)
    for column in ("reviewed_items", "delegation_reason", "delegated_by"):
        op.drop_column("invoice_review", column)
    for column in (
        "input_tax_deductible",
        "construction_withholding",
        "reverse_charge",
        "retention_amount",
        "prepaid_amount",
        "discount_amount",
        "attachment_document_ids",
        "issuer_tax_number",
        "issuer_vat_id",
        "service_place",
        "reference_invoice_id",
        "recurring_plan_id",
        "service_contract_id",
    ):
        op.drop_column("invoice", column)
