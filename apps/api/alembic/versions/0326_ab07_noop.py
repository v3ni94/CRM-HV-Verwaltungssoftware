"""GA07-02, GA07-03, GA06-02, GA06-03 (AB07): no schema change; keeps the chain linear.

Revision ID: 0326
Revises: 0325
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0326"
down_revision: str | None = "0325"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
