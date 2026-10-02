"""AI07 (GAH-206, GAH-202): failure counter of outgoing webhooks and two tenant switches.

* ``webhook_subscription``: ``consecutive_failures``, ``last_failure_at``, ``disabled_reason``.
* ``tenant_settings.webhook_auto_disable_after``: NULL = never deactivate (default).
* ``tenant_settings.objektakte_webhook_require_timestamp``: default false.

Revision ID: 0441
Revises: 0440
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0441"
down_revision: str | None = "0440"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_subscription",
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "webhook_subscription",
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "webhook_subscription",
        sa.Column("disabled_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "tenant_settings", sa.Column("webhook_auto_disable_after", sa.Integer(), nullable=True)
    )
    op.add_column(
        "tenant_settings",
        sa.Column(
            "objektakte_webhook_require_timestamp",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_tenant_settings_webhook_auto_disable_after_range"),
        "tenant_settings",
        "webhook_auto_disable_after IS NULL OR webhook_auto_disable_after BETWEEN 1 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_tenant_settings_webhook_auto_disable_after_range"),
        "tenant_settings",
        type_="check",
    )
    op.drop_column("tenant_settings", "objektakte_webhook_require_timestamp")
    op.drop_column("tenant_settings", "webhook_auto_disable_after")
    op.drop_column("webhook_subscription", "disabled_reason")
    op.drop_column("webhook_subscription", "last_failure_at")
    op.drop_column("webhook_subscription", "consecutive_failures")
