"""AC12: documentation only, no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0345
Revises: 0344
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0345"
down_revision: str | None = "0344"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
