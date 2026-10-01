"""Q15: invoice letter of a fee invoice (M13-05). Expected: net 80,00, 19 % = 15,20, gross 95,20."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from mhvp.accounting import fee_documents as fd
from mhvp.accounting import xrechnung as xr
from mhvp.documents import letters


def _data(sign: int = 1) -> xr.InvoiceData:
    addr = xr.Address("Rheinpromenade 1", "40789", "Monheim am Rhein", "DE")
    return xr.InvoiceData(
        number="PQ-2026-000001",
        issue_date=date(2026, 4, 2),
        buyer_reference="04011000-12345-67",
        seller=xr.Seller(
            name="Hausverwaltung Müller GmbH",
            address=addr,
            vat_id="DE123456789",
            payee_iban="DE02120300000000202051",
        ),
        buyer=xr.Buyer(name="WEG Haus 1", address=addr),
        lines=[xr.Line("Verwaltung", Decimal(2), Decimal("40.00") * sign, Decimal("80.00") * sign)],
        net=Decimal("80.00") * sign,
        vat_percent=Decimal(19),
        vat=Decimal("15.20") * sign,
        gross=Decimal("95.20") * sign,
    )


def _invoice(kind: str) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))


def test_invoice_letter_has_mandatory_blocks_and_renders() -> None:
    letter = fd.build_letter(_data(), _invoice("invoice"))  # type: ignore[arg-type]
    info = dict(letter.info)
    assert info["Datum"] == "02.04.2026"
    assert info["Leistungszeitraum"] == "01.01.2026 bis 31.03.2026"
    assert info["USt-IdNr."] == "DE123456789"
    rows = letter.tables[fd.TABLE].rows
    assert rows[-1] == ["Gesamtbetrag", "", "95,20 EUR"]
    assert "Bitte überweisen Sie 95,20 EUR" in letter.body
    head = letters.Letterhead(
        company={
            "name": "Hausverwaltung Müller GmbH",
            "street": "Str. 1",
            "postal_code": "40789",
            "city": "Monheim",
        },
        branding={},
    )
    assert letters.render_pdf(head, letter).startswith(b"%PDF")


def test_credit_note_letter_names_original_and_keeps_negative_amounts() -> None:
    original = SimpleNamespace(number="PQ-2026-000001", invoice_date=date(2026, 4, 2))
    letter = fd.build_letter(_data(-1), _invoice("credit_note"), original)  # type: ignore[arg-type]
    assert dict(letter.info)["Bezug"] == "Rechnung PQ-2026-000001 vom 02.04.2026"
    assert letter.tables[fd.TABLE].rows[-1][2] == "-95,20 EUR"
    assert "Gutschrift" in letter.subject
    assert "überweisen" not in letter.body
