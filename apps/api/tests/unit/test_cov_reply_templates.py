"""Coverage: placeholders of ticket reply templates (operator 26.09.2026): labels of property
and unit, letter name of companies, salutation without last name, render with empty text."""

from dataclasses import dataclass

from mhvp.tickets import reply_templates as rt


@dataclass
class _Contact:
    salutation: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str = ""


@dataclass
class _Property:
    name: str | None
    street: str | None = None
    house_number: str | None = None


@dataclass
class _Unit:
    number: str | None
    label: str | None = None


@dataclass
class _Ticket:
    number: int
    title: str | None


def test_property_label_combines_name_and_address() -> None:
    assert rt.property_label(None) == ""
    assert rt.property_label(_Property("WEG Rheinblick")) == "WEG Rheinblick"
    assert rt.property_label(_Property("WEG Rheinblick", "Hauptstr.", "3a")) == (
        "WEG Rheinblick, Hauptstr. 3a"
    )
    assert rt.property_label(_Property("WEG Rheinblick", "Hauptstr.")) == (
        "WEG Rheinblick, Hauptstr."
    )
    assert rt.property_label(_Property(None, "Hauptstr.", "3")) == "Hauptstr. 3"
    assert rt.property_label(_Property(None)) == ""


def test_unit_label_with_and_without_label() -> None:
    assert rt.unit_label(None) == ""
    assert rt.unit_label(_Unit("01")) == "01"
    assert rt.unit_label(_Unit("01", "WE 01 links")) == "01 (WE 01 links)"
    assert rt.unit_label(_Unit(None)) == ""


def test_full_name_prefers_person_name_and_falls_back_to_display_name() -> None:
    assert rt.full_name(None) == ""
    assert rt.full_name(_Contact(first_name=" Erika ", last_name=" Muster ")) == "Erika Muster"
    assert rt.full_name(_Contact(last_name="Muster")) == "Muster"
    assert rt.full_name(_Contact(first_name="Erika")) == "Erika"
    assert rt.full_name(_Contact(display_name="Muster GmbH")) == "Muster GmbH"
    assert rt.full_name(_Contact(first_name="  ", display_name="Muster GmbH")) == "Muster GmbH"


def test_salutation_without_last_name_or_unknown_form_is_neutral() -> None:
    assert rt.salutation(_Contact(salutation="Herr", last_name=None)) == (
        "Sehr geehrte Damen und Herren"
    )
    assert rt.salutation(_Contact(salutation="Divers", last_name="Muster")) == (
        "Sehr geehrte Damen und Herren"
    )
    assert rt.salutation(_Contact(salutation="Frau", last_name="")) == (
        "Sehr geehrte Damen und Herren"
    )


def test_render_and_unknown_placeholders_edge_cases() -> None:
    assert rt.render(None, {}) == ""
    assert rt.render("ohne Platzhalter", {}) == "ohne Platzhalter"
    # numeric or dashed markers are not placeholders at all
    assert rt.render("{1} {a-b} {name}", {"name": "X"}) == "{1} {a-b} X"
    assert rt.unknown_placeholders("{1} {a-b} {x} {x} {y}") == ["x", "y"]
    assert rt.unknown_placeholders("") == []


def test_values_for_with_property_unit_and_company_contact() -> None:
    values = rt.values_for(
        ticket=_Ticket(number=7, title=None),
        contact=_Contact(display_name="Muster GmbH"),
        prop=_Property("Haus A", "Weg", "1"),
        unit=_Unit("02", "WE 02"),
        today="01.01.2026",
    )
    assert values["anrede"] == "Sehr geehrte Damen und Herren"
    assert values["name"] == "Muster GmbH"
    assert values["vorname"] == ""
    assert values["nachname"] == ""
    assert values["objekt"] == "Haus A, Weg 1"
    assert values["einheit"] == "02 (WE 02)"
    assert values["ticketnummer"] == "7"
    assert values["tickettitel"] == ""
    assert rt.render("{anrede}, {objekt} {einheit} {ticketnummer}", values) == (
        "Sehr geehrte Damen und Herren, Haus A, Weg 1 02 (WE 02) 7"
    )


def test_values_for_without_contact() -> None:
    values = rt.values_for(
        ticket=_Ticket(number=8, title="Titel"), contact=None, prop=None, unit=None, today="x"
    )
    assert values["name"] == ""
    assert values["vorname"] == ""
    assert values["nachname"] == ""
    assert values["tickettitel"] == "Titel"
