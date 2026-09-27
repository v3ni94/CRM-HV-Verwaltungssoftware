"""Bank CSV import (M11-02): synthetic sample files per recognised format, encoding/delimiter/
decimal-comma/date robustness, unmatched-format handling, and the generic user mapping path."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.banking import csv_formats
from mhvp.banking.csv_formats import ColumnMapping

SPARKASSE_CAMT = (
    "Auftragskonto;Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;Glaeubiger ID;"
    "Mandatsreferenz;Kundenreferenz (End-to-End);Sammlerreferenz;"
    "Lastschrift Ursprungsbetrag;Auslagenersatz Ruecklastschrift;"
    "Beguenstigter/Zahlungspflichtiger;Kontonummer/IBAN;BIC (SWIFT-Code);Betrag;Waehrung;Info\r\n"
    'DE02120300000000202051;05.01.26;05.01.26;SEPA-GUTSCHRIFT;"Hausgeld Januar Nr. 01, für WE 01";'
    "DE98ZZZ09999999999;M-1;E2E-4711;;;;Maria Mustermann;DE75512108001245126199;"
    "COBADEFFXXX;400,00;EUR;\r\n"
).encode("cp1252")

N26_SAMPLE = (
    b"Date,Payee,Account number,Transaction type,Payment reference,Amount (EUR)\n"
    b"2026-01-05,Maria Mustermann,DE75512108001245126199,Direct Debit,Hausgeld Januar,-45.90\n"
)

DKB_SAMPLE = (
    "Buchungsdatum;Wertstellung;Status;Zahlungspflichtige*r;Zahlungsempfänger*in;"
    "Verwendungszweck;Betrag (€)\n"
    "05.01.2026;05.01.2026;Gebucht;Max Mieter;Hausverwaltung Müller GmbH;"
    "Miete Januar;-950,00\n"
)

UNKNOWN_HEADER = "Datum;Beschreibung;Wert\n05.01.2026;Sonstiges;10,00\n"


def test_sparkasse_camt_detected_and_parsed() -> None:
    result = csv_formats.preview(SPARKASSE_CAMT)
    assert result.format_id == "sparkasse_camt_csv"
    assert result.confidence == "erkannt"
    assert result.encoding == "cp1252"
    assert result.delimiter == ";"
    assert result.row_count == 1
    assert not result.errors
    assert result.parsed is not None
    tx = result.parsed.statements[0].transactions[0]
    assert tx.amount == Decimal("400.00")
    assert tx.booking_date == date(2026, 1, 5)
    assert tx.counterpart_iban == "DE75512108001245126199"
    assert tx.purpose == "Hausgeld Januar Nr. 01, für WE 01"
    assert result.parsed.statements[0].iban == "DE02120300000000202051"


def test_n26_comma_delimited_utf8() -> None:
    result = csv_formats.preview(N26_SAMPLE, own_iban_override="DE75512108001245126199")
    assert result.format_id == "n26_csv"
    assert result.delimiter == ","
    assert result.encoding in ("utf-8", "utf-8-sig")
    assert result.parsed is not None
    tx = result.parsed.statements[0].transactions[0]
    assert tx.amount == Decimal("-45.90")
    assert tx.counterpart_name == "Maria Mustermann"


def test_dkb_detected_but_flagged_for_review() -> None:
    result = csv_formats.preview(DKB_SAMPLE.encode())
    assert result.format_id == "dkb_csv"
    assert result.confidence == "zu_pruefen"
    # DKB export has no own-IBAN column: without an account override no parsed file is built,
    # only a preview (row count and errors), so the CSV is never imported blind.
    assert result.parsed is None
    assert result.row_count == 1


def test_unknown_header_falls_back_to_generic_without_mapping() -> None:
    result = csv_formats.preview(UNKNOWN_HEADER.encode())
    assert result.format_id == csv_formats.GENERIC
    assert result.row_count == 0
    assert result.parsed is None


def test_generic_mapping_overrides_detection() -> None:
    mapping = ColumnMapping(booking_date="datum", amount="wert", purpose="beschreibung")
    result = csv_formats.preview(
        UNKNOWN_HEADER.encode(),
        mapping_override=mapping,
        own_iban_override="DE02120300000000202051",
    )
    assert result.format_id == csv_formats.GENERIC
    assert result.row_count == 1
    tx = result.parsed.statements[0].transactions[0]  # type: ignore[union-attr]
    assert tx.amount == Decimal("10.00")
    assert tx.booking_date == date(2026, 1, 5)


def test_debit_credit_split_columns() -> None:
    text = (
        "Buchungstag;Soll;Haben;Verwendungszweck\n"
        "05.01.2026;120,50;;Miete\n"
        "06.01.2026;;300,00;Gutschrift\n"
    )
    mapping = ColumnMapping(
        booking_date="buchungstag",
        amount_debit="soll",
        amount_credit="haben",
        purpose="verwendungszweck",
    )
    result = csv_formats.preview(text.encode(), mapping_override=mapping, own_iban_override="DE00")
    txs = result.parsed.statements[0].transactions  # type: ignore[union-attr]
    assert txs[0].amount == Decimal("-120.50")
    assert txs[1].amount == Decimal("300.00")


def test_broken_row_reported_as_row_error_not_dropping_the_file() -> None:
    text = "Buchungstag;Betrag;Verwendungszweck\n05.01.2026;100,00;OK\nkein-datum;50,00;Kaputt\n"
    mapping = ColumnMapping(booking_date="buchungstag", amount="betrag", purpose="verwendungszweck")
    result = csv_formats.preview(text.encode(), mapping_override=mapping, own_iban_override="DE00")
    assert result.row_count == 1
    assert len(result.errors) == 1
    assert result.errors[0].line == 3


def test_amount_parsing_variants() -> None:
    assert csv_formats.parse_amount("1.234,56") == Decimal("1234.56")
    assert csv_formats.parse_amount("-45,90") == Decimal("-45.90")
    assert csv_formats.parse_amount("(12,00)") == Decimal("-12.00")
    assert csv_formats.parse_amount("100.00") == Decimal("100.00")
    with pytest.raises(ValueError, match="nicht lesbar"):
        csv_formats.parse_amount("abc")


def test_date_parsing_variants() -> None:
    assert csv_formats.parse_date("05.01.2026") == date(2026, 1, 5)
    assert csv_formats.parse_date("2026-01-05") == date(2026, 1, 5)
    with pytest.raises(ValueError, match="nicht lesbar"):
        csv_formats.parse_date("not-a-date")


def test_garbage_encoding_raises_csv_import_error() -> None:
    with pytest.raises(csv_formats.CsvImportError):
        csv_formats.decode(b"\xff\xfe\x00\x81\x82")
