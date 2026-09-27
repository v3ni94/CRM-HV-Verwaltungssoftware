"""dunning_case_out_property_noop: M16-15, ``_case_out`` (mhvp.accounting.routers) now
derives ledger_id, legal_entity_id, property_id and property_number from the existing
``dunning_case.ledger_id`` FK; no schema change needed.

Revision ID: 0206
Revises: 0205
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0206"
down_revision: str | None = "0205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
