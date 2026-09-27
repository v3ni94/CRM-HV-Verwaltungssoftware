"""No-op migration keeping the chain linear (dossiers and Playwright core paths, 27.09.2026).

Revision ID: 0180
Revises: 0179
"""

from collections.abc import Sequence

revision: str = "0180"
down_revision: str | None = "0179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
