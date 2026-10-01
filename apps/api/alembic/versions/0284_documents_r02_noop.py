"""Documents R02 (Q03 rest): no schema change, keeps the revision chain.

The shared mailbox switch, the distribution watermark and the direct upload switch live in
``tenant_settings.sources`` (JSONB), so no column is needed.

Revision ID: 0284
Revises: 0283
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0284"
down_revision: str | None = "0283"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
