"""automation_rule, automation_run, automation_watermark: rule engine stage 1 (section 15.2,
M9, task A38). Tenant RLS on all three tables. Rules never post, pay or approve.

Revision ID: 0100
Revises: 0099
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0100"
down_revision: str | None = "0099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("automation_rule", "automation_run", "automation_watermark")


def upgrade() -> None:
    op.create_table(
        "automation_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trigger_event_type", sa.String(100), nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_automation_rule_name"),
    )
    op.create_index("ix_automation_rule_tenant_id", "automation_rule", ["tenant_id"])
    op.create_table(
        "automation_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rule.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "rule_id", "event_id", name="uq_automation_run_event"),
    )
    op.create_index(
        "ix_automation_run_tenant_started", "automation_run", ["tenant_id", "started_at"]
    )
    op.create_table(
        "automation_watermark",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", name="uq_automation_watermark_tenant"),
    )
    for table in _TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("automation_watermark")
    op.drop_index("ix_automation_run_tenant_started", table_name="automation_run")
    op.drop_table("automation_run")
    op.drop_index("ix_automation_rule_tenant_id", table_name="automation_rule")
    op.drop_table("automation_rule")
