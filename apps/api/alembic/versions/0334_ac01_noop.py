"""AC01 (review of waves 12 and 13): no schema change; keeps the revision chain linear.

Revision ID: 0334
Revises: 0333
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0334"
down_revision: str | None = "0333"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
