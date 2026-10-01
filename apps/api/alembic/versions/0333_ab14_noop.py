"""GA09 (AB14): no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0333
Revises: 0332
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0333"
down_revision: str | None = "0332"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
