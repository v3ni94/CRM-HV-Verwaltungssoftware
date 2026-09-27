"""rent_invoice: rent invoices with VAT (Mietrechnung, Dauermietrechnung) for tenancies with
a VAT option and their gapless number counter per tenant, legal entity and year (M13-03
follow up, rule M13-04 section "Mietrechnung", V21). Cancellation only by credit note.

Revision ID: 0210
Revises: 0209
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0210"
down_revision: str | None = "0209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNTER = "rent_invoice_number_counter"
INVOICE = "rent_invoice"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    if not _has_table(COUNTER):
        op.create_table(
            COUNTER,
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column("legal_entity_id", _uuid(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entity.id"]),
            sa.UniqueConstraint("tenant_id", "legal_entity_id", "year"),
        )
        for statement in tenant_rls_statements(COUNTER):
            op.execute(statement)
    if not _has_table(INVOICE):
        kind = postgresql.ENUM(
            "invoice", "standing", "credit_note", name="rent_invoice_kind", create_type=False
        )
        status = postgresql.ENUM(
            "issued", "cancelled", name="rent_invoice_status", create_type=False
        )
        op.execute(
            "DO $$ BEGIN CREATE TYPE rent_invoice_kind AS ENUM "
            "('invoice', 'standing', 'credit_note'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
        op.execute(
            "DO $$ BEGIN CREATE TYPE rent_invoice_status AS ENUM ('issued', 'cancelled'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
        op.create_table(
            INVOICE,
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("tenant_id", _uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("created_by", _uuid()),
            sa.Column("updated_by", _uuid()),
            sa.Column("contract_id", _uuid(), nullable=False),
            sa.Column("legal_entity_id", _uuid(), nullable=False),
            sa.Column("contact_id", _uuid()),
            sa.Column("kind", kind, nullable=False),
            sa.Column("status", status, nullable=False, server_default="issued"),
            sa.Column("number", sa.String(40), nullable=False),
            sa.Column("invoice_date", sa.Date(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("net_total", sa.Numeric(14, 2), nullable=False),
            sa.Column("vat_total", sa.Numeric(14, 2), nullable=False),
            sa.Column("gross_total", sa.Numeric(14, 2), nullable=False),
            sa.Column(
                "lines",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("tax_identifier_kind", sa.String(16), nullable=False),
            sa.Column("draft", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("cancels_invoice_id", _uuid()),
            sa.Column("cancelled_by_invoice_id", _uuid()),
            sa.Column("document_id", _uuid()),
            sa.Column("issued_by", _uuid()),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
            sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entity.id"]),
            sa.ForeignKeyConstraint(["contact_id"], ["contact.id"]),
            sa.ForeignKeyConstraint(["cancels_invoice_id"], ["rent_invoice.id"]),
            sa.ForeignKeyConstraint(["cancelled_by_invoice_id"], ["rent_invoice.id"]),
            sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
            sa.UniqueConstraint("tenant_id", "legal_entity_id", "number"),
        )
        op.create_index(
            f"ix_{INVOICE}_contract", INVOICE, ["tenant_id", "contract_id", "period_start"]
        )
        for statement in tenant_rls_statements(INVOICE):
            op.execute(statement)


def downgrade() -> None:
    for table in (INVOICE, COUNTER):
        if _has_table(table):
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    op.execute("DROP TYPE IF EXISTS rent_invoice_status")
    op.execute("DROP TYPE IF EXISTS rent_invoice_kind")
