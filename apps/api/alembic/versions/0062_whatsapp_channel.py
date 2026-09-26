"""whatsapp_channel: M35, operator decision 25.09.2026. Adds WhatsApp (Meta Cloud API) as a
second escalation and notification channel next to SMS. ``sla_alert_channel`` and
``consent_kind`` gain the value ``whatsapp``; new tenant tables ``sla_whatsapp_config`` (per
tenant Cloud API configuration and template mapping) and ``sla_whatsapp_delivery`` (delivery
status per sent template message, updated by the status webhook).

Revision ID: 0062
Revises: 0061

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("sla_whatsapp_config", "sla_whatsapp_delivery")


def upgrade() -> None:
    op.execute("ALTER TYPE sla_alert_channel ADD VALUE IF NOT EXISTS 'whatsapp'")
    op.execute("ALTER TYPE consent_kind ADD VALUE IF NOT EXISTS 'whatsapp'")

    op.create_table(
        "sla_whatsapp_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("phone_number_id", sa.String(length=64)),
        sa.Column("whatsapp_business_account_id", sa.String(length=64)),
        sa.Column("access_token", sa.LargeBinary()),
        sa.Column(
            "template_names", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("template_language", sa.String(length=10), nullable=False, server_default="de"),
        sa.Column("sms_fallback", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_table(
        "sla_whatsapp_delivery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True)),
        sa.Column("wa_message_id", sa.String(length=128)),
        sa.Column("to", sa.String(length=40), nullable=False),
        sa.Column("template_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["alert_id"], ["sla_emergency_alert.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_sla_whatsapp_delivery_wa_message_id", "sla_whatsapp_delivery", ["wa_message_id"]
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_index("ix_sla_whatsapp_delivery_wa_message_id", table_name="sla_whatsapp_delivery")
    op.drop_table("sla_whatsapp_delivery")
    op.drop_table("sla_whatsapp_config")

    # Postgres cannot remove an enum value; the added values stay unused after downgrade.
