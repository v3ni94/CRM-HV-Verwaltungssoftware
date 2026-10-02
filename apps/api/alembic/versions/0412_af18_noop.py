"""AF18: intake, objektakte and migration masks (web-crm only), no schema change; keeps the
revision chain linear.

Revision ID: 0412
Revises: 0411
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0412"
down_revision: str | None = "0411"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
