"""No-op migration (D47, M9-05, B18, M27-03): this task adds only operational scripts and
docs (restore drill, SSH hardening proposal, Verfahrensdokumentation draft, Immoware
parallel-run plan), no schema change. Kept so the migration chain stays linear.

Revision ID: 0179
Revises: 0178
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0179"
down_revision: str | None = "0178"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
