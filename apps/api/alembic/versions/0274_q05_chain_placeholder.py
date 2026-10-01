"""Chain placeholder of package Q05 (CRM screens, no schema change).

Package Q05 needs no migration. Revision 0274 is reserved for it in the wave 3 numbering and
revision 0275 (package Q06) points to it, so the revision stays as an empty link of the chain.

Revision ID: 0274
Revises: 0273
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0274"
down_revision: str | None = "0273"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema change."""


def downgrade() -> None:
    """No schema change."""
