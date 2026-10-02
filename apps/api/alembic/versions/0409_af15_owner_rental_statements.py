"""AF15 / GAC-01: tenant switch for owner statements (rental/SEV) in the owner portal.

``portal_feature_setting.owner_rental_statements_enabled`` defaults to false; the output also
needs release gate G3.

Revision ID: 0409
Revises: 0408
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0409"
down_revision: str | None = "0408"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column(
            "owner_rental_statements_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("portal_feature_setting", "owner_rental_statements_enabled")
