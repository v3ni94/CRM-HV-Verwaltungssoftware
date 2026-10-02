"""AF20: letting, handover and integration masks (web-crm only), no schema change; keeps the
revision chain linear.

Revision ID: 0414
Revises: 0413
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0414"
down_revision: str | None = "0413"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
