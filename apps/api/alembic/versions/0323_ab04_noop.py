"""GA04-05 und GA04-06 (AB04): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0323
Revises: 0322
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0323"
down_revision: str | None = "0322"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
