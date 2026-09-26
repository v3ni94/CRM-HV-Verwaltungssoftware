"""M12-03: payer's determination from the purpose (D39), deterministic parsing."""

from datetime import date

import pytest

from mhvp.banking.allocation import AllocationHints, matches_item, parse_allocation_hint


@pytest.mark.parametrize(
    ("purpose", "invoices", "charges", "periods"),
    [
        ("Miete 09/2026", (), (), ((2026, 9),)),
        ("Miete 9.2026 Musterstr. 5", (), (), ((2026, 9),)),
        ("Hausgeld September 2026", (), (), ((2026, 9),)),
        ("Hausgeld Sept. 2026", (), (), ((2026, 9),)),
        ("Hausgeld 3. Quartal 2026", (), (), ((2026, 7), (2026, 8), (2026, 9))),
        ("Vorauszahlung Q4/2026", (), (), ((2026, 10), (2026, 11), (2026, 12))),
        ("Miete Maerz", (), (), ((None, 3),)),
        ("Rechnung Nr. RE-2026-0042", ("re-2026-0042",), (), ()),
        ("Re.-Nr. 2026/117 Hausmeister", ("2026/117",), (), ()),
        ("RG-NR 88123 Danke", ("88123",), (), ()),
        ("Sollstellung 4711", (), ("4711",), ()),
        ("Sollstellungsnummer: SST-4711-26", (), ("sst-4711-26",), ()),
        # false positives: IBAN digits, dates and SEPA references are no numbers or periods
        ("DE02 1005 0000 0054 5404 02 Hausgeld", (), (), ()),
        ("Uebertrag von DE02100500000054540402", (), (), ()),
        ("Zahlung vom 05.02.2026", (), (), ()),
        ("EREF+RE-4711-09/2026 MREF+M-2026-01", (), (), ()),
        ("Referenz 12345678 Danke", (), (), ()),
        ("Dauerauftrag Jansen", (), (), ()),
    ],
)
def test_parse(
    purpose: str,
    invoices: tuple[str, ...],
    charges: tuple[str, ...],
    periods: tuple[tuple[int | None, int], ...],
) -> None:
    hints = parse_allocation_hint(purpose)
    assert hints.invoice_numbers == invoices
    assert hints.charge_numbers == charges
    assert hints.periods == periods


def test_units_and_properties() -> None:
    hints = parse_allocation_hint("Hausgeld 10/2026 Obj. 722 WE 12")
    assert hints.properties == ("722",)
    assert hints.units == ("12",)
    assert hints.periods == ((2026, 10),)


def test_empty_purpose() -> None:
    assert parse_allocation_hint("").empty
    assert parse_allocation_hint("Vielen Dank").empty


def test_matches_item_by_period_and_reference() -> None:
    feb = parse_allocation_hint("Hausgeld Februar 2026 V-100")
    assert matches_item(feb, reference=None, period=date(2026, 2, 3))
    assert not matches_item(feb, reference=None, period=date(2026, 1, 3))
    assert not matches_item(feb, reference=None, period=date(2025, 2, 3))
    exact = parse_allocation_hint("Rechnung RE-2026-0042")
    assert matches_item(exact, reference="re 2026/0042", period=None)
    assert not matches_item(exact, reference="RE-2026-0043", period=None)
    assert not matches_item(AllocationHints(), reference="RE-2026-0042", period=date(2026, 2, 1))
