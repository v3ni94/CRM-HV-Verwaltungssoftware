# ruff: noqa: T201 - operator CLI, output goes to the terminal
"""``python -m mhvp.imports.kontakte``: contacts from the Immoware24 contact lists.

Immoware24 exports one list per contact group (owners, tenants, banks, others) with the columns
id, Name, Briefanrede, Benutzername, Adresse, Stadt, PLZ, Staat, Land, Landesvorwahl, Vorwahl,
Telefonnummer, E-Mail. This command creates the contacts of those lists for one tenant and sets
the operator role (Eigentümer, Mieter, Bank, Sonstiges) from the list. The Immoware24 id is kept
in ``external_ids["immoware24"]``; a contact that already carries the id is not created again,
it only receives the additional role. Names are split heuristically ("Nachname, Vorname" or
"Vorname Nachname"); everything unclear stays in the name fields as exported and is listed in
the report. No contract, receivable or bank account is created (rule 0.1.3).

Default is a test run without database changes; ``--apply`` writes.
"""

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
from pathlib import Path
from typing import Any

from sqlalchemy import select

from mhvp.ai.imports import create_contact, create_party
from mhvp.contacts import schemas as cs
from mhvp.contacts.models import Completeness, ContactKind, ContactRoleCode
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import configure_logging, get_logger
from mhvp.imports import services as import_services
from mhvp.platform.models import Tenant, User

ROLE_BY_KEYWORD = {
    "eigentuemer": ContactRoleCode.EIGENTUEMER,
    "eigentümer": ContactRoleCode.EIGENTUEMER,
    "mieter": ContactRoleCode.MIETER,
    "bank": ContactRoleCode.BANK,
    "sonstige": ContactRoleCode.SONSTIGES,
    "sonstiges": ContactRoleCode.SONSTIGES,
    "verwalter": ContactRoleCode.VERWALTER,
    "dienstleister": ContactRoleCode.DIENSTLEISTER,
}
COUNTRIES = {
    "deutschland": "DE",
    "niederlande": "NL",
    "schweiz": "CH",
    "belgien": "BE",
    "frankreich": "FR",
    "österreich": "AT",
    "luxemburg": "LU",
    "polen": "PL",
    "spanien": "ES",
    "italien": "IT",
    "türkei": "TR",
    "china": "CN",
    "usa": "US",
    "vereinigte staaten": "US",
    "großbritannien": "GB",
    "vereinigtes königreich": "GB",
}
_COMPANY_WORDS = re.compile(
    r"\b(gmbh|ag|kg|ohg|ug|e\.? ?k\.?|e\.? ?v\.?|eg|mbh|\w*bank|sparkasse|\w*kasse|raiffeisen|"
    r"stadt|gemeinde|amt|finanzamt|landgericht|amtsgericht|jobcenter|verein|versicherung|"
    r"immobilien|verwaltung|hausverwaltung|weg|gbr|kirche|kanzlei|praxis|ventures|holding|"
    r"vermittlung|musikschule|gesellschaft|stiftung|betrieb|service|werke|technik|bau|"
    r"ministerium|bezirk|kreis|landkreis|ndl|filiale|orga|extern|praktikant|azubi)\b",
    re.IGNORECASE,
)
_HOUSE_NUMBER = re.compile(r"^(?P<street>.+?)\s+(?P<number>\d+[\w\-/ .]*?)\s*$")


@dataclass
class ContactRow:
    external_id: str
    name: str
    salutation_line: str | None
    username: str | None
    address: str | None
    city: str | None
    postal_code: str | None
    state: str | None
    country: str | None
    country_code: str | None
    area_code: str | None
    phone: str | None
    email: str | None
    role: ContactRoleCode
    source_file: str
    line: int


@dataclass
class Prepared:
    row: ContactRow
    data: cs.ContactIn | None
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def role_from_filename(path: str) -> ContactRoleCode | None:
    stem = Path(path).stem.lower()
    for keyword, role in ROLE_BY_KEYWORD.items():
        if keyword in stem:
            return role
    return None


def parse_kontakte(text: str, role: ContactRoleCode, source_file: str) -> list[ContactRow]:
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    reader = csv.reader(io.StringIO(text), dialect)
    headers = [h.strip() for h in next(reader)]
    required = ("id", "Name")
    missing = [h for h in required if h not in headers]
    if missing:
        raise ValueError(f"{source_file}: Spalten fehlen: {', '.join(missing)}")
    index = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], name: str) -> str | None:
        i = index.get(name)
        if i is None or i >= len(row):
            return None
        return row[i].strip() or None

    rows: list[ContactRow] = []
    for line, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        external_id = cell(row, "id")
        name = cell(row, "Name")
        if external_id is None or name is None:
            raise ValueError(f"{source_file} Zeile {line}: id oder Name fehlt")
        rows.append(
            ContactRow(
                external_id=external_id,
                name=name,
                salutation_line=cell(row, "Briefanrede"),
                username=cell(row, "Benutzername"),
                address=cell(row, "Adresse"),
                city=cell(row, "Stadt"),
                postal_code=cell(row, "PLZ"),
                state=cell(row, "Staat"),
                country=cell(row, "Land"),
                country_code=cell(row, "Landesvorwahl"),
                area_code=cell(row, "Vorwahl"),
                phone=cell(row, "Telefonnummer"),
                email=cell(row, "E-Mail"),
                role=role,
                source_file=source_file,
                line=line,
            )
        )
    return rows


def is_company(name: str, role: ContactRoleCode) -> bool:
    if role is ContactRoleCode.BANK:
        return True
    stripped = name.strip().rstrip(",")
    if " " not in stripped and stripped.isupper() and len(stripped) >= 3:
        return True
    return bool(_COMPANY_WORDS.search(name))


_SALUTATION_PREFIX = re.compile(
    r"^\s*sehr\s+geehrte[rs]?\s+(herr|frau|eheleute|familie|damen\s+und\s+herren)?\s*",
    re.IGNORECASE,
)


def split_person_name(
    name: str, salutation_line: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """``(first_name, last_name, note)``. "Nachname, Vorname" is unambiguous; otherwise the
    family name named in the salutation line ("Sehr geehrte Frau Joachims") decides, and only
    as a last resort the final token counts as family name (noted as a guess)."""
    clean = name.strip().rstrip(",").strip()
    if "," in clean:
        last, first = (p.strip() for p in clean.split(",", 1))
        return (first or None), (last or None), None
    parts = clean.split()
    if len(parts) == 1:
        return None, parts[0], None
    if salutation_line:
        rest = _SALUTATION_PREFIX.sub("", salutation_line).strip().rstrip(",").split()
        if rest:
            candidate = rest[-1]
            lowered = [p.lower() for p in parts]
            if candidate.lower() in lowered:
                i = lowered.index(candidate.lower())
                first = " ".join(parts[:i] + parts[i + 1 :])
                return (first or None), parts[i], None
    return " ".join(parts[:-1]), parts[-1], "Reihenfolge Vorname Nachname angenommen"


def salutation(line: str | None) -> str | None:
    if not line:
        return None
    lowered = line.lower()
    if "herr" in lowered and "damen" not in lowered:
        return "Herr"
    if "frau" in lowered and "damen" not in lowered:
        return "Frau"
    return None


def split_street(address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    match = _HOUSE_NUMBER.match(address)
    if match and not re.fullmatch(r"\d.*", address.strip()):
        number = match.group("number").strip()
        if len(number) <= 20:
            return match.group("street").strip(), number
    # Two addresses in one field ("Venner Straße 16 / Annakirchenstraße 24"): keep as text.
    return address.strip()[:200], None


def compose_phone(
    country_code: str | None, area_code: str | None, number: str | None
) -> str | None:
    if not number and not area_code:
        return None
    area = (area_code or "").strip()
    local = (number or "").strip()
    cc = (country_code or "").strip()
    if cc.startswith("00") and len(cc) > 2:
        return f"+{cc[2:]}{area.lstrip('0')}{local}"
    if cc.startswith("+"):
        return f"{cc}{area.lstrip('0')}{local}"
    domestic = f"{cc}{area}{local}"
    if domestic and not domestic.startswith("0"):
        domestic = "0" + domestic
    return domestic or None


def prepare_row(row: ContactRow) -> Prepared:
    notes: list[str] = []
    problems: list[str] = []
    company = is_company(row.name, row.role)
    data: dict[str, Any] = {
        "kind": ContactKind.COMPANY.value if company else ContactKind.PERSON.value,
        "external_ids": {"immoware24": row.external_id},
        "roles": [row.role.value],
    }
    if company:
        data["company_name"] = row.name.strip().rstrip(",").strip()[:200]
    else:
        first, last, note = split_person_name(row.name, row.salutation_line)
        data["first_name"] = first[:100] if first else None
        data["last_name"] = last[:100] if last else None
        data["salutation"] = salutation(row.salutation_line)
        if note:
            notes.append(note)
    if row.username:
        data["external_ids"]["immoware24_user"] = row.username
    country = "DE"
    if row.country:
        mapped = COUNTRIES.get(row.country.strip().lower())
        if mapped is None:
            notes.append(f"Land {row.country!r} nicht zugeordnet, DE angenommen")
        else:
            country = mapped
    street, house_number = split_street(row.address)
    if any((street, row.postal_code, row.city)):
        data["addresses"] = [
            {
                "street": street,
                "house_number": house_number,
                "postal_code": row.postal_code,
                "city": row.city,
                "country": country,
                "is_primary": True,
            }
        ]
    else:
        data["completeness"] = Completeness.INCOMPLETE.value
    phone = compose_phone(row.country_code, row.area_code, row.phone)
    if phone:
        try:
            data["phones"] = [cs.PhoneIn.model_validate({"number": phone, "is_primary": True})]
        except ValueError:
            notes.append(f"Telefon {phone!r} ungültig, nur als Notiz übernommen")
            data["notes"] = f"Telefon laut Altsystem: {phone}"
    if row.email:
        try:
            data["emails"] = [cs.EmailIn.model_validate({"email": row.email, "is_primary": True})]
        except ValueError:
            notes.append(f"E-Mail {row.email!r} ungültig, nur als Notiz übernommen")
            data["notes"] = "\n".join(
                n for n in (data.get("notes"), f"E-Mail laut Altsystem: {row.email}") if n
            )
    try:
        contact_in = cs.ContactIn.model_validate(data)
    except ValueError as exc:
        problems.append(f"Kontakt ungültig: {exc}")
        return Prepared(row, None, notes, problems)
    return Prepared(row, contact_in, notes, problems)


def prepare(rows: list[ContactRow]) -> list[Prepared]:
    return [prepare_row(r) for r in rows]


class _DryRunError(Exception):
    pass


async def import_prepared(
    factory: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    prepared: list[Prepared],
    *,
    apply: bool,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    lines: list[dict[str, Any]] = []

    async def work(session: Any) -> None:
        for item in prepared:
            entry: dict[str, Any] = {
                "datei": item.row.source_file,
                "zeile": item.row.line,
                "id": item.row.external_id,
                "name": item.row.name,
                "rolle": item.row.role.value,
                "hinweise": list(item.notes),
            }
            lines.append(entry)
            if item.data is None:
                entry["status"] = "invalid"
                entry["probleme"] = item.problems
                counts["invalid"] += 1
                continue
            existing = await import_services._contact(session, item.row.external_id)
            if existing is not None:
                roles = set(existing.roles or [])
                if item.row.role.value in roles:
                    entry["status"] = "unchanged"
                    counts["unchanged"] += 1
                else:
                    existing.roles = sorted(roles | {item.row.role.value})
                    entry["status"] = "role_added"
                    counts["role_added"] += 1
                continue
            contact = await create_contact(session, tenant_id, user_id, item.data)
            await create_party(session, tenant_id, user_id, [contact])
            entry["status"] = "created"
            counts["created"] += 1
        await session.flush()
        if not apply:
            raise _DryRunError

    try:
        async with tenant_transaction(factory, tenant_id) as session:
            await work(session)
    except _DryRunError:
        pass
    return {"apply": apply, "counts": dict(counts), "kontakte": lines}


def _read_file(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8-sig", errors="strict")


def load_files(specs: list[str]) -> list[ContactRow]:
    """``ROLE=PATH`` or a path whose file name carries the group (eigentuemer, mieter, bank,
    sonstige)."""
    rows: list[ContactRow] = []
    for spec in specs:
        if "=" in spec and not Path(spec).exists():
            role_text, path = spec.split("=", 1)
            role = ROLE_BY_KEYWORD.get(role_text.strip().lower())
            if role is None:
                raise ValueError(
                    f"Rolle {role_text!r} unbekannt (eigentuemer, mieter, bank, sonstige)"
                )
        else:
            path = spec
            role = role_from_filename(path)
            if role is None:
                raise ValueError(
                    f"{path}: Rolle nicht aus dem Dateinamen erkennbar, "
                    "bitte als ROLLE=PFAD angeben"
                )
        rows.extend(parse_kontakte(_read_file(path), role, Path(path).name))
    return rows


def _print_report(report: dict[str, Any], verbose: bool) -> None:
    mode = "ÜBERNOMMEN" if report["apply"] else "TESTLAUF (nichts gespeichert)"
    print(f"Kontakt-Import: {mode}")
    for key, value in sorted(report["counts"].items()):
        print(f"  {key}: {value}")
    for entry in report["kontakte"]:
        flagged = entry.get("probleme") or entry.get("hinweise")
        if not verbose and not flagged:
            continue
        print(
            f"{entry['datei']}:{entry['zeile']} [{entry['id']}] {entry['name']}: {entry['status']}"
        )
        for note in entry.get("hinweise", []):
            print(f"    Hinweis: {note}")
        for problem in entry.get("probleme", []):
            print(f"    Problem: {problem}")


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.imports.kontakte",
        description="Kontakte aus Immoware24-Kontaktlisten anlegen.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="CSV-Dateien; Rolle aus dem Dateinamen (eigentuemer, mieter, bank, sonstige) "
        "oder als ROLLE=PFAD",
    )
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
        "--verbose", action="store_true", help="jede Zeile ausgeben, nicht nur Hinweise"
    )
    args = parser.parse_args(argv)
    prepared = prepare(load_files(args.files))

    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.imports.kontakte")
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
        report = await import_prepared(factory, tenant_id, user_id, prepared, apply=args.apply)
        _print_report(report, args.verbose)
        log.info("kontakte_import", apply=args.apply, counts=report["counts"])
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
