"""GA13-24 (AC10): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0343
Revises: 0342
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0343"
down_revision: str | None = "0342"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
