"""posting_proposal_noop: two stage posting proposal (M12-01) needs no schema change; the
stage 1 proposals are computed on read, the AI stage keeps using ``ai_proposal``.

Revision ID: 0194
Revises: 0193
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0194"
down_revision: str | None = "0193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
