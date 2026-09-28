"""Entry standards ES-01 to ES-10 (docs/rules/ES-erfassungsstandards.md): predefined inputs
with expected rule ids."""

from datetime import date

import pytest

from mhvp.dataquality import rules


def _ids(findings: list[rules.Finding]) -> list[str]:
    return [f.rule for f in findings]


@pytest.mark.parametrize(
    ("country", "postcode", "invalid"),
    [
        ("DE", "40789", False),
        ("DE", " 40789 ", False),
        ("DE", "4078", True),
        ("DE", "407890", True),
        ("DE", "D-40789", True),
        ("DE", None, False),
        ("DE", "", False),
        (None, "123", True),
        ("AT", "1010", False),
        ("NL", "1011 AB", False),
    ],
)
def test_postcode(country: str | None, postcode: str | None, invalid: bool) -> None:
    assert (rules.postcode_error(country, postcode) is not None) is invalid


def test_property_standard_name_is_clean() -> None:
    data = {
        "name": "Rheinpromenade 13, 40789 Monheim am Rhein",
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
        "country": "DE",
    }
    assert rules.check_property(data) == []
    assert rules.check_property({**data, "name": "Hauptstraße 4a-6, 41812 Erkelenz"}) == []


def test_property_findings() -> None:
    found = rules.check_property(
        {"name": "WEG Monheim", "street": "Rheinpromenade 13", "postal_code": "4078"}
    )
    assert _ids(found) == ["ES-01", "ES-02", "ES-02", "ES-03", "ES-04"]
    assert [f.field for f in found if f.rule == "ES-02"] == ["house_number", "city"]
    assert found[0].severity == "error"
    assert "Anschrift ergänzen" in found[-1].message


def test_property_name_suggestion() -> None:
    found = rules.check_property(
        {
            "name": "Monheim",
            "street": "Rheinpromenade",
            "house_number": "13",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        }
    )
    assert _ids(found) == ["ES-04"]
    assert "Rheinpromenade 13, 40789 Monheim am Rhein" in found[0].message


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"kind": "person", "first_name": "Anna", "last_name": "Schmidt"}, []),
        ({"kind": "person", "first_name": "Anna", "last_name": "von Bülow"}, []),
        ({"kind": "person", "first_name": "", "last_name": "von Bülow"}, ["ES-08"]),
        ({"kind": "person", "first_name": None, "last_name": "Anna Schmidt"}, ["ES-06"]),
        ({"kind": "person", "first_name": None, "last_name": "Schmidt, Anna"}, ["ES-05"]),
        ({"kind": "person", "first_name": "", "last_name": "Muster GmbH"}, ["ES-06", "ES-07"]),
        ({"kind": "person", "first_name": "", "last_name": "Stadtwerke"}, ["ES-07"]),
        ({"kind": "person", "first_name": "", "last_name": "Schmidt"}, ["ES-08"]),
        ({"kind": "company", "company_name": "Muster GmbH"}, []),
        ({"kind": "company", "company_name": " "}, ["ES-08"]),
    ],
)
def test_contact_rules(data: dict[str, object], expected: list[str]) -> None:
    assert _ids(rules.check_contact(data)) == expected


def test_deadline_rules() -> None:
    today = date(2026, 9, 28)
    assert rules.check_deadline({"due_on": "2026-09-28", "assignee_user_id": "x"}, today) == []
    assert _ids(rules.check_deadline({"due_on": date(2026, 9, 27)}, today)) == ["ES-09", "ES-10"]
    assert rules.check_deadline({"due_on": None}, today) == []
    with pytest.raises(ValueError, match="isoformat"):
        rules.check_deadline({"due_on": "27.09.2026"}, today)
