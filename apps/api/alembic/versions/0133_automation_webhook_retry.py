"""automation_webhook_delivery: outbox and delivery log of the rule action ``webhook`` (A82,
M9-08). Until now a rule webhook was called exactly once per run; a failure ended the run.
The run now enqueues the payload here and the beat job delivers it after the retry schedule
of ``mhvp.core.webhooks`` (1 min, 5 min, 30 min, 2 h, 6 h, 24 h, then failed); manual
redelivery resets a row to pending.

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).

Revision ID: 0133
Revises: 0132
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0133"
down_revision: str | None = "0132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "automation_webhook_delivery"
TENANT_TABLES = (TABLE,)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["automation_run.id"],
            name=op.f("fk_automation_webhook_delivery_run_id_automation_run"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["automation_rule.id"],
            name=op.f("fk_automation_webhook_delivery_rule_id_automation_rule"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_automation_webhook_delivery_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_webhook_delivery")),
        sa.UniqueConstraint("run_id", "action_index", name="uq_automation_webhook_delivery_run"),
    )
    op.create_index(
        "ix_automation_webhook_delivery_due",
        TABLE,
        ["tenant_id", "status", "next_attempt_at"],
        unique=False,
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_automation_webhook_delivery_due", table_name=TABLE)
    op.drop_table(TABLE)
