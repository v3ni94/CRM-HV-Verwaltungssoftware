"""AF03: banking connections and direct debit masks (web-crm only), no schema change; keeps
the revision chain linear.

Revision ID: 0397
Revises: 0396
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0397"
down_revision: str | None = "0396"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
