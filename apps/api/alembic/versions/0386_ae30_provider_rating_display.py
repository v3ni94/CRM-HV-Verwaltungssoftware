"""AE30 (AA14-02): tenant switch for the display of provider ratings in the portal administration.

Revision ID: 0386
Revises: 0385
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0386"
down_revision: str | None = "0385"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column("provider_rating_display", sa.String(16), nullable=False, server_default="off"),
    )
    op.create_check_constraint(
        "provider_rating_display",
        "portal_feature_setting",
        "provider_rating_display IN ('off', 'staff')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_portal_feature_setting_provider_rating_display"),
        "portal_feature_setting",
        type_="check",
    )
    op.drop_column("portal_feature_setting", "provider_rating_display")
