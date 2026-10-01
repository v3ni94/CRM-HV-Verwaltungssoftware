"""GA02-07 (AB08): no schema change; the status check of 0310 is unchanged. Placeholder that
keeps the revision chain linear.

Revision ID: 0327
Revises: 0326
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0327"
down_revision: str | None = "0326"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
