"""AF05: accounting masks and reports (web-crm only), no schema change; keeps the chain linear.

Revision ID: 0399
Revises: 0398
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0399"
down_revision: str | None = "0398"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
