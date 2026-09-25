"""mailbox_calendar: Google Calendar toggle and target calendar id per mailbox (M23-02,
docs/plans/M23.md, 25.09.2026). Operator decision: the CRM calendar uses Google Calendar,
tenant default calendar = default mailbox account, each user additionally sees/writes to their
assigned mailbox calendar.

Revision ID: 0048
Revises: 0047
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mailbox",
        sa.Column("calendar_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "mailbox",
        sa.Column("calendar_id", sa.String(length=320), nullable=False, server_default="primary"),
    )


def downgrade() -> None:
    op.drop_column("mailbox", "calendar_id")
    op.drop_column("mailbox", "calendar_enabled")
