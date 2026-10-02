"""AF09: hoa meeting and statement masks (web-crm only), no schema change; keeps the revision
chain linear.

Revision ID: 0403
Revises: 0402
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0403"
down_revision: str | None = "0402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
