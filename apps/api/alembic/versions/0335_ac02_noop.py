"""Platform audit page (AC02): no schema change, keeps the chain linear.

Revision ID: 0335
Revises: 0334
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0335"
down_revision: str | None = "0334"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
