"""``python -m mhvp.imports.objektdaten``: properties and units from an Immoware24 object list.

The operator exports "Objektdaten" (one row per unit: object number, name, management type,
building, unit number, description, location, current owner or tenant with the agreed amount).
This command creates the properties and units of that file for one tenant. It reuses the M8
apply functions, so existing records are left untouched (unchanged or conflict, never
overwritten). Names of owners and tenants and the agreed amounts are stored only as source
notes in ``custom_fields`` of the unit; no contact, contract or receivable is created, no
amount is posted (rule 0.1.3: an amount from a list is no released rule).

Default is a test run without database changes; ``--apply`` writes. Object numbers with more
than three digits cannot be created (``property.number`` is three characters) and must be
assigned with ``--number-map OLD=NEW``; one and two digit numbers are zero padded and reported.
"""

# ruff: noqa: T201 - operator CLI, output goes to the terminal
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import configure_logging, get_logger
from mhvp.imports import services as import_services
from mhvp.imports.models import RowStatus
from mhvp.platform.models import Tenant, User
from mhvp.properties.models import Property, PropertyStatus, Unit, UnitType

MANAGEMENT_MAP = {
    "WEG-Verwaltung": "hoa",
    "Mietverwaltung": "rental",
    "WEG mit SE-Verwaltung": "hoa_with_sev",
    "Sondereigentumsverwaltung": "hoa_with_sev",
}
# Immoware24 name prefixes the operator uses to mark the state of an object.
_HANDED_OVER = re.compile(r"^\s*Z\s*[-.]?\s*ABGE(GE)?BEN\b[\s:-]*", re.IGNORECASE)
_FINAL_STATEMENT = re.compile(r"^\s*Y\s*ABRECHNUNG\b[\s:-]*", re.IGNORECASE)
SOURCE_SYSTEM = "immoware24"


@dataclass
class UnitRow:
    number: str
    label: str | None
    building: str | None
    location: str | None
    owner: str | None
    owner_amount: str | None
    tenant: str | None
    tenant_amount: str | None
    line: int

    @property
    def unit_type(self) -> UnitType:
        return guess_unit_type(self.label, self.location)


@dataclass
class PropertyRow:
    source_number: str
    name: str
    management: str
    units: list[UnitRow] = field(default_factory=list)
    line: int = 0


@dataclass
class Prepared:
    number: str | None
    name: str
    management_type: str | None
    status: PropertyStatus
    notes: list[str]
    problems: list[str]
    row: PropertyRow


def guess_unit_type(label: str | None, location: str | None) -> UnitType:
    """Unit type from the description; anything unclear is ``other`` (reviewed by hand)."""
    raw = f"{label or ''} {location or ''}".strip().lower()
    text = re.sub(r"[_./\-]+", " ", raw)
    if not text:
        return UnitType.OTHER
    if re.search(r"garage|\bga\s?\d", text):
        return UnitType.GARAGE
    if re.search(
        r"stellpl|tiefgarage|\btg\b|\btg\s?\d|\bstp\s?\d|\bst\s?\d|\bs\s?\d{1,3}\b|carport",
        text,
    ):
        return UnitType.PARKING
    if re.search(r"keller|abstell|lager", text):
        return UnitType.STORAGE
    if re.search(r"gewerbe|\bgew\b|laden|büro|buero|praxis|\bge\s?\d", text):
        return UnitType.COMMERCIAL
    if re.search(r"garten", text):
        return UnitType.GARDEN
    if re.search(
        r"wohnung|\bwe\s?\d|\bwhg\b|\bog\b|\beg\b|\bdg\b|\bug\b|bungalow"
        r"|\bha\s?\d|\b\d\s?[rlm]\b|^\d+( \d+)?$",
        text,
    ):
        return UnitType.APARTMENT
    return UnitType.OTHER


def normalise_number(raw: str, number_map: dict[str, str]) -> tuple[str | None, str | None]:
    """Three digit platform number for a source number; ``(None, reason)`` if impossible."""
    src = raw.strip()
    if src in number_map:
        target = number_map[src]
        if not re.fullmatch(r"[0-9]{3}", target):
            return None, f"Zuordnung {src}={target} ist nicht dreistellig"
        return target, f"Objektnummer {src} laut Zuordnung als {target} angelegt"
    if re.fullmatch(r"[0-9]{3}", src):
        return src, None
    if re.fullmatch(r"[0-9]{1,2}", src):
        return src.zfill(3), f"Objektnummer {src} mit führenden Nullen als {src.zfill(3)} angelegt"
    return None, (
        f"Objektnummer {src!r} ist nicht dreistellig; bitte mit --number-map {src}=NNN zuordnen"
    )


def classify_name(name: str) -> tuple[str, PropertyStatus, str | None]:
    """Strip the operator's state prefixes and derive the property status from them."""
    if _HANDED_OVER.match(name):
        clean = _HANDED_OVER.sub("", name).strip() or name.strip()
        return clean, PropertyStatus.TERMINATED, "Im Altsystem als abgegeben geführt (Präfix Z)"
    if _FINAL_STATEMENT.match(name):
        clean = _FINAL_STATEMENT.sub("", name).strip() or name.strip()
        return clean, PropertyStatus.ACTIVE, "Im Altsystem nur noch Abrechnung offen (Präfix Y)"
    return name.strip(), PropertyStatus.ONBOARDING, None


def parse_objektdaten(text: str) -> list[PropertyRow]:
    """Rows grouped by object number in file order; header names as Immoware24 exports them."""
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    reader = csv.reader(io.StringIO(text), dialect)
    headers = [h.strip() for h in next(reader)]
    required = ("Objekt-Nummer", "Objekt", "Verwaltungsart", "VE-Nummer")
    missing = [h for h in required if h not in headers]
    if missing:
        raise ValueError(f"Spalten fehlen: {', '.join(missing)}")
    index = {h: i for i, h in enumerate(headers)}
    # "vereinbarter Zahlbetrag" appears twice: after the owner and after the tenant column.
    amount_cols = [i for i, h in enumerate(headers) if h == "vereinbarter Zahlbetrag"]
    owner_col = index.get("aktueller Eigentümer")
    tenant_col = index.get("aktueller Mieter")

    def cell(row: list[str], i: int | None) -> str | None:
        if i is None or i >= len(row):
            return None
        return row[i].strip() or None

    def amount_after(row: list[str], col: int | None) -> str | None:
        if col is None:
            return None
        following = [i for i in amount_cols if i > col]
        return cell(row, following[0]) if following else None

    grouped: dict[str, PropertyRow] = {}
    for line, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        src = cell(row, index["Objekt-Nummer"])
        unit_number = cell(row, index["VE-Nummer"])
        if src is None or unit_number is None:
            raise ValueError(f"Zeile {line}: Objekt-Nummer oder VE-Nummer fehlt")
        prop = grouped.get(src)
        if prop is None:
            prop = PropertyRow(
                source_number=src,
                name=cell(row, index["Objekt"]) or "",
                management=cell(row, index["Verwaltungsart"]) or "",
                line=line,
            )
            grouped[src] = prop
        prop.units.append(
            UnitRow(
                number=unit_number,
                label=cell(row, index.get("VE-Beschreibung")),
                building=cell(row, index.get("Gebäude")),
                location=cell(row, index.get("VE-Lage")),
                owner=cell(row, owner_col),
                owner_amount=amount_after(row, owner_col),
                tenant=cell(row, tenant_col),
                tenant_amount=amount_after(row, tenant_col),
                line=line,
            )
        )
    return list(grouped.values())


def prepare(rows: list[PropertyRow], number_map: dict[str, str]) -> list[Prepared]:
    out: list[Prepared] = []
    for row in rows:
        number, number_note = normalise_number(row.source_number, number_map)
        name, status, state_note = classify_name(row.name)
        management_type = MANAGEMENT_MAP.get(row.management)
        problems: list[str] = []
        notes = [n for n in (number_note, state_note) if n]
        if number is None and number_note:
            problems.append(number_note)
        if management_type is None:
            problems.append(f"Verwaltungsart {row.management!r} ist nicht zugeordnet")
        if not name:
            problems.append("Bezeichnung fehlt")
        seen: Counter[str] = Counter(u.number for u in row.units)
        for unit_number, count in seen.items():
            if count > 1:
                problems.append(f"VE-Nummer {unit_number} kommt {count} mal vor")
        out.append(Prepared(number, name[:200], management_type, status, notes, problems, row))
    return out


def _source_note(unit: UnitRow, imported_at: str) -> dict[str, Any]:
    note: dict[str, Any] = {"quelle": "Immoware24 Objektdaten", "stand": imported_at}
    if unit.owner:
        note["eigentuemer"] = unit.owner
        note["hausgeld_vereinbart"] = unit.owner_amount
    if unit.tenant:
        note["mieter"] = unit.tenant
        note["miete_vereinbart"] = unit.tenant_amount
    return note


class _DryRunError(Exception):
    pass


@dataclass
class _Principal:
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None


async def apply_prepared(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    prepared: list[Prepared],
    *,
    skip_handed_over: bool = False,
    recorder: Any | None = None,
) -> dict[str, Any]:
    """Create properties and units in an open tenant session (CLI and API share this).

    The caller decides whether the transaction is committed (apply) or rolled back (test run).
    ``recorder`` (``mhvp.ai.imports.Recorder``) registers created rows for undo."""
    principal = _Principal(tenant_id, user_id)
    imported_at = datetime.now(UTC).strftime("%d.%m.%Y")
    counts: Counter[str] = Counter()
    lines: list[dict[str, Any]] = []
    for item in prepared:
        entry: dict[str, Any] = {
            "objekt": item.row.source_number,
            "nummer": item.number,
            "bezeichnung": item.name,
            "hinweise": list(item.notes),
            "einheiten": {},
        }
        lines.append(entry)
        if item.problems:
            entry["status"] = "übersprungen"
            entry["probleme"] = item.problems
            counts["property_skipped"] += 1
            continue
        if skip_handed_over and item.status is PropertyStatus.TERMINATED:
            entry["status"] = "übersprungen"
            entry["probleme"] = ["abgegebenes Objekt (Option --skip-handed-over)"]
            counts["property_skipped"] += 1
            continue
        if item.number is None or item.management_type is None:  # pragma: no cover
            continue
        status, _, prop_id, messages = await import_services._apply_property(
            session,
            principal,
            {"number": item.number, "name": item.name, "management_type": item.management_type},
            recorder,
        )
        entry["status"] = status.value
        if messages:
            entry["probleme"] = messages
        counts[f"property_{status.value}"] += 1
        if status is RowStatus.CREATED:
            prop = await session.get(Property, prop_id)
            prop.status = item.status
            prop.source_system = SOURCE_SYSTEM
            prop.source_id = item.row.source_number
            if item.notes:
                prop.notes = "\n".join(item.notes)
        elif status is not RowStatus.UNCHANGED:
            continue
        unit_counts: Counter[str] = Counter()
        for unit in item.row.units:
            ustatus, _, unit_id, umessages = await import_services._apply_unit(
                session,
                principal,
                {
                    "property_number": item.number,
                    "number": unit.number,
                    "label": (unit.label or None) and unit.label[:50],
                    "building": unit.building,
                    "location": (unit.location or None) and unit.location[:100],
                    "unit_type": unit.unit_type.value,
                },
                recorder,
            )
            unit_counts[ustatus.value] += 1
            counts[f"unit_{ustatus.value}"] += 1
            if umessages:
                entry.setdefault("einheiten_probleme", []).append(
                    {"ve": unit.number, "meldungen": umessages}
                )
            if ustatus is RowStatus.CREATED:
                created = await session.get(Unit, unit_id)
                created.source_system = SOURCE_SYSTEM
                created.source_id = f"{item.row.source_number}/{unit.number}"
                created.custom_fields = {
                    **(created.custom_fields or {}),
                    "altsystem": _source_note(unit, imported_at),
                }
        entry["einheiten"] = dict(unit_counts)
    await session.flush()
    return {"counts": dict(counts), "objekte": lines}


async def import_prepared(
    factory: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    prepared: list[Prepared],
    *,
    apply: bool,
    skip_handed_over: bool = False,
) -> dict[str, Any]:
    """Create properties and units; a test run rolls the transaction back."""
    report: dict[str, Any] = {}
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            report = await apply_prepared(
                session, tenant_id, user_id, prepared, skip_handed_over=skip_handed_over
            )
            if not apply:
                raise _DryRunError
    except _DryRunError:
        pass
    return {"apply": apply, **report}


def _parse_number_map(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        for pair in value.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise argparse.ArgumentTypeError(f"--number-map erwartet ALT=NEU, nicht {pair!r}")
            old, new = (p.strip() for p in pair.split("=", 1))
            out[old] = new
    return out


def _print_report(report: dict[str, Any]) -> None:
    mode = "ÜBERNOMMEN" if report["apply"] else "TESTLAUF (nichts gespeichert)"
    print(f"Objektdaten-Import: {mode}")
    for key, value in sorted(report["counts"].items()):
        print(f"  {key}: {value}")
    for entry in report["objekte"]:
        head = (
            f"{entry['objekt']} -> {entry['nummer'] or '-'} {entry['bezeichnung']}: "
            f"{entry['status']}"
        )
        units = ", ".join(f"{k} {v}" for k, v in sorted(entry["einheiten"].items()))
        print(f"{head}" + (f" (Einheiten: {units})" if units else ""))
        for note in entry.get("hinweise", []):
            print(f"    Hinweis: {note}")
        for problem in entry.get("probleme", []):
            print(f"    Problem: {problem}")
        for up in entry.get("einheiten_probleme", []):
            print(f"    VE {up['ve']}: {'; '.join(up['meldungen'])}")


def _read_file(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8-sig", errors="strict")


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.imports.objektdaten",
        description="Objekte und Einheiten aus einer Immoware24-Objektliste anlegen.",
    )
    parser.add_argument("file", help="CSV (Semikolon, UTF-8) mit den Objektdaten")
    parser.add_argument(
        "--tenant", required=True, help="Mandanten-Slug, z. B. hausverwaltung-mueller"
    )
    parser.add_argument(
        "--user", help="E-Mail des ausführenden Benutzers (wird als Ersteller vermerkt)"
    )
    parser.add_argument(
        "--apply", action="store_true", help="wirklich speichern (Standard: Testlauf)"
    )
    parser.add_argument(
        "--number-map",
        action="append",
        default=[],
        help="ALT=NEU[,ALT=NEU] für Objektnummern, die nicht dreistellig sind",
    )
    parser.add_argument(
        "--skip-handed-over",
        action="store_true",
        help="Objekte mit Präfix 'Z ABGEGEBEN' nicht anlegen",
    )
    args = parser.parse_args(argv)
    number_map = _parse_number_map(args.number_map)
    prepared = prepare(parse_objektdaten(_read_file(args.file)), number_map)

    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.imports.objektdaten")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == args.tenant))
            if tenant is None:
                print(f"Mandant {args.tenant!r} nicht gefunden", file=sys.stderr)
                return 2
            tenant_id = tenant.id
            user_id: uuid.UUID | None = None
            if args.user:
                user = await session.scalar(select(User).where(User.email == args.user.lower()))
                if user is None:
                    print(f"Benutzer {args.user!r} nicht gefunden", file=sys.stderr)
                    return 2
                user_id = user.id
        report = await import_prepared(
            factory,
            tenant_id,
            user_id,
            prepared,
            apply=args.apply,
            skip_handed_over=args.skip_handed_over,
        )
        _print_report(report)
        log.info("objektdaten_import", apply=args.apply, counts=report["counts"])
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
