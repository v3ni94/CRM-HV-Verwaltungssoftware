"""metering_heiwako_deposit_noop: bved 3.10 upload dialog (web-crm) and posting_proposal
``is_deposit`` derivation (mhvp.banking.posting_proposal.stage1_for_transaction) over the
contract's existing ``Deposit`` demand; no schema change (see docs/ASSUMPTIONS.md, entry
"posting_proposal is_deposit").

Revision ID: 0207
Revises: 0206
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0207"
down_revision: str | None = "0206"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
