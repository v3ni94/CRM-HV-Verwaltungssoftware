"""Knowledge base usage and feedback counters (audit 29.09.2026).

* ``ai_knowledge_entry``: ``usage_count``, ``last_used_at``, ``helpful_count``,
  ``unhelpful_count`` (how often an approved entry fed a run and how staff rated the answers);
  partial index on the live approved rows the context query reads.
* ``playbook``: ``helpful_count``, ``unhelpful_count`` for the suggested playbook.
* ``ai_task_run.feedback``: "helpful" / "unhelpful" on a chat answer.

Counters only; the release workflow (M34-01) and posted records are untouched.

Revision ID: 0237
Revises: 0223
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0237"
down_revision: str | None = "0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), nullable=False, server_default="0")


def upgrade() -> None:
    op.add_column("ai_knowledge_entry", _counter("usage_count"))
    op.add_column(
        "ai_knowledge_entry", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("ai_knowledge_entry", _counter("helpful_count"))
    op.add_column("ai_knowledge_entry", _counter("unhelpful_count"))
    op.create_index(
        "ix_ai_knowledge_entry_live_approved",
        "ai_knowledge_entry",
        ["tenant_id", "property_id"],
        postgresql_where=sa.text(
            "status = 'approved' AND superseded_at IS NULL AND deleted_at IS NULL"
        ),
    )
    op.add_column("playbook", _counter("helpful_count"))
    op.add_column("playbook", _counter("unhelpful_count"))
    op.add_column("ai_task_run", sa.Column("feedback", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_task_run", "feedback")
    op.drop_column("playbook", "unhelpful_count")
    op.drop_column("playbook", "helpful_count")
    op.drop_index("ix_ai_knowledge_entry_live_approved", table_name="ai_knowledge_entry")
    op.drop_column("ai_knowledge_entry", "unhelpful_count")
    op.drop_column("ai_knowledge_entry", "helpful_count")
    op.drop_column("ai_knowledge_entry", "last_used_at")
    op.drop_column("ai_knowledge_entry", "usage_count")
