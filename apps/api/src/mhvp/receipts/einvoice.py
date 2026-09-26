"""E-invoice reading for the Belegeingang (M14, spec 13.5, PÜ01, cases D41 and D42).

Reads the structured part of an incoming e-invoice deterministically, without any provider
call: XRechnung as a plain XML file (UBL 2.1 ``Invoice`` or UN/CEFACT CII
``CrossIndustryInvoice``) and ZUGFeRD / Factur-X (PDF with an embedded XML attachment named
``factur-x.xml``, ``zugferd-invoice.xml``, ``ZUGFeRD-invoice.xml`` or ``xrechnung.xml``).

What this module guarantees and what it does not (0.2 Produktschutz, PÜ03):

* Values are taken from the XML as they are; nothing is computed except the deterministic
  check net + tax = gross, which becomes a finding, never a corrected value.
* Formal readability is no statement on the substance of the invoice (D41): the draft still
  runs through the ordinary review steps PÜ01 to PÜ03 in `mhvp.accounting.invoices`.
* The IBAN from the payment block is exposed only masked (same rule as the AI path, 0.1.6);
  the raw value is returned to `extraction.prepare` for the encrypted candidate list only.
* Hybrid invoices: `text_conflicts` compares the XML values against the PDF text layer;
  `ai_conflicts` compares them against the AI extraction of the PDF text. Both produce visible
  conflicts (D42) instead of a silent choice.

Parsing uses `defusedxml` (no entity expansion, no external DTD) on files that are limited by
the upload size (A-016). Schematron or XSD validation against the XRechnung rules is not done
here; the file is read, not certified.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree.ElementTree import Element  # parsing goes through defusedxml

from defusedxml import ElementTree as SafeElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mhvp.accounting.xrechnung import NS_CAC, NS_CBC, NS_INVOICE
from mhvp.receipts.masking import iban_checksum_ok, normalize_iban

log = logging.getLogger(__name__)

# Namespaces of the two syntaxes admitted for XRechnung (EN 16931 CIUS). The UBL namespaces
# are shared with the outgoing side (`mhvp.accounting.xrechnung`), not duplicated.
UBL_INVOICE = NS_INVOICE
UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
UBL_CBC = NS_CBC
UBL_CAC = NS_CAC
CII_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
CII_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
CII_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"

# Embedded XML attachment names of ZUGFeRD 1.0, ZUGFeRD 2.x / Factur-X and the XRechnung
# hybrid profile.
ATTACHMENT_NAMES: tuple[str, ...] = (
    "factur-x.xml",
    "zugferd-invoice.xml",
    "ZUGFeRD-invoice.xml",
    "xrechnung.xml",
)
XML_MIME_TYPES = frozenset({"application/xml", "text/xml"})
MAX_XML_BYTES = 20_000_000
# XRechnung convention for cash discounts inside the payment terms note:
# ``#SKONTO#TAGE=14#PROZENT=2.00#`` (optionally ``#BASISBETRAG=...#``).
_SKONTO = re.compile(r"#SKONTO#TAGE=(\d+)#PROZENT=([0-9]+(?:\.[0-9]+)?)#", re.IGNORECASE)
_WS = re.compile(r"\s+")


class EInvoiceError(ValueError):
    """The file is an XML or PDF, but not a readable e-invoice (reason in ``str(exc)``)."""


@dataclass
class EInvoiceLine:
    position: str | None
    description: str | None
    quantity: str | None
    unit: str | None
    net: str | None
    vat_percent: str | None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EInvoicePayment:
    means_code: str | None = None
    payee_name: str | None = None
    iban: str | None = None  # raw, never exposed; see `masked_view`
    reference: str | None = None
    terms: str | None = None

    def masked_view(self) -> dict[str, Any]:
        """What leaves the API: everything except the IBAN, which is masked (0.1.6)."""
        iban = normalize_iban(self.iban) if self.iban else None
        return {
            "means_code": self.means_code,
            "payee_name": self.payee_name,
            "reference": self.reference,
            "terms": self.terms,
            "iban_masked": f"{iban[:4]} ... {iban[-4:]}" if iban and len(iban) > 8 else None,
            "iban_checksum_ok": iban_checksum_ok(iban) if iban else None,
        }


@dataclass
class EInvoice:
    format: str  # xrechnung (plain XML) or zugferd (embedded in a PDF)
    syntax: str  # ubl or cii
    customization_id: str | None = None
    profile_id: str | None = None
    attachment_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    seller_name: str | None = None
    buyer_name: str | None = None
    buyer_reference: str | None = None
    order_reference: str | None = None
    net: Decimal | None = None
    vat: Decimal | None = None
    gross: Decimal | None = None
    payable: Decimal | None = None
    currency: str | None = None
    service_from: date | None = None
    service_to: date | None = None
    discount_percent: Decimal | None = None
    discount_days: int | None = None
    notes: list[str] = field(default_factory=list)
    lines: list[EInvoiceLine] = field(default_factory=list)
    payment: EInvoicePayment = field(default_factory=EInvoicePayment)


@dataclass
class EInvoiceReadResult:
    einvoice: EInvoice | None
    findings: list[str]


# Reading -------------------------------------------------------------------------------


def _text(node: Element | None, path: str, ns: dict[str, str]) -> str | None:
    if node is None:
        return None
    found = node.find(path, ns)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _attr(node: Element | None, path: str, ns: dict[str, str], name: str) -> str | None:
    if node is None:
        return None
    found = node.find(path, ns)
    return found.get(name) if found is not None else None


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, ValueError):
        return None


def _iso(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _cii_date(raw: str | None) -> date | None:
    """``udt:DateTimeString`` with format 102 (``JJJJMMTT``); ISO is accepted as well."""
    if not raw:
        return None
    raw = raw.strip()
    if re.fullmatch(r"\d{8}", raw):
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None
    return _iso(raw)


def _parse_ubl(root: Element, fmt: str) -> EInvoice:
    ns = {"cbc": UBL_CBC, "cac": UBL_CAC}
    inv = EInvoice(format=fmt, syntax="ubl")
    inv.customization_id = _text(root, "cbc:CustomizationID", ns)
    inv.profile_id = _text(root, "cbc:ProfileID", ns)
    inv.invoice_number = _text(root, "cbc:ID", ns)
    inv.invoice_date = _iso(_text(root, "cbc:IssueDate", ns))
    inv.due_date = _iso(_text(root, "cbc:DueDate", ns))
    inv.currency = _text(root, "cbc:DocumentCurrencyCode", ns)
    inv.buyer_reference = _text(root, "cbc:BuyerReference", ns)
    inv.order_reference = _text(root, "cac:OrderReference/cbc:ID", ns)
    inv.notes = [n.text.strip() for n in root.findall("cbc:Note", ns) if n.text and n.text.strip()]
    period = root.find("cac:InvoicePeriod", ns)
    inv.service_from = _iso(_text(period, "cbc:StartDate", ns))
    inv.service_to = _iso(_text(period, "cbc:EndDate", ns))
    for role, attr in (("Supplier", "seller_name"), ("Customer", "buyer_name")):
        party = root.find(f"cac:Accounting{role}Party/cac:Party", ns)
        name = _text(party, "cac:PartyLegalEntity/cbc:RegistrationName", ns) or _text(
            party, "cac:PartyName/cbc:Name", ns
        )
        setattr(inv, attr, name)
    totals = root.find("cac:LegalMonetaryTotal", ns)
    inv.net = _decimal(_text(totals, "cbc:TaxExclusiveAmount", ns))
    inv.gross = _decimal(_text(totals, "cbc:TaxInclusiveAmount", ns))
    inv.payable = _decimal(_text(totals, "cbc:PayableAmount", ns))
    tax_amounts = [
        _decimal(t.text) for t in root.findall("cac:TaxTotal/cbc:TaxAmount", ns) if t.text
    ]
    if tax_amounts and all(t is not None for t in tax_amounts):
        inv.vat = sum((t for t in tax_amounts if t is not None), Decimal("0"))
    means = root.find("cac:PaymentMeans", ns)
    inv.payment = EInvoicePayment(
        means_code=_text(means, "cbc:PaymentMeansCode", ns),
        payee_name=_text(root, "cac:PayeeParty/cac:PartyName/cbc:Name", ns),
        iban=_text(means, "cac:PayeeFinancialAccount/cbc:ID", ns),
        reference=_text(means, "cbc:PaymentID", ns),
        terms=_text(root, "cac:PaymentTerms/cbc:Note", ns),
    )
    for line in root.findall("cac:InvoiceLine", ns):
        inv.lines.append(
            EInvoiceLine(
                position=_text(line, "cbc:ID", ns),
                description=_text(line, "cac:Item/cbc:Name", ns),
                quantity=_text(line, "cbc:InvoicedQuantity", ns),
                unit=_attr(line, "cbc:InvoicedQuantity", ns, "unitCode"),
                net=_text(line, "cbc:LineExtensionAmount", ns),
                vat_percent=_text(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", ns),
            )
        )
    return inv


def _parse_cii(root: Element, fmt: str) -> EInvoice:
    ns = {"rsm": CII_RSM, "ram": CII_RAM, "udt": CII_UDT}
    inv = EInvoice(format=fmt, syntax="cii")
    inv.customization_id = _text(
        root,
        "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
        ns,
    )
    inv.profile_id = _text(
        root,
        "rsm:ExchangedDocumentContext/ram:BusinessProcessSpecifiedDocumentContextParameter/ram:ID",
        ns,
    )
    document = root.find("rsm:ExchangedDocument", ns)
    inv.invoice_number = _text(document, "ram:ID", ns)
    inv.invoice_date = _cii_date(_text(document, "ram:IssueDateTime/udt:DateTimeString", ns))
    inv.notes = [
        n.text.strip()
        for n in (
            document.findall("ram:IncludedNote/ram:Content", ns) if document is not None else []
        )
        if n.text and n.text.strip()
    ]
    transaction = root.find("rsm:SupplyChainTradeTransaction", ns)
    agreement = (
        transaction.find("ram:ApplicableHeaderTradeAgreement", ns)
        if transaction is not None
        else None
    )
    inv.seller_name = _text(agreement, "ram:SellerTradeParty/ram:Name", ns)
    inv.buyer_name = _text(agreement, "ram:BuyerTradeParty/ram:Name", ns)
    inv.buyer_reference = _text(agreement, "ram:BuyerReference", ns)
    inv.order_reference = _text(
        agreement, "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID", ns
    )
    settlement = (
        transaction.find("ram:ApplicableHeaderTradeSettlement", ns)
        if transaction is not None
        else None
    )
    inv.currency = _text(settlement, "ram:InvoiceCurrencyCode", ns)
    summation = (
        settlement.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", ns)
        if settlement is not None
        else None
    )
    inv.net = _decimal(_text(summation, "ram:TaxBasisTotalAmount", ns))
    inv.vat = _decimal(_text(summation, "ram:TaxTotalAmount", ns))
    inv.gross = _decimal(_text(summation, "ram:GrandTotalAmount", ns))
    inv.payable = _decimal(_text(summation, "ram:DuePayableAmount", ns))
    period = settlement.find("ram:BillingSpecifiedPeriod", ns) if settlement is not None else None
    inv.service_from = _cii_date(_text(period, "ram:StartDateTime/udt:DateTimeString", ns))
    inv.service_to = _cii_date(_text(period, "ram:EndDateTime/udt:DateTimeString", ns))
    terms = (
        settlement.find("ram:SpecifiedTradePaymentTerms", ns) if settlement is not None else None
    )
    inv.due_date = _cii_date(_text(terms, "ram:DueDateDateTime/udt:DateTimeString", ns))
    means = (
        settlement.find("ram:SpecifiedTradeSettlementPaymentMeans", ns)
        if settlement is not None
        else None
    )
    inv.payment = EInvoicePayment(
        means_code=_text(means, "ram:TypeCode", ns),
        payee_name=_text(settlement, "ram:PayeeTradeParty/ram:Name", ns),
        iban=_text(means, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID", ns),
        reference=_text(settlement, "ram:PaymentReference", ns),
        terms=_text(terms, "ram:Description", ns),
    )
    for item in (
        transaction.findall("ram:IncludedSupplyChainTradeLineItem", ns)
        if transaction is not None
        else []
    ):
        inv.lines.append(
            EInvoiceLine(
                position=_text(item, "ram:AssociatedDocumentLineDocument/ram:LineID", ns),
                description=_text(item, "ram:SpecifiedTradeProduct/ram:Name", ns),
                quantity=_text(item, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", ns),
                unit=_attr(
                    item, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", ns, "unitCode"
                ),
                net=_text(
                    item,
                    "ram:SpecifiedLineTradeSettlement/"
                    "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                    ns,
                ),
                vat_percent=_text(
                    item,
                    "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/"
                    "ram:RateApplicablePercent",
                    ns,
                ),
            )
        )
    return inv


def _apply_terms(inv: EInvoice) -> None:
    """Cash discount from the XRechnung payment terms convention; the deadline stays empty
    (the reference date, invoice or receipt, is a review decision), the days are noted."""
    if not inv.payment.terms:
        return
    match = _SKONTO.search(inv.payment.terms)
    if match:
        inv.discount_days = int(match.group(1))
        inv.discount_percent = _decimal(match.group(2))


def parse_xml(data: bytes, *, fmt: str = "xrechnung") -> EInvoice:
    """Parses one XML document. Raises `EInvoiceError` when it is not a supported invoice."""
    if len(data) > MAX_XML_BYTES:
        raise EInvoiceError("XML-Teil überschreitet die zulässige Größe.")
    try:
        root = SafeElementTree.fromstring(data)
    except (SafeElementTree.ParseError, DefusedXmlException, ValueError) as exc:
        raise EInvoiceError(f"XML nicht lesbar ({type(exc).__name__}).") from None
    tag = root.tag
    if tag == f"{{{UBL_INVOICE}}}Invoice":
        inv = _parse_ubl(root, fmt)
    elif tag == f"{{{CII_RSM}}}CrossIndustryInvoice":
        inv = _parse_cii(root, fmt)
    elif tag == f"{{{UBL_CREDIT_NOTE}}}CreditNote":
        raise EInvoiceError("UBL-Gutschrift (CreditNote) wird im Belegeingang nicht gelesen.")
    else:
        raise EInvoiceError("XML ist keine XRechnung (weder UBL Invoice noch CII).")
    _apply_terms(inv)
    return inv


def embedded_xml(pdf: bytes) -> tuple[str, bytes] | None:
    """The first embedded file whose name is one of `ATTACHMENT_NAMES` (case sensitive names
    first, then a case insensitive match), or None for a plain PDF."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        attachments = reader.attachments
        names = list(attachments.keys())
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        log.warning("einvoice_pdf_attachments_failed", extra={"error": type(exc).__name__})
        return None
    wanted = {n.lower(): n for n in ATTACHMENT_NAMES}
    for name in names:
        if name in ATTACHMENT_NAMES or name.lower() in wanted:
            parts = attachments[name]
            if parts:
                return name, bytes(parts[0])
    return None


def read(mime_type: str, data: bytes) -> EInvoiceReadResult:
    """Detects and reads the structured part. Plain PDFs and non invoice XML give no e-invoice;
    unreadable candidates give a finding (PÜ01: the structured part is a required part of an
    e-invoice, its failure must be visible)."""
    findings: list[str] = []
    try:
        if mime_type in XML_MIME_TYPES:
            return EInvoiceReadResult(parse_xml(data, fmt="xrechnung"), findings)
        if mime_type == "application/pdf":
            found = embedded_xml(data)
            if found is None:
                return EInvoiceReadResult(None, findings)
            name, xml = found
            inv = parse_xml(xml, fmt="zugferd")
            inv.attachment_name = name
            return EInvoiceReadResult(inv, findings)
    except EInvoiceError as exc:
        findings.append(f"E-Rechnung: strukturierter Teil nicht lesbar: {exc}")
    return EInvoiceReadResult(None, findings)


# Draft fields and checks -----------------------------------------------------------------


def _iso_out(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _xml_field(value: Any, note: str, *, confidence: float = 1.0) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": confidence if value is not None else 0.0,
        "source": "xml" if value is not None else "none",
        "note": note if value is not None else None,
    }


def draft_fields(inv: EInvoice) -> dict[str, dict[str, Any]]:
    """Per-field proposal with source ``xml``. The confidence 1.0 says only that the value
    was read from the structured part, not that it is correct (D41)."""
    label = "XRechnung" if inv.format == "xrechnung" else "ZUGFeRD/Factur-X"
    note = f"Aus dem strukturierten Teil ({label}, {inv.syntax.upper()})"
    fields = {
        "supplier_name": _xml_field(inv.seller_name, note),
        "recipient_name": _xml_field(inv.buyer_name, note),
        "invoice_number": _xml_field(inv.invoice_number, note),
        "invoice_date": _xml_field(_iso_out(inv.invoice_date), note),
        "due_date": _xml_field(_iso_out(inv.due_date), note),
        "net": _xml_field(_money(inv.net), note),
        "vat": _xml_field(_money(inv.vat), note),
        "gross": _xml_field(_money(inv.gross), note),
        "currency": _xml_field(inv.currency, note),
        "discount_percent": _xml_field(
            _money(inv.discount_percent),
            f"{note}; Skonto laut Zahlungsbedingung, {inv.discount_days} Tage",
        ),
        "discount_until": _xml_field(
            None,
            note,
        ),
        "order_reference": _xml_field(inv.order_reference or inv.buyer_reference, note),
    }
    if inv.discount_days is not None:
        fields["discount_until"]["note"] = (
            f"Frist nicht als Datum im XML; Zahlungsbedingung nennt {inv.discount_days} Tage."
        )
    if inv.payable is not None and inv.gross is not None and inv.payable != inv.gross:
        fields["gross"]["note"] = (
            f"{note}; Zahlbetrag laut XML {inv.payable} (Vorauszahlung oder Abzug ausgewiesen)"
        )
    return fields


def formal_findings(inv: EInvoice) -> list[str]:
    """PÜ01 completeness of the structured part and the one arithmetic check. Only hints."""
    out: list[str] = []
    missing = [
        label
        for label, value in (
            ("Rechnungsnummer", inv.invoice_number),
            ("Rechnungsdatum", inv.invoice_date),
            ("Rechnungsaussteller", inv.seller_name),
            ("Rechnungsempfänger", inv.buyer_name),
            ("Bruttobetrag", inv.gross),
            ("Währung", inv.currency),
        )
        if value is None
    ]
    if missing:
        out.append(f"E-Rechnung: Pflichtangabe fehlt im XML: {', '.join(missing)}")
    if (
        inv.net is not None
        and inv.vat is not None
        and inv.gross is not None
        and inv.net + inv.vat != inv.gross
    ):
        out.append(
            "E-Rechnung: Netto plus Steuer ergibt im XML nicht den Bruttobetrag "
            f"({inv.net} + {inv.vat} gegenüber {inv.gross})"
        )
    if inv.lines:
        total = Decimal("0")
        complete = True
        for line in inv.lines:
            amount = _decimal(line.net)
            if amount is None:
                complete = False
                break
            total += amount
        if complete and inv.net is not None and total != inv.net:
            out.append(
                f"E-Rechnung: Summe der Positionen ({total}) weicht vom Nettobetrag ({inv.net}) ab"
            )
    if inv.currency and inv.currency.upper() != "EUR":
        out.append(f"E-Rechnung: Fremdwährung {inv.currency} (nur EUR wird unterstützt)")
    return out


def _amount_variants(value: Decimal) -> list[str]:
    plain = f"{value:.2f}"
    german = plain.replace(".", ",")
    whole, _, frac = german.partition(",")
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    return [plain, german, f"{whole}{grouped},{frac}"]


def _norm(text: str) -> str:
    return _WS.sub(" ", text).casefold().strip()


def text_conflicts(inv: EInvoice, text: str | None) -> list[dict[str, Any]]:
    """Hybrid invoice (D42): the structured values must appear in the PDF text layer. A
    missing invoice number or gross amount in the text is a visible conflict, never a silent
    choice; without a text layer the comparison is reported as not possible."""
    if inv.format != "zugferd":
        return []
    if not text or not text.strip():
        return [
            {
                "field": "document",
                "xml": None,
                "other": None,
                "other_source": "pdf_text",
                "note": (
                    "PDF ohne Textebene: Vergleich XML gegen PDF nicht möglich, am Original prüfen."
                ),
            }
        ]
    normal = _norm(text)
    compact = normal.replace(" ", "")
    out: list[dict[str, Any]] = []
    if inv.invoice_number and _norm(inv.invoice_number).replace(" ", "") not in compact:
        out.append(
            {
                "field": "invoice_number",
                "xml": inv.invoice_number,
                "other": None,
                "other_source": "pdf_text",
                "note": "Rechnungsnummer aus dem XML kommt im PDF-Text nicht vor.",
            }
        )
    if inv.gross is not None and not any(
        re.search(rf"(?<![\d.,]){re.escape(v)}(?!\d)", normal) for v in _amount_variants(inv.gross)
    ):
        out.append(
            {
                "field": "gross",
                "xml": str(inv.gross),
                "other": None,
                "other_source": "pdf_text",
                "note": "Bruttobetrag aus dem XML kommt im PDF-Text nicht vor.",
            }
        )
    return out


_COMPARED = ("invoice_number", "invoice_date", "due_date", "net", "vat", "gross", "currency")


def ai_conflicts(
    xml_fields: dict[str, dict[str, Any]], ai_fields: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """XML value against the AI reading of the PDF text (both present, different)."""
    out: list[dict[str, Any]] = []
    for name in _COMPARED:
        xml_value = (xml_fields.get(name) or {}).get("value")
        ai_value = (ai_fields.get(name) or {}).get("value")
        if xml_value is None or ai_value is None:
            continue
        if name in ("net", "vat", "gross"):
            same = _decimal(str(xml_value)) == _decimal(str(ai_value))
        else:
            same = _norm(str(xml_value)) == _norm(str(ai_value))
        if not same:
            out.append(
                {
                    "field": name,
                    "xml": str(xml_value),
                    "other": str(ai_value),
                    "other_source": "ai",
                    "note": "XML und PDF-Text (KI-Lesung) nennen unterschiedliche Werte.",
                }
            )
    xml_supplier = (xml_fields.get("supplier_name") or {}).get("value")
    ai_supplier = (ai_fields.get("supplier_name") or {}).get("value")
    if xml_supplier and ai_supplier:
        a, b = _norm(str(xml_supplier)), _norm(str(ai_supplier))
        if a not in b and b not in a:
            out.append(
                {
                    "field": "supplier_name",
                    "xml": str(xml_supplier),
                    "other": str(ai_supplier),
                    "other_source": "ai",
                    "note": "Aussteller laut XML und laut PDF-Text weichen ab.",
                }
            )
    return out


def property_hint(inv: EInvoice) -> str | None:
    """Raw text for the local property match: buyer reference, order reference, notes and
    line texts; never a property assignment by itself."""
    parts = [inv.buyer_reference, inv.order_reference, *inv.notes]
    parts.extend(line.description for line in inv.lines)
    text = " | ".join(p for p in parts if p)
    return text or None
