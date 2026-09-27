"""M18-01 Folgepunkt (docs/rules/M18-06 Abschnitt Konto/Gegenkonto-Bildung, Entwurf,
Quellenstatus zu prüfen durch Steuerberater): Konto/Gegenkonto-Paarbildung in
``mhvp.accounting.reports.datev_csv`` (``_split_group_target``, ``_stapel_row``) und die
Auswirkung auf die Selbstprüfung ``mhvp.accounting.datev_check``.

Pure unit tests: the ORM instances below are built in memory only (no session, no database);
the pairing helpers just read their plain attributes.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from mhvp.accounting import datev_check
from mhvp.accounting.models import JournalEntry, JournalLine, LedgerAccount
from mhvp.accounting.reports import _split_group_target, _stapel_row


def _line(*, debit: Decimal = Decimal("0.00"), credit: Decimal = Decimal("0.00")) -> JournalLine:
    return JournalLine(id=uuid4(), debit=debit, credit=credit, text=None)


def _account(number: str) -> LedgerAccount:
    return LedgerAccount(number=number, name=f"Konto {number}")


def _entry(**kw: Any) -> JournalEntry:
    defaults: dict[str, Any] = {
        "booking_date": date(2026, 5, 1),
        "text": "Buchung",
        "reference": "TB-1",
        "document_id": None,
    }
    defaults.update(kw)
    return JournalEntry(**defaults)


def _header_and_body(stapel_rows: list[list[str]]) -> str:
    """Build a minimal but well formed EXTF file (header, column header, given rows) so that
    ``datev_check.check_batch`` can run against it, mirroring ``reports.datev_csv``."""
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "EXTF",
            "700",
            "21",
            "Buchungsstapel",
            "7",
            "20260501000000000",
            "",
            "RE",
            "",
            "",
            "1001",
            "10001",
            "20260101",
            "4",
            "20260501",
            "20260531",
            "",
            "",
            "1",
            "SKR03",
            "0",
        ]
    )
    writer.writerow(
        [
            datev_check.COL_AMOUNT,
            datev_check.COL_SH,
            datev_check.COL_ACCOUNT,
            datev_check.COL_CONTRA,
            datev_check.COL_DATE,
            datev_check.COL_TEXT,
            datev_check.COL_REF,
        ]
    )
    for row in stapel_rows:
        writer.writerow(row)
    return out.getvalue()


# Konto/Gegenkonto pairing --------------------------------------------------------------


def test_two_line_booking_is_not_a_split() -> None:
    """A booking with exactly one Soll and one Haben line is handled by the dedicated two
    line branch in ``reports.datev_csv``, not by ``_split_group_target`` (both sides have
    exactly one line, so no single summing side can be told apart)."""
    debit = _line(debit=Decimal("250.00"))
    credit = _line(credit=Decimal("250.00"))
    result = _split_group_target([(debit, _account("1200")), (credit, _account("8400"))])
    assert result is None
    # Konto/Gegenkonto: Soll line as Konto, Haben line as Gegenkonto, one Stapelzeile.
    entry = _entry()
    row = _stapel_row(entry, debit, "1200", "8400")
    assert row[0] == "250,00"
    assert row[1] == "S"
    assert row[2] == "1200"
    assert row[3] == "8400"


def test_split_booking_with_one_summing_side() -> None:
    """Three debit lines against a single credit line (Sammelkonto = the credit account, the
    side with exactly one line)."""
    d1, d2, d3 = (_line(debit=Decimal(v)) for v in ("100.00", "50.00", "30.00"))
    c1 = _line(credit=Decimal("180.00"))
    lines = [
        (d1, _account("4200")),
        (d2, _account("4210")),
        (d3, _account("4250")),
        (c1, _account("1200")),
    ]
    result = _split_group_target(lines)
    assert result is not None
    (summen_line, _summen_account), split_lines = result
    assert summen_line is c1
    assert {id(sl[0]) for sl in split_lines} == {id(d1), id(d2), id(d3)}


def test_split_booking_without_single_summing_side_is_not_representable() -> None:
    """Two debit lines and two credit lines: neither side has exactly one line, so the split
    cannot be paired this way (docs/rules/M18-06)."""
    d1, d2 = (_line(debit=Decimal(v)) for v in ("100.00", "50.00"))
    c1, c2 = (_line(credit=Decimal(v)) for v in ("80.00", "70.00"))
    lines = [
        (d1, _account("4200")),
        (d2, _account("4210")),
        (c1, _account("1200")),
        (c2, _account("1201")),
    ]
    assert _split_group_target(lines) is None


# Effect on the self check ---------------------------------------------------------------


def test_self_check_has_no_dc14_on_two_line_bookings() -> None:
    """The formerly known finding (DC-14 on every line, Gegenkonto empty) does not occur once
    Konto and Gegenkonto are filled from a real two line booking."""
    entry = _entry()
    debit = _line(debit=Decimal("250.00"))
    row = _stapel_row(entry, debit, "1200", "8400")
    content = _header_and_body([row])
    report = datev_check.check_batch(content)
    dc14 = [f for f in report.findings if f.rule == "DC-14"]
    assert dc14 == []
    assert report.status in ("formal_ok", "mit_hinweisen")


def test_self_check_has_no_dc14_on_representable_split() -> None:
    entry = _entry()
    d1, d2 = (_line(debit=Decimal(v)) for v in ("100.00", "50.00"))
    rows = [
        _stapel_row(entry, d1, "4200", "1200"),
        _stapel_row(entry, d2, "4210", "1200"),
    ]
    report = datev_check.check_batch(_header_and_body(rows))
    assert [f for f in report.findings if f.rule == "DC-14"] == []


def test_split_amounts_match_journal_per_booking() -> None:
    """The sum of the written split lines equals the journal amount of the booking on both
    sides (double entry stays balanced, no silent rounding or loss)."""
    debit_amounts = [Decimal("100.00"), Decimal("50.00"), Decimal("30.00")]
    lines = [_line(debit=a) for a in debit_amounts]
    credit_line = _line(credit=sum(debit_amounts, Decimal("0.00")))
    grouped = [(line, _account("4200")) for line in lines] + [(credit_line, _account("1200"))]
    result = _split_group_target(grouped)
    assert result is not None
    (summen_line, _summen_account), split_lines = result
    assert summen_line.credit == sum(debit_amounts, Decimal("0.00"))
    entry = _entry()
    written = [
        _stapel_row(entry, split_line, "4200", "1200") for split_line, _account_ in split_lines
    ]
    total_written = sum((Decimal(row[0].replace(",", ".")) for row in written), Decimal("0.00"))
    assert total_written == summen_line.credit == sum(debit_amounts, Decimal("0.00"))
