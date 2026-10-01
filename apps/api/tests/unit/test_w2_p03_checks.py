"""Wave 2 P03: pure checks of the incoming invoice (PÜ01, PÜ03), plan dates, e-invoice
evidence (S711-01, S711-04) and the credit note XRechnung (S711-02). Expected values are
fixed by hand: 2 % of 1.190,00 = 23,80; 119,00 at 19 % = 100,00 + 19,00; 31.01. monthly gives
28.02. and 31.03.; credit note of 119,00 states 119,00 positive with reference HVM-2026-000001."""

import hashlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]

from mhvp.accounting import invoice_checks as ic
from mhvp.accounting import xrechnung as x
from mhvp.accounting import xrechnung_credit as xc
from mhvp.accounting.creditor_routers import add_months, split_gross
from mhvp.accounting.models import Invoice
from mhvp.receipts import einvoice
from tests.unit.test_m13_xrechnung import _data
from tests.unit.test_m14_einvoice import CII, PDF_TEXT_MATCHING, make_zugferd_pdf


def _inv(**over: Any) -> Invoice:
    values: dict[str, Any] = {
        "document_id": None,
        "provider_contact_id": "p",
        "recipient_name": None,
        "service_place": None,
        "service_from": date(2026, 1, 1),
        "service_to": date(2026, 1, 31),
        "invoice_date": date(2026, 2, 1),
        "number": "R-1",
        "gross": Decimal("1190.00"),
        "vat": Decimal("190.00"),
        "issuer_vat_id": None,
        "issuer_tax_number": None,
        "order_reference": None,
        "service_contract_id": None,
        "discount_percent": Decimal("2"),
        "discount_amount": Decimal("23.80"),
        "prepaid_amount": None,
        "retention_amount": None,
        "reverse_charge": False,
        "construction_withholding": False,
        "deductions": [],
    }
    values.update(over)
    return cast(Invoice, SimpleNamespace(**values))


def test_pu01_checklist_and_completeness() -> None:
    inv = _inv()
    checklist = {i["item"]: i["present"] for i in ic.mandatory_checklist(inv)}
    assert checklist["service_place"] is False
    assert checklist["tax_data"] is False
    assert checklist["service_period"] is True
    findings = ic.completeness_findings(inv)
    assert "Leistungsort fehlt (PÜ01)" in findings
    reversed_period = _inv(service_from=date(2026, 2, 1), service_to=date(2026, 1, 1))
    assert "Leistungszeitraum: Ende liegt vor dem Beginn" in ic.completeness_findings(
        reversed_period
    )
    crossing = _inv(service_from=date(2025, 12, 1), service_place="x", issuer_vat_id="DE1")
    assert any("Wirtschaftsjahr" in f for f in ic.completeness_findings(crossing))
    # Fiscal year starting in July: December to January is the same year.
    assert not any("Wirtschaftsjahr" in f for f in ic.completeness_findings(crossing, 7))


def test_pu03_discount_payable_and_markers() -> None:
    assert ic.stated_discount(_inv()) == Decimal("23.80")
    assert ic.amount_findings(_inv()) == []
    wrong = ic.amount_findings(_inv(discount_amount=Decimal("25.00")))
    assert wrong == ["Skonto nachgerechnet 23.80 statt angegeben 25.00"]
    inv = _inv(prepaid_amount=Decimal("100.00"), retention_amount=Decimal("59.50"))
    assert ic.payable_amount(inv) == Decimal("1030.50")
    assert ic.payable_amount(inv, Decimal("1100.00")) == Decimal("-69.50")
    over = _inv(prepaid_amount=Decimal("1200.00"))
    assert "Abzüge, Anzahlungen und Einbehalt übersteigen den Rechnungsbetrag" in (
        ic.amount_findings(over)
    )
    rc = ic.amount_findings(_inv(reverse_charge=True, construction_withholding=True))
    assert "Reverse Charge gekennzeichnet, aber Umsatzsteuer ausgewiesen" in rc
    assert any("Bauabzugsteuer" in f for f in rc)


def test_plan_month_end_and_gross_split() -> None:
    assert add_months(date(2026, 1, 31), 1, 31) == date(2026, 2, 28)
    assert add_months(date(2026, 2, 28), 1, 31) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 30), 3, 30) == date(2027, 2, 28)
    assert add_months(date(2027, 12, 15), 1, 15) == date(2028, 1, 15)
    assert split_gross(Decimal("119.00"), Decimal("19")) == (Decimal("100.00"), Decimal("19.00"))
    assert split_gross(Decimal("80.00"), Decimal("0")) == (Decimal("80.00"), Decimal("0.00"))
    net, vat = split_gross(Decimal("10.00"), Decimal("19"))
    assert net + vat == Decimal("10.00")


def test_s711_evidence_validation_and_hybrid_deviations() -> None:
    pdf = make_zugferd_pdf(PDF_TEXT_MATCHING, CII)
    evidence = einvoice.archive_evidence("application/pdf", pdf)
    assert evidence["original_sha256"] == hashlib.sha256(pdf).hexdigest()
    found = einvoice.embedded_xml(pdf)
    assert found is not None
    assert evidence["structured_sha256"] == hashlib.sha256(found[1]).hexdigest()
    assert evidence["structured_name"] == "factur-x.xml"
    xml = CII.encode()
    assert einvoice.archive_evidence("application/xml", xml)["structured_sha256"] == (
        hashlib.sha256(xml).hexdigest()
    )
    assert einvoice.archive_evidence("application/pdf", None)["original_sha256"] is None

    inv = einvoice.read("application/pdf", pdf).einvoice
    assert inv is not None
    validation = einvoice.formal_validation(inv, [])
    assert validation["validator"] == einvoice.FORMAL_CHECK_NAME
    assert validation["official"] is False
    assert validation["result"] == "ok"
    deviations = {d["field"] for d in einvoice.hybrid_deviations(inv, "\n".join(PDF_TEXT_MATCHING))}
    # Net, tax and invoice date are printed; due date 15.03.2026 and the IBAN are not.
    assert deviations == {"due_date", "iban"}
    assert einvoice.hybrid_deviations(inv, "") == []


def test_s711_02_credit_note_xml_with_billing_reference() -> None:
    data = _data(
        number="HVM-2026-000002",
        net=Decimal("-100.00"),
        vat=Decimal("-19.00"),
        gross=Decimal("-119.00"),
        lines=[x.Line(ln.text, ln.quantity, ln.unit_price, -ln.amount) for ln in _data().lines],
    )
    xml = xc.build_credit_note_xml(data, "HVM-2026-000001", date(2026, 9, 26))
    root = SafeET.fromstring(xml)
    ns = {"cn": xc.NS_CREDIT_NOTE, "cac": x.NS_CAC, "cbc": x.NS_CBC}
    assert root.tag == f"{{{xc.NS_CREDIT_NOTE}}}CreditNote"
    assert root.findtext("cbc:CreditNoteTypeCode", namespaces=ns) == "381"
    ref = "cac:BillingReference/cac:InvoiceDocumentReference/"
    assert root.findtext(ref + "cbc:ID", namespaces=ns) == "HVM-2026-000001"
    assert root.findtext(ref + "cbc:IssueDate", namespaces=ns) == "2026-09-26"
    assert root.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=ns) == "119.00"
    assert root.findall("cac:CreditNoteLine", namespaces=ns)
    tags = [child.tag.split("}")[1] for child in root]
    assert tags.index("BillingReference") < tags.index("AccountingSupplierParty")
    assert xc.check_credit_note(xml) == []
    broken = xml.replace(b"<cbc:ID>HVM-2026-000001</cbc:ID>", b"<cbc:ID></cbc:ID>")
    assert [f.code for f in xc.check_credit_note(broken)] == ["BT-25"]
    assert xc.check_credit_note(x.build_xml(_data()))[0].code == "UBL"


def test_reverse_charge_flags_13b_release_point() -> None:
    """GA08-01: the flag adds an explicit § 13b UStG release point, never an automatic rule."""
    out = ic.amount_findings(_inv(reverse_charge=True))
    assert any("§ 13b UStG" in f and "keine Automatik" in f for f in out)
    assert not any("§ 13b UStG" in f for f in ic.amount_findings(_inv(reverse_charge=False)))


def test_reverse_charge_13b_triggers_no_automation() -> None:
    """AB10 GA08-01: the flag only adds hints; amounts, VAT and flags stay as entered."""
    inv = _inv(reverse_charge=True, vat=Decimal("0.00"), gross=Decimal("1000.00"))
    before = (inv.gross, inv.vat, inv.reverse_charge, inv.construction_withholding)
    out = ic.amount_findings(inv)
    assert (inv.gross, inv.vat, inv.reverse_charge, inv.construction_withholding) == before
    assert sum("§ 13b UStG" in f for f in out) == 1
    assert not any("Umsatzsteuer ausgewiesen" in f for f in out)
