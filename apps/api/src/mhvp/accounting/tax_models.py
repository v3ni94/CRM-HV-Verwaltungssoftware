"""Tax data of incoming invoices as drafts (M14-02 input tax, M14-04 reverse charge,
construction withholding tax and § 35a EStG, M14-03 approval limits per role).

Everything here is recorded and proposed, never posted or withheld by itself: the tenant
switches in ``AccountingTaxSettings`` are off by default, the input tax deduction stays behind
release gate G1 (``invoices.post`` keeps its ``ACC_VAT_NOT_RELEASED`` lock), a withholding
proposal needs an explicit approval by a second person and a second approval above the role
limit is an additional product safeguard, never a legal claim (docs/rules/M14-02.md,
M14-03.md, M14-04.md, source status "zu prüfen durch Steuerberater").
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
RATE = Numeric(20, 8)

# Draft value of the construction withholding tax rate (Bauabzugsteuer); source status "zu
# prüfen durch Steuerberater" (docs/rules/M14-04.md). Only a proposal, never withheld alone.
DEFAULT_WITHHOLDING_PERCENT = Decimal("15.00")

SECTION_35A_KINDS = ("household_service", "craftsman")


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class AccountingTaxSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """One row per tenant; every switch is off by default (product safeguard)."""

    __tablename__ = "accounting_tax_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_accounting_tax_settings_tenant"),
        CheckConstraint(
            "construction_withholding_percent BETWEEN 0 AND 100",
            name="ck_accounting_tax_withholding_percent",
        ),
        # AI18 (GAH-101, migration 0443): selection basis of the § 35a certificate.
        CheckConstraint(
            "section_35a_basis IN ('invoice_date', 'payment_date')", name="section_35a_basis"
        ),
    )

    # M14-02: input tax proposals (deductible share per opted property) are computed only
    # with this switch; the account number must exist in the ledger's chart (no default).
    input_tax_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    input_tax_account_number: Mapped[str | None] = mapped_column(String(6))
    # M14-04: construction withholding tax warning and proposal.
    construction_withholding_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    construction_withholding_percent: Mapped[Decimal] = mapped_column(
        RATE, nullable=False, default=DEFAULT_WITHHOLDING_PERCENT, server_default="15.00"
    )
    # M14-04: § 35a certificate drafts per tenant contract.
    section_35a_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # M14-03: [{"role_code": str, "limit_amount": "1234.56"}]; an invoice above the limit of
    # the releasing person's roles (highest limit wins) needs a second approval before posting.
    approval_limits_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    approval_limits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # AC01-02: sub ledger check hides written off items and items of reversed entries from the
    # difference (counted separately); display only, nothing is posted. Default on.
    subledger_exclude_written_off: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # AI18 (GAH-101, migration 0443): ``invoice_date`` (default, previous behaviour) takes the
    # marked lines by invoice date; ``payment_date`` only paid invoices whose payment date lies
    # in the year. Technical preparation, the tax criterion stays an open decision (G3, G4).
    section_35a_basis: Mapped[str] = mapped_column(
        String(16), nullable=False, default="invoice_date", server_default="invoice_date"
    )


class PropertyTaxProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    """VAT option and revenue key (Umsatzschlüssel) per property, draft values."""

    __tablename__ = "property_tax_profile"
    __table_args__ = (
        UniqueConstraint("property_id", name="uq_property_tax_profile_property"),
        CheckConstraint(
            "revenue_key_percent IS NULL OR revenue_key_percent BETWEEN 0 AND 100",
            name="ck_property_tax_profile_key_range",
        ),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    vat_opted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Share of opted (taxable) revenue in percent; NULL means "not determined", no deduction.
    revenue_key_percent: Mapped[Decimal | None] = mapped_column(RATE)
    note: Mapped[str | None] = mapped_column(String(500))


class SupplierTaxProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    """Reverse charge and construction withholding markers per supplier contact."""

    __tablename__ = "supplier_tax_profile"
    __table_args__ = (
        UniqueConstraint("contact_id", name="uq_supplier_tax_profile_contact"),
        CheckConstraint(
            "exemption_valid_to IS NULL OR exemption_valid_from IS NULL "
            "OR exemption_valid_to >= exemption_valid_from",
            name="ck_supplier_tax_profile_exemption_period",
        ),
    )

    contact_id: Mapped[uuid.UUID] = _fk("contact.id", ondelete="CASCADE")
    construction_services: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Freistellungsbescheinigung: number, validity and the filed document.
    exemption_number: Mapped[str | None] = mapped_column(String(100))
    exemption_valid_from: Mapped[date | None] = mapped_column(Date)
    exemption_valid_to: Mapped[date | None] = mapped_column(Date)
    exemption_document_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )
    note: Mapped[str | None] = mapped_column(String(500))


class InvoiceTaxData(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tax data recorded per invoice plus the deterministic proposals and warnings."""

    __tablename__ = "invoice_tax_data"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_invoice_tax_data_invoice"),)

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id", ondelete="CASCADE")
    vat_rate: Mapped[Decimal | None] = mapped_column(RATE)
    input_tax_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    construction_service: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Proposals (recomputed on every save, never applied by themselves).
    deductible_percent: Mapped[Decimal | None] = mapped_column(RATE)
    deductible_input_tax: Mapped[Decimal | None] = mapped_column(MONEY)
    withholding_percent: Mapped[Decimal | None] = mapped_column(RATE)
    withholding_proposal: Mapped[Decimal | None] = mapped_column(MONEY)
    withholding_approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    withholding_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withholding_approved_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class InvoiceLineSection35a(IdMixin, TimestampMixin, TenantMixin, Base):
    """§ 35a EStG marker per cost line: kind, labour share and material share."""

    __tablename__ = "invoice_line_section35a"
    __table_args__ = (
        UniqueConstraint("invoice_line_id", name="uq_invoice_line_section35a_line"),
        CheckConstraint("kind IN ('household_service', 'craftsman')", name="ck_section35a_kind"),
        CheckConstraint("labor_amount >= 0 AND material_amount >= 0", name="ck_section35a_amounts"),
        Index("ix_invoice_line_section35a_invoice_id", "invoice_id"),
    )

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id", ondelete="CASCADE")
    invoice_line_id: Mapped[uuid.UUID] = _fk("invoice_line.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    labor_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0"
    )
    material_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0"
    )
    text: Mapped[str | None] = mapped_column(String(500))


class InvoiceSecondApproval(IdMixin, TenantMixin, Base):
    """M14-03: second approval above the role limit, bound to version and payment hash."""

    __tablename__ = "invoice_second_approval"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_invoice_second_approval_invoice"),)

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    limit_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Section35aCertificateLog(IdMixin, TenantMixin, Base):
    """AI18 (GAH-101, migration 0443): record of every generated § 35a certificate (PDF or
    filed document) per contract and year. No lock: a second certificate of the same year only
    shows a notice. Append only, nothing financial is changed."""

    __tablename__ = "section35a_certificate_log"
    __table_args__ = (
        Index("ix_section35a_certificate_log_contract_year", "tenant_id", "contract_id", "year"),
        CheckConstraint("output IN ('pdf', 'document')", name="output"),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    output: Mapped[str] = mapped_column(String(16), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    labor_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
