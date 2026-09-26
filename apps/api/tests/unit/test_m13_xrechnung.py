"""A12 / D41 (formal validity): XRechnung XML for Verwalterhonorar invoices. Expected values
are fixed here, not derived from the generator: 3 x 25,00 = 75,00 plus adjustment 25,00 to
the minimum fee 100,00, 19 % = 19,00, gross 119,00."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]

from mhvp.accounting import xrechnung as x
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantBillingSettings, VatStatus

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
DRAFT: dict[str, Any] = {
    "lines": [{"unit_type": "apartment", "count": 3, "rate": "25.00", "amount": "75.00"}],
    "net": "100.00",
    "vat_percent": "19",
    "vat": "19.00",
    "gross": "119.00",
}


def _lines(draft: dict[str, Any]) -> list[x.Line]:
    return [
        x.Line(
            ln["text"], Decimal(ln["quantity"]), Decimal(ln["unit_price"]), Decimal(ln["amount"])
        )
        for ln in x.fee_lines(draft, "monthly")
    ]


def _data(**overrides: object) -> x.InvoiceData:
    values: dict[str, object] = {
        "number": "HVM-2026-000001",
        "issue_date": date(2026, 9, 26),
        "buyer_reference": "04011000-12345-67",
        "seller": SELLER,
        "buyer": BUYER,
        "lines": _lines(DRAFT),
        "net": Decimal("100.00"),
        "vat_percent": Decimal("19"),
        "vat": Decimal("19.00"),
        "gross": Decimal("119.00"),
    }
    values.update(overrides)
    return x.InvoiceData(**values)  # type: ignore[arg-type]


def _settings(**overrides: object) -> TenantBillingSettings:
    values: dict[str, object] = {
        "vat_status": VatStatus.REGELBESTEUERT,
        "vat_id": "DE123456789",
        "tax_number": None,
        "kleinunternehmer_note": None,
        "leitweg_id": "04011000-12345-67",
        "payee_iban": "DE02120300000000202051",
    }
    values.update(overrides)
    return cast(TenantBillingSettings, SimpleNamespace(**values))


def test_d41_fee_lines_carry_minimum_and_maximum_as_explicit_adjustment() -> None:
    minimum = x.fee_lines(DRAFT, "monthly")
    assert [ln["amount"] for ln in minimum] == ["75.00", "25.00"]
    assert minimum[0]["text"] == "Verwalterhonorar Wohnung, monatlich"
    assert minimum[1] == {
        "text": "Anpassung auf Mindesthonorar",
        "quantity": "1",
        "unit_price": "25.00",
        "amount": "25.00",
    }
    maximum = x.fee_lines(
        {
            **DRAFT,
            "lines": [{**DRAFT["lines"][0], "count": 10, "amount": "250.00"}],
            "net": "200.00",
        },
        "monthly",
    )
    # BR-27: a reduction is quantity -1 with a positive price, never a negative price.
    assert maximum[1] == {
        "text": "Anpassung auf Höchsthonorar",
        "quantity": "-1",
        "unit_price": "50.00",
        "amount": "-50.00",
    }
    assert sum(Decimal(ln["amount"]) for ln in maximum) == Decimal("200.00")


def test_d41_xml_structure_mandatory_fields_and_sums() -> None:
    xml = x.build_xml(_data())
    root = SafeET.fromstring(xml)
    ns = x.NS
    assert root.tag == f"{{{x.NS_INVOICE}}}Invoice"
    assert root.find("cbc:CustomizationID", ns).text == (
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
    )
    assert root.find("cbc:ID", ns).text == "HVM-2026-000001"
    assert root.find("cbc:IssueDate", ns).text == "2026-09-26"
    assert root.find("cbc:DocumentCurrencyCode", ns).text == "EUR"
    assert root.find("cbc:BuyerReference", ns).text == "04011000-12345-67"
    seller = root.find("cac:AccountingSupplierParty/cac:Party", ns)
    assert seller is not None
    assert seller.find("cac:PartyTaxScheme/cbc:CompanyID", ns).text == "DE123456789"
    assert seller.find("cac:Contact/cbc:ElectronicMail", ns).text == "info@example.org"
    buyer = root.find("cac:AccountingCustomerParty/cac:Party", ns)
    assert buyer is not None
    assert buyer.find("cac:PartyName/cbc:Name", ns).text == "WEG Sollhaus"
    endpoint = buyer.find("cbc:EndpointID", ns)
    assert endpoint is not None
    assert endpoint.get("schemeID") == "0204"
    assert (
        root.find("cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", ns).text
        == "DE02120300000000202051"
    )
    total = root.find("cac:LegalMonetaryTotal", ns)
    assert total is not None
    assert total.find("cbc:LineExtensionAmount", ns).text == "100.00"
    assert total.find("cbc:TaxExclusiveAmount", ns).text == "100.00"
    assert total.find("cbc:TaxInclusiveAmount", ns).text == "119.00"
    assert total.find("cbc:PayableAmount", ns).text == "119.00"
    assert root.find("cac:TaxTotal/cbc:TaxAmount", ns).text == "19.00"
    lines = root.findall("cac:InvoiceLine", ns)
    assert [ln.find("cbc:LineExtensionAmount", ns).text for ln in lines] == [
        "75.00",
        "25.00",
    ]
    assert x.check_structure(xml) == []


def test_d41_kleinunternehmer_uses_exemption_category_with_reason() -> None:
    data = _data(
        seller=x.Seller(
            name="Timo Müller",
            address=SELLER.address,
            tax_number="135/5555/1234",
            register_number="HRA 1",
            payee_iban=SELLER.payee_iban,
            email="tm@example.org",
            phone="+49 2173 1",
            contact_name="Timo Müller",
        ),
        vat_percent=Decimal("0"),
        vat=Decimal("0.00"),
        gross=Decimal("100.00"),
        tax_exemption_reason="Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
    )
    xml = x.build_xml(data)
    root = SafeET.fromstring(xml)
    category = root.find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", x.NS)
    assert category is not None
    assert category.find("cbc:ID", x.NS).text == "E"
    assert "§ 19 UStG" in category.find("cbc:TaxExemptionReason", x.NS).text
    schemes = root.findall("cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme", x.NS)
    assert [s.find("cac:TaxScheme/cbc:ID", x.NS).text for s in schemes] == ["FC"]
    assert x.check_structure(xml) == []


def test_d41_structure_check_reports_sum_and_field_findings() -> None:
    wrong = _data(gross=Decimal("120.00"), vat=Decimal("19.50"))
    codes = {f.code for f in x.check_structure(x.build_xml(wrong))}
    assert "BR-CO-15" in codes  # net plus tax is not gross
    assert "BR-CO-17" in codes  # 100,00 x 19 % is 19,00, not 19,50
    bad_line = _data(lines=[x.Line("Honorar", Decimal(3), Decimal("25.00"), Decimal("80.00"))])
    codes = {f.code for f in x.check_structure(x.build_xml(bad_line))}
    assert {"BR-CO-10", "BR-CO-13"} <= codes
    missing = _data(buyer_reference="")
    assert "BT-10" in {f.code for f in x.check_structure(x.build_xml(missing))}
    assert x.check_structure(b"<not xml")[0].code == "XML"
    assert x.check_structure(b"<other/>")[0].code == "UBL"


def test_d41_generation_locked_without_leitweg_id_iban_or_tax_data() -> None:
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(_settings(leitweg_id=None))
    assert info.value.error is ErrorCodes.BILLING_LEITWEG_ID_MISSING
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(_settings(leitweg_id="   "))
    assert info.value.error is ErrorCodes.BILLING_LEITWEG_ID_MISSING
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(_settings(payee_iban=None))
    assert info.value.error is ErrorCodes.BILLING_PAYEE_IBAN_MISSING
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(_settings(vat_status=VatStatus.UNSET))
    assert info.value.error is ErrorCodes.BILLING_VAT_STATUS_MISSING
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(_settings(vat_id=None))
    assert info.value.error is ErrorCodes.BILLING_TAX_DATA_MISSING
    with pytest.raises(ProblemError) as info:
        x.assert_generation_allowed(None)
    assert info.value.error is ErrorCodes.BILLING_VAT_STATUS_MISSING
    x.assert_generation_allowed(_settings())  # complete data: no lock
