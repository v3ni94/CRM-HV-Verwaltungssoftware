"""AN02 / GAJ-401: tenant switch for the photo of portal meter readings.

``portal_feature_setting.meter_photo_mode`` (off, hint, required) defaults to hint.

Revision ID: 0451
Revises: 0450
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0451"
down_revision: str | None = "0450"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column("meter_photo_mode", sa.String(16), nullable=False, server_default="hint"),
    )
    op.create_check_constraint(
        "meter_photo_mode",
        "portal_feature_setting",
        "meter_photo_mode IN ('off', 'hint', 'required')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_portal_feature_setting_meter_photo_mode"),
        "portal_feature_setting",
        type_="check",
    )
    op.drop_column("portal_feature_setting", "meter_photo_mode")
