"""AG12 / AF25-02: switch for community owner statements in the owner portal.

``portal_feature_setting.owner_hoa_rental_statements_enabled`` defaults to false.

Revision ID: 0430
Revises: 0429
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0430"
down_revision: str | None = "0429"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column(
            "owner_hoa_rental_statements_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("portal_feature_setting", "owner_hoa_rental_statements_enabled")
