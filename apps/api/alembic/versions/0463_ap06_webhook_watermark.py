"""AP06 / GAM-503: watermark per webhook subscription (webhook_subscription).

Revision ID: 0463
Revises: 0462
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0463"
down_revision: str | None = "0462"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_subscription",
        sa.Column("watermark_occurred_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_subscription", "watermark_occurred_at")
