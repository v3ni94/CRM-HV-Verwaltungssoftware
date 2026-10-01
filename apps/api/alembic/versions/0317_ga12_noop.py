"""GA12 (AA15): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0317
Revises: 0316
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0317"
down_revision: str | None = "0316"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
