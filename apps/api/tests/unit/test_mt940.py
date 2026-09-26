"""MT940 parser (A28, M11-02) with synthetic statements only: standard case with the German
``:86:`` subfield convention, several statements in one file, intermediate balances
``:60M:``/``:62M:``, raw text fallback for an unknown ``:86:`` layout, reversal lines and
format detection on the `FileConnector` seam."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.banking import mt940
from mhvp.banking.connectors import FileConnector

IBAN = "DE02120300000000202051"
PAYER = "DE75512108001245126199"

STANDARD = f""":20:STARTUMSE
:25:{IBAN}
:28C:00017/001
:60F:C260104EUR10000,00
:61:2601050105CR400,00NTRFNONREF//BANKREF-1
:86:166?00SEPA-GUTSCHRIFT?10931?20EREF+E2E-4711?21MREF+M-1?22CRED+DE98ZZZ0
9999999999?23SVWZ+Hausgeld Januar WE 01?30COBADEFFXXX?31{PAYER}?32Maria Muster
?33mann?34000
:61:2601100110DR1000,00NMSCNONREF
:86:177?00UEBERWEISUNG?20Umbuchung Ruecklage?3037040044?310532013000?32GdWE Bankhaus
:62F:C260131EUR9400,00
-
"""


def test_standard_statement_with_dk_subfields() -> None:
    parsed = mt940.parse(STANDARD.encode())
    assert parsed.version == "mt940"
    assert len(parsed.statements) == 1
    stmt = parsed.statements[0]
    assert stmt.iban == IBAN
    assert stmt.statement_ref == "00017/001"
    assert stmt.currency == "EUR"
    assert (stmt.opening_balance, stmt.closing_balance) == (Decimal("10000.00"), Decimal("9400.00"))
    assert (stmt.from_date, stmt.to_date) == (date(2026, 1, 4), date(2026, 1, 31))
    assert len(stmt.transactions) == 2

    credit, debit = stmt.transactions
    assert credit.amount == Decimal("400.00")
    assert credit.currency == "EUR"
    assert (credit.booking_date, credit.value_date) == (date(2026, 1, 5), date(2026, 1, 5))
    assert credit.bank_reference == "BANKREF-1"
    assert credit.raw["reference_source"] == "61//bank_reference"
    assert credit.raw["customer_reference"] == "NONREF"
    assert credit.raw["transaction_type"] == "NTRF"
    assert credit.transaction_code == "166"
    assert credit.purpose == "Hausgeld Januar WE 01"
    assert credit.end_to_end_id == "E2E-4711"
    assert credit.mandate_reference == "M-1"
    assert credit.creditor_id == "DE98ZZZ09999999999"  # continuation line joined
    assert credit.counterpart_name == "Maria Mustermann"
    assert credit.counterpart_iban == PAYER
    assert credit.counterpart_bic == "COBADEFFXXX"
    assert credit.raw["info"]["convention"] == "dk_subfields"
    assert credit.raw["info"]["posting_text"] == "SEPA-GUTSCHRIFT"
    assert credit.raw["info"]["info_raw"].startswith("166?00SEPA-GUTSCHRIFT")

    assert debit.amount == Decimal("-1000.00")
    assert debit.booking_date == date(2026, 1, 10)
    # No ``//`` bank reference: a deterministic reference from statement number, line and
    # value date, so that a re-import of the same file is recognised (D05), marked as derived.
    assert debit.bank_reference == "00017/001/2/2026-01-10"
    assert debit.raw["reference_source"] == "derived:28C/line/value_date"
    assert debit.purpose == "Umbuchung Ruecklage"
    assert debit.counterpart_name == "GdWE Bankhaus"
    assert debit.counterpart_iban is None  # BLZ/Konto is not an IBAN, kept raw only
    assert debit.raw["info"]["counterpart_account"] == "0532013000"
    assert debit.raw["info"]["counterpart_bank"] == "37040044"
    assert debit.counterpart_bic is None
    assert debit.end_to_end_id is None


def test_multiple_statements_in_one_file_with_swift_blocks() -> None:
    second = f""":20:STARTUMSE
:25:{IBAN}
:28C:00018/001
:60F:C260131EUR9400,00
:61:2602030203CR200,00NTRFNONREF
:86:166?20SVWZ+Nachzahlung?32Zahler
:62F:C260228EUR9600,00
-
"""
    wrapped = "{1:F01BANKDEFFAXXX0000000000}{2:I940BANKDEFFXXXXN}{4:\n" + STANDARD + "}"
    wrapped += "{1:F01BANKDEFFAXXX0000000000}{2:I940BANKDEFFXXXXN}{4:\n" + second + "}"
    parsed = mt940.parse(wrapped.encode("latin-1"))
    assert [s.statement_ref for s in parsed.statements] == ["00017/001", "00018/001"]
    assert parsed.statements[1].opening_balance == parsed.statements[0].closing_balance
    assert parsed.statements[1].transactions[0].bank_reference == "00018/001/1/2026-02-03"

    plain = mt940.parse((STANDARD + second).encode())
    assert [s.statement_ref for s in plain.statements] == ["00017/001", "00018/001"]


def test_intermediate_balances_60m_62m_and_year_turn() -> None:
    text = f""":20:STARTUMSE
:25:{IBAN}
:28C:00001/002
:60M:D251231EUR500,00
:61:2601020101CR300,00NTRFNONREF
:86:166?20SVWZ+Miete Januar
:61:2512311231DR20,00NCHGNONREF
:86:808?20Entgelt
:62M:D260102EUR220,00
"""
    stmt = mt940.parse(text.encode()).statements[0]
    assert stmt.opening_balance == Decimal("-500.00")
    assert stmt.closing_balance == Decimal("-220.00")
    assert stmt.from_date == date(2025, 12, 31)
    assert stmt.to_date == date(2026, 1, 2)
    first, second = stmt.transactions
    # Entry date 0101 with value date 02.01.2026 stays in 2026; entry 1231 with value
    # 31.12.2025 stays in 2025 (no year in the entry date).
    assert (first.booking_date, first.value_date) == (date(2026, 1, 1), date(2026, 1, 2))
    assert (second.booking_date, second.value_date) == (date(2025, 12, 31), date(2025, 12, 31))
    assert second.transaction_code == "808"


def test_year_turn_between_entry_and_value_date() -> None:
    text = f""":20:X
:25:{IBAN}
:28C:1/1
:60F:C251231EUR0,00
:61:2601021230DR10,00NMSCNONREF
:86:999?20x
:61:2512310102CR10,00NMSCNONREF
:86:999?20y
:62F:C260102EUR0,00
"""
    a, b = mt940.parse(text.encode()).statements[0].transactions
    assert a.booking_date == date(2025, 12, 30)  # entry in December of the previous year
    assert b.booking_date == date(2026, 1, 2)  # entry in January of the next year


def test_raw_text_fallback_and_missing_86() -> None:
    text = f""":20:X
:25:{IBAN}
:28C:2/1
:60F:C260101EUR0,00
:61:2601050105CR50,00NTRFKUNDENREF//BR-7
:86:Freitext ohne Unterfelder
Zweite Zeile
:61:2601060106DR5,00NCHGNONREF
:62F:C260106EUR45,00
"""
    stmt = mt940.parse(text.encode()).statements[0]
    first, second = stmt.transactions
    assert first.raw["info"]["convention"] is None
    assert first.raw["info"]["info_raw"] == "Freitext ohne Unterfelder\nZweite Zeile"
    assert first.purpose == "Freitext ohne Unterfelder Zweite Zeile"
    assert first.counterpart_name is None
    assert first.counterpart_iban is None
    assert first.transaction_code == "NTRF"  # no GVC known, the SWIFT type code is kept
    assert first.raw["customer_reference"] == "KUNDENREF"
    assert first.bank_reference == "BR-7"
    assert second.raw["info"]["info_raw"] is None
    assert second.purpose is None
    assert second.amount == Decimal("-5.00")


def test_reversal_and_account_forms() -> None:
    text = """:20:X
:25:37040044/0532013000
:28C:3/1
:60F:C260101EUR100,00
:61:2601050105RC30,00NRTINONREF
:86:159?20Rueckbuchung
:61:2601050105RD30,00NRTINONREF
:86:159?20Rueckbuchung
:62F:C260105EUR100,00
"""
    stmt = mt940.parse(text.encode()).statements[0]
    assert stmt.iban == "37040044/0532013000"  # not an IBAN: refused later by account matching
    rc, rd = stmt.transactions
    assert rc.amount == Decimal("-30.00")  # reversal of a credit
    assert rd.amount == Decimal("30.00")  # reversal of a debit
    assert rc.raw["debit_credit"] == "RC"
    with_iban = mt940.parse(text.replace("37040044/0532013000", f"BLZ/{IBAN}").encode())
    assert with_iban.statements[0].iban == IBAN


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<Document/>", "kein MT940"),
        (":20:X\n:28C:1\n:60F:C260101EUR0,00\n:62F:C260101EUR0,00\n", ":25:"),
        (f":20:X\n:25:{IBAN}\n:28C:1\n:62F:C260101EUR0,00\n", "Anfangs- oder Schlusssaldo"),
        (f":20:X\n:25:{IBAN}\n:60F:C260101EUR0,00\n:62F:C260101USD0,00\n", "Währungen"),
        (
            f":20:X\n:25:{IBAN}\n:60F:C260101EUR0,00\n:61:kaputt\n:62F:C260101EUR0,00\n",
            "Zeile :61:",
        ),
        (
            f":20:X\n:25:{IBAN}\n:60F:C260101EUR0,00\n:61:2601050105CR1,234NTRFX\n"
            ":62F:C260101EUR0,00\n",
            "Nachkommastellen",
        ),
    ],
)
def test_unsupported_structures_are_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        mt940.parse(text.encode())


def test_format_detection_on_file_connector() -> None:
    assert FileConnector.detect_format(STANDARD.encode(), "auszug.xml") == "mt940"  # content
    assert FileConnector.detect_format(b"\xef\xbb\xbf" + STANDARD.encode(), None) == "mt940"
    assert FileConnector.detect_format(b"{1:F01X}{4:\n:20:X\n-}", None) == "mt940"
    assert FileConnector.detect_format(b"<Document/>", "auszug.sta") == "mt940"  # suffix
    assert FileConnector.detect_format(b"<Document/>", "auszug.xml") == "camt"
    assert FileConnector.parse(STANDARD.encode(), "k.sta").version == "mt940"
    with pytest.raises(ValueError, match="XML"):
        FileConnector.parse(b"kein xml", "k.xml")
    with pytest.raises(ValueError, match="MT940"):
        FileConnector.parse(b"<a/>", "k.sta")
