# ruff: noqa: E501 (synthetic XML samples are kept as single lines per element)
"""M14 e-invoice reading (spec 13.5, PÜ01, cases D41, D42, D44), deterministic parts: UBL 2.1
and CII XRechnung parsing, ZUGFeRD / Factur-X extraction from a synthetic PDF, formal findings,
conflict detection XML against PDF text and against the AI reading, and the § 35a estimate
marker of the AI path."""

from __future__ import annotations

import io
from decimal import Decimal

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from mhvp.receipts import einvoice
from mhvp.receipts.extraction import estimate_findings, field_confidences

IBAN = "DE89370400440532013000"

UBL = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>RE-2026-042</cbc:ID>
  <cbc:IssueDate>2026-03-01</cbc:IssueDate>
  <cbc:DueDate>2026-03-15</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:Note>Objekt Musterstraße 12, Treppenhausreinigung März</cbc:Note>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cbc:BuyerReference>WEG-0815</cbc:BuyerReference>
  <cac:OrderReference><cbc:ID>AUF-77</cbc:ID></cac:OrderReference>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyName><cbc:Name>Belegki Handwerk GmbH</cbc:Name></cac:PartyName>
    <cac:PartyLegalEntity><cbc:RegistrationName>Belegki Handwerk GmbH</cbc:RegistrationName></cac:PartyLegalEntity>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party>
    <cac:PartyLegalEntity><cbc:RegistrationName>WEG Musterstraße 12</cbc:RegistrationName></cac:PartyLegalEntity>
  </cac:Party></cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
    <cbc:PaymentID>RE-2026-042</cbc:PaymentID>
    <cac:PayeeFinancialAccount><cbc:ID>{IBAN}</cbc:ID></cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  <cac:PaymentTerms><cbc:Note>#SKONTO#TAGE=10#PROZENT=2.00#</cbc:Note></cac:PaymentTerms>
  <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">95.00</cbc:TaxAmount></cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="EUR">500.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">500.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="EUR">595.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">595.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="HUR">10</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">400.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Arbeitszeit Reinigung</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent></cac:ClassifiedTaxCategory>
    </cac:Item>
  </cac:InvoiceLine>
  <cac:InvoiceLine>
    <cbc:ID>2</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Reinigungsmittel</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent></cac:ClassifiedTaxCategory>
    </cac:Item>
  </cac:InvoiceLine>
</Invoice>
"""

CII = f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>RE-2026-042</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString format="102">20260301</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument><ram:LineID>1</ram:LineID></ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct><ram:Name>Arbeitszeit Reinigung</ram:Name></ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="HUR">10</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax><ram:RateApplicablePercent>19</ram:RateApplicablePercent></ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>500.00</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:BuyerReference>WEG-0815</ram:BuyerReference>
      <ram:SellerTradeParty><ram:Name>Belegki Handwerk GmbH</ram:Name></ram:SellerTradeParty>
      <ram:BuyerTradeParty><ram:Name>WEG Musterstraße 12</ram:Name></ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:PaymentReference>RE-2026-042</ram:PaymentReference>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementPaymentMeans>
        <ram:TypeCode>58</ram:TypeCode>
        <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>{IBAN}</ram:IBANID></ram:PayeePartyCreditorFinancialAccount>
      </ram:SpecifiedTradeSettlementPaymentMeans>
      <ram:SpecifiedTradePaymentTerms>
        <ram:Description>Zahlbar bis 15.03.2026</ram:Description>
        <ram:DueDateDateTime><udt:DateTimeString format="102">20260315</udt:DateTimeString></ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>500.00</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>500.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">95.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>595.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>595.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>
"""


def make_pdf(lines: list[str]) -> bytes:
    """A one page PDF with a real text layer (reportlab), the visual part of a hybrid."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(50, y, line)
        y -= 20
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_zugferd_pdf(lines: list[str], xml: str, name: str = "factur-x.xml") -> bytes:
    """Synthetic ZUGFeRD / Factur-X: text PDF plus the XML as embedded file. The PDF/A-3
    metadata of a real ZUGFeRD file is not reproduced; the reader only needs the attachment."""
    reader = PdfReader(io.BytesIO(make_pdf(lines)))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_attachment(name, xml.encode("utf-8"))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


PDF_TEXT_MATCHING = [
    "Belegki Handwerk GmbH",
    "Rechnung RE-2026-042 vom 01.03.2026",
    "Netto 500,00 EUR USt 95,00 EUR Brutto 595,00 EUR",
]
PDF_TEXT_CONFLICTING = [
    "Belegki Handwerk GmbH",
    "Rechnung RE-2026-099 vom 01.03.2026",
    "Netto 700,00 EUR USt 133,00 EUR Brutto 833,00 EUR",
]


def test_ubl_xrechnung_is_read_with_structured_fields_and_masked_payment() -> None:
    result = einvoice.read("application/xml", UBL.encode())
    inv = result.einvoice
    assert inv is not None
    assert result.findings == []
    assert (inv.format, inv.syntax) == ("xrechnung", "ubl")
    assert inv.customization_id is not None
    assert "xrechnung_3.0" in inv.customization_id
    assert inv.invoice_number == "RE-2026-042"
    assert (str(inv.invoice_date), str(inv.due_date)) == ("2026-03-01", "2026-03-15")
    assert (inv.seller_name, inv.buyer_name) == ("Belegki Handwerk GmbH", "WEG Musterstraße 12")
    assert (inv.net, inv.vat, inv.gross) == (Decimal("500.00"), Decimal("95.00"), Decimal("595.00"))
    assert inv.currency == "EUR"
    assert (inv.order_reference, inv.buyer_reference) == ("AUF-77", "WEG-0815")
    assert (inv.discount_percent, inv.discount_days) == (Decimal("2.00"), 10)
    assert [(ln.position, ln.description, ln.net, ln.vat_percent, ln.unit) for ln in inv.lines] == [
        ("1", "Arbeitszeit Reinigung", "400.00", "19", "HUR"),
        ("2", "Reinigungsmittel", "100.00", "19", "C62"),
    ]
    assert inv.payment.iban == IBAN
    view = inv.payment.masked_view()
    assert IBAN not in str(view)
    assert view["iban_masked"] == "DE89 ... 3000"
    assert view["iban_checksum_ok"] is True
    assert (view["means_code"], view["reference"]) == ("30", "RE-2026-042")

    fields = einvoice.draft_fields(inv)
    assert fields["gross"] == {
        "value": "595.00",
        "confidence": 1.0,
        "source": "xml",
        "note": "Aus dem strukturierten Teil (XRechnung, UBL)",
    }
    assert fields["recipient_name"]["value"] == "WEG Musterstraße 12"
    assert fields["discount_percent"]["value"] == "2.00"
    assert fields["discount_until"]["value"] is None
    assert "10 Tage" in (fields["discount_until"]["note"] or "")
    assert fields["order_reference"]["value"] == "AUF-77"
    assert einvoice.formal_findings(inv) == []
    assert "Musterstraße 12" in (einvoice.property_hint(inv) or "")
    # A plain XRechnung is not a hybrid: no PDF text comparison.
    assert einvoice.text_conflicts(inv, "irgendein Text") == []


def test_cii_cross_industry_invoice_is_read() -> None:
    inv = einvoice.read("text/xml", CII.encode()).einvoice
    assert inv is not None
    assert (inv.format, inv.syntax) == ("xrechnung", "cii")
    assert inv.invoice_number == "RE-2026-042"
    assert (str(inv.invoice_date), str(inv.due_date)) == ("2026-03-01", "2026-03-15")
    assert (inv.seller_name, inv.buyer_name) == ("Belegki Handwerk GmbH", "WEG Musterstraße 12")
    assert (inv.net, inv.vat, inv.gross, inv.payable) == (
        Decimal("500.00"),
        Decimal("95.00"),
        Decimal("595.00"),
        Decimal("595.00"),
    )
    assert inv.buyer_reference == "WEG-0815"
    assert inv.payment.means_code == "58"
    assert inv.payment.terms == "Zahlbar bis 15.03.2026"
    assert [(ln.description, ln.net, ln.vat_percent) for ln in inv.lines] == [
        ("Arbeitszeit Reinigung", "500.00", "19")
    ]
    assert einvoice.formal_findings(inv) == []


def test_non_invoice_xml_and_plain_pdf_are_not_e_invoices() -> None:
    other = einvoice.read("application/xml", b"<?xml version='1.0'?><root><a>1</a></root>")
    assert other.einvoice is None
    assert other.findings == [
        "E-Rechnung: strukturierter Teil nicht lesbar: XML ist keine XRechnung (weder UBL "
        "Invoice noch CII)."
    ]
    broken = einvoice.read("application/xml", b"<Invoice xmlns='urn:oasis:names:specification:ubl")
    assert broken.einvoice is None
    assert broken.findings
    assert "nicht lesbar" in broken.findings[0]
    plain = einvoice.read("application/pdf", make_pdf(PDF_TEXT_MATCHING))
    assert plain.einvoice is None
    assert plain.findings == []
    assert einvoice.read("image/png", b"\x89PNG").einvoice is None


def test_zugferd_pdf_attachment_is_extracted_under_all_known_names() -> None:
    for name in ("factur-x.xml", "zugferd-invoice.xml", "ZUGFeRD-invoice.xml", "xrechnung.xml"):
        pdf = make_zugferd_pdf(PDF_TEXT_MATCHING, CII, name=name)
        found = einvoice.embedded_xml(pdf)
        assert found is not None
        assert found[0] == name
        inv = einvoice.read("application/pdf", pdf).einvoice
        assert inv is not None, name
        assert (inv.format, inv.syntax, inv.attachment_name) == ("zugferd", "cii", name)
        assert inv.gross == Decimal("595.00")
    # An unrelated attachment is not an e-invoice.
    assert einvoice.embedded_xml(make_zugferd_pdf(PDF_TEXT_MATCHING, CII, name="notes.xml")) is None


def test_d42_hybrid_conflicts_xml_against_pdf_text_and_against_ai_reading() -> None:
    pdf = make_zugferd_pdf(PDF_TEXT_CONFLICTING, CII)
    inv = einvoice.read("application/pdf", pdf).einvoice
    assert inv is not None
    text = "\n".join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().splitlines())
    conflicts = einvoice.text_conflicts(inv, text)
    assert [(c["field"], c["xml"], c["other"], c["other_source"]) for c in conflicts] == [
        ("invoice_number", "RE-2026-042", None, "pdf_text"),
        ("gross", "595.00", None, "pdf_text"),
    ]
    # The matching text layer yields no conflict, in German and in ISO number formats.
    matching = "\n".join(PDF_TEXT_MATCHING)
    assert einvoice.text_conflicts(inv, matching) == []
    assert einvoice.text_conflicts(inv, "RE-2026-042 total 595.00") == []
    assert einvoice.text_conflicts(inv, "RE-2026-042 Brutto 1.595,00")  # 595,00 not contained
    # No text layer: the comparison itself is reported, never skipped silently.
    none = einvoice.text_conflicts(inv, "")
    assert len(none) == 1
    assert none[0]["field"] == "document"

    xml_fields = einvoice.draft_fields(inv)
    ai_fields = field_confidences(
        {
            "supplier_name": "Belegki Handwerk GmbH",
            "invoice_number": "RE-2026-099",
            "invoice_date": "2026-03-01",
            "net": "700.00",
            "vat": "133.00",
            "gross": "833.00",
            "currency": "EUR",
            "confidence": 0.9,
        }
    )
    ai = einvoice.ai_conflicts(xml_fields, ai_fields)
    assert [(c["field"], c["xml"], c["other"]) for c in ai] == [
        ("invoice_number", "RE-2026-042", "RE-2026-099"),
        ("net", "500.00", "700.00"),
        ("vat", "95.00", "133.00"),
        ("gross", "595.00", "833.00"),
    ]
    assert all(c["other_source"] == "ai" for c in ai)
    # Same values in another spelling are no conflict (595.00 vs 595.0, same supplier).
    agreeing = field_confidences(
        {
            "supplier_name": "Belegki Handwerk GmbH ",
            "invoice_number": "re-2026-042",
            "net": "500.0",
            "vat": "95",
            "gross": "595.0",
            "confidence": 0.9,
        }
    )
    assert einvoice.ai_conflicts(xml_fields, agreeing) == []


def test_formal_findings_name_missing_mandatory_fields_and_arithmetic() -> None:
    xml = UBL.replace("<cbc:ID>RE-2026-042</cbc:ID>", "").replace(
        '<cbc:TaxInclusiveAmount currencyID="EUR">595.00</cbc:TaxInclusiveAmount>',
        '<cbc:TaxInclusiveAmount currencyID="EUR">600.00</cbc:TaxInclusiveAmount>',
    )
    inv = einvoice.parse_xml(xml.encode())
    findings = einvoice.formal_findings(inv)
    assert findings == [
        "E-Rechnung: Pflichtangabe fehlt im XML: Rechnungsnummer",
        "E-Rechnung: Netto plus Steuer ergibt im XML nicht den Bruttobetrag (500.00 + 95.00 "
        "gegenüber 600.00)",
    ]
    # Line totals against the net amount.
    inv.lines[0].net = "450.00"
    assert any("Summe der Positionen (550.00)" in f for f in einvoice.formal_findings(inv))


def test_d44_section_35a_estimate_is_never_evidence() -> None:
    base = {"supplier_name": "X", "net": "500", "vat": "95", "gross": "595", "confidence": 0.9}
    estimate = field_confidences(
        {**base, "section_35a_amount": "300.00", "section_35a_basis": None}
    )
    assert estimate["section_35a_amount"]["source"] == "ai_estimate"
    assert estimate["section_35a_amount"]["confidence"] == 0
    assert estimate["section_35a_amount"]["value"] == "300.00"
    assert "nicht als belegt" in (estimate["section_35a_amount"]["note"] or "")
    assert estimate_findings(estimate) == [
        "§-35a-Anteil 300.00 ist nur eine KI-Schätzung und nicht belegt: keine Übernahme, "
        "belegbare Aufteilung (Positionsbeleg oder Rechnungsangabe) beim Aussteller "
        "nachfordern (PÜ03, D44)."
    ]
    explicit = field_confidences(
        {**base, "section_35a_amount": "300.00", "section_35a_basis": "estimate"}
    )
    assert explicit["section_35a_amount"]["source"] == "ai_estimate"
    stated = field_confidences(
        {**base, "section_35a_amount": "300.00", "section_35a_basis": "invoice_statement"}
    )
    assert stated["section_35a_amount"]["source"] == "ai"
    assert stated["section_35a_amount"]["confidence"] == 0.9
    assert estimate_findings(stated) == []
    missing = field_confidences(base)
    assert missing["section_35a_amount"] == {
        "value": None,
        "confidence": 0,
        "source": "none",
        "note": None,
    }
    assert estimate_findings(missing) == []
