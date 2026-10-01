"""Notification preference: delivery of the mail, immediate or daily (M23-04).

Revision ID: 0293
Revises: 0292
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0293"
down_revision: str | None = "0292"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_preference",
        sa.Column(
            "email_mode", sa.String(16), nullable=False, server_default=sa.text("'immediate'")
        ),
    )
    op.create_check_constraint(
        op.f("ck_notification_preference_email_mode"),
        "notification_preference",
        "email_mode IN ('immediate', 'daily')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_notification_preference_email_mode"), "notification_preference", type_="check"
    )
    op.drop_column("notification_preference", "email_mode")
