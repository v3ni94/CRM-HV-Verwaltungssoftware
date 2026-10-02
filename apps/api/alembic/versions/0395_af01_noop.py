"""AF01: switch on of the booking automation only via request, no schema change.

Revision ID: 0395
Revises: 0394
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0395"
down_revision: str | None = "0394"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
