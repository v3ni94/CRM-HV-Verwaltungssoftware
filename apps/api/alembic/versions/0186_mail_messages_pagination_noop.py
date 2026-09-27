"""No-op migration keeping the chain linear (mail messages real pagination, 27.09.2026).

Revision ID: 0186
Revises: 0185
"""

from collections.abc import Sequence

revision: str = "0186"
down_revision: str | None = "0185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
