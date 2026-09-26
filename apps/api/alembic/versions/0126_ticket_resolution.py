"""ticket_resolution: Erledigungsnotiz am Ticket (``resolution_kind``, ``resolution_note``,
``resolved_by``), ``playbook.last_used_at`` und die KI-Aufgabe ``ticket_resolution`` für die
Lernbeispiele aus Erledigungen (Betreiberauftrag 26.09.2026). Keine neuen Mandantentabellen.

Revision ID: 0126
Revises: 0125
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0126"
down_revision: str | None = "0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_task ADD VALUE IF NOT EXISTS 'ticket_resolution'")
    op.add_column("ticket", sa.Column("resolution_kind", sa.String(length=32), nullable=True))
    op.add_column("ticket", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("ticket", sa.Column("resolved_by", sa.UUID(), nullable=True))
    op.add_column("playbook", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("playbook", "last_used_at")
    op.drop_column("ticket", "resolved_by")
    op.drop_column("ticket", "resolution_note")
    op.drop_column("ticket", "resolution_kind")
    # The enum value stays defined (same convention as 0083).
