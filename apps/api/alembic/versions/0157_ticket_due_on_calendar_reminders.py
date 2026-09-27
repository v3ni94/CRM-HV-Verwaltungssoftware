"""ticket.due_on and calendar_entry.reminders_sent (P1 AP7 follow up, spec 4.9 and B.30).

``ticket.due_on`` is the optional due date of a ticket (a working deadline, independent of
the SLA due time whose escalation has its own notifications); the calendar source
``ticket_due`` reads it. ``calendar_entry.reminders_sent`` records the reminder codes the
deadline job has already turned into a notification (``"<code>@<occurrence date>"``), so a
rerun never notifies twice and recurring entries are reminded per occurrence.

Revision ID: 0157
Revises: 0154
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0157"
down_revision: str | None = "0156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket", sa.Column("due_on", sa.Date(), nullable=True))
    op.add_column(
        "calendar_entry",
        sa.Column(
            "reminders_sent",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("calendar_entry", "reminders_sent")
    op.drop_column("ticket", "due_on")
