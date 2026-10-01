"""GA12-08 (AC09): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0342
Revises: 0341
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0342"
down_revision: str | None = "0341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
