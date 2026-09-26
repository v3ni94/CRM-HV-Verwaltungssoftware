"""automation_rule: trigger kind, schedule and schedule watermark (rule engine stage 2,
section 15.2, task A39). ``trigger_event_type`` becomes optional (schedule rules). RLS of
the automation tables is unchanged (migration 0100); no new tenant table.

Revision ID: 0110
Revises: 0109
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0110"
down_revision: str | None = "0109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automation_rule",
        sa.Column("trigger_kind", sa.String(16), nullable=False, server_default=sa.text("'event'")),
    )
    op.add_column(
        "automation_rule",
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automation_rule", sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.alter_column(
        "automation_rule", "trigger_event_type", existing_type=sa.String(100), nullable=True
    )
    op.create_index(
        "ix_automation_rule_tenant_kind_active",
        "automation_rule",
        ["tenant_id", "trigger_kind", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_automation_rule_tenant_kind_active", table_name="automation_rule")
    # The migrator owns the table but RLS is forced (ADR 0002): lift it for the data fix only.
    op.execute("ALTER TABLE automation_rule NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE automation_rule SET trigger_event_type = 'schedule.due' "
        "WHERE trigger_event_type IS NULL"
    )
    op.execute("ALTER TABLE automation_rule FORCE ROW LEVEL SECURITY")
    op.alter_column(
        "automation_rule", "trigger_event_type", existing_type=sa.String(100), nullable=False
    )
    op.drop_column("automation_rule", "last_scheduled_at")
    op.drop_column("automation_rule", "schedule")
    op.drop_column("automation_rule", "trigger_kind")
