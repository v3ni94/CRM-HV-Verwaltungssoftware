"""AE25 / S13-03: ZUGFeRD / Factur-X generation (CII EN 16931 in a PDF with PDF/A-3 marking)
and the reading of profile and container data.

Expected values are fixed here, not derived from the generator: 3 x 25,00 = 75,00 plus the
adjustment 25,00 to the minimum fee 100,00; 19 % of 100,00 = 19,00; gross 119,00. Service
period 01.07.2026 to 30.09.2026. A credit note of the same invoice states 100,00, 19,00 and
119,00 positive with type code 381.
"""

import hashlib
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import reportlab
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from mhvp.accounting import xrechnung as x
from mhvp.accounting import zugferd as z
from mhvp.receipts import einvoice

SELLER = x.Seller(
    name="Hausverwaltung Müller GmbH",
    address=x.Address("Rheinpromenade 13", "40789", "Monheim am Rhein"),
    vat_id="DE123456789",
    payee_iban="DE02120300000000202051",
    register_number="HRB 104762",
    email="info@example.org",
    phone="+49 2173 000000",
    contact_name="Timo Müller",
)
BUYER = x.Buyer("WEG Sollhaus", x.Address("Rheinpromenade 13", "40789", "Monheim am Rhein"))
LINES = [
    x.Line("Verwaltung 3 Wohnungen", Decimal("3"), Decimal("25.00"), Decimal("75.00")),
    x.Line("Anpassung Mindesthonorar", Decimal("1"), Decimal("25.00"), Decimal("25.00")),
]
NOW = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
PERIOD = (date(2026, 7, 1), date(2026, 9, 30))
NS = z.CII_NS


def _data(**overrides: object) -> x.InvoiceData:
    values: dict[str, object] = {
        "number": "AE25-2026-000001",
        "issue_date": date(2026, 9, 26),
        "buyer_reference": "04011000-12345-67",
        "seller": SELLER,
        "buyer": BUYER,
        "lines": LINES,
        "net": Decimal("100.00"),
        "vat_percent": Decimal("19"),
        "vat": Decimal("19.00"),
        "gross": Decimal("119.00"),
    }
    values.update(overrides)
    return x.InvoiceData(**values)  # type: ignore[arg-type]


def _text(root: object, path: str) -> str | None:
    node = root.find(path, NS)  # type: ignore[attr-defined]
    return node.text if node is not None else None


def _visual(font: str = "Helvetica") -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, initialFontName=font)
    canvas.setFont(font, 11)
    canvas.drawString(70, 760, "Rechnung AE25-2026-000001 vom 26.09.2026")
    canvas.drawString(70, 740, "Netto 100,00 EUR USt 19,00 EUR Brutto 119,00 EUR")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


SETTLEMENT = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement"
AGREEMENT = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement"


def test_cii_en16931_carries_the_fixed_amounts_parties_and_period() -> None:
    xml = z.build_cii(_data(), period=PERIOD)
    root = SafeET.fromstring(xml)
    assert (
        _text(
            root,
            "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
        )
        == "urn:cen.eu:en16931:2017"
    )
    assert _text(root, "rsm:ExchangedDocument/ram:ID") == "AE25-2026-000001"
    assert _text(root, "rsm:ExchangedDocument/ram:TypeCode") == "380"
    issue = root.find("rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString", NS)
    assert issue.text == "20260926"
    assert issue.get("format") == "102"
    assert _text(root, f"{AGREEMENT}/ram:BuyerReference") == "04011000-12345-67"
    assert _text(root, f"{AGREEMENT}/ram:SellerTradeParty/ram:Name") == "Hausverwaltung Müller GmbH"
    vat_id = root.find(f"{AGREEMENT}/ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID", NS)
    assert vat_id.text == "DE123456789"
    assert vat_id.get("schemeID") == "VA"
    assert (
        _text(root, f"{AGREEMENT}/ram:SellerTradeParty/ram:SpecifiedLegalOrganization/ram:ID")
        == "HRB 104762"
    )
    endpoint = root.find(
        f"{AGREEMENT}/ram:BuyerTradeParty/ram:URIUniversalCommunication/ram:URIID", NS
    )
    assert endpoint.text == "04011000-12345-67"
    assert endpoint.get("schemeID") == "0204"
    assert (
        _text(root, f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode") == "58"
    )
    assert (
        _text(
            root,
            f"{SETTLEMENT}/ram:SpecifiedTradeSettlementPaymentMeans/"
            "ram:PayeePartyCreditorFinancialAccount/ram:IBANID",
        )
        == "DE02120300000000202051"
    )
    tax = root.find(f"{SETTLEMENT}/ram:ApplicableTradeTax", NS)
    assert [
        _text(tax, f"ram:{k}") for k in ("CalculatedAmount", "BasisAmount", "CategoryCode")
    ] == [
        "19.00",
        "100.00",
        "S",
    ]
    assert _text(tax, "ram:RateApplicablePercent") == "19.00"
    period = f"{SETTLEMENT}/ram:BillingSpecifiedPeriod"
    assert _text(root, f"{period}/ram:StartDateTime/udt:DateTimeString") == "20260701"
    assert _text(root, f"{period}/ram:EndDateTime/udt:DateTimeString") == "20260930"
    sums = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    assert [
        _text(root, f"{sums}/ram:{k}")
        for k in (
            "LineTotalAmount",
            "TaxBasisTotalAmount",
            "TaxTotalAmount",
            "GrandTotalAmount",
            "DuePayableAmount",
        )
    ] == ["100.00", "100.00", "19.00", "119.00", "119.00"]
    assert root.find(f"{sums}/ram:TaxTotalAmount", NS).get("currencyID") == "EUR"
    items = root.findall("rsm:SupplyChainTradeTransaction/ram:IncludedSupplyChainTradeLineItem", NS)
    assert len(items) == 2
    first = items[0]
    assert _text(first, "ram:SpecifiedTradeProduct/ram:Name") == "Verwaltung 3 Wohnungen"
    assert (
        _text(
            first, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount"
        )
        == "25.00"
    )
    quantity = first.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
    assert quantity.text == "3"
    assert quantity.get("unitCode") == "C62"
    assert (
        _text(
            first,
            "ram:SpecifiedLineTradeSettlement/"
            "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
        )
        == "75.00"
    )
    assert z.check_cii(xml, _data()) == []


def test_kleinunternehmer_uses_exemption_category_with_reason() -> None:
    note = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."  # operator text in the test only
    data = _data(
        vat_percent=Decimal("0"),
        vat=Decimal("0.00"),
        gross=Decimal("100.00"),
        tax_exemption_reason=note,
    )
    xml = z.build_cii(data)
    root = SafeET.fromstring(xml)
    tax = root.find(f"{SETTLEMENT}/ram:ApplicableTradeTax", NS)
    assert _text(tax, "ram:CategoryCode") == "E"
    assert _text(tax, "ram:RateApplicablePercent") == "0.00"
    assert _text(tax, "ram:CalculatedAmount") == "0.00"
    assert _text(tax, "ram:ExemptionReason") == note
    assert z.check_cii(xml, data) == []


def test_credit_note_is_381_with_positive_amounts_and_reference() -> None:
    stored = _data(
        number="AE25-2026-000002",
        lines=[
            x.Line(ln.text, ln.quantity, -ln.unit_price, -ln.amount)  # stored credit is negative
            for ln in LINES
        ],
        net=Decimal("-100.00"),
        vat=Decimal("-19.00"),
        gross=Decimal("-119.00"),
    )
    xml = z.build_cii(stored, corrects=("AE25-2026-000001", date(2026, 9, 26)))
    root = SafeET.fromstring(xml)
    assert _text(root, "rsm:ExchangedDocument/ram:TypeCode") == "381"
    sums = f"{SETTLEMENT}/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    assert _text(root, f"{sums}/ram:GrandTotalAmount") == "119.00"
    ref = f"{SETTLEMENT}/ram:InvoiceReferencedDocument"
    assert _text(root, f"{ref}/ram:IssuerAssignedID") == "AE25-2026-000001"
    assert _text(root, f"{ref}/ram:FormattedIssueDateTime/qdt:DateTimeString") == "20260926"
    assert z.check_cii(xml, stored, credit_note=True) == []
    # Read as an invoice it is the wrong document type.
    assert any(f.code == "BT-3" for f in z.check_cii(xml, stored))


def test_check_reports_deviation_from_the_invoice_and_broken_sums() -> None:
    xml = z.build_cii(_data())
    tampered = xml.replace(
        b"<ram:GrandTotalAmount>119.00</ram:GrandTotalAmount>",
        b"<ram:GrandTotalAmount>120.00</ram:GrandTotalAmount>",
    )
    codes = {f.code for f in z.check_cii(tampered, _data())}
    assert {"BT-112", "EN16931"} <= codes  # 100,00 + 19,00 is not 120,00
    other = z.check_cii(xml, _data(number="AE25-2026-000099"))
    assert [f.code for f in other] == ["BT-1"]
    assert z.check_cii(b"<kein xml", _data())[0].code == "XML"


def test_hybrid_embeds_the_xml_with_pdfa3_marking_and_is_read_back() -> None:
    xml = z.build_cii(_data(), period=PERIOD)
    pdf = z.make_hybrid(
        _visual(), xml, title="Rechnung AE25-2026-000001", author=SELLER.name, now=NOW
    )
    assert pdf.startswith(b"%PDF-1.7\n%")
    name, embedded = einvoice.embedded_xml(pdf) or ("", b"")
    assert name == "factur-x.xml"
    assert hashlib.sha256(embedded).hexdigest() == hashlib.sha256(xml).hexdigest()
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    assert "Brutto 119,00 EUR" in reader.pages[0].extract_text()
    info = reader.metadata
    assert info is not None
    assert info.title == "Rechnung AE25-2026-000001"
    assert info["/Producer"] == z.PRODUCER
    assert info["/CreationDate"] == "D:20261001083000+00'00'"
    attachment = next(iter(reader.attachment_list))
    assert attachment.associated_file_relationship == "/Alternative"
    assert attachment.subtype == "/text/xml"
    assert attachment.size == len(xml)
    assert attachment.checksum == hashlib.md5(xml).digest()  # noqa: S324 - PDF checksum
    catalog = reader.trailer["/Root"].get_object()
    assert catalog["/AF"][0].get_object() == attachment.pdf_object
    intent = catalog["/OutputIntents"][0].get_object()
    assert intent["/S"] == "/GTS_PDFA1"
    assert intent["/DestOutputProfile"].get_object()["/N"] == 3
    assert "/Filter" not in catalog["/Metadata"].get_object()
    xmp = einvoice.xmp_values(catalog["/Metadata"].get_object().get_data())
    assert xmp["pdfaid:part"] == "3"
    assert xmp["pdfaid:conformance"] == "B"
    assert xmp["fx:ConformanceLevel"] == "EN 16931"
    assert xmp["fx:DocumentFileName"] == "factur-x.xml"
    assert xmp["fx:DocumentType"] == "INVOICE"
    assert xmp["fx:Version"] == "1.0"
    assert xmp["dc:title"] == "Rechnung AE25-2026-000001"
    assert xmp["dc:creator"] == SELLER.name
    assert z.FX_NAMESPACE in xmp["extension_namespaces"]

    # The Belegeingang reads the own hybrid like any received ZUGFeRD invoice.
    result = einvoice.read("application/pdf", pdf)
    inv = result.einvoice
    assert inv is not None
    assert result.findings == []
    assert (inv.format, inv.syntax, inv.profile) == ("zugferd", "cii", "EN 16931")
    assert (inv.invoice_number, inv.gross, inv.net, inv.vat) == (
        "AE25-2026-000001",
        Decimal("119.00"),
        Decimal("100.00"),
        Decimal("19.00"),
    )
    assert (inv.service_from, inv.service_to) == PERIOD
    assert inv.container == {
        "pdfa_part": "3",
        "pdfa_conformance": "B",
        "fx_document_type": "INVOICE",
        "fx_document_file_name": "factur-x.xml",
        "fx_version": "1.0",
        "fx_conformance_level": "EN 16931",
        "af_relationship": "Alternative",
        "attachment_subtype": "text/xml",
        "in_catalog_af": True,
    }
    assert einvoice.formal_findings(inv) == []
    assert einvoice.container_findings(inv) == []
    # The test page prints no IBAN: the hybrid comparison of the reader notices it.
    deviations = einvoice.hybrid_deviations(inv, reader.pages[0].extract_text())
    assert [d["field"] for d in deviations] == ["iban"]
    validation = einvoice.formal_validation(inv, [])
    assert validation["result"] == "ok"
    assert validation["official"] is False
    assert validation["profile"] == "EN 16931"
    assert validation["container_findings"] == []


def test_precheck_names_non_embedded_fonts_and_never_claims_conformance() -> None:
    xml = z.build_cii(_data())
    pdf = z.make_hybrid(_visual(), xml, title="Rechnung", author=SELLER.name, now=NOW)
    check = z.pdfa_precheck(pdf)
    assert check["official"] is False
    assert check["claimed"] == "PDF/A-3B"
    assert check["conformance"] == "not_verified"
    assert check["blockers"] == ["Schriften nicht eingebettet: Helvetica."]
    assert "factur-x.xml: im Katalog /AF verknüpft" in check["passed"]
    assert check["not_checked"] == list(z.NOT_CHECKED)


def test_precheck_without_blockers_for_embedded_fonts_still_not_verified() -> None:
    vera = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    if "AE25Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("AE25Vera", str(vera)))
    pdf = z.make_hybrid(_visual("AE25Vera"), z.build_cii(_data()), title="R", author="A", now=NOW)
    check = z.pdfa_precheck(pdf)
    assert check["blockers"] == []
    assert check["conformance"] == "not_verified"  # only veraPDF can decide (AE25-01)


def test_precheck_of_a_plain_pdf_lists_the_missing_marking() -> None:
    check = z.pdfa_precheck(_visual())
    assert check["claimed"] is None
    for expected in (
        "XMP-Metadaten fehlen oder sind gefiltert.",
        "PDF/A-3 Kennzeichnung (pdfaid) fehlt im XMP.",
        "Ausgabebedingung GTS_PDFA1 mit eingebettetem ICC-Profil fehlt.",
        "Keine eingebettete Datei vorhanden.",
    ):
        assert expected in check["blockers"]
    assert z.pdfa_precheck(b"kein pdf")["blockers"][0].startswith("PDF nicht lesbar")


@pytest.mark.parametrize(
    ("guideline", "profile"),
    [
        ("urn:factur-x.eu:1p0:minimum", "MINIMUM"),
        ("urn:factur-x.eu:1p0:basicwl", "BASIC WL"),
        ("urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic", "BASIC"),
        ("urn:cen.eu:en16931:2017", "EN 16931"),
        ("urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended", "EXTENDED"),
        ("urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0", "XRECHNUNG"),
        ("urn:example:unknown", None),
        (None, None),
    ],
)
def test_profile_name_from_the_guideline_identifier(
    guideline: str | None, profile: str | None
) -> None:
    assert einvoice.profile_name(guideline) == profile


def test_container_hints_for_minimum_profile_and_missing_marking() -> None:
    minimum = z.build_cii(_data()).replace(
        b"<ram:ID>urn:cen.eu:en16931:2017</ram:ID>", b"<ram:ID>urn:factur-x.eu:1p0:minimum</ram:ID>"
    )
    pdf = z.make_hybrid(_visual(), minimum, title="R", author="A", now=NOW)
    inv = einvoice.read("application/pdf", pdf).einvoice
    assert inv is not None
    assert inv.profile == "MINIMUM"
    assert einvoice.container_findings(inv) == [
        "ZUGFeRD: Profil MINIMUM enthält nicht alle Pflichtangaben der EN 16931; "
        "Rechnungsinhalt anhand des PDF prüfen.",
        "ZUGFeRD: Profil laut XMP (EN 16931) weicht vom Profil des XML (MINIMUM) ab.",
    ]
    # A bare attachment without PDF/A marking (synthetic, as in test_m14_einvoice).
    reader = PdfReader(io.BytesIO(_visual()))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_attachment("factur-x.xml", z.build_cii(_data()))
    out = io.BytesIO()
    writer.write(out)
    bare = einvoice.read("application/pdf", out.getvalue()).einvoice
    assert bare is not None
    assert bare.profile == "EN 16931"
    assert einvoice.container_findings(bare) == [
        "ZUGFeRD: PDF ohne PDF/A-Kennzeichnung im XMP (pdfaid).",
        "ZUGFeRD: Profilangabe (ConformanceLevel) fehlt im XMP.",
        "ZUGFeRD: Anhang ohne AFRelationship (Associated File).",
    ]
    # The formal reading itself is unaffected (hints only).
    assert einvoice.formal_validation(bare, [])["result"] == "ok"


def test_zugferd_1_root_gets_a_clear_reading_error() -> None:
    xml = b'<rsm:CrossIndustryDocument xmlns:rsm="urn:ferd:CrossIndustryDocument:invoice:1p0"/>'
    with pytest.raises(einvoice.EInvoiceError, match=r"ZUGFeRD 1\.0"):
        einvoice.parse_xml(xml, fmt="zugferd")
    assert einvoice.container_findings(einvoice.parse_xml(x.build_xml(_data()))) == []


def test_format_versions_are_pinned_as_in_adr_0020() -> None:
    # ADR 0020: a silent change of profile, file name or XMP version must fail.
    assert z.GUIDELINE_EN16931 == "urn:cen.eu:en16931:2017"
    assert z.CONFORMANCE_LEVEL == "EN 16931"
    assert z.ATTACHMENT_NAME == "factur-x.xml"
    assert z.FX_VERSION == "1.0"
    assert z.FX_NAMESPACE == "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
    assert z.AF_RELATIONSHIP == "/Alternative"
    assert z.PDF_HEADER == "%PDF-1.7"
