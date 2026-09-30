"""No-op link for package P18 (AI): no schema change was needed, the number is kept so the
chain 0266 -> 0267 -> 0268 stays linear.

Revision ID: 0267
Revises: 0266
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0267"
down_revision: str | None = "0266"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
