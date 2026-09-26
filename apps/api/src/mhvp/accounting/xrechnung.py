"""XRechnung (UBL 2.1) for issued Verwalterhonorar invoices (A12, 13.5 E-Rechnung, M13-04, D41).

Scope: generation of the XML for an ``AdminFeeInvoice`` and a structural self check of the
EN 16931 mandatory fields and the sum consistency (net plus tax equals gross, line sums equal
net). The self check is not the official validation: the KoSIT validator with the XRechnung
configuration is the reference (``scripts/kosit_validate.sh``, P05) and is not bundled.

Nothing is invented: Leitweg-ID, USt-IdNr. and Steuernummer come only from
``TenantBillingSettings``; the seller name and address come from the tenant company data
(``TenantSettings.company``). A missing value locks the generation with a problem code.
"""

import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import numbering
from mhvp.accounting.models import (
    AdminFeeInvoice,
    AdminFeeInvoiceStatus,
    AdminFeeSetting,
    Invoice,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantBillingSettings, TenantSettings, VatStatus

CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
INVOICE_TYPE_CODE = "380"  # commercial invoice (UNTDID 1001)
UNIT_CODE = "C62"  # one (UN/ECE Recommendation 20)
PAYMENT_MEANS_SEPA_CREDIT_TRANSFER = "58"
EAS_LEITWEG_ID = "0204"  # electronic address scheme of the Leitweg-ID (EAS code list)
# BT-20: the due date of the fee follows the management contract; no term is invented here
# (operator text is an open point in docs/OPEN_QUESTIONS.md M13-04).
PAYMENT_TERMS_NOTE = "Fälligkeit gemäß Verwaltervertrag."

NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS = {"ubl": NS_INVOICE, "cac": NS_CAC, "cbc": NS_CBC}
CENT = Decimal("0.01")
UNIT_TYPE_LABELS = {
    "apartment": "Wohnung",
    "commercial": "Gewerbeeinheit",
    "parking": "Stellplatz",
    "garage": "Garage",
    "storage": "Lagerraum",
    "other": "Sonstige Einheit",
}
INTERVAL_LABELS = {
    "monthly": "monatlich",
    "quarterly": "vierteljährlich",
    "yearly": "jährlich",
    "annual": "jährlich",
}


# Data ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Address:
    street: str
    postal_code: str
    city: str
    country: str = "DE"


@dataclass(frozen=True)
class Seller:
    name: str
    address: Address
    vat_id: str | None = None
    tax_number: str | None = None
    payee_iban: str | None = None
    # BT-30 legal registration identifier (e.g. HRB number); XRechnung needs BT-29, BT-30 or
    # BT-31 (BR-CO-26), a tax number alone is not enough.
    register_number: str | None = None
    email: str | None = None
    phone: str | None = None
    contact_name: str | None = None


@dataclass(frozen=True)
class Buyer:
    name: str
    address: Address
    email: str | None = None


@dataclass(frozen=True)
class Line:
    text: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class InvoiceData:
    number: str
    issue_date: date
    buyer_reference: str
    seller: Seller
    buyer: Buyer
    lines: list[Line]
    net: Decimal
    vat_percent: Decimal
    vat: Decimal
    gross: Decimal
    currency: str = "EUR"
    # Kleinunternehmer (§ 19 UStG): no VAT, the operator's mandatory note is the exemption reason.
    tax_exemption_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def tax_category(self) -> str:
        return "E" if self.tax_exemption_reason else "S"


@dataclass(frozen=True)
class Finding:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


# Fee lines ------------------------------------------------------------------------------


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def fee_lines(draft: dict[str, Any], interval: str) -> list[dict[str, str]]:
    """Invoice lines from an admin fee draft (``receivables.admin_fee``).

    A minimum or maximum fee that moves the net away from the sum of the unit lines becomes an
    explicit adjustment line, so that the line sum always equals the net amount (B06).
    """
    period = INTERVAL_LABELS.get(interval, interval)
    lines: list[dict[str, str]] = []
    total = Decimal("0.00")
    for raw in draft["lines"]:
        label = UNIT_TYPE_LABELS.get(str(raw["unit_type"]), str(raw["unit_type"]))
        amount = _money(raw["amount"])
        total += amount
        lines.append(
            {
                "text": f"Verwalterhonorar {label}, {period}",
                "quantity": str(int(raw["count"])),
                "unit_price": str(_money(raw["rate"])),
                "amount": str(amount),
            }
        )
    net = _money(draft["net"])
    if net != total:
        difference = net - total
        # A reduction is a negative quantity with a positive price (BR-27: the item net price
        # is never negative); the line amount then carries the sign.
        lines.append(
            {
                "text": "Anpassung auf Mindesthonorar"
                if difference > 0
                else "Anpassung auf Höchsthonorar",
                "quantity": "1" if difference > 0 else "-1",
                "unit_price": str(abs(difference)),
                "amount": str(difference),
            }
        )
    return lines


# Locks ------------------------------------------------------------------------------------


def assert_generation_allowed(settings: TenantBillingSettings | None) -> None:
    """Tax data (M13-04) and Leitweg-ID (BT-10) must be entered; nothing is defaulted."""
    numbering.assert_xrechnung_allowed(settings)
    if settings is None:  # pragma: no cover - assert_xrechnung_allowed raises before
        raise ProblemError(ErrorCodes.BILLING_VAT_STATUS_MISSING)
    if not (settings.leitweg_id or "").strip():
        raise ProblemError(
            ErrorCodes.BILLING_LEITWEG_ID_MISSING,
            detail="Leitweg-ID des Rechnungsempfängers ist nicht eingetragen (BT-10).",
        )
    if not (settings.payee_iban or "").strip():
        raise ProblemError(
            ErrorCodes.BILLING_PAYEE_IBAN_MISSING,
            detail="IBAN des Rechnungsstellers für die Überweisung ist nicht eingetragen (BT-84).",
        )


def _company_address(company: dict[str, Any], owner: str) -> Address:
    missing = [k for k in ("name", "street", "postal_code", "city") if not company.get(k)]
    if missing:
        raise ProblemError(
            ErrorCodes.LETTERHEAD_INCOMPLETE,
            detail=f"Fehlende Firmendaten des {owner}: {', '.join(missing)}.",
        )
    return Address(
        street=str(company["street"]),
        postal_code=str(company["postal_code"]),
        city=str(company["city"]),
        country=str(company.get("country") or "DE"),
    )


# Persistence ------------------------------------------------------------------------------


async def issue(
    session: AsyncSession,
    *,
    fee: AdminFeeSetting,
    draft: dict[str, Any],
    number: str,
    issue_date: date,
    billing: TenantBillingSettings | None,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> AdminFeeInvoice:
    """Freeze the issued fee invoice (number, date, amounts, lines, debtor) for the XML."""
    row = AdminFeeInvoice(
        tenant_id=tenant_id,
        created_by=user_id,
        fee_setting_id=fee.id,
        property_id=fee.property_id,
        number=number,
        invoice_date=issue_date,
        status=AdminFeeInvoiceStatus.ISSUED,
        net=_money(draft["net"]),
        vat_percent=Decimal(str(draft["vat_percent"])),
        vat=_money(draft["vat"]),
        gross=_money(draft["gross"]),
        lines=fee_lines(draft, fee.interval),
        debtor_legal_entity_id=(
            uuid.UUID(draft["debtor_legal_entity_id"])
            if draft.get("debtor_legal_entity_id")
            else None
        ),
        invoice_debtor_party_id=fee.invoice_debtor_party_id,
        buyer_reference=(billing.leitweg_id if billing else None),
    )
    session.add(row)
    await session.flush()
    return row


async def _buyer(session: AsyncSession, invoice: AdminFeeInvoice) -> Buyer:
    from mhvp.contacts.models import Contact, ContactAddress, Party, PartyMember
    from mhvp.properties.models import LegalEntity, Property

    prop = await session.get(Property, invoice.property_id)
    if invoice.invoice_debtor_party_id is not None:
        party = await session.get(Party, invoice.invoice_debtor_party_id)
        if party is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Schuldner nicht gefunden.")
        member = await session.scalar(
            select(PartyMember)
            .where(PartyMember.party_id == party.id)
            .order_by(PartyMember.role, PartyMember.created_at)
            .limit(1)
        )
        contact = await session.get(Contact, member.contact_id) if member else None
        address = (
            await session.scalar(
                select(ContactAddress)
                .where(ContactAddress.contact_id == contact.id)
                .order_by(ContactAddress.is_primary.desc(), ContactAddress.created_at)
                .limit(1)
            )
            if contact
            else None
        )
        if address is None or not (address.street and address.postal_code and address.city):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Für {party.name} ist keine vollständige Anschrift erfasst (BT-50 bis BT-55)."
                ),
            )
        street = " ".join(p for p in (address.street, address.house_number) if p)
        return Buyer(
            name=party.name,
            address=Address(street, address.postal_code, address.city, address.country or "DE"),
        )
    entity = (
        await session.get(LegalEntity, invoice.debtor_legal_entity_id)
        if invoice.debtor_legal_entity_id
        else None
    )
    if entity is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Rechtsträger des Rechnungsempfängers fehlt (Gemeinschaft nicht angelegt).",
        )
    if prop is None or not (prop.street and prop.postal_code and prop.city):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Objektanschrift ist unvollständig (Käuferanschrift BT-50 bis BT-55).",
        )
    street = " ".join(p for p in (prop.street, prop.house_number) if p)
    return Buyer(
        name=entity.name, address=Address(street, prop.postal_code, prop.city, prop.country or "DE")
    )


async def load(session: AsyncSession, invoice: AdminFeeInvoice) -> InvoiceData:
    """Assemble the XML input; every lock of ``assert_generation_allowed`` applies here."""
    billing = await session.scalar(
        select(TenantBillingSettings).where(TenantBillingSettings.tenant_id == invoice.tenant_id)
    )
    assert_generation_allowed(billing)
    if billing is None:  # pragma: no cover - assert_generation_allowed raises before
        raise ProblemError(ErrorCodes.BILLING_VAT_STATUS_MISSING)
    settings = await session.scalar(select(TenantSettings))
    company = dict(settings.company) if settings else {}
    seller = Seller(
        name=str(company.get("name") or ""),
        address=_company_address(company, "Mandanten"),
        vat_id=billing.vat_id or None,
        tax_number=billing.tax_number or None,
        payee_iban=billing.payee_iban or None,
        register_number=company.get("register_number") or None,
        email=company.get("email") or None,
        phone=company.get("phone") or None,
        contact_name=(company.get("management") or [None])[0],
    )
    contact_missing = [
        label
        for label, value in (
            ("E-Mail (BT-34, BT-43)", seller.email),
            ("Telefon (BT-42)", seller.phone),
            ("Ansprechpartner (BT-41, Geschäftsführung)", seller.contact_name),
        )
        if not value
    ]
    if contact_missing:
        # BR-DE-2, BR-DE-5 to BR-DE-7 and the seller electronic address: mandatory in XRechnung.
        raise ProblemError(
            ErrorCodes.LETTERHEAD_INCOMPLETE,
            detail="Fehlende Firmendaten des Mandanten: " + ", ".join(contact_missing) + ".",
        )
    if not (seller.vat_id or seller.register_number):
        raise ProblemError(
            ErrorCodes.BILLING_TAX_DATA_MISSING,
            detail=(
                "XRechnung braucht die USt-IdNr. oder eine Registernummer des Rechnungsstellers "
                "(BR-CO-26); die Steuernummer allein reicht nicht."
            ),
        )
    exemption: str | None = None
    if billing.vat_status is VatStatus.KLEINUNTERNEHMER:
        if invoice.vat_percent != 0 or invoice.vat != 0:
            raise ProblemError(
                ErrorCodes.BILLING_TAX_DATA_MISSING,
                detail="Kleinunternehmer: die Honorarrechnung darf keine Umsatzsteuer ausweisen.",
            )
        exemption = billing.kleinunternehmer_note
    elif invoice.vat_percent <= 0:
        raise ProblemError(
            ErrorCodes.BILLING_TAX_DATA_MISSING,
            detail=(
                "Regelbesteuert ohne Steuersatz: die Steuerkategorie der Position ist nicht "
                "bestimmbar; Steuersatz am Verwalterhonorar eintragen."
            ),
        )
    lines = [
        Line(
            text=str(ln["text"]),
            quantity=Decimal(str(ln["quantity"])),
            unit_price=Decimal(str(ln["unit_price"])),
            amount=_money(ln["amount"]),
        )
        for ln in invoice.lines
    ]
    if not lines:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Die Rechnung enthält keine Positionen (BG-25)."
        )
    return InvoiceData(
        number=invoice.number,
        issue_date=invoice.invoice_date,
        buyer_reference=str(billing.leitweg_id).strip(),
        seller=seller,
        buyer=await _buyer(session, invoice),
        lines=lines,
        net=invoice.net,
        vat_percent=Decimal(invoice.vat_percent),
        vat=invoice.vat,
        gross=invoice.gross,
        currency=invoice.currency,
        tax_exemption_reason=exemption,
    )


# XML --------------------------------------------------------------------------------------


def _fmt(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _pct(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text if "." in text else f"{text}.00"


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    prefix, name = tag.split(":")
    element = ET.SubElement(parent, f"{{{NS[prefix]}}}{name}", attrs)
    if text is not None:
        element.text = text
    return element


def _address(parent: ET.Element, address: Address) -> None:
    node = _sub(parent, "cac:PostalAddress")
    _sub(node, "cbc:StreetName", address.street)
    _sub(node, "cbc:CityName", address.city)
    _sub(node, "cbc:PostalZone", address.postal_code)
    _sub(_sub(node, "cac:Country"), "cbc:IdentificationCode", address.country)


def _tax_category(parent: ET.Element, tag: str, data: InvoiceData) -> None:
    category = _sub(parent, tag)
    _sub(category, "cbc:ID", data.tax_category)
    _sub(category, "cbc:Percent", _pct(data.vat_percent))
    if tag == "cac:TaxCategory" and data.tax_exemption_reason:
        _sub(category, "cbc:TaxExemptionReason", data.tax_exemption_reason)
    _sub(_sub(category, "cac:TaxScheme"), "cbc:ID", "VAT")


def build_xml(data: InvoiceData) -> bytes:
    """UBL 2.1 invoice in the XRechnung 3.0 customization; element order follows the schema."""
    for prefix, uri in NS.items():
        ET.register_namespace("" if prefix == "ubl" else prefix, uri)
    root = ET.Element(f"{{{NS_INVOICE}}}Invoice")
    _sub(root, "cbc:CustomizationID", CUSTOMIZATION_ID)
    _sub(root, "cbc:ProfileID", PROFILE_ID)
    _sub(root, "cbc:ID", data.number)  # BT-1
    _sub(root, "cbc:IssueDate", data.issue_date.isoformat())  # BT-2
    _sub(root, "cbc:InvoiceTypeCode", INVOICE_TYPE_CODE)  # BT-3
    for note in data.notes:
        _sub(root, "cbc:Note", note)
    _sub(root, "cbc:DocumentCurrencyCode", data.currency)  # BT-5
    _sub(root, "cbc:BuyerReference", data.buyer_reference)  # BT-10 (Leitweg-ID)

    supplier = _sub(_sub(root, "cac:AccountingSupplierParty"), "cac:Party")
    if data.seller.email:
        _sub(supplier, "cbc:EndpointID", data.seller.email, schemeID="EM")  # BT-34
    _sub(_sub(supplier, "cac:PartyName"), "cbc:Name", data.seller.name)  # BT-27
    _address(supplier, data.seller.address)  # BG-5
    if data.seller.vat_id:  # BT-31
        scheme = _sub(supplier, "cac:PartyTaxScheme")
        _sub(scheme, "cbc:CompanyID", data.seller.vat_id)
        _sub(_sub(scheme, "cac:TaxScheme"), "cbc:ID", "VAT")
    if data.seller.tax_number:  # BT-32
        scheme = _sub(supplier, "cac:PartyTaxScheme")
        _sub(scheme, "cbc:CompanyID", data.seller.tax_number)
        _sub(_sub(scheme, "cac:TaxScheme"), "cbc:ID", "FC")
    legal = _sub(supplier, "cac:PartyLegalEntity")
    _sub(legal, "cbc:RegistrationName", data.seller.name)
    if data.seller.register_number:
        _sub(legal, "cbc:CompanyID", data.seller.register_number)  # BT-30
    if data.seller.contact_name or data.seller.phone or data.seller.email:  # BG-6
        contact = _sub(supplier, "cac:Contact")
        if data.seller.contact_name:
            _sub(contact, "cbc:Name", data.seller.contact_name)
        if data.seller.phone:
            _sub(contact, "cbc:Telephone", data.seller.phone)
        if data.seller.email:
            _sub(contact, "cbc:ElectronicMail", data.seller.email)

    customer = _sub(_sub(root, "cac:AccountingCustomerParty"), "cac:Party")
    if data.buyer.email:
        _sub(customer, "cbc:EndpointID", data.buyer.email, schemeID="EM")  # BT-49
    else:
        # BT-49 with the Leitweg-ID scheme: the electronic address of the invoice recipient.
        _sub(customer, "cbc:EndpointID", data.buyer_reference, schemeID=EAS_LEITWEG_ID)
    _sub(_sub(customer, "cac:PartyName"), "cbc:Name", data.buyer.name)  # BT-44
    _address(customer, data.buyer.address)  # BG-8
    _sub(_sub(customer, "cac:PartyLegalEntity"), "cbc:RegistrationName", data.buyer.name)

    # BG-16: SEPA credit transfer to the payee IBAN of the invoicing tenant (BT-84, BR-61).
    means = _sub(root, "cac:PaymentMeans")
    _sub(means, "cbc:PaymentMeansCode", PAYMENT_MEANS_SEPA_CREDIT_TRANSFER)
    if data.seller.payee_iban:
        _sub(_sub(means, "cac:PayeeFinancialAccount"), "cbc:ID", data.seller.payee_iban)

    _sub(_sub(root, "cac:PaymentTerms"), "cbc:Note", PAYMENT_TERMS_NOTE)  # BT-20

    tax_total = _sub(root, "cac:TaxTotal")
    _sub(tax_total, "cbc:TaxAmount", _fmt(data.vat), currencyID=data.currency)  # BT-110
    subtotal = _sub(tax_total, "cac:TaxSubtotal")
    _sub(subtotal, "cbc:TaxableAmount", _fmt(data.net), currencyID=data.currency)  # BT-116
    _sub(subtotal, "cbc:TaxAmount", _fmt(data.vat), currencyID=data.currency)  # BT-117
    _tax_category(subtotal, "cac:TaxCategory", data)

    total = _sub(root, "cac:LegalMonetaryTotal")
    line_sum = sum((ln.amount for ln in data.lines), Decimal("0.00"))
    _sub(total, "cbc:LineExtensionAmount", _fmt(line_sum), currencyID=data.currency)  # BT-106
    _sub(total, "cbc:TaxExclusiveAmount", _fmt(data.net), currencyID=data.currency)  # BT-109
    _sub(total, "cbc:TaxInclusiveAmount", _fmt(data.gross), currencyID=data.currency)  # BT-112
    _sub(total, "cbc:PayableAmount", _fmt(data.gross), currencyID=data.currency)  # BT-115

    for index, ln in enumerate(data.lines, start=1):
        line = _sub(root, "cac:InvoiceLine")
        _sub(line, "cbc:ID", str(index))  # BT-126
        _sub(line, "cbc:InvoicedQuantity", format(ln.quantity, "f"), unitCode=UNIT_CODE)
        _sub(line, "cbc:LineExtensionAmount", _fmt(ln.amount), currencyID=data.currency)
        item = _sub(line, "cac:Item")
        _sub(item, "cbc:Name", ln.text)  # BT-153
        _tax_category(item, "cac:ClassifiedTaxCategory", data)
        _sub(
            _sub(line, "cac:Price"),
            "cbc:PriceAmount",
            _fmt(ln.unit_price),
            currencyID=data.currency,
        )

    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


# Structural self check -------------------------------------------------------------------

_REQUIRED: list[tuple[str, str, str]] = [
    ("BT-1", "Rechnungsnummer", "cbc:ID"),
    ("BT-2", "Rechnungsdatum", "cbc:IssueDate"),
    ("BT-3", "Rechnungstyp", "cbc:InvoiceTypeCode"),
    ("BT-5", "Währung", "cbc:DocumentCurrencyCode"),
    ("BT-10", "Leitweg-ID (BuyerReference)", "cbc:BuyerReference"),
    ("BT-24", "Spezifikationskennung", "cbc:CustomizationID"),
    ("BT-27", "Verkäufername", "cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name"),
    (
        "BT-37",
        "Verkäufer Ort",
        "cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:CityName",
    ),
    (
        "BT-38",
        "Verkäufer PLZ",
        "cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cbc:PostalZone",
    ),
    (
        "BT-40",
        "Verkäufer Land",
        "cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cac:Country/cbc:IdentificationCode",
    ),
    (
        "BT-34",
        "Verkäufer elektronische Adresse",
        "cac:AccountingSupplierParty/cac:Party/cbc:EndpointID",
    ),
    (
        "BT-41",
        "Verkäufer Kontakt Name",
        "cac:AccountingSupplierParty/cac:Party/cac:Contact/cbc:Name",
    ),
    (
        "BT-42",
        "Verkäufer Kontakt Telefon",
        "cac:AccountingSupplierParty/cac:Party/cac:Contact/cbc:Telephone",
    ),
    (
        "BT-43",
        "Verkäufer Kontakt E-Mail",
        "cac:AccountingSupplierParty/cac:Party/cac:Contact/cbc:ElectronicMail",
    ),
    ("BT-44", "Käufername", "cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name"),
    (
        "BT-52",
        "Käufer Ort",
        "cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:CityName",
    ),
    (
        "BT-53",
        "Käufer PLZ",
        "cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cbc:PostalZone",
    ),
    (
        "BT-55",
        "Käufer Land",
        "cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cac:Country/cbc:IdentificationCode",
    ),
    (
        "BT-49",
        "Käufer elektronische Adresse",
        "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID",
    ),
    ("BT-20", "Zahlungsbedingungen", "cac:PaymentTerms/cbc:Note"),
    ("BT-110", "Steuersumme", "cac:TaxTotal/cbc:TaxAmount"),
    ("BT-106", "Summe der Positionen", "cac:LegalMonetaryTotal/cbc:LineExtensionAmount"),
    ("BT-109", "Nettobetrag", "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"),
    ("BT-112", "Bruttobetrag", "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"),
    ("BT-115", "Zahlbetrag", "cac:LegalMonetaryTotal/cbc:PayableAmount"),
]


def _text(node: ET.Element | None, path: str) -> str | None:
    found = node.find(path, NS) if node is not None else None
    return found.text.strip() if found is not None and found.text else None


def _dec(text: str | None) -> Decimal | None:
    try:
        return Decimal(text) if text is not None else None
    except ArithmeticError:
        return None


def check_structure(xml: bytes) -> list[Finding]:
    """Findings on mandatory fields and sums; an empty list means structurally consistent.

    This mirrors the EN 16931 business terms the module writes and the arithmetic rules
    BR-CO-10, BR-CO-13, BR-CO-15 and BR-CO-17 as far as this invoice type uses them. It is not
    a replacement for the official validator (schematron of the KoSIT configuration).
    """
    findings: list[Finding] = []
    try:
        root = SafeET.fromstring(xml)
    except (ET.ParseError, ValueError) as exc:
        return [Finding("XML", f"Kein wohlgeformtes XML: {exc}")]
    if root.tag != f"{{{NS_INVOICE}}}Invoice":
        findings.append(Finding("UBL", "Wurzelelement ist keine UBL-Invoice."))
        return findings
    for code, label, path in _REQUIRED:
        if not _text(root, path):
            findings.append(Finding(code, f"{label} fehlt."))
    if _text(root, "cbc:CustomizationID") != CUSTOMIZATION_ID:
        findings.append(Finding("BT-24", "Spezifikationskennung ist nicht XRechnung 3.0."))
    supplier = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    tax_ids = [
        _text(scheme, "cbc:CompanyID")
        for scheme in (supplier.findall("cac:PartyTaxScheme", NS) if supplier is not None else [])
    ]
    if not any(tax_ids):
        findings.append(Finding("BT-31", "Weder USt-IdNr. (BT-31) noch Steuernummer (BT-32)."))
    vat_ids = [
        _text(scheme, "cbc:CompanyID")
        for scheme in (supplier.findall("cac:PartyTaxScheme", NS) if supplier is not None else [])
        if _text(scheme, "cac:TaxScheme/cbc:ID") == "VAT"
    ]
    if not any(vat_ids) and not _text(supplier, "cac:PartyLegalEntity/cbc:CompanyID"):
        findings.append(
            Finding(
                "BR-CO-26", "Weder USt-IdNr. (BT-31) noch Registernummer (BT-30) des Verkäufers."
            )
        )
    if _text(root, "cac:PaymentMeans/cbc:PaymentMeansCode") in ("30", "58") and not _text(
        root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID"
    ):
        findings.append(
            Finding("BR-61", "Überweisung ohne Kontoverbindung des Zahlungsempfängers.")
        )
    lines = root.findall("cac:InvoiceLine", NS)
    if not lines:
        findings.append(Finding("BG-25", "Keine Rechnungsposition."))
    line_sum = Decimal("0.00")
    for index, line in enumerate(lines, start=1):
        amount = _dec(_text(line, "cbc:LineExtensionAmount"))
        quantity = _dec(_text(line, "cbc:InvoicedQuantity"))
        price = _dec(_text(line, "cac:Price/cbc:PriceAmount"))
        if not _text(line, "cbc:ID"):
            findings.append(Finding("BT-126", f"Position {index}: Kennung fehlt."))
        if not _text(line, "cac:Item/cbc:Name"):
            findings.append(Finding("BT-153", f"Position {index}: Bezeichnung fehlt."))
        if amount is None or quantity is None or price is None:
            findings.append(Finding("BT-131", f"Position {index}: Menge, Preis oder Betrag fehlt."))
            continue
        expected = (quantity * price).quantize(CENT, rounding=ROUND_HALF_UP)
        if expected != amount:
            findings.append(
                Finding(
                    "BR-CO-10",
                    f"Position {index}: Menge mal Preis ergibt {expected}, nicht {amount}.",
                )
            )
        line_sum += amount
    total = root.find("cac:LegalMonetaryTotal", NS)
    ext = _dec(_text(total, "cbc:LineExtensionAmount"))
    net = _dec(_text(total, "cbc:TaxExclusiveAmount"))
    gross = _dec(_text(total, "cbc:TaxInclusiveAmount"))
    payable = _dec(_text(total, "cbc:PayableAmount"))
    tax = _dec(_text(root, "cac:TaxTotal/cbc:TaxAmount"))
    if ext is not None and lines and ext != line_sum:
        findings.append(
            Finding("BR-CO-10", f"Summe der Positionen {line_sum} weicht von BT-106 {ext} ab.")
        )
    if ext is not None and net is not None and ext != net:
        findings.append(
            Finding("BR-CO-13", f"Netto {net} entspricht nicht der Positionssumme {ext}.")
        )
    if net is not None and tax is not None and gross is not None and net + tax != gross:
        findings.append(
            Finding("BR-CO-15", f"Netto {net} plus Steuer {tax} ergibt nicht Brutto {gross}.")
        )
    if gross is not None and payable is not None and gross != payable:
        findings.append(Finding("BR-CO-16", f"Zahlbetrag {payable} weicht von Brutto {gross} ab."))
    subtotal_tax = Decimal("0.00")
    for subtotal in root.findall("cac:TaxTotal/cac:TaxSubtotal", NS):
        taxable = _dec(_text(subtotal, "cbc:TaxableAmount"))
        sub_tax = _dec(_text(subtotal, "cbc:TaxAmount"))
        percent = _dec(_text(subtotal, "cac:TaxCategory/cbc:Percent"))
        category = _text(subtotal, "cac:TaxCategory/cbc:ID")
        if taxable is None or sub_tax is None or percent is None:
            findings.append(Finding("BG-23", "Steueraufschlüsselung unvollständig."))
            continue
        subtotal_tax += sub_tax
        expected = (taxable * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if expected != sub_tax:
            findings.append(
                Finding("BR-CO-17", f"Steuer {sub_tax} statt {expected} bei {percent} %.")
            )
        if category == "E" and not _text(subtotal, "cac:TaxCategory/cbc:TaxExemptionReason"):
            findings.append(Finding("BR-E-10", "Steuerbefreiung ohne Begründungstext."))
    if tax is not None and subtotal_tax != tax:
        findings.append(
            Finding(
                "BR-CO-14", f"Summe der Steueraufschlüsselung {subtotal_tax} weicht von {tax} ab."
            )
        )
    return findings


# API --------------------------------------------------------------------------------------

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


async def _issued(session: AsyncSession, invoice_id: uuid.UUID) -> AdminFeeInvoice:
    row = await session.get(AdminFeeInvoice, invoice_id)
    if row is None:
        if await session.get(Invoice, invoice_id) is not None:
            # An incoming invoice or a draft is never rendered as the tenant's own XRechnung.
            raise ProblemError(
                ErrorCodes.XRECHNUNG_NOT_ISSUED,
                detail="Nur ausgestellte Honorarrechnungen werden als XRechnung erzeugt.",
            )
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status not in (AdminFeeInvoiceStatus.ISSUED, AdminFeeInvoiceStatus.RELEASED):
        raise ProblemError(ErrorCodes.XRECHNUNG_NOT_ISSUED)
    return row


def _filename(invoice: AdminFeeInvoice) -> str:
    return f"{invoice.number}.xml"


@router.get(
    "/invoices/{invoice_id}/xrechnung.xml",
    summary="Honorarrechnung als XRechnung (UBL 2.1, XRechnung 3.0)",
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}}},
)
async def xrechnung_xml(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    """Generated on request from the frozen invoice and the current tenant tax data; drafts and
    incoming invoices answer 409 (MHVP-BILL-0006), missing Leitweg-ID or tax data 409
    (MHVP-BILL-0002/0003/0005)."""
    async with tenant_tx(request, principal) as session:
        invoice = await _issued(session, invoice_id)
        xml = build_xml(await load(session, invoice))
        findings = check_structure(xml)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(invoice)}"',
            "X-MHVP-XRechnung-Findings": str(len(findings)),
        },
    )


@router.get(
    "/invoices/{invoice_id}/xrechnung/check", summary="Strukturprüfung der XRechnung (Findings)"
)
async def xrechnung_check(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Own structural check only (mandatory fields, sums); the official KoSIT validator is run
    outside the platform (P05, scripts/kosit_validate.sh)."""
    async with tenant_tx(request, principal) as session:
        invoice = await _issued(session, invoice_id)
        xml = build_xml(await load(session, invoice))
    findings = check_structure(xml)
    return {
        "invoice_id": invoice.id,
        "number": invoice.number,
        "structure_ok": not findings,
        "findings": [f.as_dict() for f in findings],
        "official_validation": "not_run",
    }


@router.post(
    "/invoices/{invoice_id}/xrechnung/document",
    status_code=201,
    summary="XRechnung als Dokument ablegen (Objekt und Rechtsträger verknüpft)",
)
async def xrechnung_store(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Files the XML once in the document index (source generated); a second call returns the
    existing document. Nothing is sent to the recipient."""
    from mhvp.documents import services as docs
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole

    async with tenant_tx(request, principal) as session:
        invoice = await _issued(session, invoice_id)
        if invoice.xml_document_id is not None:
            return {"document_id": invoice.xml_document_id, "created": False}
        xml = build_xml(await load(session, invoice))
        links: list[tuple[str, uuid.UUID, LinkRole]] = [
            ("property", invoice.property_id, LinkRole.GENERATED)
        ]
        if invoice.debtor_legal_entity_id is not None:
            links.append(("legal_entity", invoice.debtor_legal_entity_id, LinkRole.GENERATED))
        document = await docs.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=xml,
            title=f"XRechnung {invoice.number}",
            filename=_filename(invoice),
            mime_type="application/xml",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=links,
            created_by=principal.user_id,
        )
        invoice.xml_document_id = document.id
        invoice.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.xrechnung_stored",
            entity_type="admin_fee_invoice",
            entity_id=invoice.id,
            actor_user_id=principal.user_id,
            payload={"number": invoice.number, "document_id": str(document.id)},
        )
        await session.flush()
        return {"document_id": document.id, "created": True}
