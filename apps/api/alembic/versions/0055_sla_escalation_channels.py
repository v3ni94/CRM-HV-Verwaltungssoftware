"""sla_escalation_channels: e-mail and SMS delivery of SLA escalations (M35). Adds the SMS
channel, delivery state on emergency alerts, channels per escalation level on SLA rules, the
tenant SMS gateway configuration and the member mobile phone for on-call SMS.

Revision ID: 0055
Revises: 0054

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("sla_sms_gateway",)


def upgrade() -> None:
    op.execute("ALTER TYPE sla_alert_channel ADD VALUE IF NOT EXISTS 'sms'")
    op.add_column("sla_emergency_alert", sa.Column("delivered_at", sa.DateTime(timezone=True)))
    op.add_column("sla_emergency_alert", sa.Column("delivery_error", sa.Text()))
    op.add_column("sla_rule", sa.Column("channels_by_level", postgresql.JSONB(), nullable=True))
    op.add_column("membership", sa.Column("mobile_phone", sa.String(length=40)))

    op.create_table(
        "sla_sms_gateway",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("url", sa.String(length=500)),
        sa.Column("method", sa.String(length=8), nullable=False, server_default="POST"),
        sa.Column("auth_header_name", sa.String(length=100)),
        sa.Column("auth_header_value", sa.LargeBinary()),
        sa.Column("body_template", sa.Text()),
        sa.Column("sender", sa.String(length=40)),
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
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_sla_sms_gateway_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_sms_gateway")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_sla_sms_gateway_tenant_id")),
    )
    for table in TENANT_TABLES:
        for stmt in tenant_rls_statements(table):
            op.execute(stmt)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for stmt in drop_tenant_rls_statements(table):
            op.execute(stmt)
    op.drop_table("sla_sms_gateway")
    op.drop_column("membership", "mobile_phone")
    op.drop_column("sla_rule", "channels_by_level")
    op.drop_column("sla_emergency_alert", "delivery_error")
    op.drop_column("sla_emergency_alert", "delivered_at")
    # Enum values cannot be dropped in PostgreSQL; 'sms' stays in sla_alert_channel.
