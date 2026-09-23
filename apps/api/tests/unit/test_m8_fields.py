"""M8 value parsing: German numbers and dates are read strictly, never guessed."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.imports.fields import convert, parse_date, parse_decimal
from mhvp.imports.models import ReportType


def test_numbers() -> None:
    assert parse_decimal("1.234,56") == Decimal("1234.56")
    assert parse_decimal("71,35") == Decimal("71.35")
    assert parse_decimal("71.35") == Decimal("71.35")
    assert parse_decimal("650,00 EUR") == Decimal("650.00")
    assert parse_decimal(55) == Decimal(55)
    for bad in ("abc", "1,2,3", True):
        with pytest.raises(ValueError, match="nicht lesbar"):
            parse_decimal(bad)


def test_dates() -> None:
    assert parse_date("01.03.2021") == date(2021, 3, 1)
    assert parse_date("2021-03-01") == date(2021, 3, 1)
    with pytest.raises(ValueError, match="nicht lesbar"):
        parse_date("03/01/2021")
    with pytest.raises(ValueError, match="gibt es nicht"):
        parse_date("31.02.2021")


def test_convert_reports_missing_and_unmapped_values() -> None:
    columns = {"number": "Nr", "name": "Name", "management_type": "Typ"}
    values, errors = convert(ReportType.PROPERTIES, {"Nr": "12", "Typ": "WEG"}, columns, {})
    assert values == {"number": "12"}
    assert any("Bezeichnung: fehlt" in e for e in errors)
    assert any("nicht zugeordnet" in e for e in errors)
    assert any("nicht dreistellig" in e for e in errors)
    values, errors = convert(
        ReportType.PROPERTIES,
        {"Nr": "342", "Name": "WEG", "Typ": "WEG"},
        columns,
        {"management_type": {"WEG": "hoa"}},
    )
    assert errors == []
    assert values["management_type"] == "hoa"
