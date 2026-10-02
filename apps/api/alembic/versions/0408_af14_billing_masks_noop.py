"""AF14 billing masks (GAE-19, GAE-20, GAF-12, GAF-13): no schema change.

Revision ID: 0408
Revises: 0407
"""

from collections.abc import Sequence

revision: str = "0408"
down_revision: str | None = "0407"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema change: the masks use existing endpoints."""


def downgrade() -> None:
    """No schema change."""
