"""AE19: comparison of external heating amounts with the own calculation (expected values
computed by hand: difference = own minus external, tolerance 0,50 EUR and 1,0 percent)."""

from decimal import Decimal

import pytest

from mhvp.billing import heating_compare as hc


def _result() -> dict:
    return {
        "per_occupant": {
            "contract:a": {"total": "1000.00", "unit_number": "01", "vacancy": "false"},
            "contract:b": {"total": "500.00", "unit_number": "02", "vacancy": "false"},
            "contract:c": {"total": "300.00", "unit_number": "03", "vacancy": "false"},
        }
    }


KEYS = {"contract:a": "ua", "contract:b": "ub", "contract:c": "uc"}


def test_missing_own_result_is_not_computable() -> None:
    out = hc.compare(result=None, key_to_unit={}, external=[])
    assert out["status"] == "nicht_berechenbar"
    assert out["rows"] == []


def test_ok_deviation_and_missing() -> None:
    ext = [
        hc.ExternalItem(
            "Messdienst",
            {"contract:a": "1000.30", "contract:b": "450.00"},  # a within, b deviates
        )
    ]
    out = hc.compare(result=_result(), key_to_unit=KEYS, external=ext)
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["contract:a"]["status"] == "ok"
    assert rows["contract:a"]["difference"] == "-0.30"
    assert rows["contract:b"]["status"] == "abweichung"
    assert rows["contract:b"]["difference"] == "50.00"
    assert rows["contract:b"]["percent"] == "11.11"
    assert rows["contract:c"]["status"] == "extern_fehlt"
    assert rows["contract:c"]["external"] is None
    s = out["summary"]
    assert (s["deviations"], s["missing_external"]) == (1, 1)
    assert s["own_total"] == "1800.00"
    assert s["external_total"] == "1450.30"
    assert s["difference_total"] == "49.70"


def test_unit_id_key_and_unmatched() -> None:
    ext = [hc.ExternalItem("X", {"uc": "300.00", "unbekannt": "5.00", "contract:a": "abc"})]
    out = hc.compare(result=_result(), key_to_unit=KEYS, external=ext)
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["contract:c"]["status"] == "ok"
    assert len(out["unmatched_external"]) == 2


def test_tolerance_both_must_be_exceeded_and_validation() -> None:
    ext = [hc.ExternalItem("X", {"contract:a": "990.00"})]  # diff 10,00 = 1,01 percent
    strict = hc.compare(result=_result(), key_to_unit=KEYS, external=ext)
    assert strict["rows"][0]["status"] == "abweichung"
    loose = hc.compare(
        result=_result(), key_to_unit=KEYS, external=ext, tolerance_percent=Decimal("2")
    )
    assert loose["rows"][0]["status"] == "ok"
    with pytest.raises(ValueError, match="Toleranzen"):
        hc.compare(result=_result(), key_to_unit=KEYS, external=[], tolerance_abs=Decimal("-1"))


def test_csv_lists_only_deviations() -> None:
    ext = [hc.ExternalItem("X", {"contract:a": "1000.00", "contract:b": "450.00"})]
    csv = hc.report_csv(hc.compare(result=_result(), key_to_unit=KEYS, external=ext))
    lines = csv.strip().splitlines()
    assert len(lines) == 3
    assert "50,00" in lines[1]
    assert "extern_fehlt" in lines[2]
