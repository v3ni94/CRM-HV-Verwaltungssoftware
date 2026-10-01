"""Placeholder for package AA04 (GA04-05, GA04-06): no schema change, keeps the chain linear.

Revision ID: 0306
Revises: 0305
"""

from collections.abc import Sequence

revision: str = "0306"
down_revision: str | None = "0305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
