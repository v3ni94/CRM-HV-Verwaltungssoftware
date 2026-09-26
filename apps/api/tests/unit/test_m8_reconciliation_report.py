"""Pure parts of the reconciliation report (A68): row aggregation with Soll/Haben or signed
amount, normalisation of numbers, column validation, German CSV, beat time from settings."""

from datetime import date
from decimal import Decimal

import pytest
from celery.schedules import crontab

from mhvp.core.config import Settings
from mhvp.core.problems import ProblemError
from mhvp.imports import reconciliation as rec
from mhvp.imports.models import ReportType
from mhvp.imports.tasks import beat_time
from mhvp.worker import create_celery
from tests.conftest import make_settings

J = ReportType.JOURNAL
B = ReportType.BANK_TRANSACTIONS


def test_normalisers() -> None:
    assert rec.normalise_property_number("7") == "007"
    assert rec.normalise_property_number(81.0) == "081"
    assert rec.normalise_property_number("10012") == "10012"
    assert rec.normalise_property_number(" ") is None
    assert rec.normalise_account_number("1200") == "001200"
    assert rec.normalise_account_number(1200.0) == "001200"
    assert rec.normalise_account_number("09-0001") == "090001"
    assert rec.normalise_account_number("") is None
    assert rec.normalise_iban("de02 1203 0000 0000 2020 51") == "DE02120300000000202051"


def test_aggregate_journal_signed_amount_and_debit_credit() -> None:
    columns = rec.DEFAULT_COLUMNS
    rows = [
        (J, 2, {"Objekt": "12", "Konto": "1200", "Datum": "05.01.2026", "Betrag": "1.000,50"}),
        (
            J,
            3,
            {"Objekt": "12", "Konto": "1200", "Datum": "06.01.2026", "Soll": "", "Haben": "200"},
        ),
        (
            J,
            4,
            {"Objekt": "12", "Konto": "1200", "Datum": "07.01.2026", "Soll": "10", "Haben": "4"},
        ),
        (J, 5, {"Objekt": "12", "Konto": "1200", "Datum": "01.02.2026", "Betrag": "99"}),
        (J, 6, {"Objekt": "12", "Konto": "1200", "Datum": "kein Datum", "Betrag": "1"}),
        (J, 7, {"Objekt": "12", "Konto": "", "Datum": "05.01.2026", "Betrag": "1"}),
        (J, 8, {"Objekt": "12", "Konto": "1300", "Datum": "05.01.2026"}),
    ]
    agg = rec.aggregate_rows(rows, columns, date(2026, 1, 31))
    # 1.000,50 - 200,00 + (10,00 - 4,00) = 806,50; row 5 after as_of, rows 6 to 8 invalid.
    assert agg.journal == {("012", "001200"): Decimal("806.50")}
    assert dict(agg.counts) == {"journal": 3, "after_as_of": 1, "invalid": 3}
    assert agg.max_date == date(2026, 1, 7)
    assert [w.split(":")[0] for w in agg.warnings] == [
        "journal Zeile 6",
        "journal Zeile 7",
        "journal Zeile 8",
    ]
    assert "Betrag fehlt" in agg.warnings[2]


def test_aggregate_bank_rows_balance_and_credits() -> None:
    iban = "DE02120300000000202051"
    rows = [
        (
            B,
            2,
            {"Objekt": "801", "IBAN": iban, "Datum": "12.01.2026", "Betrag": "-50", "Saldo": "950"},
        ),
        (
            B,
            3,
            {
                "Objekt": "801",
                "IBAN": iban,
                "Datum": "10.01.2026",
                "Betrag": "300",
                "Saldo": "1.000,00",
            },
        ),
        (B, 4, {"Objekt": "801", "IBAN": iban, "Datum": "10.01.2026", "Betrag": "100"}),
        (B, 5, {"Objekt": "801", "IBAN": "", "Datum": "10.01.2026", "Betrag": "100"}),
    ]
    agg = rec.aggregate_rows(rows, rec.DEFAULT_COLUMNS, None)
    entry = agg.bank[("801", iban)]
    # Credits 300 + 100 = 400; turnover 350; latest balance by date is row 2 (12.01.): 950.
    assert entry["credits"] == Decimal("400.00")
    assert entry["turnover"] == Decimal("350.00")
    assert entry["balance"] == Decimal("950.00")
    assert (entry["from_date"], entry["to_date"]) == (date(2026, 1, 10), date(2026, 1, 12))
    assert dict(agg.counts) == {"bank_transactions": 3, "invalid": 1}
    assert agg.properties == ["801"]


def test_compare_property_without_platform_property() -> None:
    agg = rec.SourceAggregate(journal={("999", "001200"): Decimal("1.00")})
    lines = rec.compare_property("999", agg, rec.PlatformFigures(), {})
    assert lines == [
        {
            "property_number": "999",
            "metric": "kontosaldo",
            "key": "001200",
            "source": "1.00",
            "platform": None,
            "difference": None,
            "deviates": True,
            "hint": "Objekt nicht auf der Plattform",
        }
    ]


def test_validate_columns() -> None:
    checked = rec.validate_columns({"journal": {"property_number": "O", "account_number": "K"}})
    assert checked["journal"] == {"property_number": "O", "account_number": "K"}
    assert checked["bank_transactions"] == rec.DEFAULT_COLUMNS["bank_transactions"]
    with pytest.raises(ProblemError):
        rec.validate_columns({"payments": {}})
    with pytest.raises(ProblemError):
        rec.validate_columns({"journal": {"property_number": "O", "nope": "x"}})
    with pytest.raises(ProblemError):
        rec.validate_columns({"bank_transactions": {"property_number": "O", "iban": "I"}})


def test_format_eur_and_csv() -> None:
    assert rec.format_eur("1234.5") == "1.234,50"
    assert rec.format_eur("-1234567.891") == "-1.234.567,89"
    assert rec.format_eur("0") == "0,00"
    assert rec.format_eur(None) == ""
    text = rec.report_csv(
        {
            "lines": [
                {
                    "property_number": "851",
                    "metric": "bankstand",
                    "key": "2051",
                    "source": "10150.00",
                    "platform": "10200.00",
                    "difference": "50.00",
                    "deviates": True,
                    "hint": None,
                }
            ]
        }
    )
    assert text.startswith(
        "﻿Objekt;Kennzahl;Schlüssel;Quelle;Plattform;Differenz;Abweichung;Hinweis\r\n"
    )
    assert text.endswith("851;bankstand;2051;10.150,00;10.200,00;50,00;ja;\r\n")


def test_beat_time_from_settings(settings: Settings) -> None:
    assert beat_time(settings) == (5, 30)
    custom = make_settings(import_reconciliation_time="06:15")
    assert beat_time(custom) == (6, 15)
    entry = create_celery(custom).conf.beat_schedule["imports-reconciliation-report"]
    assert entry["task"] == "mhvp.imports.reconciliation_all"
    assert entry["schedule"] == crontab(hour=6, minute=15)
    with pytest.raises(ValueError, match="import_reconciliation_time"):
        make_settings(import_reconciliation_time="6:15")
