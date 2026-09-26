"""Zuordnung CLI without database: parser, name normalisation, amounts, contact index,
idempotency rule and the unit loop with a fake session."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.imports.objektdaten import parse_objektdaten
from mhvp.imports.zuordnung import (
    ContactEntry,
    ContactIndex,
    Decision,
    amount_cents,
    apply_rows,
    decide,
    default_start_date,
    normalise_name,
    parse_amount,
)

CSV = "\n".join(
    [
        "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
        "aktueller Eigentümer;vereinbarter Zahlbetrag;aktueller Mieter;vereinbarter Zahlbetrag",
        "391;Z ABGEGEBEN Weidenbruch 1;WEG mit SE-Verwaltung;Haus;1;WE 1;EG;Bunte, Eva;290,00;"
        "Stark, Tim;1.745,50",
        "216;Haagstraße 32;Mietverwaltung;Haus;15;WE 15;DG;;;Leerstand;",
    ]
)


def test_parser_reads_both_amount_columns_by_position() -> None:
    rows = parse_objektdaten(CSV).rows
    unit = rows[0].units[0]
    assert (unit.owner, unit.owner_amount) == ("Bunte, Eva", "290,00")
    assert (unit.tenant, unit.tenant_amount) == ("Stark, Tim", "1.745,50")
    assert rows[1].units[0].tenant == "Leerstand"
    assert rows[1].units[0].tenant_amount is None


def test_normalise_name() -> None:
    assert normalise_name("  Koch,  Maria u. Peter ") == "koch, maria & peter"
    assert normalise_name("KOCH, Maria&Peter") == "koch, maria & peter"
    assert normalise_name("Müller u.Söhne") == "müller & söhne"
    assert normalise_name("Haus u Hof") == "haus u hof"  # only "u." counts
    assert normalise_name("Leerstand") == "leerstand"


def test_amounts() -> None:
    assert parse_amount("1.019,71") == Decimal("1019.71")
    assert parse_amount("230,00") == Decimal("230.00")
    assert parse_amount("11") == Decimal("11.00")
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount("n/a") is None
    assert amount_cents(Decimal("1019.71")) == 101971


def test_default_start_date() -> None:
    assert default_start_date(date(2026, 9, 26)) == date(2026, 1, 1)


def _entry(external_id: str, display: str) -> ContactEntry:
    return ContactEntry(uuid.uuid4(), external_id, display)


def test_contact_index_primary_secondary_and_ambiguous() -> None:
    index = ContactIndex()
    steiger = _entry("10", "Steiger, Rolf")
    index.add(
        steiger,
        source_name="Steiger, Rolf",
        first_name="Rolf",
        last_name="Steiger",
        company_name=None,
    )
    hamacher = _entry("111", "Hamacher, Sven")
    index.add(
        hamacher, source_name=None, first_name="Sven", last_name="Hamacher", company_name=None
    )
    for ext in ("12", "13"):
        index.add(
            _entry(ext, "Meier, Hans"),
            source_name="Meier, Hans",
            first_name="Hans",
            last_name="Meier",
            company_name=None,
        )
    firma = _entry("3", "Commerzbank Halle")
    index.add(
        firma, source_name=None, first_name=None, last_name=None, company_name="Commerzbank Halle"
    )
    assert index.lookup("steiger,  rolf") == [steiger]
    assert index.lookup("Sven Hamacher") == [hamacher]  # reordered name as fallback
    assert [e.external_id for e in index.lookup("Meier, Hans")] == ["12", "13"]
    assert index.lookup("COMMERZBANK HALLE") == [firma]
    assert index.lookup("Unbekannt") == []


def test_decide_idempotency() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert decide([], a) == Decision.CREATE
    assert decide([a], a) == Decision.EXISTS
    assert decide([b], a) == Decision.CONFLICT
    assert decide([b], None) == Decision.CONFLICT


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def __iter__(self) -> Any:
        return iter(self.rows)

    def __aiter__(self) -> Any:
        async def gen() -> Any:
            for r in self.rows:
                yield r

        return gen()


class FakeSession:
    """Answers the two bulk loads; any per-unit query would fail the test."""

    def __init__(self, contacts: list[Any], units: list[Any]) -> None:
        self.contacts, self.units, self.flushed = contacts, units, 0

    async def stream(self, _stmt: Any) -> _Result:
        return _Result(self.contacts)

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self.units)

    async def flush(self) -> None:
        self.flushed += 1


def test_loop_reports_vacancy_missing_unit_handed_over_and_ambiguity() -> None:
    contacts = [
        (
            uuid.uuid4(),
            {"immoware24": "1", "immoware24_name": "Bunte, Eva"},
            "Bunte, Eva",
            "Eva",
            "Bunte",
            None,
        ),
        (
            uuid.uuid4(),
            {"immoware24": "2", "immoware24_name": "Bunte, Eva"},
            "Bunte, Eva",
            "Eva",
            "Bunte",
            None,
        ),
    ]
    units = [("391/1", uuid.uuid4(), uuid.uuid4())]  # 216/15 was never imported
    rows = parse_objektdaten(CSV).rows
    session = FakeSession(contacts, units)

    report = asyncio.run(
        apply_rows(
            session,
            uuid.uuid4(),
            None,
            rows,
            apply=False,
            start=date(2026, 1, 1),
            start_assumed=True,
        )
    )
    data = report.as_dict()
    assert data["einheiten_gesamt"] == 2
    assert data["start_date_assumed"] is True
    assert [x["name"] for x in data["mehrdeutig"]] == ["Bunte, Eva"]
    # Tenant exists, owner ambiguous: the tenant is unknown as contact.
    assert [x["name"] for x in data["nicht_gefunden"]] == ["Stark, Tim"]
    assert data["counts"]["einheit_fehlt"] == 1
    assert data["eigentuemer_zugeordnet"] == 0

    skipped = asyncio.run(
        apply_rows(
            FakeSession(contacts, units),
            uuid.uuid4(),
            None,
            rows,
            apply=False,
            start=date(2026, 1, 1),
            start_assumed=False,
            skip_handed_over=True,
        )
    )
    assert skipped.counts["uebersprungen_abgegeben"] == 1
    assert skipped.ambiguous == []
