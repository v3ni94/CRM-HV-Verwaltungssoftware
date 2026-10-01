"""GA08-06, GA08-08 (AC07): no schema change; the access export review workflow is journaled
in domain_event and the deletion checklist is derived from existing rows and events.
Placeholder that keeps the revision chain linear.

Revision ID: 0340
Revises: 0339
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0340"
down_revision: str | None = "0339"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
