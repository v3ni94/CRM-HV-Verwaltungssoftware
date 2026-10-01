"""AE24: GoCardless connector placeholder (package cancelled by the operator), no schema change.

Revision ID: 0380
Revises: 0379
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0380"
down_revision: str | None = "0379"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
