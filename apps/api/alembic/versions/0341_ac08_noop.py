"""GA10-06 (AC08): no schema change; placeholder that keeps the revision chain linear.

Tool use stores its protocol in ``ai_task_run.input_ref`` and its switch in
``ai_provider_config.models`` (both existing JSONB columns).

Revision ID: 0341
Revises: 0340
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0341"
down_revision: str | None = "0340"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
