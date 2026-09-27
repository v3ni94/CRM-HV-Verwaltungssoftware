"""M34 Nachtrag 27.09.2026 (Masterprompt 9.4 Erklaerbarkeit): ``ai_proposal.rejection_reason``
so a reject in the assistant chat can carry a reason, which is then also stored as a learning
example (``ai_example``, ADR 0010) by ``mhvp.ai.examples.record_rejection``. Idempotent (column
checked before being added); no other schema change is needed for this task.

Revision ID: 0212
Revises: 0211
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0212"
down_revision: str | None = "0211"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("ai_proposal"):
        existing = {c["name"] for c in inspector.get_columns("ai_proposal")}
        if "rejection_reason" not in existing:
            op.add_column("ai_proposal", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("ai_proposal"):
        existing = {c["name"] for c in inspector.get_columns("ai_proposal")}
        if "rejection_reason" in existing:
            op.drop_column("ai_proposal", "rejection_reason")
