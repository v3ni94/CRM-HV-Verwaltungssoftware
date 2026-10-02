"""AG09 / GAF-36: tenant switch for the owner receipt search in the portal.

``portal_feature_setting.portal_owner_receipts_enabled`` defaults to false; the list also needs
release gate G4.

Revision ID: 0427
Revises: 0426
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0427"
down_revision: str | None = "0426"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column(
            "portal_owner_receipts_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("portal_feature_setting", "portal_owner_receipts_enabled")
