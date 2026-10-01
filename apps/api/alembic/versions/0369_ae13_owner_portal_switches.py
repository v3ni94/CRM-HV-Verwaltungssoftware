"""AE13: owner portal switches (rental income view, ticket scope) on portal_feature_setting.

Revision ID: 0369
Revises: 0368
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0369"
down_revision: str | None = "0368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column(
            "owner_rental_income_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "portal_feature_setting",
        sa.Column("owner_ticket_scope", sa.String(16), nullable=False, server_default="released"),
    )
    op.create_check_constraint(
        "owner_ticket_scope",
        "portal_feature_setting",
        "owner_ticket_scope IN ('none', 'released', 'property')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_portal_feature_setting_owner_ticket_scope"),
        "portal_feature_setting",
        type_="check",
    )
    op.drop_column("portal_feature_setting", "owner_ticket_scope")
    op.drop_column("portal_feature_setting", "owner_rental_income_enabled")
