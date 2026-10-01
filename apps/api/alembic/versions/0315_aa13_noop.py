"""AA13 (GA10-01 to GA10-05): no schema change; placeholder that keeps the revision chain linear.

Direct filing uses ``TenantSettings.sources`` (JSONB), follow-ups live in ``AiProposal.final``.

Revision ID: 0315
Revises: 0314
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0315"
down_revision: str | None = "0314"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
