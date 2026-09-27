"""Tax drafts of the invoice intake (M14-02 input tax, M14-03 approval limits per role,
M14-04 reverse charge, construction withholding tax and § 35a EStG): tenant switches (default
off), property and supplier tax profiles, tax data and § 35a markers per invoice, second
approval above the role limit. Nothing is posted or withheld (G1 unaffected).

Revision ID: 0185
Revises: 0184
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0185"
down_revision: str | None = "0184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(14, 2)
RATE = sa.Numeric(20, 8)
UUID = postgresql.UUID(as_uuid=True)


def _base(*, timestamps: bool = True) -> list[Any]:
    columns: list[Any] = [
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
        ),
    ]
    if timestamps:
        columns += [
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
            sa.Column("created_by", UUID),
            sa.Column("updated_by", UUID),
        ]
    return columns


TABLES: dict[str, list[Any]] = {
    "accounting_tax_settings": [
        *_base(),
        sa.Column("input_tax_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("input_tax_account_number", sa.String(length=6)),
        sa.Column(
            "construction_withholding_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("construction_withholding_percent", RATE, nullable=False, server_default="15.00"),
        sa.Column("section_35a_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_limits_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "approval_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("tenant_id", name="uq_accounting_tax_settings_tenant"),
        sa.CheckConstraint(
            "construction_withholding_percent BETWEEN 0 AND 100",
            name="ck_accounting_tax_withholding_percent",
        ),
    ],
    "property_tax_profile": [
        *_base(),
        sa.Column(
            "property_id", UUID, sa.ForeignKey("property.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("vat_opted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("revenue_key_percent", RATE),
        sa.Column("note", sa.String(length=500)),
        sa.UniqueConstraint("property_id", name="uq_property_tax_profile_property"),
        sa.CheckConstraint(
            "revenue_key_percent IS NULL OR revenue_key_percent BETWEEN 0 AND 100",
            name="ck_property_tax_profile_key_range",
        ),
    ],
    "supplier_tax_profile": [
        *_base(),
        sa.Column(
            "contact_id", UUID, sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("construction_services", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reverse_charge", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("exemption_number", sa.String(length=100)),
        sa.Column("exemption_valid_from", sa.Date()),
        sa.Column("exemption_valid_to", sa.Date()),
        sa.Column("exemption_document_id", UUID, sa.ForeignKey("document.id", ondelete="SET NULL")),
        sa.Column("note", sa.String(length=500)),
        sa.UniqueConstraint("contact_id", name="uq_supplier_tax_profile_contact"),
        sa.CheckConstraint(
            "exemption_valid_to IS NULL OR exemption_valid_from IS NULL "
            "OR exemption_valid_to >= exemption_valid_from",
            name="ck_supplier_tax_profile_exemption_period",
        ),
    ],
    "invoice_tax_data": [
        *_base(),
        sa.Column(
            "invoice_id", UUID, sa.ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("vat_rate", RATE),
        sa.Column("input_tax_amount", MONEY),
        sa.Column("reverse_charge", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("construction_service", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deductible_percent", RATE),
        sa.Column("deductible_input_tax", MONEY),
        sa.Column("withholding_percent", RATE),
        sa.Column("withholding_proposal", MONEY),
        sa.Column("withholding_approved_by", UUID),
        sa.Column("withholding_approved_at", sa.DateTime(timezone=True)),
        sa.Column("withholding_approved_amount", MONEY),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("invoice_id", name="uq_invoice_tax_data_invoice"),
    ],
    "invoice_line_section35a": [
        *_base(),
        sa.Column(
            "invoice_id", UUID, sa.ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "invoice_line_id",
            UUID,
            sa.ForeignKey("invoice_line.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("labor_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("material_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("text", sa.String(length=500)),
        sa.UniqueConstraint("invoice_line_id", name="uq_invoice_line_section35a_line"),
        sa.CheckConstraint("kind IN ('household_service', 'craftsman')", name="ck_section35a_kind"),
        sa.CheckConstraint(
            "labor_amount >= 0 AND material_amount >= 0", name="ck_section35a_amounts"
        ),
    ],
    "invoice_second_approval": [
        *_base(timestamps=False),
        sa.Column(
            "invoice_id", UUID, sa.ForeignKey("invoice.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("invoice_version", sa.Integer(), nullable=False),
        sa.Column("payment_hash", sa.String(length=64), nullable=False),
        sa.Column("limit_amount", MONEY),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("invoice_id", name="uq_invoice_second_approval_invoice"),
    ],
}

INDEXES = {"invoice_line_section35a": ("ix_invoice_line_section35a_invoice_id", ["invoice_id"])}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()
    for name, columns in TABLES.items():
        if name in existing:
            continue
        op.create_table(name, *columns)
        if name in INDEXES:
            index_name, cols = INDEXES[name]
            op.create_index(index_name, name, cols)
        for statement in tenant_rls_statements(name):
            op.execute(statement)


def downgrade() -> None:
    existing = _tables()
    for name in reversed(list(TABLES)):
        if name not in existing:
            continue
        for statement in drop_tenant_rls_statements(name):
            op.execute(statement)
        op.drop_table(name)
