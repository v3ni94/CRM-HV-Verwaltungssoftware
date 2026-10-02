"""AF16 (GAC-02): tenant portal switch for released operating cost statements.

Revision ID: 0410
Revises: 0409
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0410"
down_revision: str | None = "0409"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_feature_setting",
        sa.Column("tenant_statement_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("portal_feature_setting", "tenant_statement_enabled")
