"""dunning_fee_invoice_draft_timestamps: fixes migration 0068 further, which created
``dunning_fee_invoice_draft`` and ``dunning_mahnbescheid_prep`` without the ``server_default``
on ``created_at``/``updated_at`` that ``TimestampMixin`` relies on. Caught by
``tests/integration/test_m16_dunning.py`` (NotNullViolation on insert).

Revision ID: 0072
Revises: 0071
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("dunning_fee_invoice_draft", "dunning_mahnbescheid_prep")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN created_at SET DEFAULT now()")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN updated_at SET DEFAULT now()")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN created_at DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN updated_at DROP DEFAULT")
