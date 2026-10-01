"""AE02: four eyes switch on the chart of accounts template (M10-01, SA-08).

Revision ID: 0358
Revises: 0357
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0358"
down_revision: str | None = "0357"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chart_of_accounts_template",
        sa.Column(
            "four_eyes_required", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )


def downgrade() -> None:
    op.drop_column("chart_of_accounts_template", "four_eyes_required")
