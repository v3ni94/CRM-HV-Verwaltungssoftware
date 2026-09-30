"""Ledger operations M10-01, M10-05, M10-06 (gap list 30.09.2026, package P01).

No schema change: ``ledger_account_allocation``, ``service_provider_relation.
creditor_account_id`` and the entry kinds ``cost_transfer`` and ``interest`` already exist.
The revision keeps the numbering chain of wave 2 (0251 revises 0250).

Revision ID: 0250
Revises: 0249
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0250"
down_revision: str | None = "0249"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
