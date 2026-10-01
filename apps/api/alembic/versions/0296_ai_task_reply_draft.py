"""ai_task_reply_draft: adds the ``reply_draft`` AI task (`mhvp.ai.models.AiTask`, T12, R09-02):
own provider schema for the reply draft to a mail (tone, placeholders, mailbox style as input).
Result is only a proposal under ``message.suggestion.reply_ai`` with explicit human approval,
never sent (rule 0.1.6). ``draft_reply`` stays the playbook draft. No table changes.

Revision ID: 0296
Revises: 0295
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0296"
down_revision: str | None = "0295"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'reply_draft'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; the value stays defined on downgrade (same
    # convention as 0083_ai_task_contact_master_data_change).
    pass
