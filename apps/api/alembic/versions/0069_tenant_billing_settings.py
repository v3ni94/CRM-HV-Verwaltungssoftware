"""tenant_billing_settings: invoicing entity, invoice number counter, VAT status and DATEV
parameters per tenant (operator decision 25.09.2026, docs/OPEN_QUESTIONS.md M13-04/M18-01,
docs/plans/M13.md, M18.md). All fields nullable/unset by default; no value is invented.

Revision ID: 0069
Revises: 0068
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VAT_STATUS = postgresql.ENUM(
    "unset", "regelbesteuert", "kleinunternehmer", name="tenant_vat_status", create_type=False
)
_CHART_KIND = postgresql.ENUM(
    "unset", "skr03", "skr04", name="tenant_chart_of_accounts_kind", create_type=False
)


def upgrade() -> None:
    _VAT_STATUS.create(op.get_bind(), checkfirst=True)
    _CHART_KIND.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tenant_billing_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_prefix", sa.String(16), nullable=True),
        sa.Column("vat_status", _VAT_STATUS, nullable=False, server_default="unset"),
        sa.Column("vat_id", sa.LargeBinary(), nullable=True),
        sa.Column("tax_number", sa.LargeBinary(), nullable=True),
        sa.Column("leitweg_id", sa.String(64), nullable=True),
        sa.Column("kleinunternehmer_note", sa.Text(), nullable=True),
        sa.Column("datev_consultant_number", sa.String(32), nullable=True),
        sa.Column("datev_client_number", sa.String(32), nullable=True),
        sa.Column("datev_chart_of_accounts", _CHART_KIND, nullable=False, server_default="unset"),
        sa.Column("datev_account_length", sa.Integer(), nullable=True),
        sa.Column(
            "datev_fiscal_year_start_month", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_billing_settings_tenant"),
    )
    op.create_index(
        "ix_tenant_billing_settings_tenant_id", "tenant_billing_settings", ["tenant_id"]
    )
    for statement in tenant_rls_statements("tenant_billing_settings"):
        op.execute(statement)

    op.create_table(
        "invoice_number_counter",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "tenant_id", "prefix", "year", name="uq_invoice_number_counter_tenant_prefix_year"
        ),
    )
    op.create_index("ix_invoice_number_counter_tenant_id", "invoice_number_counter", ["tenant_id"])
    for statement in tenant_rls_statements("invoice_number_counter"):
        op.execute(statement)

    op.add_column("export_run", sa.Column("note", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("export_run", "note")

    for statement in drop_tenant_rls_statements("invoice_number_counter"):
        op.execute(statement)
    op.drop_index("ix_invoice_number_counter_tenant_id", table_name="invoice_number_counter")
    op.drop_table("invoice_number_counter")

    for statement in drop_tenant_rls_statements("tenant_billing_settings"):
        op.execute(statement)
    op.drop_index("ix_tenant_billing_settings_tenant_id", table_name="tenant_billing_settings")
    op.drop_table("tenant_billing_settings")

    postgresql.ENUM(name="tenant_chart_of_accounts_kind").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="tenant_vat_status").drop(op.get_bind(), checkfirst=True)
