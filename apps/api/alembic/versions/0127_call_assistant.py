"""call_assistant: Hallo-Heidi-Anrufe am Ticket (Betreiberauftrag 26.09.2026). Adds the
``call_summary`` AI task (`mhvp.ai.models.AiTask`, used by `mhvp.tickets.call_assistant`) and
the tenant configuration ``tenant_settings.call_assistant`` (JSONB, shape
``{"enabled": bool, "sender_patterns": [str], "keywords": [str]}``). The result of a call mail
is always an ``ai_proposal`` with ``entity_type="contact_change"``, never applied
automatically (rule 0.1.6).

Revision ID: 0127
Revises: 0126 (0126_ticket_resolution, Parallelstand, vor diesem Stand zu mergen)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0127"
down_revision: str | None = "0126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'call_summary'")
    op.add_column(
        "tenant_settings",
        sa.Column(
            "call_assistant",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_settings", "call_assistant")
    # Postgres enum values cannot be removed; the value stays defined (same as 0083).
