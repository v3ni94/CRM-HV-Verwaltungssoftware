"""Placeholder for package AA12 (GA08-01, 02, 03, 05, 07): no schema change, keeps the chain linear.

Revision ID: 0314
Revises: 0313
"""

from collections.abc import Sequence

revision: str = "0314"
down_revision: str | None = "0313"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
