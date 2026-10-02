"""AF06 (wave 17): no schema change; placeholder keeps the migration chain linear.

Revision ID: 0400
Revises: 0399
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0400"
down_revision: str | None = "0399"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
