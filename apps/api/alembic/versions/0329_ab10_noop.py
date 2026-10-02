"""GA08-01, GA08-02, GA08-05 (AB10): no schema change; placeholder that keeps the revision
chain linear.

Revision ID: 0329
Revises: 0328
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0329"
down_revision: str | None = "0328"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
