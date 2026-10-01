"""Y01 (M2-02): reconciliation report filtered to the assigned properties (pure function)."""

import uuid

from mhvp.imports.reconciliation import scope_report

OWN, FOREIGN = uuid.uuid4(), uuid.uuid4()


def _report() -> dict[str, object]:
    return {
        "as_of": "2026-09-30",
        "warnings": ["Objekt 2 unbekannt"],
        "counts": {"journal": 3},
        "totals": {"properties": 3, "compared": 3, "deviations": 2, "missing_on_platform": 1},
        "properties": [
            {"number": "1", "property_id": str(OWN)},
            {"number": "2", "property_id": str(FOREIGN)},
            {"number": "3", "property_id": None},
        ],
        "lines": [
            {"property_number": "1", "deviates": True},
            {"property_number": "2", "deviates": True},
            {"property_number": "3", "deviates": False},
        ],
    }


def test_unrestricted_unchanged() -> None:
    report = _report()
    assert scope_report(report, None) is report


def test_restricted_keeps_assigned_only() -> None:
    out = scope_report(_report(), frozenset({OWN}))
    assert [p["number"] for p in out["properties"]] == ["1"]
    assert [line["property_number"] for line in out["lines"]] == ["1"]
    assert out["totals"] == {
        "properties": 1,
        "compared": 1,
        "deviations": 1,
        "missing_on_platform": 0,
    }
    assert out["warnings"] == []
    assert out["counts"] == {}


def test_restricted_without_property_ids_sees_nothing() -> None:
    old = _report()
    for p in old["properties"]:  # type: ignore[attr-defined]
        p.pop("property_id")
    out = scope_report(old, frozenset({OWN}))
    assert out["properties"] == []
    assert out["lines"] == []
