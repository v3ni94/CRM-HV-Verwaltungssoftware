"""AD11: quick send signature of the acting user, no schema change; keeps the revision chain linear.

Revision ID: 0356
Revises: 0355
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0356"
down_revision: str | None = "0355"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
