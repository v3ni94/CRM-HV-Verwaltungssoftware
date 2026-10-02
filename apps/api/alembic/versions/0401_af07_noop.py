"""AF07 (wave 17): no schema change; placeholder keeps the migration chain linear.

Revision ID: 0401
Revises: 0400
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0401"
down_revision: str | None = "0400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
