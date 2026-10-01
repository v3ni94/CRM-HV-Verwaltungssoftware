"""GA14-02 und GA14-04 (AB02): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0321
Revises: 0320
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0321"
down_revision: str | None = "0320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
