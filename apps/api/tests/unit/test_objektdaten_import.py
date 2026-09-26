"""Objektdaten CLI: parsing, number normalisation, prefixes and unit type guesses."""

import pytest

from mhvp.imports.objektdaten import (
    classify_name,
    guess_unit_type,
    normalise_number,
    parse_objektdaten,
    prepare,
)
from mhvp.properties.models import PropertyStatus, UnitType

HEADER = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    '"aktueller Eigentümer";"vereinbarter Zahlbetrag";"aktueller Mieter";"vereinbarter Zahlbetrag"'
)
SAMPLE = "\n".join(
    [
        HEADER,
        '359;"Z ABGEGEBEN Brunnenstraße 145";WEG-Verwaltung;Haupthaus;10001;01;EG;"Sakwa, Agata";230,00;;',  # noqa: E501
        '359;"Z ABGEGEBEN Brunnenstraße 145";WEG-Verwaltung;Haupthaus;10002;02;1.OG;"Schmitz";288,80;;',  # noqa: E501
        '216;"Haagstraße 32";Mietverwaltung;"Haagstraße 32";14;"WE 14";DG;;;"Roggen, Anna";620,00',
        '81;"Z-ABGEBEN Roskaul 70-72";WEG-Verwaltung;"Roskaul 70-72";1;"WE 1";"WE 1";"Hoos, Marcel";130,00;;',  # noqa: E501
        '10012;"Am Bildchen 9";Mietverwaltung;Haus;1;"Stellplatz Nr. 1";;;;"Meier";40,00',
        '600;"Fontanestr. 7";"WEG mit SE-Verwaltung";Haus;1;GE 01;EG;"Firma";100,00;;',
        '600;"Fontanestr. 7";"WEG mit SE-Verwaltung";Haus;1;GE 02;EG;"Firma";100,00;;',
    ]
)


def test_parse_groups_units_and_reads_owner_and_tenant_amounts() -> None:
    rows = parse_objektdaten(SAMPLE).rows
    assert [r.source_number for r in rows] == ["359", "216", "81", "10012", "600"]
    weg = rows[0]
    assert weg.management == "WEG-Verwaltung"
    assert [u.number for u in weg.units] == ["10001", "10002"]
    assert weg.units[0].owner == "Sakwa, Agata"
    assert weg.units[0].owner_amount == "230,00"
    assert weg.units[0].tenant is None
    rental = rows[1].units[0]
    assert rental.tenant == "Roggen, Anna"
    assert rental.tenant_amount == "620,00"
    assert rental.owner_amount is None


def test_parse_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="Spalten fehlen: Objekt-Nummer, Objekt, Verwaltungsart"):
        parse_objektdaten("Nr;Name\n1;x\n")


def test_number_normalisation() -> None:
    assert normalise_number("359", {}) == ("359", None)
    number, note = normalise_number("81", {})
    assert number == "081"
    assert "führenden Nullen" in (note or "")
    assert normalise_number("10012", {})[0] is None
    assert normalise_number("10012", {"10012": "012"})[0] == "012"
    assert normalise_number("10012", {"10012": "12"})[0] == "012"
    assert normalise_number("10012", {"10012": "1234"})[0] is None


def test_prefix_classification() -> None:
    assert classify_name("Z ABGEGEBEN Brunnenstraße 145") == (
        "Brunnenstraße 145",
        PropertyStatus.TERMINATED,
        "Im Altsystem als abgegeben geführt (Präfix Z)",
    )
    assert classify_name("Z-ABGEBEN Roskaul 70-72")[0] == "Roskaul 70-72"
    assert classify_name("Z - ABGEGEBEN Schenkendorfstraße 6")[0] == "Schenkendorfstraße 6"
    assert classify_name("Z.Abgegeben Nesselrodestraße 109")[0] == "Nesselrodestraße 109"
    name, status, _ = classify_name("Y ABRECHNUNG Schadestraße 3a")
    assert (name, status) == ("Schadestraße 3a", PropertyStatus.ACTIVE)
    assert classify_name("Gladbacher Straße 95") == (
        "Gladbacher Straße 95",
        PropertyStatus.ONBOARDING,
        None,
    )


def test_unit_type_guess() -> None:
    assert guess_unit_type("WE 14", "DG") is UnitType.APARTMENT
    assert guess_unit_type("01", "EG") is UnitType.APARTMENT
    assert guess_unit_type("Stellplatz Nr. 13", None) is UnitType.PARKING
    assert guess_unit_type("S01", None) is UnitType.PARKING
    assert guess_unit_type("Garage 10", None) is UnitType.GARAGE
    assert guess_unit_type("GE 02", "EG") is UnitType.COMMERCIAL
    assert guess_unit_type("MVW 3", None) is UnitType.OTHER
    assert guess_unit_type("STP01", "UG") is UnitType.PARKING
    assert guess_unit_type("VE01_SIL8_EG.R_GEW", "SIL8_EG.R") is UnitType.COMMERCIAL
    assert guess_unit_type("VE02_SIL8_1R", "SIL8_1.R") is UnitType.APARTMENT
    assert guess_unit_type("3", "3") is UnitType.APARTMENT
    assert guess_unit_type(None, None) is UnitType.OTHER


def test_prepare_reports_problems_per_property() -> None:
    prepared = prepare(parse_objektdaten(SAMPLE), {})
    by_src = {p.row.source_number: p for p in prepared}
    assert by_src["359"].number == "359"
    assert by_src["359"].problems == []
    assert by_src["359"].management_type == "hoa"
    assert by_src["216"].management_type == "rental"
    assert by_src["81"].number == "081"
    assert any("nicht dreistellig" in p for p in by_src["10012"].problems)
    assert by_src["600"].management_type == "hoa_with_sev"
    assert any(
        "VE-Nummer 1 kommt 2 mal mit abweichenden Angaben" in p for p in by_src["600"].problems
    )
