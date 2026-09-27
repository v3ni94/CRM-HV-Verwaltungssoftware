"""No-op migration: this task fixes stale Playwright e2e specs (login/ticket filter/object
list) after the 1.34.x UI changes, no schema change. Kept so the migration chain stays linear.

Revision ID: 0181
Revises: 0180
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0181"
down_revision: str | None = "0180"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
