"""GA03-01, GA07-01 (AB06): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0325
Revises: 0324
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0325"
down_revision: str | None = "0324"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
