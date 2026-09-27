"""direct_debit_pain008_versions_noop: M15-01 follow-up. pain.008 version selection reuses the
existing ``payment_bank_config.pain008_version`` column and ``direct_debit_run.format``; the
download and submission protocol reuses the existing append-only ``domain_event`` table
(``mhvp.core.events``) instead of a new table. No schema change needed.

Revision ID: 0211
Revises: 0210
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0211"
down_revision: str | None = "0210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
