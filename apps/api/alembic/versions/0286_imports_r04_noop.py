"""Imports R04 (Q08 rest): no schema change, keeps the revision chain.

The balance check, the journal candidate list and the undo of history rows work on the tables
of revision 0277; the search additions use existing columns.

Revision ID: 0286
Revises: 0285
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0286"
down_revision: str | None = "0285"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
