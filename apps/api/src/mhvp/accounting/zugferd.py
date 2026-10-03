"""ZUGFeRD / Factur-X hybrid for issued Verwalterhonorar invoices (13.5 E-Rechnung, S13-03).

What is generated: the readable invoice document on the tenant letterhead (the same letter as
``POST /accounting/admin-fee-invoices/{id}/document``) with the structured invoice embedded as
``factur-x.xml``: UN/CEFACT CII (D16B) in the profile EN 16931 (guideline
``urn:cen.eu:en16931:2017``). Both parts are built from the same frozen invoice data and the
same locks as the XRechnung (``xrechnung.load``), so PDF, CII and UBL never differ.

PDF/A-3 marking (done with pypdf, no further library):

* the XML as associated file: file specification with ``F``/``UF``/``Desc`` and
  ``AFRelationship /Alternative``, embedded file stream with ``Subtype text/xml`` and ``Params``
  (``ModDate``, ``Size``, ``CheckSum``), referenced from the catalog ``/AF`` array;
* XMP metadata (uncompressed): ``pdfaid:part 3`` / ``pdfaid:conformance B``, the Factur-X
  extension schema and ``fx:DocumentType``, ``fx:DocumentFileName``, ``fx:Version``,
  ``fx:ConformanceLevel``; ``dc``/``xmp``/``pdf`` values identical to the Info dictionary;
* an output intent ``GTS_PDFA1`` with the sRGB profile of LittleCMS (via Pillow);
* a file identifier in the trailer and the header ``%PDF-1.7``.

What is NOT claimed: conformance with ISO 19005-3. The own pre-check (``pdfa_precheck``) lists
the blockers it can see (for example fonts that are not embedded: the letterhead renderer of
``mhvp.documents.letters`` uses the non embedded standard fonts) and the points it cannot check
at all. The reference is veraPDF; it is not bundled (docs/OPEN_QUESTIONS.md AE25-01). Nothing
is sent to a recipient and nothing is posted.
"""

from __future__ import annotations

import hashlib
import html
import io
import uuid
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Request, Response
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
    PdfObject,
    StreamObject,
    TextStringObject,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import xrechnung as xr
from mhvp.accounting.models import AdminFeeInvoice, AdminFeeInvoiceStatus, Invoice
from mhvp.accounting.response_models import AccountingEInvoiceCheckOut, AccountingZugferdStoredOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.pdf_fonts import FALLBACK_HINT

# CII ----------------------------------------------------------------------------------------

NS_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
NS_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"
NS_QDT = "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
CII_NS = {"rsm": NS_RSM, "ram": NS_RAM, "udt": NS_UDT, "qdt": NS_QDT}
# BT-24 of the Factur-X / ZUGFeRD profile EN 16931 (the CEN core without extension).
GUIDELINE_EN16931 = "urn:cen.eu:en16931:2017"
CREDIT_NOTE_TYPE_CODE = "381"
DATE_FORMAT_102 = "102"  # CCYYMMDD (UNTDID 2379)

# Factur-X container ---------------------------------------------------------------------

ATTACHMENT_NAME = "factur-x.xml"
CONFORMANCE_LEVEL = "EN 16931"
FX_VERSION = "1.0"
FX_DOCUMENT_TYPE = "INVOICE"
FX_NAMESPACE = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
AF_RELATIONSHIP = "/Alternative"
PDF_HEADER = "%PDF-1.7"
PRODUCER = "MH Verwaltungsplattform (pypdf)"
CREATOR = "MH Verwaltungsplattform"
OUTPUT_CONDITION = "sRGB"

PRECHECK_NAME = "mhvp-pdfa-precheck"
PRECHECK_VERSION = "1.0"
# What the own pre-check cannot decide; only a PDF/A validator (veraPDF) can.
NOT_CHECKED: tuple[str, ...] = (
    "Farbräume der Inhalte und Bilder gegen die Ausgabebedingung",
    "Zulässigkeit der ICC-Profilversion (LittleCMS sRGB, ICC 4.4)",
    "Schriftprogramme (Glyphenbreiten, Zeichenkodierung, CIDSet)",
    "Dateisyntax nach ISO 19005-3 Abschnitt 6.1",
    "XMP gegen die Regeln für Erweiterungsschemata",
    "Transparenz und Überblendmodi",
)


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    prefix, name = tag.split(":")
    element = ET.SubElement(parent, f"{{{CII_NS[prefix]}}}{name}", attrs)
    if text is not None:
        element.text = text
    return element


def _amount(value: Decimal) -> str:
    return str(value.quantize(xr.CENT, rounding=ROUND_HALF_UP))


def _date(parent: ET.Element, tag: str, value: date, *, qualified: bool = False) -> None:
    holder = _sub(parent, tag)
    _sub(
        holder,
        "qdt:DateTimeString" if qualified else "udt:DateTimeString",
        value.strftime("%Y%m%d"),
        format=DATE_FORMAT_102,
    )


def _postal(parent: ET.Element, address: xr.Address) -> None:
    node = _sub(parent, "ram:PostalTradeAddress")
    _sub(node, "ram:PostcodeCode", address.postal_code)  # BT-38 / BT-53
    _sub(node, "ram:LineOne", address.street)  # BT-35 / BT-50
    _sub(node, "ram:CityName", address.city)  # BT-37 / BT-52
    _sub(node, "ram:CountryID", address.country)  # BT-40 / BT-55


def positive(data: xr.InvoiceData) -> xr.InvoiceData:
    """A credit note states its amounts positive; the type code 381 expresses the correction."""
    lines = [replace(ln, amount=abs(ln.amount), unit_price=abs(ln.unit_price)) for ln in data.lines]
    return replace(data, lines=lines, net=abs(data.net), vat=abs(data.vat), gross=abs(data.gross))


def build_cii(
    data: xr.InvoiceData,
    *,
    period: tuple[date, date] | None = None,
    corrects: tuple[str, date] | None = None,
) -> bytes:
    """CII ``CrossIndustryInvoice`` in the profile EN 16931; element order follows the D16B
    schema. ``corrects`` (number, date of the original) makes it a credit note 381 with BG-3."""
    for prefix, uri in CII_NS.items():
        ET.register_namespace(prefix, uri)
    if corrects is not None:
        data = positive(data)
    cur = data.currency
    root = ET.Element(f"{{{NS_RSM}}}CrossIndustryInvoice")
    context = _sub(root, "rsm:ExchangedDocumentContext")
    _sub(
        _sub(context, "ram:BusinessProcessSpecifiedDocumentContextParameter"),
        "ram:ID",
        xr.PROFILE_ID,
    )
    _sub(
        _sub(context, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", GUIDELINE_EN16931
    )

    document = _sub(root, "rsm:ExchangedDocument")
    _sub(document, "ram:ID", data.number)  # BT-1
    _sub(
        document,
        "ram:TypeCode",
        CREDIT_NOTE_TYPE_CODE if corrects is not None else xr.INVOICE_TYPE_CODE,
    )  # BT-3
    _date(document, "ram:IssueDateTime", data.issue_date)  # BT-2
    for note in data.notes:
        _sub(_sub(document, "ram:IncludedNote"), "ram:Content", note)  # BT-22

    transaction = _sub(root, "rsm:SupplyChainTradeTransaction")
    for index, ln in enumerate(data.lines, start=1):
        item = _sub(transaction, "ram:IncludedSupplyChainTradeLineItem")
        _sub(_sub(item, "ram:AssociatedDocumentLineDocument"), "ram:LineID", str(index))  # BT-126
        _sub(_sub(item, "ram:SpecifiedTradeProduct"), "ram:Name", ln.text)  # BT-153
        price = _sub(_sub(item, "ram:SpecifiedLineTradeAgreement"), "ram:NetPriceProductTradePrice")
        _sub(price, "ram:ChargeAmount", _amount(ln.unit_price))  # BT-146
        _sub(
            _sub(item, "ram:SpecifiedLineTradeDelivery"),
            "ram:BilledQuantity",
            format(ln.quantity, "f"),
            unitCode=xr.UNIT_CODE,
        )  # BT-129, BT-130
        settlement = _sub(item, "ram:SpecifiedLineTradeSettlement")
        tax = _sub(settlement, "ram:ApplicableTradeTax")
        _sub(tax, "ram:TypeCode", "VAT")
        _sub(tax, "ram:CategoryCode", data.tax_category)  # BT-151
        _sub(tax, "ram:RateApplicablePercent", xr._pct(data.vat_percent))  # BT-152
        _sub(
            _sub(settlement, "ram:SpecifiedTradeSettlementLineMonetarySummation"),
            "ram:LineTotalAmount",
            _amount(ln.amount),
        )  # BT-131

    agreement = _sub(transaction, "ram:ApplicableHeaderTradeAgreement")
    _sub(agreement, "ram:BuyerReference", data.buyer_reference)  # BT-10
    seller = _sub(agreement, "ram:SellerTradeParty")
    _sub(seller, "ram:Name", data.seller.name)  # BT-27
    if data.seller.register_number:
        _sub(_sub(seller, "ram:SpecifiedLegalOrganization"), "ram:ID", data.seller.register_number)
    if data.seller.contact_name or data.seller.phone or data.seller.email:  # BG-6
        contact = _sub(seller, "ram:DefinedTradeContact")
        if data.seller.contact_name:
            _sub(contact, "ram:PersonName", data.seller.contact_name)  # BT-41
        if data.seller.phone:
            _sub(
                _sub(contact, "ram:TelephoneUniversalCommunication"),
                "ram:CompleteNumber",
                data.seller.phone,
            )  # BT-42
        if data.seller.email:
            _sub(
                _sub(contact, "ram:EmailURIUniversalCommunication"), "ram:URIID", data.seller.email
            )  # BT-43
    _postal(seller, data.seller.address)  # BG-5
    if data.seller.email:
        _sub(
            _sub(seller, "ram:URIUniversalCommunication"),
            "ram:URIID",
            data.seller.email,
            schemeID="EM",
        )  # BT-34
    if data.seller.vat_id:
        _sub(
            _sub(seller, "ram:SpecifiedTaxRegistration"),
            "ram:ID",
            data.seller.vat_id,
            schemeID="VA",
        )
    if data.seller.tax_number:
        _sub(
            _sub(seller, "ram:SpecifiedTaxRegistration"),
            "ram:ID",
            data.seller.tax_number,
            schemeID="FC",
        )
    buyer = _sub(agreement, "ram:BuyerTradeParty")
    _sub(buyer, "ram:Name", data.buyer.name)  # BT-44
    _postal(buyer, data.buyer.address)  # BG-8
    endpoint = _sub(buyer, "ram:URIUniversalCommunication")
    if data.buyer.email:
        _sub(endpoint, "ram:URIID", data.buyer.email, schemeID="EM")  # BT-49
    else:
        _sub(endpoint, "ram:URIID", data.buyer_reference, schemeID=xr.EAS_LEITWEG_ID)

    _sub(transaction, "ram:ApplicableHeaderTradeDelivery")

    settlement = _sub(transaction, "ram:ApplicableHeaderTradeSettlement")
    _sub(settlement, "ram:PaymentReference", data.number)  # BT-83
    _sub(settlement, "ram:InvoiceCurrencyCode", cur)  # BT-5
    means = _sub(settlement, "ram:SpecifiedTradeSettlementPaymentMeans")  # BG-16
    _sub(means, "ram:TypeCode", xr.PAYMENT_MEANS_SEPA_CREDIT_TRANSFER)
    if data.seller.payee_iban:
        _sub(
            _sub(means, "ram:PayeePartyCreditorFinancialAccount"),
            "ram:IBANID",
            data.seller.payee_iban,
        )  # BT-84
    header_tax = _sub(settlement, "ram:ApplicableTradeTax")  # BG-23
    _sub(header_tax, "ram:CalculatedAmount", _amount(data.vat))  # BT-117
    _sub(header_tax, "ram:TypeCode", "VAT")
    if data.tax_exemption_reason:
        _sub(header_tax, "ram:ExemptionReason", data.tax_exemption_reason)  # BT-120
    _sub(header_tax, "ram:BasisAmount", _amount(data.net))  # BT-116
    _sub(header_tax, "ram:CategoryCode", data.tax_category)  # BT-118
    _sub(header_tax, "ram:RateApplicablePercent", xr._pct(data.vat_percent))  # BT-119
    if period is not None:  # BG-14 service period, as printed on the letter
        billing = _sub(settlement, "ram:BillingSpecifiedPeriod")
        _date(billing, "ram:StartDateTime", period[0])  # BT-73
        _date(billing, "ram:EndDateTime", period[1])  # BT-74
    _sub(
        _sub(settlement, "ram:SpecifiedTradePaymentTerms"), "ram:Description", xr.PAYMENT_TERMS_NOTE
    )
    totals = _sub(settlement, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    line_sum = sum((ln.amount for ln in data.lines), Decimal("0.00"))
    _sub(totals, "ram:LineTotalAmount", _amount(line_sum))  # BT-106
    _sub(totals, "ram:TaxBasisTotalAmount", _amount(data.net))  # BT-109
    _sub(totals, "ram:TaxTotalAmount", _amount(data.vat), currencyID=cur)  # BT-110
    _sub(totals, "ram:GrandTotalAmount", _amount(data.gross))  # BT-112
    _sub(totals, "ram:DuePayableAmount", _amount(data.gross))  # BT-115
    if corrects is not None:  # BG-3 preceding invoice
        ref = _sub(settlement, "ram:InvoiceReferencedDocument")
        _sub(ref, "ram:IssuerAssignedID", corrects[0])  # BT-25
        _date(ref, "ram:FormattedIssueDateTime", corrects[1], qualified=True)  # BT-26
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _find(node: ET.Element | None, path: str) -> str | None:
    found = node.find(path, CII_NS) if node is not None else None
    return found.text.strip() if found is not None and found.text else None


def _dec(text: str | None) -> Decimal | None:
    try:
        return Decimal(text) if text is not None else None
    except ArithmeticError:
        return None


def check_cii(xml: bytes, data: xr.InvoiceData, *, credit_note: bool = False) -> list[xr.Finding]:
    """Own structural check: the CII is read back with the Belegeingang reader
    (``mhvp.receipts.einvoice``) and compared with the frozen invoice data, plus the EN 16931
    arithmetic rules this invoice type uses. Not the official validation (KoSIT, P05)."""
    from mhvp.receipts import einvoice

    expected = positive(data) if credit_note else data
    try:
        inv = einvoice.parse_xml(xml, fmt="zugferd")
    except einvoice.EInvoiceError as exc:
        return [xr.Finding("XML", str(exc))]
    findings: list[xr.Finding] = []
    if inv.syntax != "cii":
        findings.append(xr.Finding("CII", "Wurzelelement ist keine CrossIndustryInvoice."))
        return findings
    if inv.customization_id != GUIDELINE_EN16931:
        findings.append(xr.Finding("BT-24", "Spezifikationskennung ist nicht EN 16931."))
    root = SafeET.fromstring(xml)
    type_code = _find(root, "rsm:ExchangedDocument/ram:TypeCode")
    wanted_type = CREDIT_NOTE_TYPE_CODE if credit_note else xr.INVOICE_TYPE_CODE
    if type_code != wanted_type:
        findings.append(xr.Finding("BT-3", f"Rechnungstyp {type_code} statt {wanted_type}."))
    compared: list[tuple[str, str, Any, Any]] = [
        ("BT-1", "Rechnungsnummer", inv.invoice_number, expected.number),
        ("BT-2", "Rechnungsdatum", inv.invoice_date, expected.issue_date),
        ("BT-5", "Währung", inv.currency, expected.currency),
        ("BT-10", "Leitweg-ID (BuyerReference)", inv.buyer_reference, expected.buyer_reference),
        ("BT-27", "Verkäufername", inv.seller_name, expected.seller.name),
        ("BT-44", "Käufername", inv.buyer_name, expected.buyer.name),
        ("BT-109", "Nettobetrag", inv.net, expected.net),
        ("BT-110", "Steuersumme", inv.vat, expected.vat),
        ("BT-112", "Bruttobetrag", inv.gross, expected.gross),
        ("BT-115", "Zahlbetrag", inv.payable, expected.gross),
        ("BT-84", "IBAN", inv.payment.iban, expected.seller.payee_iban),
    ]
    for code, label, found, want in compared:
        if found != want:
            findings.append(xr.Finding(code, f"{label} im XML weicht von der Rechnung ab."))
    if len(inv.lines) != len(expected.lines):
        findings.append(xr.Finding("BG-25", "Anzahl der Positionen weicht ab."))
    else:
        for index, (line, want_line) in enumerate(zip(inv.lines, expected.lines, strict=True), 1):
            amount = _dec(line.net)
            if amount != want_line.amount:
                findings.append(xr.Finding("BT-131", f"Position {index}: Betrag weicht ab."))
            if line.description != want_line.text:
                findings.append(xr.Finding("BT-153", f"Position {index}: Bezeichnung weicht ab."))
    for message in einvoice.formal_findings(inv):
        findings.append(xr.Finding("EN16931", message))
    for party, label in (("SellerTradeParty", "Verkäufer"), ("BuyerTradeParty", "Käufer")):
        base = f"rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/ram:{party}"
        for field, name in (
            ("ram:PostcodeCode", "PLZ"),
            ("ram:CityName", "Ort"),
            ("ram:CountryID", "Land"),
        ):
            if not _find(root, f"{base}/ram:PostalTradeAddress/{field}"):
                findings.append(
                    xr.Finding("BG-5" if party[0] == "S" else "BG-8", f"{label} {name} fehlt.")
                )
    settlement = root.find(
        "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement", CII_NS
    )
    if not _find(settlement, "ram:SpecifiedTradePaymentTerms/ram:Description") and not _find(
        settlement, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString"
    ):
        findings.append(xr.Finding("BR-CO-25", "Weder Fälligkeit (BT-9) noch Zahlungsbedingung."))
    tax_sum = Decimal("0.00")
    for tax in (
        settlement.findall("ram:ApplicableTradeTax", CII_NS) if settlement is not None else []
    ):
        basis = _dec(_find(tax, "ram:BasisAmount"))
        amount = _dec(_find(tax, "ram:CalculatedAmount"))
        rate = _dec(_find(tax, "ram:RateApplicablePercent"))
        if basis is None or amount is None or rate is None:
            findings.append(xr.Finding("BG-23", "Steueraufschlüsselung unvollständig."))
            continue
        tax_sum += amount
        want_tax = (basis * rate / 100).quantize(xr.CENT, rounding=ROUND_HALF_UP)
        if want_tax != amount:
            findings.append(
                xr.Finding("BR-CO-17", f"Steuer {amount} statt {want_tax} bei {rate} %.")
            )
        if _find(tax, "ram:CategoryCode") == "E" and not _find(tax, "ram:ExemptionReason"):
            findings.append(xr.Finding("BR-E-10", "Steuerbefreiung ohne Begründungstext."))
    if inv.vat is not None and tax_sum != inv.vat:
        findings.append(
            xr.Finding(
                "BR-CO-14", f"Summe der Steueraufschlüsselung {tax_sum} weicht von {inv.vat} ab."
            )
        )
    if credit_note and not _find(settlement, "ram:InvoiceReferencedDocument/ram:IssuerAssignedID"):
        findings.append(xr.Finding("BT-25", "Gutschrift ohne Bezug auf die Ursprungsrechnung."))
    return findings


# PDF/A-3 marking --------------------------------------------------------------------------


def srgb_profile() -> bytes:
    """sRGB ICC profile generated by LittleCMS (Pillow); no profile file is shipped."""
    from PIL import ImageCms

    return bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())


def _pdf_date(value: datetime) -> str:
    return value.astimezone(UTC).strftime("D:%Y%m%d%H%M%S+00'00'")


def _xmp_date(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _fx_property(name: str, description: str) -> str:
    return (
        '<rdf:li rdf:parseType="Resource">'
        f"<pdfaProperty:name>{name}</pdfaProperty:name>"
        "<pdfaProperty:valueType>Text</pdfaProperty:valueType>"
        "<pdfaProperty:category>external</pdfaProperty:category>"
        f"<pdfaProperty:description>{description}</pdfaProperty:description>"
        "</rdf:li>"
    )


def xmp_packet(*, title: str, author: str, created: datetime) -> bytes:
    """XMP with the PDF/A identification, the Factur-X extension schema and the fx values."""
    esc = html.escape
    stamp = _xmp_date(created)
    properties = "".join(
        (
            _fx_property("DocumentFileName", "The name of the embedded XML document"),
            _fx_property("DocumentType", "The type of the hybrid document in capital letters"),
            _fx_property("Version", "The actual version of the standard of the embedded XML"),
            _fx_property("ConformanceLevel", "The conformance level of the embedded XML"),
        )
    )
    text = (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">'
        "<pdfaid:part>3</pdfaid:part><pdfaid:conformance>B</pdfaid:conformance>"
        "</rdf:Description>\n"
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{esc(title)}</rdf:li></rdf:Alt>'
        f"</dc:title><dc:creator><rdf:Seq><rdf:li>{esc(author)}</rdf:li></rdf:Seq></dc:creator>"
        "</rdf:Description>\n"
        '<rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">'
        f"<pdf:Producer>{esc(PRODUCER)}</pdf:Producer></rdf:Description>\n"
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        f"<xmp:CreatorTool>{esc(CREATOR)}</xmp:CreatorTool>"
        f"<xmp:CreateDate>{stamp}</xmp:CreateDate><xmp:ModifyDate>{stamp}</xmp:ModifyDate>"
        "</rdf:Description>\n"
        '<rdf:Description rdf:about="" '
        'xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" '
        'xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" '
        'xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">'
        '<pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">'
        "<pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>"
        f"<pdfaSchema:namespaceURI>{FX_NAMESPACE}</pdfaSchema:namespaceURI>"
        "<pdfaSchema:prefix>fx</pdfaSchema:prefix>"
        f"<pdfaSchema:property><rdf:Seq>{properties}</rdf:Seq></pdfaSchema:property>"
        "</rdf:li></rdf:Bag></pdfaExtension:schemas></rdf:Description>\n"
        f'<rdf:Description rdf:about="" xmlns:fx="{FX_NAMESPACE}">'
        f"<fx:DocumentType>{FX_DOCUMENT_TYPE}</fx:DocumentType>"
        f"<fx:DocumentFileName>{ATTACHMENT_NAME}</fx:DocumentFileName>"
        f"<fx:Version>{FX_VERSION}</fx:Version>"
        f"<fx:ConformanceLevel>{CONFORMANCE_LEVEL}</fx:ConformanceLevel>"
        "</rdf:Description>\n"
        "</rdf:RDF>\n</x:xmpmeta>\n"
        '<?xpacket end="w"?>'
    )
    return text.encode("utf-8")


def _stream(
    writer: PdfWriter, data: bytes, entries: dict[str, PdfObject], *, compress: bool
) -> IndirectObject:
    stream: StreamObject = DecodedStreamObject()
    stream.set_data(data)
    stream.update({NameObject(k): v for k, v in entries.items()})
    if compress:
        stream = stream.flate_encode()
    return writer._add_object(stream)


def make_hybrid(
    pdf: bytes, xml: bytes, *, title: str, author: str, now: datetime | None = None
) -> bytes:
    """Embeds ``xml`` as ``factur-x.xml`` into ``pdf`` and writes the PDF/A-3 marking (see the
    module docstring). The visual content is copied unchanged."""
    created = now or datetime.now(UTC)
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.pdf_header = PDF_HEADER
    name = TextStringObject(ATTACHMENT_NAME)
    params = DictionaryObject(
        {
            NameObject("/ModDate"): TextStringObject(_pdf_date(created)),
            NameObject("/Size"): NumberObject(len(xml)),
            NameObject("/CheckSum"): ByteStringObject(hashlib.md5(xml).digest()),  # noqa: S324 - PDF checksum
        }
    )
    file_ref = _stream(
        writer,
        xml,
        {
            "/Type": NameObject("/EmbeddedFile"),
            "/Subtype": NameObject("/text/xml"),
            "/Params": params,
        },
        compress=True,
    )
    filespec = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): name,
            NameObject("/UF"): name,
            NameObject("/Desc"): TextStringObject("Factur-X/ZUGFeRD Rechnungsdaten (CII)"),
            NameObject("/AFRelationship"): NameObject(AF_RELATIONSHIP),
            NameObject("/EF"): DictionaryObject(
                {NameObject("/F"): file_ref, NameObject("/UF"): file_ref}
            ),
        }
    )
    spec_ref = writer._add_object(filespec)
    root = writer.root_object
    root[NameObject("/Names")] = DictionaryObject(
        {
            NameObject("/EmbeddedFiles"): DictionaryObject(
                {NameObject("/Names"): ArrayObject([name, spec_ref])}
            )
        }
    )
    root[NameObject("/AF")] = ArrayObject([spec_ref])
    icc_ref = _stream(writer, srgb_profile(), {"/N": NumberObject(3)}, compress=True)
    root[NameObject("/OutputIntents")] = ArrayObject(
        [
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/OutputIntent"),
                    NameObject("/S"): NameObject("/GTS_PDFA1"),
                    NameObject("/OutputConditionIdentifier"): TextStringObject(OUTPUT_CONDITION),
                    NameObject("/Info"): TextStringObject("sRGB (LittleCMS)"),
                    NameObject("/DestOutputProfile"): icc_ref,
                }
            )
        ]
    )
    # PDF/A: the metadata stream is not filtered.
    root[NameObject("/Metadata")] = _stream(
        writer,
        xmp_packet(title=title, author=author, created=created),
        {"/Type": NameObject("/Metadata"), "/Subtype": NameObject("/XML")},
        compress=False,
    )
    stamp = _pdf_date(created)
    writer.metadata = {
        "/Title": title,
        "/Author": author,
        "/Creator": CREATOR,
        "/Producer": PRODUCER,
        "/CreationDate": stamp,
        "/ModDate": stamp,
    }
    writer.generate_file_identifiers()
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# Own PDF/A pre-check ----------------------------------------------------------------------


def _resolve(value: Any) -> Any:
    return value.get_object() if isinstance(value, IndirectObject) else value


def _font_embedded(font: DictionaryObject) -> bool:
    subtype = font.get("/Subtype")
    if subtype == "/Type3":
        return True
    if subtype == "/Type0":
        descendants = _resolve(font.get("/DescendantFonts")) or []
        font = _resolve(descendants[0]) if descendants else DictionaryObject()
    descriptor = _resolve(font.get("/FontDescriptor"))
    return bool(descriptor) and any(
        key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")
    )


def _fonts(resources: Any, seen: set[int], out: dict[str, bool]) -> None:
    resources = _resolve(resources)
    if not isinstance(resources, DictionaryObject):
        return
    for _key, ref in (_resolve(resources.get("/Font")) or {}).items():
        font = _resolve(ref)
        if isinstance(font, DictionaryObject):
            label = str(font.get("/BaseFont", _key)).lstrip("/")
            out[label] = out.get(label, True) and _font_embedded(font)
    for ref in (_resolve(resources.get("/XObject")) or {}).values():
        if isinstance(ref, IndirectObject):
            if ref.idnum in seen:
                continue
            seen.add(ref.idnum)
        xobject = _resolve(ref)
        if isinstance(xobject, StreamObject) and xobject.get("/Subtype") == "/Form":
            _fonts(xobject.get("/Resources"), seen, out)


def _xmp_values(root: Any) -> dict[str, str]:
    from mhvp.receipts import einvoice

    metadata = _resolve(root.get("/Metadata"))
    if not isinstance(metadata, StreamObject):
        return {}
    return einvoice.xmp_values(metadata.get_data())


def pdfa_precheck(pdf: bytes) -> dict[str, Any]:
    """Deterministic checks of the points this module writes and of the font embedding.
    ``conformance`` is never ``conform``: an empty blocker list only means that this check
    found nothing; the PDF/A validation itself is open (veraPDF, AE25-01)."""
    blockers: list[str] = []
    passed: list[str] = []

    def check(ok: bool, good: str, bad: str) -> None:
        (passed if ok else blockers).append(good if ok else bad)

    try:
        reader = PdfReader(io.BytesIO(pdf))
        root: Any = reader.trailer["/Root"].get_object()
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        return {
            "validator": PRECHECK_NAME,
            "validator_version": PRECHECK_VERSION,
            "official": False,
            "claimed": None,
            "conformance": "not_verified",
            "blockers": [f"PDF nicht lesbar ({type(exc).__name__})."],
            "passed": [],
            "not_checked": list(NOT_CHECKED),
        }
    second_line = pdf.split(b"\n", 2)[1] if pdf.count(b"\n") >= 2 else b""
    check(
        pdf.startswith(b"%PDF-1.") or pdf.startswith(b"%PDF-2."),
        "Dateikopf vorhanden",
        "Dateikopf fehlt.",
    )
    check(
        second_line.startswith(b"%") and sum(1 for b in second_line[1:5] if b > 127) == 4,
        "Binärkommentar nach dem Dateikopf",
        "Binärkommentar nach dem Dateikopf fehlt.",
    )
    check(not reader.is_encrypted, "Nicht verschlüsselt", "Die Datei ist verschlüsselt.")
    trailer_id = reader.trailer.get("/ID")
    check(bool(trailer_id), "Dateikennung (ID) im Trailer", "Dateikennung (ID) im Trailer fehlt.")
    metadata = _resolve(root.get("/Metadata"))
    check(
        isinstance(metadata, StreamObject) and "/Filter" not in metadata,
        "XMP-Metadaten ungefiltert im Katalog",
        "XMP-Metadaten fehlen oder sind gefiltert.",
    )
    xmp = _xmp_values(root)
    claimed = (
        f"PDF/A-{xmp['pdfaid:part']}{xmp.get('pdfaid:conformance', '')}"
        if xmp.get("pdfaid:part")
        else None
    )
    check(
        xmp.get("pdfaid:part") == "3" and xmp.get("pdfaid:conformance") in ("A", "B", "U"),
        "PDF/A-3 Kennzeichnung im XMP",
        "PDF/A-3 Kennzeichnung (pdfaid) fehlt im XMP.",
    )
    check(
        xmp.get("fx:ConformanceLevel") == CONFORMANCE_LEVEL
        and xmp.get("fx:DocumentFileName") == ATTACHMENT_NAME
        and xmp.get("fx:DocumentType") == FX_DOCUMENT_TYPE
        and bool(xmp.get("fx:Version")),
        "Factur-X Angaben im XMP",
        "Factur-X Angaben (fx) im XMP fehlen oder weichen ab.",
    )
    check(
        FX_NAMESPACE in xmp.get("extension_namespaces", ""),
        "Erweiterungsschema für Factur-X im XMP",
        "Erweiterungsschema für Factur-X fehlt im XMP.",
    )
    info: Any = reader.metadata or {}
    check(
        str(info.get("/Title") or "") == xmp.get("dc:title", "")
        and str(info.get("/Producer") or "") == xmp.get("pdf:Producer", "")
        and str(info.get("/Author") or "") == xmp.get("dc:creator", ""),
        "Info-Verzeichnis und XMP stimmen überein",
        "Info-Verzeichnis und XMP weichen voneinander ab (Titel, Autor oder Producer).",
    )
    intents = _resolve(root.get("/OutputIntents")) or []
    check(
        any(
            _resolve(i).get("/S") == "/GTS_PDFA1"
            and isinstance(_resolve(_resolve(i).get("/DestOutputProfile")), StreamObject)
            for i in intents
        ),
        "Ausgabebedingung GTS_PDFA1 mit ICC-Profil",
        "Ausgabebedingung GTS_PDFA1 mit eingebettetem ICC-Profil fehlt.",
    )
    af = [_resolve(x) for x in (_resolve(root.get("/AF")) or [])]
    names = _resolve(_resolve(_resolve(root.get("/Names")) or {}).get("/EmbeddedFiles")) or {}
    flat = list(_resolve(names.get("/Names")) or [])
    specs = [_resolve(flat[i + 1]) for i in range(0, len(flat) - 1, 2)]
    check(bool(specs), "Eingebettete Datei vorhanden", "Keine eingebettete Datei vorhanden.")
    for spec in specs:
        label = str(spec.get("/UF") or spec.get("/F") or "?")
        stream = _resolve(_resolve(spec.get("/EF") or {}).get("/F"))
        params = _resolve(stream.get("/Params")) if isinstance(stream, StreamObject) else None
        check(
            spec in af,
            f"{label}: im Katalog /AF verknüpft",
            f"{label}: nicht im Katalog /AF verknüpft.",
        )
        check(
            "/AFRelationship" in spec and "/F" in spec and "/UF" in spec,
            f"{label}: AFRelationship, F und UF gesetzt",
            f"{label}: AFRelationship, F oder UF fehlt.",
        )
        check(
            isinstance(stream, StreamObject)
            and "/Subtype" in stream
            and isinstance(params, DictionaryObject)
            and "/ModDate" in params,
            f"{label}: MIME-Typ und Änderungsdatum gesetzt",
            f"{label}: MIME-Typ (Subtype) oder Änderungsdatum (Params ModDate) fehlt.",
        )
    javascript = "/JavaScript" in (_resolve(root.get("/Names")) or {}) or "/AA" in root
    action = _resolve(root.get("/OpenAction"))
    if isinstance(action, DictionaryObject) and action.get("/S") == "/JavaScript":
        javascript = True
    fonts: dict[str, bool] = {}
    seen: set[int] = set()
    unprinted = 0
    for page in reader.pages:
        _fonts(page.get("/Resources"), seen, fonts)
        if "/AA" in page:
            javascript = True
        for annot in _resolve(page.get("/Annots")) or []:
            annot = _resolve(annot)
            flags = int(annot.get("/F", 0))
            if annot.get("/Subtype") != "/Popup" and (not flags & 4 or flags & (1 | 2 | 32)):
                unprinted += 1
    check(
        not javascript,
        "Keine JavaScript- oder Zusatzaktionen",
        "JavaScript oder Zusatzaktionen enthalten.",
    )
    check(
        unprinted == 0,
        "Anmerkungen druckbar gekennzeichnet",
        f"{unprinted} Anmerkung(en) ohne Druckkennzeichen.",
    )
    missing = sorted(name for name, ok in fonts.items() if not ok)
    check(
        not missing,
        "Alle Schriften eingebettet",
        f"Schriften nicht eingebettet: {', '.join(missing)}. {FALLBACK_HINT}",
    )
    return {
        "validator": PRECHECK_NAME,
        "validator_version": PRECHECK_VERSION,
        "official": False,
        "claimed": claimed,
        "conformance": "not_verified",
        "blockers": blockers,
        "passed": passed,
        "not_checked": list(NOT_CHECKED),
    }


# API --------------------------------------------------------------------------------------

router = APIRouter(tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


async def _issued(
    session: AsyncSession, invoice_id: uuid.UUID, *, lock: bool = False
) -> tuple[AdminFeeInvoice, AdminFeeInvoice | None]:
    query = select(AdminFeeInvoice).where(AdminFeeInvoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        if await session.get(Invoice, invoice_id) is not None:
            raise ProblemError(
                ErrorCodes.XRECHNUNG_NOT_ISSUED,
                detail="Nur ausgestellte Honorarrechnungen werden als ZUGFeRD erzeugt.",
            )
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status not in (
        AdminFeeInvoiceStatus.ISSUED,
        AdminFeeInvoiceStatus.RELEASED,
        AdminFeeInvoiceStatus.CANCELLED,
    ):
        raise ProblemError(ErrorCodes.XRECHNUNG_NOT_ISSUED)
    original: AdminFeeInvoice | None = None
    if row.kind == "credit_note":
        if row.corrects_invoice_id is None:
            raise ProblemError(
                ErrorCodes.XRECHNUNG_NOT_ISSUED, detail="Nur Gutschriften mit Ursprungsbezug."
            )
        original = await session.get(AdminFeeInvoice, row.corrects_invoice_id)
        if original is None:  # pragma: no cover - FK
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row, original


async def render(
    session: AsyncSession, request: Request, row: AdminFeeInvoice, original: AdminFeeInvoice | None
) -> tuple[bytes, bytes, list[xr.Finding]]:
    """The hybrid PDF, its CII and the CII findings. Every lock of ``xrechnung.load`` applies."""
    from mhvp.accounting.fee_documents import CREDIT_LABEL, INVOICE_LABEL, build_letter
    from mhvp.documents import letters
    from mhvp.documents import services as docs
    from mhvp.documents.blobs import BlobStore

    data = await xr.load(session, row)
    period = (row.period_start, row.period_end) if row.period_start and row.period_end else None
    corrects = (original.number, original.invoice_date) if original is not None else None
    xml = build_cii(data, period=period, corrects=corrects)
    findings = check_cii(xml, data, credit_note=original is not None)
    head = await docs.letterhead(session, BlobStore(request.app.state.settings))
    visual = letters.render_pdf(head, build_letter(data, row, original))
    label = CREDIT_LABEL if original is not None else INVOICE_LABEL
    pdf = make_hybrid(visual, xml, title=f"{label} {row.number}", author=data.seller.name)
    return pdf, xml, findings


def _filename(row: AdminFeeInvoice) -> str:
    return f"{row.number}-zugferd.pdf"


def _check_body(row: AdminFeeInvoice, pdf: bytes, findings: list[xr.Finding]) -> dict[str, Any]:
    return {
        "invoice_id": row.id,
        "number": row.number,
        "profile": CONFORMANCE_LEVEL,
        "guideline_id": GUIDELINE_EN16931,
        "attachment_name": ATTACHMENT_NAME,
        "structure_ok": not findings,
        "findings": [f.as_dict() for f in findings],
        "pdfa": pdfa_precheck(pdf),
        "official_validation": "not_run",
    }


@router.get(
    "/admin-fee-invoices/{invoice_id}/zugferd.pdf",
    summary="Honorarrechnung als ZUGFeRD/Factur-X (PDF mit CII EN 16931, PDF/A-3 nicht geprüft)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def zugferd_pdf(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    """Generated on request; drafts and incoming invoices answer 409 (MHVP-BILL-0006), missing
    Leitweg-ID, IBAN or tax data 409 like the XRechnung. Nothing is sent."""
    async with tenant_tx(request, principal) as session:
        row, original = await _issued(session, invoice_id)
        pdf, _xml, findings = await render(session, request, row, original)
    pdfa = pdfa_precheck(pdf)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(row)}"',
            "X-MHVP-ZUGFeRD-Findings": str(len(findings)),
            "X-MHVP-PDFA-Status": str(pdfa["conformance"]),
            "X-MHVP-PDFA-Blockers": str(len(pdfa["blockers"])),
        },
    )


@router.get(
    "/admin-fee-invoices/{invoice_id}/zugferd/check",
    summary="Prüfung des ZUGFeRD-Belegs (CII-Struktur und eigene PDF/A-Vorprüfung)",
    response_model=AccountingEInvoiceCheckOut,
)
async def zugferd_check(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Own checks only; the KoSIT validator and veraPDF run outside the platform."""
    async with tenant_tx(request, principal) as session:
        row, original = await _issued(session, invoice_id)
        pdf, _xml, findings = await render(session, request, row, original)
    return _check_body(row, pdf, findings)


@router.post(
    "/admin-fee-invoices/{invoice_id}/zugferd/document",
    status_code=201,
    summary="ZUGFeRD-Beleg als Dokument ablegen (Prüfergebnis gespeichert)",
    response_model=AccountingZugferdStoredOut,
)
async def zugferd_store(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Files the hybrid once in the document index (source generated) with the check result at
    the invoice; a second call returns the existing document. Nothing is sent."""
    from mhvp.accounting.fee_documents import _links
    from mhvp.documents import services as docs
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource

    async with tenant_tx(request, principal) as session:
        row, original = await _issued(session, invoice_id, lock=True)
        if row.zugferd_document_id is not None:
            return {
                "document_id": row.zugferd_document_id,
                "created": False,
                "check": row.zugferd_check,
            }
        pdf, _xml, findings = await render(session, request, row, original)
        check = {
            **_check_body(row, pdf, findings),
            "invoice_id": str(row.id),
            "checked_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        }
        document = await docs.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=pdf,
            title=f"ZUGFeRD {row.number}",
            filename=_filename(row),
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=_links(row),
            created_by=principal.user_id,
        )
        row.zugferd_document_id = document.id
        row.zugferd_check = check
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.zugferd_stored",
            entity_type="admin_fee_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "number": row.number,
                "document_id": str(document.id),
                "structure_ok": not findings,
                "pdfa_blockers": len(check["pdfa"]["blockers"]),
            },
        )
        await session.flush()
        return {"document_id": document.id, "created": True, "check": check}
