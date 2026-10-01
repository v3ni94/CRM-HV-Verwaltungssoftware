"""Accounting fee invoices: PDF document reference (M13-05).

Revision ID: 0282
Revises: 0281
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0282"
down_revision: str | None = "0281"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_fee_invoice", sa.Column("pdf_document_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "admin_fee_invoice_pdf_document_id_fkey",
        "admin_fee_invoice",
        "document",
        ["pdf_document_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "admin_fee_invoice_pdf_document_id_fkey", "admin_fee_invoice", type_="foreignkey"
    )
    op.drop_column("admin_fee_invoice", "pdf_document_id")
