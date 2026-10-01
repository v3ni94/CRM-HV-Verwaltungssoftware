"""GA09 (AA16): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0318
Revises: 0317
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0318"
down_revision: str | None = "0317"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
