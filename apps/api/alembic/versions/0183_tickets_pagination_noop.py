"""No-op migration keeping the chain linear (tickets/mail pagination frontend fix, 27.09.2026).

Revision ID: 0183
Revises: 0182
"""

from collections.abc import Sequence

revision: str = "0183"
down_revision: str | None = "0182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
