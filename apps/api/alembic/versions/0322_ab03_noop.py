"""AB03: no schema change (message receipts reuse the columns of 0305)

Revision ID: 0322
Revises: 0321
"""

from collections.abc import Sequence

revision: str = "0322"
down_revision: str | None = "0321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
