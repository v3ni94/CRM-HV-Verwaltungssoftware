"""GA14-06 and subledger report (AB01): no schema change, keeps the chain linear.

Revision ID: 0320
Revises: 0319
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0320"
down_revision: str | None = "0319"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
