"""AD04: documentation only, no schema change; placeholder that keeps the revision chain linear.

Revision ID: 0349
Revises: 0348
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0349"
down_revision: str | None = "0348"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
