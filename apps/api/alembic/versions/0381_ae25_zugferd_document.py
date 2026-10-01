"""AE25 / S13-03: ZUGFeRD / Factur-X document of a Verwalterhonorar invoice.

* ``admin_fee_invoice.zugferd_document_id`` (nullable, FK to ``document``): the filed hybrid
  PDF with the embedded CII (``POST /accounting/admin-fee-invoices/{id}/zugferd/document``).
* ``admin_fee_invoice.zugferd_check`` (JSONB, nullable): the own check result at filing time
  (CII structure, PDF/A pre-check, ``official`` false). Nothing is posted or sent.

Revision ID: 0381
Revises: 0380
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0381"
down_revision: str | None = "0380"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_fee_invoice", sa.Column("zugferd_document_id", sa.UUID(), nullable=True))
    op.add_column(
        "admin_fee_invoice",
        sa.Column("zugferd_check", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "admin_fee_invoice_zugferd_document_id_fkey",
        "admin_fee_invoice",
        "document",
        ["zugferd_document_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "admin_fee_invoice_zugferd_document_id_fkey", "admin_fee_invoice", type_="foreignkey"
    )
    op.drop_column("admin_fee_invoice", "zugferd_check")
    op.drop_column("admin_fee_invoice", "zugferd_document_id")
