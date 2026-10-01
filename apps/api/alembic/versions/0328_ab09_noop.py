"""GA02-05, GA03-07 (AB09): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0328
Revises: 0327
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0328"
down_revision: str | None = "0327"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
