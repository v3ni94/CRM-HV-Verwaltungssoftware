"""GA10-03 und GA12-06 (AB11): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0330
Revises: 0329
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0330"
down_revision: str | None = "0329"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
