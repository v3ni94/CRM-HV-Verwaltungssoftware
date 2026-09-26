"""finAPI user identity per connection and incremental sync cursor (M11-01, operator decision
26.09.2026: aggregator finAPI first, EBICS later). Adds the encrypted finAPI user password of
a connection (OAuth2 password grant for the user token, never a bank credential) and the
per account sync cursor (newest booking date and provider transaction id imported so far).
Columns only; both tables keep their RLS policies from migration 0050 (ADR 0002).

Revision ID: 0141
Revises: 0140
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0141"
down_revision: str | None = "0140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finapi_connection", sa.Column("finapi_user_password", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "finapi_account_link", sa.Column("last_synced_booking_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "finapi_account_link",
        sa.Column("last_synced_transaction_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("finapi_account_link", "last_synced_transaction_id")
    op.drop_column("finapi_account_link", "last_synced_booking_date")
    op.drop_column("finapi_connection", "finapi_user_password")
