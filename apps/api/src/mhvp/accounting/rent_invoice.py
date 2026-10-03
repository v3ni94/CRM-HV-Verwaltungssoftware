"""Rent invoices with VAT for tenancies with a VAT option (Mietrechnung, Dauermietrechnung).

Rule M13-04 section "Mietrechnung mit Umsatzsteuerausweis" (draft, to be checked by the tax
adviser). The invoice is assembled from the receivable items (Sollstellungsposten) of the
contract and period: ``net_amount``, ``vat_percent``, ``vat_amount`` and ``amount`` (gross) per
item, nothing is recomputed here (the split is made and rounded in ``receivables``,
rule M13-03). Invoicing party is the legal entity of the contract (Rechtsträger, B01); the
managing company only signs "im Auftrag". The PDF uses the tenant letterhead
(``mhvp.documents.letters``) and is filed as a document linked to contract and contact.

Locks (no placeholder replaces a mandatory value, rule 0.1.3):
- contract without VAT option, or items without a released VAT split: MHVP-BILL-0011;
- no tax number or VAT id of the legal entity in the master data: MHVP-BILL-0012;
- no items in the period: MHVP-BILL-0013.
Cancellation only by credit note (MHVP-BILL-0014 for a second one). While release gate G1 is
closed for the tenant the PDF carries the draft watermark; nothing is posted or sent.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import ItemStatus, ReceivableItem, ReceivableRun
from mhvp.accounting.rent_invoice_models import (
    RentInvoice,
    RentInvoiceKind,
    RentInvoiceNumberCounter,
    RentInvoiceStatus,
)
from mhvp.contacts import recipients
from mhvp.contacts.models import ContactIdentifier, IdentifierKind, PartyMember
from mhvp.contracts.models import Contract, ContractVatOption
from mhvp.core.money import round_cents
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.models import DocumentSource, LinkRole
from mhvp.platform.models import TenantBillingSettings
from mhvp.properties.models import LegalEntity, LegalEntityKind, Property, Unit

NUMBER_PREFIX = "MR"
DRAFT_LABEL = "Entwurf, Freigabestufe G1 nicht erteilt, kein Versand"
CREDIT_NOTE_LABEL = "Gutschrift (Rechnungskorrektur)"
VAT_OPTIONS = (ContractVatOption.COMMERCIAL_FULL_VAT, ContractVatOption.COMMERCIAL_REDUCED_VAT)
TAX_ID_LABELS = {"vat_id": "USt-IdNr.", "tax_number": "Steuernummer"}
PAYMENT_TYPE_LABELS = {
    "rent": "Miete",
    "operating_costs": "Betriebskostenvorauszahlung",
    "heating_costs": "Heizkostenvorauszahlung",
}

# Mandatory content of the invoice (field list; legal basis to be confirmed by the tax
# adviser, docs/rules/M13-04.md). Each field names where the value comes from.
MANDATORY_FIELDS: tuple[tuple[str, str], ...] = (
    ("invoice_number", "fortlaufende Nummer je Rechtsträger und Jahr"),
    ("invoice_date", "Rechnungsdatum"),
    ("issuer", "Name und Anschrift des Rechtsträgers (Vermieter)"),
    ("issuer_tax_id", "Steuernummer oder USt-IdNr. des Rechtsträgers aus den Stammdaten"),
    ("recipient", "Name und Anschrift des Leistungsempfängers"),
    ("service_period", "Leistungszeitraum"),
    ("description", "Art der Leistung (Vermietung, Einheit)"),
    ("net", "Entgelt netto"),
    ("vat_percent", "Steuersatz"),
    ("vat", "Steuerbetrag"),
    ("gross", "Bruttobetrag"),
)


def format_number(year: int, number: int) -> str:
    return f"{NUMBER_PREFIX}-{year:04d}-{number:06d}"


def _money(value: Decimal | str | None) -> Decimal:
    return round_cents(Decimal(str(value or "0")))


def _eur(value: Decimal | str) -> str:
    amount = _money(value)
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{groups},{frac} EUR"


def _pct(value: Decimal | str) -> str:
    rate = Decimal(str(value)).normalize()
    text = f"{rate:f}".replace(".", ",")
    return f"{text} %"


def _d(value: date) -> str:
    return value.strftime("%d.%m.%Y")


# Numbering -------------------------------------------------------------------------------


DRAFT_NUMBER_PREFIX = "ENTWURF"
NUMBERING_SOURCE_KEY = "rent_invoice_draft_numbering"
NUMBERING_MODES = ("draft_numbers", "regular_numbers", "reject_when_g1_closed")
DEFAULT_NUMBERING_MODE = "draft_numbers"


def format_draft_number(year: int, number: int) -> str:
    return f"{DRAFT_NUMBER_PREFIX}-{year:04d}-{number:06d}"


def numbering_mode_of(sources: dict[str, Any] | None) -> str:
    """Tenant switch AC03-01; unknown or missing values fall back to the conservative default."""
    value = (sources or {}).get(NUMBERING_SOURCE_KEY)
    return value if value in NUMBERING_MODES else DEFAULT_NUMBERING_MODE


async def numbering_mode(session: AsyncSession) -> str:
    from mhvp.platform.models import TenantSettings

    sources = await session.scalar(select(TenantSettings.sources))
    return numbering_mode_of(sources)


def uses_draft_number(mode: str, draft: bool) -> bool:
    return draft and mode == "draft_numbers"


async def allocate_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    year: int,
    *,
    draft_number: bool = False,
) -> str:
    """Next gapless number per tenant, legal entity and year; the counter row is locked.

    Draft numbers (AC03-01) use their own counter row (year stored negated) so that drafts
    never consume the regular ``MR-`` series.
    """
    counter_year = -year if draft_number else year
    await session.execute(
        insert(RentInvoiceNumberCounter)
        .values(
            tenant_id=tenant_id, legal_entity_id=legal_entity_id, year=counter_year, last_number=0
        )
        .on_conflict_do_nothing()
    )
    counter = await session.scalar(
        select(RentInvoiceNumberCounter)
        .where(
            RentInvoiceNumberCounter.tenant_id == tenant_id,
            RentInvoiceNumberCounter.legal_entity_id == legal_entity_id,
            RentInvoiceNumberCounter.year == counter_year,
        )
        .with_for_update()
    )
    if counter is None:  # pragma: no cover - inserted above
        raise ProblemError(ErrorCodes.CONFLICT)
    counter.last_number += 1
    await session.flush()
    if draft_number:
        return format_draft_number(year, counter.last_number)
    return format_number(year, counter.last_number)


# Tax identifier of the legal entity ---------------------------------------------------------


@dataclass(frozen=True)
class TaxIdentifier:
    kind: str  # "vat_id" | "tax_number"
    value: str


async def tax_identifier(session: AsyncSession, entity: LegalEntity) -> TaxIdentifier | None:
    """USt-IdNr. (preferred) or Steuernummer of the legal entity from the master data: the
    tenant billing settings for the managing company, otherwise the identifiers of the
    contacts behind the entity's party. Never derived or invented."""
    if entity.kind is LegalEntityKind.MANAGER:
        billing = await session.scalar(
            select(TenantBillingSettings).where(TenantBillingSettings.tenant_id == entity.tenant_id)
        )
        if billing is not None:
            if billing.vat_id:
                return TaxIdentifier("vat_id", billing.vat_id)
            if billing.tax_number:
                return TaxIdentifier("tax_number", billing.tax_number)
        return None
    if entity.party_id is None:
        return None
    rows = (
        await session.execute(
            select(ContactIdentifier.kind, ContactIdentifier.value)
            .join(PartyMember, PartyMember.contact_id == ContactIdentifier.contact_id)
            .where(
                PartyMember.party_id == entity.party_id,
                ContactIdentifier.kind.in_([IdentifierKind.VAT_ID, IdentifierKind.TAX_NUMBER]),
            )
            .order_by(PartyMember.created_at, ContactIdentifier.created_at)
        )
    ).all()
    for wanted in (IdentifierKind.VAT_ID, IdentifierKind.TAX_NUMBER):
        for kind, value in rows:
            if kind is wanted and value and value.strip():
                return TaxIdentifier(wanted.value, value.strip())
    return None


# Items -----------------------------------------------------------------------------------


def _line_from_item(item: ReceivableItem) -> dict[str, Any]:
    start = item.period_start or item.period_month
    end = item.period_end or _month_end(item.period_month)
    return {
        "receivable_item_id": str(item.id),
        "payment_type_code": item.payment_type_code,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "net": str(_money(item.net_amount)),
        "vat_percent": str(Decimal(str(item.vat_percent)).normalize()),
        "vat": str(_money(item.vat_amount)),
        "gross": str(_money(item.amount)),
    }


def _month_end(month: date) -> date:
    import calendar

    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


async def collect_items(
    session: AsyncSession, contract: Contract, period_start: date, period_end: date
) -> list[ReceivableItem]:
    """Posted items of the contract in the period; where nothing is posted yet (G1 closed),
    the ready items of the newest preview run per month and payment type. Manual or blocked
    items are never invoiced. Items without a VAT split lock the invoice (BILL-0011)."""
    rows = (
        await session.execute(
            select(ReceivableItem, ReceivableRun.created_at)
            .join(ReceivableRun, ReceivableRun.id == ReceivableItem.run_id)
            .where(
                ReceivableItem.contract_id == contract.id,
                ReceivableItem.period_month >= period_start.replace(day=1),
                ReceivableItem.period_month <= period_end,
                ReceivableItem.status.in_([ItemStatus.POSTED, ItemStatus.READY]),
            )
            .order_by(ReceivableItem.period_month, ReceivableRun.created_at.desc())
        )
    ).all()
    chosen: dict[tuple[date, str, uuid.UUID | None], ReceivableItem] = {}
    for item, _created in rows:
        key = (item.period_month, item.payment_type_code, item.contract_payment_id)
        current = chosen.get(key)
        if current is None or (
            current.status is not ItemStatus.POSTED and item.status is ItemStatus.POSTED
        ):
            chosen[key] = item
    items = sorted(chosen.values(), key=lambda i: (i.period_month, i.payment_type_code))
    for item in items:
        if item.net_amount is None or item.vat_amount is None:
            raise ProblemError(
                ErrorCodes.RENT_INVOICE_NOT_ALLOWED,
                detail=(
                    "Der Sollstellungsposten trägt keinen Umsatzsteuerausweis "
                    "(Regel M13-03 nicht freigegeben oder Steuersatz ohne Option)."
                ),
            )
    return items


# Issue -----------------------------------------------------------------------------------


async def issue(
    session: AsyncSession,
    *,
    contract: Contract,
    period_start: date,
    period_end: date,
    standing: bool,
    invoice_date: date,
    draft: bool,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    mode: str = DEFAULT_NUMBERING_MODE,
) -> RentInvoice:
    """Freeze the items of the period into an invoice with a new gapless number."""
    if contract.vat_option not in VAT_OPTIONS:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_NOT_ALLOWED,
            detail="Der Vertrag hat keine Umsatzsteueroption; eine Mietrechnung mit "
            "Steuerausweis wird nicht erzeugt.",
        )
    if period_end < period_start:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum: Ende liegt vor Beginn.")
    entity = await session.get(LegalEntity, contract.legal_entity_id)
    if entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechtsträger nicht gefunden.")
    tax_id = await tax_identifier(session, entity)
    if tax_id is None:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_TAX_ID_MISSING,
            detail=f"Für den Rechtsträger {entity.name} ist weder Steuernummer noch "
            "USt-IdNr. in den Stammdaten hinterlegt. Die Rechnung wird nicht ausgegeben.",
        )
    items = await collect_items(session, contract, period_start, period_end)
    if not items:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_NO_ITEMS,
            detail="Im Zeitraum gibt es keine Sollstellungsposten zu diesem Vertrag.",
        )
    lines = [_line_from_item(i) for i in items]
    net = sum((Decimal(line["net"]) for line in lines), Decimal(0))
    vat = sum((Decimal(line["vat"]) for line in lines), Decimal(0))
    gross = sum((Decimal(line["gross"]) for line in lines), Decimal(0))
    if net + vat != gross:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_NOT_ALLOWED,
            detail="Netto plus Steuer ergibt nicht das Brutto der Posten; keine Ausgabe.",
        )
    number = await allocate_number(
        session,
        tenant_id,
        entity.id,
        invoice_date.year,
        draft_number=uses_draft_number(mode, draft),
    )
    contact_id = await recipients.debtor_contact_id(session, contract.party_id)
    row = RentInvoice(
        tenant_id=tenant_id,
        contract_id=contract.id,
        legal_entity_id=entity.id,
        contact_id=contact_id,
        kind=RentInvoiceKind.STANDING if standing else RentInvoiceKind.INVOICE,
        status=RentInvoiceStatus.ISSUED,
        number=number,
        invoice_date=invoice_date,
        period_start=period_start,
        period_end=period_end,
        net_total=net,
        vat_total=vat,
        gross_total=gross,
        lines=lines,
        tax_identifier_kind=tax_id.kind,
        draft=draft,
        issued_by=user_id,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def credit_note(
    session: AsyncSession,
    *,
    invoice: RentInvoice,
    invoice_date: date,
    draft: bool,
    user_id: uuid.UUID | None,
    mode: str = DEFAULT_NUMBERING_MODE,
) -> RentInvoice:
    """Cancel an invoice by a credit note with negated lines; the invoice itself is kept."""
    if invoice.kind is RentInvoiceKind.CREDIT_NOTE:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_CANCELLED, detail="Eine Gutschrift wird nicht storniert."
        )
    if invoice.status is RentInvoiceStatus.CANCELLED:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_CANCELLED,
            detail="Die Rechnung ist bereits durch eine Gutschrift storniert.",
        )
    lines = [
        {
            **line,
            "net": str(-Decimal(line["net"])),
            "vat": str(-Decimal(line["vat"])),
            "gross": str(-Decimal(line["gross"])),
        }
        for line in invoice.lines
    ]
    number = await allocate_number(
        session,
        invoice.tenant_id,
        invoice.legal_entity_id,
        invoice_date.year,
        draft_number=uses_draft_number(mode, draft),
    )
    row = RentInvoice(
        tenant_id=invoice.tenant_id,
        contract_id=invoice.contract_id,
        legal_entity_id=invoice.legal_entity_id,
        contact_id=invoice.contact_id,
        kind=RentInvoiceKind.CREDIT_NOTE,
        status=RentInvoiceStatus.ISSUED,
        number=number,
        invoice_date=invoice_date,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        net_total=-invoice.net_total,
        vat_total=-invoice.vat_total,
        gross_total=-invoice.gross_total,
        lines=lines,
        tax_identifier_kind=invoice.tax_identifier_kind,
        draft=draft,
        cancels_invoice_id=invoice.id,
        issued_by=user_id,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(row)
    await session.flush()
    invoice.status = RentInvoiceStatus.CANCELLED
    invoice.cancelled_by_invoice_id = row.id
    invoice.updated_by = user_id
    await session.flush()
    return row


# PDF -------------------------------------------------------------------------------------


def title_of(invoice: RentInvoice) -> str:
    if invoice.kind is RentInvoiceKind.CREDIT_NOTE:
        return CREDIT_NOTE_LABEL
    if invoice.kind is RentInvoiceKind.STANDING:
        return "Dauermietrechnung"
    return "Mietrechnung"


async def build_letter(
    session: AsyncSession,
    *,
    invoice: RentInvoice,
    contract: Contract,
    head: letters.Letterhead,
) -> letters.Letter:
    """Assemble the invoice letter from stored data only. The tax identifier is read from the
    master data at render time (never stored on the invoice); without it the PDF is refused."""
    entity = await session.get(LegalEntity, invoice.legal_entity_id)
    if entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechtsträger nicht gefunden.")
    tax_id = await tax_identifier(session, entity)
    if tax_id is None:
        raise ProblemError(
            ErrorCodes.RENT_INVOICE_TAX_ID_MISSING,
            detail=f"Für den Rechtsträger {entity.name} fehlt die Steuernummer oder "
            "USt-IdNr.; die Rechnung wird nicht ausgegeben.",
        )
    if invoice.contact_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Für den Mieter ist kein Kontakt mit Anschrift erfasst."
        )
    _contact, recipient_lines, _ = await docs.recipient(session, invoice.contact_id)
    unit = await session.get(Unit, contract.unit_id)
    prop = await session.get(Property, contract.property_id)
    object_line = " ".join(
        p
        for p in (
            getattr(prop, "street", None),
            getattr(prop, "house_number", None),
            f"Einheit {unit.number}" if unit is not None and unit.number else None,
        )
        if p
    )
    title = title_of(invoice)
    info: list[tuple[str, str]] = [
        ("Rechnungsnummer", invoice.number),
        ("Rechnungsdatum", _d(invoice.invoice_date)),
        ("Leistungszeitraum", f"{_d(invoice.period_start)} bis {_d(invoice.period_end)}"),
        ("Rechnungssteller", entity.name),
        (TAX_ID_LABELS[tax_id.kind], tax_id.value),
        ("Vertrag", contract.number),
    ]
    if invoice.kind is RentInvoiceKind.CREDIT_NOTE and invoice.cancels_invoice_id is not None:
        original = await session.get(RentInvoice, invoice.cancels_invoice_id)
        if original is not None:
            info.append(("Storniert Rechnung", original.number))
    rows = [
        [
            f"{_d(date.fromisoformat(line['period_start']))} bis "
            f"{_d(date.fromisoformat(line['period_end']))}",
            PAYMENT_TYPE_LABELS.get(line["payment_type_code"], line["payment_type_code"]),
            _eur(line["net"]),
            _pct(line["vat_percent"]),
            _eur(line["vat"]),
            _eur(line["gross"]),
        ]
        for line in invoice.lines
    ]
    rows.append(
        [
            "Summe",
            "",
            _eur(invoice.net_total),
            "",
            _eur(invoice.vat_total),
            _eur(invoice.gross_total),
        ]
    )
    table = letters.LetterTable(
        header=["Zeitraum", "Leistung", "Netto", "Steuersatz", "Steuer", "Brutto"],
        rows=rows,
        right_aligned=(2, 3, 4, 5),
        total_row=True,
        widths=(0.26, 0.2, 0.14, 0.1, 0.14, 0.16),
    )
    kind_text = (
        "die Vermietung"
        if invoice.kind is not RentInvoiceKind.CREDIT_NOTE
        else "die Korrektur der Rechnung"
    )
    body_parts = [
        f"für {kind_text} {html.escape(object_line) or 'der Mietsache'} im Zeitraum "
        f"{_d(invoice.period_start)} bis {_d(invoice.period_end)} weisen wir folgende "
        "Beträge aus:",
        letters.TABLE_MARKER.format(name="positions"),
    ]
    if invoice.kind is RentInvoiceKind.STANDING:
        body_parts.append(
            "Diese Dauerrechnung gilt für die genannten Zeiträume, solange sich die "
            "vereinbarten Beträge nicht ändern. Die Zahlung erfolgt zu den Fälligkeiten des "
            "Mietvertrags."
        )
    elif invoice.kind is RentInvoiceKind.CREDIT_NOTE:
        body_parts.append(
            "Diese Gutschrift hebt die genannte Rechnung vollständig auf. Die Rechnung "
            "bleibt in unseren Unterlagen erhalten."
        )
    else:
        body_parts.append("Die Zahlung erfolgt zu den Fälligkeiten des Mietvertrags.")
    body_parts.append(
        "Die Umsatzsteuer wird auf Grund der Option des Vermieters zur Steuerpflicht ausgewiesen."
    )
    signatory = [str(head.company.get("name", "")), f"im Auftrag von {entity.name}"]
    return letters.Letter(
        recipient_lines=recipient_lines,
        subject=html.escape(f"{title} {invoice.number}, {object_line or contract.number}"),
        body="\n\n".join(body_parts),
        letter_date=invoice.invoice_date,
        info=info,
        signatory=signatory,
        tables={"positions": table},
        draft_notice=DRAFT_LABEL if invoice.draft else None,
    )


async def store(
    session: AsyncSession,
    blobs: Any,
    *,
    invoice: RentInvoice,
    contract: Contract,
    pdf: bytes,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    """File the PDF in the document index, linked to contract and tenant contact."""
    title = title_of(invoice)
    links: list[tuple[str, uuid.UUID, LinkRole]] = [("contract", contract.id, LinkRole.GENERATED)]
    if invoice.contact_id is not None:
        links.append(("contact", invoice.contact_id, LinkRole.GENERATED))
    suffix = " (Entwurf)" if invoice.draft else ""
    document = await docs.store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=pdf,
        title=f"{title} {invoice.number}{suffix}, {contract.number}",
        filename=f"{invoice.invoice_date.isoformat()}_{title.split(' ')[0].lower()}_"
        f"{invoice.number}.pdf",
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=links,
        created_by=user_id,
    )
    invoice.document_id = document.id
    invoice.updated_by = user_id
    await session.flush()
    return document.id
