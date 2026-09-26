"""service_contract: Dienstleisterverträge mit Laufzeit, Kündigungsfrist und automatischer
Verlängerung (M9-06, A41 Fristenliste). Tenant table with RLS (ADR 0002).

Revision ID: 0122
Revises: 0121
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0122"
down_revision: str | None = "0121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "service_contract"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_contact_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=False),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column(
            "notice_period_unit", sa.String(length=8), nullable=False, server_default="months"
        ),
        sa.Column("auto_renewal_months", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_service_contract_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_contact_id"],
            ["contact.id"],
            name=op.f("fk_service_contract_provider_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_service_contract_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "notice_period_unit IN ('days', 'months')", name="ck_service_contract_notice_unit"
        ),
        sa.CheckConstraint("notice_period_days >= 0", name="ck_service_contract_notice_period"),
        sa.CheckConstraint(
            "auto_renewal_months IS NULL OR auto_renewal_months > 0",
            name="ck_service_contract_renewal",
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at", name="ck_service_contract_term"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_contract")),
    )
    op.create_index("ix_service_contract_provider", TABLE, ["tenant_id", "provider_contact_id"])
    op.create_index("ix_service_contract_property", TABLE, ["tenant_id", "property_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_service_contract_property", table_name=TABLE)
    op.drop_index("ix_service_contract_provider", table_name=TABLE)
    op.drop_table(TABLE)
