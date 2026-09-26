"""ai_task_contact_master_data_change: adds the ``contact_master_data_change`` AI task
(`mhvp.ai.models.AiTask`) used by `mhvp.tickets.proposals` (Stammdatenänderung aus einer
Ticket-Mail, Betreiberauftrag 26.09.2026). Result is always an ``ai_proposal`` with
``entity_type="contact_change"``, never applied automatically (rule 0.1.6); IBANs are never
proposed. No table changes.

Revision ID: 0083
Revises: 0082
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'contact_master_data_change'")


def downgrade() -> None:
    # Postgres enum values cannot be removed; the value stays defined on downgrade (same
    # convention as 0067_ai_fast_table_import and 0070_objektakte_ai_classification).
    pass
