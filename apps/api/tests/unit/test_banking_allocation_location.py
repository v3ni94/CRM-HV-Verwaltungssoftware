"""M12-01 (Lückenliste 30.09.2026, plan M12-03): unit and property hints of the purpose are
checked against the open item's unit and property (7.4 no. 2 and 5, D39). Expected results
are fixed in advance (rule 0.1.8)."""

from typing import Any

from mhvp.banking import allocation
from mhvp.banking import posting_proposal as pp


def _item(n: int, unit: str | None, prop: str | None = "001") -> dict[str, Any]:
    return {
        "id": f"oi-{n}",
        "kind": "receivable",
        "remaining": "250.00",
        "due_date": "2026-09-01",
        "reference": None,
        "contract_number": None,
        "mandate_reference": None,
        "party_iban_fingerprints": ["fp-1"],
        "account_number": "10001",
        "debtor_key": "d-1",
        "is_deposit": False,
        "unit_number": unit,
        "property_number": prop,
    }


def _tx(purpose: str) -> dict[str, Any]:
    return {"amount": "250.00", "purpose": purpose, "counterpart_iban_fingerprint": "fp-1"}


def test_location_matches_units_and_properties() -> None:
    hints = allocation.parse_allocation_hint("Hausgeld Whg 3 Objekt 001")
    assert allocation.location_matches(hints, unit_number="03", property_number="001") is True
    assert allocation.location_matches(hints, unit_number="04", property_number="001") is False
    assert allocation.location_matches(hints, unit_number="03", property_number="002") is False
    assert allocation.location_matches(hints, unit_number=None, property_number=None) is None
    none = allocation.parse_allocation_hint("Hausgeld September")
    assert allocation.location_matches(none, unit_number="03", property_number="001") is None


def test_unit_hint_selects_the_item_of_that_unit_for_a_debtor_with_two_units() -> None:
    scored = pp._score_receivables(_tx("Hausgeld Wohnung 12"), [_item(1, "11"), _item(2, "12")])
    assert [s.item["id"] for s in scored] == ["oi-2", "oi-1"]
    assert scored[0].determined is True
    assert allocation.REASON_LOCATION in scored[0].reasons
    assert allocation.REASON_LOCATION_MISMATCH in scored[1].reasons
    assert scored[1].determined is False


def test_period_hint_does_not_determine_an_item_of_another_unit() -> None:
    scored = pp._score_receivables(_tx("Hausgeld 09/2026 WE 5"), [_item(1, "4")])
    assert scored[0].determined is False
    assert allocation.REASON_DETERMINED not in scored[0].reasons
    assert allocation.REASON_LOCATION_MISMATCH in scored[0].reasons


def test_without_location_hint_nothing_changes() -> None:
    scored = pp._score_receivables(_tx("Hausgeld"), [_item(1, "11"), _item(2, "12")])
    assert all(not s.determined for s in scored)
    assert all(allocation.REASON_LOCATION not in s.reasons for s in scored)
