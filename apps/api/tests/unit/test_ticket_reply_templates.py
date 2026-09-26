"""Platzhalter der Antwortvorlagen (operator 26.09.2026): deterministische Ersetzung, Anrede
aus dem Kontakt, unbekannte Platzhalter werden erkannt und bleiben im Text stehen."""

from dataclasses import dataclass

from mhvp.tickets import reply_templates as rt


@dataclass
class _Contact:
    salutation: str | None
    first_name: str | None
    last_name: str | None
    display_name: str


@dataclass
class _Ticket:
    number: int
    title: str


def test_render_fills_known_placeholders_and_keeps_unknown() -> None:
    text = "{anrede},\n\nzu Ticket {ticketnummer} ({objekt}) und {unbekannt}."
    out = rt.render(
        text, {"anrede": "Sehr geehrte Frau Muster", "ticketnummer": "404", "objekt": "WEG A"}
    )
    assert out == "Sehr geehrte Frau Muster,\n\nzu Ticket 404 (WEG A) und {unbekannt}."
    assert rt.unknown_placeholders(text) == ["unbekannt"]
    assert rt.unknown_placeholders("{anrede} {name} {ticketnummer}") == []
    assert rt.unknown_placeholders(None) == []


def test_salutation_from_contact() -> None:
    assert rt.salutation(None) == "Sehr geehrte Damen und Herren"
    assert rt.salutation(_Contact("Frau", "Erika", "Muster", "Erika Muster")) == (
        "Sehr geehrte Frau Muster"
    )
    assert rt.salutation(_Contact("Herr", "Max", "Muster", "Max Muster")) == (
        "Sehr geehrter Herr Muster"
    )
    assert rt.salutation(_Contact(None, None, None, "Firma X")) == "Sehr geehrte Damen und Herren"


def test_values_for_ticket() -> None:
    values = rt.values_for(
        ticket=_Ticket(number=404, title="Heizung"),
        contact=_Contact("Herr", "Max", "Muster", "Max Muster"),
        prop=None,
        unit=None,
        today="26.09.2026",
    )
    assert values["ticketnummer"] == "404"
    assert values["name"] == "Max Muster"
    assert values["vorname"] == "Max"
    assert values["objekt"] == ""
    assert values["datum"] == "26.09.2026"
    assert set(values) == set(rt.PLACEHOLDERS)
