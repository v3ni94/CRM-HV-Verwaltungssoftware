"""M2-05 cross tenant working view for platform administrators: no schema change. The view
reads each tenant in its own transaction (RLS in force) and records ``platform.overview_viewed``
in the existing ``domain_event`` table. Kept as a no-op so the migration chain stays linear.

Revision ID: 0167
Revises: 0166
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0167"
down_revision: str | None = "0166"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
