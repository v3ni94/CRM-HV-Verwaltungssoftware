"""No-op migration keeping the chain linear (portal accessibility, V13, 27.09.2026).

Revision ID: 0188
Revises: 0187
"""

from collections.abc import Sequence

revision: str = "0188"
down_revision: str | None = "0187"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
