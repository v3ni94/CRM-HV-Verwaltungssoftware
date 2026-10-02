"""AF02 (GAB-02, GAB-03, GAE-23, GAE-25): no schema change; placeholder keeps the chain linear.

Revision ID: 0396
Revises: 0395
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0396"
down_revision: str | None = "0395"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
