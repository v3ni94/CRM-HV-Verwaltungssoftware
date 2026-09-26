"""contact_bank_account: store the rejection reason of a four eyes decision (M5-01, M19-05
addendum, review 26.09.2026). Until now the reason given with ``POST .../bank-accounts/{id}/
reject`` was only written to the audit event ``bank_account.rejected``; the API and the CRM
could not show it. Adds ``rejected_reason`` (nullable, at most 500 characters). ``rejected_by``
and ``rejected_at`` in the API are the existing ``decided_by`` and ``decided_at`` of a rejected
row, no new columns. The table already carries tenant RLS (migration 0003); the new column
inherits it, RLS unchanged.

Revision ID: 0132
Revises: 0131
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0132"
down_revision: str | None = "0131"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "contact_bank_account"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("rejected_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "rejected_reason")
