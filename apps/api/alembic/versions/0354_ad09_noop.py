"""AD09: documentation only (third gap analysis), no schema change; keeps the revision chain linear.

Revision ID: 0354
Revises: 0353
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0354"
down_revision: str | None = "0353"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
