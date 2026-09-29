"""Verbrauchsinformation nach § 6a HeizkostenV (rule H03, D26).

* ``tenant_settings``: ``consumption_info_enabled`` (monthly job, default off),
  ``consumption_info_notifications_enabled`` (portal notification, default off),
  ``consumption_info_template_verified`` (operator confirmation of the template content;
  tenants see nothing before it).
* ``property.consumption_info_enabled``: per property switch (default off).
* ``consumption_info``: one row per tenant, unit and month with the computed values, the data
  basis from ``mhvp.metering``, missing data flags, the frozen HTML snapshot and the stored
  PDF document. RLS like every tenant table.

Revision ID: 0238
Revises: 0237
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0238"
down_revision: str | None = "0237"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "consumption_info"


def _flag(name: str) -> sa.Column[bool]:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false"))


def upgrade() -> None:
    op.add_column("tenant_settings", _flag("consumption_info_enabled"))
    op.add_column("tenant_settings", _flag("consumption_info_notifications_enabled"))
    op.add_column("tenant_settings", _flag("consumption_info_template_verified"))
    op.add_column("property", _flag("consumption_info_enabled"))
    op.create_table(
        TABLE,
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
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True)),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column(
            "values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "data_basis", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "missing", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="job"),
        sa.Column("snapshot_html", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["unit.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "unit_id", "month", name="uq_consumption_info_unit_month"),
        sa.CheckConstraint("extract(day from month) = 1", name="month_first_day"),
    )
    op.create_index(
        "ix_consumption_info_property_month", TABLE, ["tenant_id", "property_id", "month"]
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_consumption_info_property_month", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_column("property", "consumption_info_enabled")
    op.drop_column("tenant_settings", "consumption_info_template_verified")
    op.drop_column("tenant_settings", "consumption_info_notifications_enabled")
    op.drop_column("tenant_settings", "consumption_info_enabled")
