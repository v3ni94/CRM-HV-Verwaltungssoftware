"""GA01-06 bis GA01-12 (AA17): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0319
Revises: 0318
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0319"
down_revision: str | None = "0318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
