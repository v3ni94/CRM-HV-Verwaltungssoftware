"""No-op migration keeping the chain linear (Playwright core-path coverage for the 27.09.2026
wave: nav rail, mailbox/ticket pagination, bank connect, WEG circular resolution lock, heating
and advance panels, deposit, settings reachability; no schema change).

Revision ID: 0200
Revises: 0199
"""

from collections.abc import Sequence

revision: str = "0200"
down_revision: str | None = "0199"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
