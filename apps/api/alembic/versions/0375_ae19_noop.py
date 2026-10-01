"""AE19: check points and heating comparison need no schema change; keeps the chain linear.

Revision ID: 0375
Revises: 0374
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0375"
down_revision: str | None = "0374"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
