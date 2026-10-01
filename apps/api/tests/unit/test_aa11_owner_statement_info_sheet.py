"""AA11 (GA03-08, GA06-02, GA06-03): pure parts with hand computed expectations.

- receipts: entries 150,00 (no receipt) and 49,50 (receipt d1) -> total 199,50, linked 1,
  missing 1, finding RECEIPT_MISSING (no receipt substituted);
- § 35a: per unit share of the WEG statement 120,00 (unit u1) and 30,00 (unit u2) -> total
  150,00, information only; SEV without shares -> empty block, no finding;
- info sheet: positions 1.200,00 and 300,00 -> sum 1.500,00, texts pending until released.
"""

from datetime import date

from mhvp.billing import info_sheet
from mhvp.billing.owner_statement import receipt_list, section_35a


def test_receipt_list_marks_missing_receipts() -> None:
    out, findings = receipt_list(
        [
            {"journal_entry_id": "e1", "booking_date": "2025-03-10", "text": "HM", "amount": "150"},
            {
                "journal_entry_id": "e2",
                "booking_date": "2025-04-02",
                "text": "Reinigung",
                "amount": "49.50",
                "document_id": "d1",
            },
        ]
    )
    assert (out["total"], out["linked"], out["missing"]) == ("199.50", 1, 1)
    assert [line["receipt_linked"] for line in out["lines"]] == [False, True]
    assert [f["code"] for f in findings] == ["RECEIPT_MISSING"]
    assert receipt_list([]) == ({"lines": [], "linked": 0, "missing": 0, "total": "0.00"}, [])


def test_section_35a_takes_over_weg_shares_only() -> None:
    hoa = {
        "statement_id": "h1",
        "units": [{"unit_id": "u1", "unit_number": "01"}, {"unit_id": "u2", "unit_number": "02"}],
        "section_35a_per_unit": {"u1": "120", "u2": "30.00"},
    }
    out, findings = section_35a({"kind": "sev_owner", "hoa_statement": hoa})
    assert (out["total"], out["source"], out["hoa_statement_id"]) == (
        "150.00",
        "hoa_statement",
        "h1",
    )
    assert out["lines"][0] == {"unit_id": "u1", "unit_number": "01", "amount": "120.00"}
    assert findings == []
    empty, notes = section_35a({"kind": "sev_owner", "hoa_statement": {"units": [], "x": 1}})
    assert (empty["total"], empty["source"]) == ("0.00", None)
    assert notes == []
    rental, none = section_35a({"kind": "rental_owner"})
    assert rental["per_unit"] == {}
    assert none == []


def test_info_sheet_from_snapshot_inputs() -> None:
    inputs = {
        "positions": [
            {
                "label": "Grundsteuer",
                "amount": "1200.00",
                "allocation_key": {"code": "area", "name": "Wohnfläche"},
                "basis": "Mietvertrag § 4",
            },
            {"label": "Hauswart", "amount": "300.00", "allocation_key": None, "basis": None},
        ]
    }
    rows = info_sheet.positions(inputs)
    assert [r["allocation_key"] for r in rows] == ["Wohnfläche", "Einzelabrechnung"]
    letter = info_sheet.build(
        period_from=date(2025, 1, 1),
        period_to=date(2025, 12, 31),
        object_line="Objekt 1 Test",
        snapshot_inputs=inputs,
        snapshot_hash="a" * 64,
        version=2,
        letter_date=date(2026, 10, 1),
    )
    table = letter.tables["positionen"]
    assert table.rows[-1] == ["Summe", "", "1.500,00 EUR"]
    assert letter.body.count(info_sheet.TEXT_PENDING) == 2
    assert "01.01.2025 bis 31.12.2025" in letter.subject
    released = info_sheet.build(
        period_from=date(2025, 1, 1),
        period_to=date(2025, 12, 31),
        object_line="Objekt 1 Test",
        snapshot_inputs=inputs,
        snapshot_hash="a" * 64,
        version=2,
        letter_date=date(2026, 10, 1),
        texts={"inspection": "Termin nach Vereinbarung", "objection": "Freigegebener Text"},
    )
    assert info_sheet.TEXT_PENDING not in released.body
