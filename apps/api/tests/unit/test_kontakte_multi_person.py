"""Multi person names in the Immoware24 contact lists (operator decision 26.09.2026, M8-04):
positive forms become members of one party, single persons and firms stay untouched, unclear
forms are reported for manual review and never guessed."""

from __future__ import annotations

import pytest

from mhvp.contacts.models import ContactRoleCode
from mhvp.imports.kontakte import (
    ContactRow,
    detect_multi_person,
    family_name_from_salutation,
    prepare_row,
)


def _names(name: str, salutation: str | None = None) -> list[tuple[str | None, str]]:
    found = detect_multi_person(name, salutation)
    assert found is not None, name
    assert found.review is None, found
    return [(p.first_name, p.last_name) for p in found.persons]


@pytest.mark.parametrize(
    ("name", "salutation", "expected"),
    [
        ("Max und Erika Mustermann", None, [("Max", "Mustermann"), ("Erika", "Mustermann")]),
        ("Goritzka, Janina & Jacek", None, [("Janina", "Goritzka"), ("Jacek", "Goritzka")]),
        (
            "Pawlinski, Andreas u. Radoslaw",
            None,
            [("Andreas", "Pawlinski"), ("Radoslaw", "Pawlinski")],
        ),
        ("Eheleute Anna und Karl Weber", None, [("Anna", "Weber"), ("Karl", "Weber")]),
        ("Herr und Frau Peter und Ute Klein", None, [("Peter", "Klein"), ("Ute", "Klein")]),
        ("Familie Lena & Tom Berg", None, [("Lena", "Berg"), ("Tom", "Berg")]),
        ("Hans Müller und Erika Müller", None, [("Hans", "Müller"), ("Erika", "Müller")]),
        # Multi word first names only when the salutation line confirms the family name.
        (
            "Hans Peter und Erika Müller",
            "Sehr geehrte Eheleute Müller",
            [("Hans Peter", "Müller"), ("Erika", "Müller")],
        ),
        (
            "Müller, Hans Peter und Erika",
            "Sehr geehrte Frau Müller, sehr geehrter Herr Müller",
            [("Hans Peter", "Müller"), ("Erika", "Müller")],
        ),
    ],
)
def test_positive_forms(
    name: str, salutation: str | None, expected: list[tuple[str | None, str]]
) -> None:
    assert _names(name, salutation) == expected


def test_titles_stay_with_the_person() -> None:
    found = detect_multi_person("Dr. Hans und Erika Müller")
    assert found is not None
    assert found.review is None
    assert [(p.title, p.first_name) for p in found.persons] == [("Dr.", "Hans"), (None, "Erika")]


@pytest.mark.parametrize(
    "name",
    [
        "Sven Hamacher",
        "Joachims Christina Maria",
        "Müller, Hans",
        "Schmidt und Partner",
        "Müller & Söhne",
        "Liam",
    ],
)
def test_negative_forms(name: str) -> None:
    assert detect_multi_person(name) is None


@pytest.mark.parametrize(
    ("name", "salutation", "fragment"),
    [
        ("Erbengemeinschaft Müller", None, "Erbengemeinschaft"),
        ("Erben nach Max Mustermann", None, "Erbengemeinschaft"),
        ("Eheleute Müller", "Sehr geehrte Eheleute Müller", "Vornamen"),
        ("Herr und Frau Mustermann", None, "Vornamen"),
        ("Max und Erika", None, "Nachname fehlt"),
        ("Jana Klauenberg & Jens Franken", "Sehr geehrte Damen und Herren", "unklar"),
        ("Hans Peter und Erika Müller", None, "unklar"),
        ("Müller, Hans und Erika Schmidt", None, "unklar"),
        ("Müller, Hans, Erika und Karl", None, "Kommas"),
        # A list before a family name at the end cannot be told from "Nachname, Vornamen".
        ("Anna, Bert und Carl Müller", None, "unklar"),
    ],
)
def test_unclear_forms_are_reported_not_guessed(
    name: str, salutation: str | None, fragment: str
) -> None:
    found = detect_multi_person(name, salutation)
    assert found is not None
    assert found.persons == []
    assert found.review is not None
    assert fragment in found.review


def test_family_name_from_salutation() -> None:
    assert family_name_from_salutation("Sehr geehrte Eheleute Weber") == "Weber"
    assert family_name_from_salutation("Sehr geehrte Frau Weber, sehr geehrter Herr Weber") == (
        "Weber"
    )
    assert family_name_from_salutation("Sehr geehrte Frau Weber, sehr geehrter Herr Kern") is None
    assert family_name_from_salutation("Sehr geehrte Damen und Herren") is None
    assert family_name_from_salutation(None) is None


def _row(name: str, salutation: str | None = None) -> ContactRow:
    return ContactRow(
        external_id="9",
        name=name,
        salutation_line=salutation,
        username=None,
        address="Wehrstraße 23",
        house_number=None,
        city="Rommerskirchen",
        postal_code="41569",
        state=None,
        country="Deutschland",
        country_code=None,
        area_code="02183",
        phone="12345",
        email="familie@example.org",
        role=ContactRoleCode.EIGENTUEMER,
        source_file="eigentuemer.csv",
        line=2,
    )


def test_prepare_row_builds_members_and_party() -> None:
    prepared = prepare_row(_row("Eheleute Anna und Karl Weber", "Sehr geehrte Eheleute Weber"))
    assert prepared.data is None
    assert prepared.review is None
    assert prepared.party_name == "Eheleute Anna und Karl Weber"
    assert [(m.first_name, m.last_name, m.salutation) for m in prepared.members] == [
        ("Anna", "Weber", None),
        ("Karl", "Weber", None),
    ]
    assert [m.external_ids for m in prepared.members] == [
        {
            "immoware24": "9",
            "immoware24_name": "Eheleute Anna und Karl Weber",
            "immoware24_member": "1",
        },
        {
            "immoware24": "9",
            "immoware24_name": "Eheleute Anna und Karl Weber",
            "immoware24_member": "2",
        },
    ]
    assert all(m.roles == [ContactRoleCode.EIGENTUEMER] for m in prepared.members)
    assert [m.addresses[0].postal_code for m in prepared.members] == ["41569", "41569"]
    assert prepared.members[0].phones
    assert prepared.members[0].emails
    assert prepared.members[1].phones == []
    assert prepared.members[1].emails == []
    assert any("2 Personen als eine Partei" in n for n in prepared.notes)


def test_prepare_row_reports_unclear_name_for_review() -> None:
    prepared = prepare_row(_row("Erbengemeinschaft Weber"))
    assert prepared.members == []
    assert prepared.party_name is None
    assert prepared.data is not None
    assert prepared.data.last_name == "Weber"
    assert prepared.data.first_name == "Erbengemeinschaft"
    assert prepared.review is not None
    assert "Erbengemeinschaft" in prepared.review
    assert any(n.startswith("Prüfung:") for n in prepared.notes)
