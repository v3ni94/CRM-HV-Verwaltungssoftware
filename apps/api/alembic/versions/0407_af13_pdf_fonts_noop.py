"""AF13: embedded TrueType fonts for the letterhead (GAE-37) need no schema change.
Noop placeholder keeps the chain linear.

Revision ID: 0407
Revises: 0406
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0407"
down_revision: str | None = "0406"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
