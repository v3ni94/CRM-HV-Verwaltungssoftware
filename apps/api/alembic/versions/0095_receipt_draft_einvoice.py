"""receipt_draft_einvoice: e-invoice reading in the Belegeingang (M14, spec 13.5, cases D41,
D42, D44). Adds to ``receipt_draft`` the format of the structured part, its line items and
masked payment block, the visible conflicts between XML and PDF (D42) and the deterministic
findings of the intake (formal completeness, unproven § 35a estimates). No data migration;
existing drafts read as ``e_invoice_format='none'`` with empty lists.

Revision ID: 0095
Revises: 0094
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0095"
down_revision: str | None = "0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt_draft",
        sa.Column("e_invoice_format", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column(
        "receipt_draft",
        sa.Column(
            "xml_lines",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "receipt_draft",
        sa.Column("xml_payment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "receipt_draft",
        sa.Column(
            "conflicts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "receipt_draft",
        sa.Column(
            "findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    for name in ("findings", "conflicts", "xml_payment", "xml_lines", "e_invoice_format"):
        op.drop_column("receipt_draft", name)
