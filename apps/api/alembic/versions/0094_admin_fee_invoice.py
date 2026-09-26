"""admin_fee_invoice: issued Verwalterhonorar invoices as the source of the XRechnung XML
(A12, M13-04, 13.5 E-Rechnung). Amounts and lines are frozen at issue time; tax identifiers
are not copied (read from tenant_billing_settings at generation time). RLS like every tenant
table (ADR 0002). Adds tenant_billing_settings.payee_iban (encrypted, BT-84/BR-61).

Revision ID: 0094
Revises: 0093
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0094"
down_revision: str | None = "0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = postgresql.ENUM("issued", "released", name="admin_fee_invoice_status", create_type=False)


def upgrade() -> None:
    op.add_column(
        "tenant_billing_settings", sa.Column("payee_iban", sa.LargeBinary(), nullable=True)
    )
    _STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "admin_fee_invoice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "fee_setting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_fee_setting.id"),
            nullable=False,
        ),
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("property.id"),
            nullable=False,
        ),
        sa.Column("number", sa.String(32), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("status", _STATUS, nullable=False, server_default="issued"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("net", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_percent", sa.Numeric(20, 8), nullable=False),
        sa.Column("vat", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross", sa.Numeric(14, 2), nullable=False),
        sa.Column("lines", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "debtor_legal_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_entity.id"),
            nullable=True,
        ),
        sa.Column(
            "invoice_debtor_party_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("party.id"),
            nullable=True,
        ),
        sa.Column("buyer_reference", sa.String(64), nullable=True),
        sa.Column(
            "xml_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("tenant_id", "number", name="uq_admin_fee_invoice_number"),
    )
    op.create_index("ix_admin_fee_invoice_tenant_id", "admin_fee_invoice", ["tenant_id"])
    for statement in tenant_rls_statements("admin_fee_invoice"):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements("admin_fee_invoice"):
        op.execute(statement)
    op.drop_index("ix_admin_fee_invoice_tenant_id", table_name="admin_fee_invoice")
    op.drop_table("admin_fee_invoice")
    _STATUS.drop(op.get_bind(), checkfirst=True)
    op.drop_column("tenant_billing_settings", "payee_iban")
