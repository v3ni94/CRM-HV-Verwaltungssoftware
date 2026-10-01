"""AE04: draft numbers for rent invoices use the existing counter table (negated year), no schema change.

Revision ID: 0360
Revises: 0359
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0360"
down_revision: str | None = "0359"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
