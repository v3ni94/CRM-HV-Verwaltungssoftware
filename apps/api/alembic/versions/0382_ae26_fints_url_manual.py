"""AE26 / M11-01: manual FinTS address per connection (bank merger, new data centre).

``fints_connection.fints_url_manual`` is NULL until an operator enters an address through
``PATCH /banking/fints/connections/{id}``; it wins over the institute list. No RLS change: the
table already carries the tenant policy.

Revision ID: 0382
Revises: 0381
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0382"
down_revision: str | None = "0381"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fints_connection", sa.Column("fints_url_manual", sa.String(length=300), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("fints_connection", "fints_url_manual")
