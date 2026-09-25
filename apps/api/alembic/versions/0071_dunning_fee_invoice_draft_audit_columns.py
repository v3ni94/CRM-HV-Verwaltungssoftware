"""dunning_fee_invoice_draft_audit_columns: fixes migration 0068, which created
``dunning_fee_invoice_draft`` and ``dunning_mahnbescheid_prep`` without the ``created_by``/
``updated_by`` columns every ``TimestampMixin`` table needs. Caught by
``tests/integration/test_m16_dunning.py`` (UndefinedColumn on insert).

Revision ID: 0071
Revises: 0070
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071"
down_revision: str | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dunning_fee_invoice_draft",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "dunning_fee_invoice_draft",
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "dunning_mahnbescheid_prep",
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dunning_mahnbescheid_prep", "updated_by")
    op.drop_column("dunning_fee_invoice_draft", "updated_by")
    op.drop_column("dunning_fee_invoice_draft", "created_by")
