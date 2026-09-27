"""Rent invoices with VAT (Mietrechnung, Dauermietrechnung) for tenancies with a VAT option
(M13-03 follow up, rule M13-04 section "Mietrechnung"; V21).

An invoice freezes the receivable items (Sollstellungsposten) of one contract and period:
net, tax rate, tax and gross per line, the invoicing legal entity (Rechtsträger) and its tax
identifier kind. Numbers are gapless per tenant, legal entity and calendar year
(``RentInvoiceNumberCounter``, locked while allocating, like ``InvoiceNumberCounter``).
Financial content is never overwritten or deleted: an invoice is cancelled only by a credit
note (``kind = credit_note``, negative amounts) that references it (rule 0.1.7). The PDF is a
draft with watermark while release gate G1 is closed for the tenant.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
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


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False) -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=nullable)


class RentInvoiceKind(StrEnum):
    INVOICE = "invoice"  # one period (usually a month)
    STANDING = "standing"  # Dauermietrechnung: several periods (usually a year), one line each
    CREDIT_NOTE = "credit_note"  # cancels an invoice or standing invoice, negative amounts


class RentInvoiceStatus(StrEnum):
    ISSUED = "issued"
    CANCELLED = "cancelled"  # a credit note references this invoice


class RentInvoiceNumberCounter(IdMixin, TenantMixin, Base):
    """Gapless numbering per tenant, legal entity and calendar year: ``MR-JJJJ-000001``."""

    __tablename__ = "rent_invoice_number_counter"
    __table_args__ = (UniqueConstraint("tenant_id", "legal_entity_id", "year"),)

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class RentInvoice(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "rent_invoice"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_entity_id", "number"),
        Index("ix_rent_invoice_contract", "tenant_id", "contract_id", "period_start"),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True)
    kind: Mapped[RentInvoiceKind] = mapped_column(
        _enum(RentInvoiceKind, "rent_invoice_kind"), nullable=False
    )
    status: Mapped[RentInvoiceStatus] = mapped_column(
        _enum(RentInvoiceStatus, "rent_invoice_status"),
        nullable=False,
        default=RentInvoiceStatus.ISSUED,
        server_default=RentInvoiceStatus.ISSUED.value,
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    net_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    gross_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Frozen lines: [{receivable_item_id, payment_type_code, period_start, period_end,
    # net, vat_percent, vat, gross}] as strings (no float, 6.9.8).
    lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # "vat_id" or "tax_number": which identifier of the legal entity the PDF shows. The value
    # itself is read at render time from the master data, never copied here.
    tax_identifier_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # True when G1 was closed at issue: the PDF carries the draft watermark (rule 0.1.1).
    draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    cancels_invoice_id: Mapped[uuid.UUID | None] = _fk("rent_invoice.id", nullable=True)
    cancelled_by_invoice_id: Mapped[uuid.UUID | None] = _fk("rent_invoice.id", nullable=True)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
