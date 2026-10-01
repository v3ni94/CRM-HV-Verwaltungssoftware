"""M17-09 pure checks of the metering service import (docs/rules/M17-09-heizkostenimport.md).
Expected values are recomputed by hand: 1.300,00 + 350,00 + 650,00 = 2.300,00 EUR."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.billing import heating_import
from mhvp.billing.models import HeatingCostImport
from mhvp.core.problems import ProblemError

MAP = {
    "user_number": "Nutzer",
    "heating_base": "HZ Grund",
    "heating_consumption": "HZ Verbrauch",
    "hot_water_base": "WW Grund",
    "hot_water_consumption": "WW Verbrauch",
    "co2_landlord": "CO2 VM",
    "co2_tenant": "CO2 MI",
}
CSV = (
    "Nutzer;HZ Grund;HZ Verbrauch;WW Grund;WW Verbrauch;CO2 VM;CO2 MI;Name\n"
    "1001;600,00;400,00;100,00;200,00;30,00;20,00;A\n"
    "1002;200,00;100,00;30,00;20,00;5,00;5,00;B\n"
    ";;;;;;;\n"
    "1003;300,00;200,00;50,00;100,00;15,00;25,00;C\n"
)


def _row(
    total: str, rows: list[dict[str, str]], co2: dict[str, str] | None = None
) -> HeatingCostImport:
    return HeatingCostImport(
        provider_name="Messdienst",
        period_from=date(2025, 1, 1),
        period_to=date(2025, 12, 31),
        document_total=Decimal(total),
        co2=co2 or {},
        rows=rows,
        user_mapping={},
    )


def test_csv_with_column_map_and_decimal_comma() -> None:
    rows = heating_import.parse_csv(CSV, delimiter=";", decimal_comma=True, column_map=MAP)
    assert [r["user_number"] for r in rows] == ["1001", "1002", "1003"]
    assert rows[0]["heating_base"] == "600.00"
    assert [str(heating_import.row_total(r)) for r in rows] == ["1300.00", "350.00", "650.00"]


def test_csv_needs_complete_map_and_known_headers() -> None:
    with pytest.raises(ProblemError) as e0:
        heating_import.parse_csv(
            CSV, delimiter=";", decimal_comma=True, column_map={**MAP, "co2_tenant": ""}
        )
    assert "co2_tenant" in (e0.value.detail or "")
    with pytest.raises(ProblemError) as e0:
        heating_import.parse_csv(
            CSV, delimiter=";", decimal_comma=True, column_map={**MAP, "co2_tenant": "X"}
        )
    assert "nicht in der Datei" in (e0.value.detail or "")
    # No format guess: a comma without the decimal comma setting is refused.
    with pytest.raises(ProblemError) as e0:
        heating_import.parse_csv(CSV, delimiter=";", decimal_comma=False, column_map=MAP)
    assert "Dezimalkomma" in (e0.value.detail or "")


def test_rows_reject_duplicates_negatives_and_fractions() -> None:
    base = dict.fromkeys(heating_import.ROW_FIELDS, "1.00")
    with pytest.raises(ProblemError) as e0:
        heating_import.normalise_rows([{"user_number": "1", **base}, {"user_number": "1", **base}])
    assert "doppelt" in (e0.value.detail or "")
    with pytest.raises(ProblemError) as e0:
        heating_import.normalise_rows([{"user_number": "1", **base, "heating_base": "-1"}])
    assert "negativ" in (e0.value.detail or "")
    with pytest.raises(ProblemError) as e0:
        heating_import.normalise_rows([{"user_number": "1", **base, "heating_base": "1.001"}])
    assert "Nachkommastellen" in (e0.value.detail or "")


def test_sum_check_against_document_total_and_co2() -> None:
    rows = heating_import.parse_csv(CSV, delimiter=";", decimal_comma=True, column_map=MAP)
    ok = heating_import.sum_check(_row("2300.00", rows, {"costs": "100.00"}))
    assert ok["findings"] == []
    assert ok["grand_total"] == "2300.00"
    assert ok["totals"]["co2_landlord"] == "50.00"
    off = heating_import.sum_check(_row("2300.01", rows, {"costs": "99.00"}))
    assert any("Differenz -0.01 EUR" in f for f in off["findings"])
    assert any("CO2-Anteile je Einheit" in f for f in off["findings"])
    too_much = [dict(rows[0], co2_landlord="1300.00")]
    res = heating_import.sum_check(_row("1300.00", too_much))
    assert any("übersteigen" in f for f in res["findings"])


def test_applied_import_is_locked() -> None:
    row = _row("1.00", [])
    row.status = "applied"
    with pytest.raises(ProblemError):
        heating_import.reset(row)
