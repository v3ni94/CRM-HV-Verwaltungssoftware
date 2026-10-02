"""AJ07 (GAI-310): failed attempt counter for the magic link e-mail code.

Revision ID: 0446
Revises: 0445
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0446"
down_revision: str | None = "0445"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "portal_magic_link",
        sa.Column(
            "code_failed_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    op.drop_column("portal_magic_link", "code_failed_attempts")
