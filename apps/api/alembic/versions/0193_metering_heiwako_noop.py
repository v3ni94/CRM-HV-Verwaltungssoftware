"""metering_heiwako_noop: M40-02 file exchange adapters (Techem, Brunata Minol,
BRUNATA-METRONA) need no schema change; placeholder keeps the revision chain linear.

Revision ID: 0193
Revises: 0192
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0193"
down_revision: str | None = "0192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
