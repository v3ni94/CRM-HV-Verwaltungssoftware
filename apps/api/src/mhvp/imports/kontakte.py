# ruff: noqa: T201 - operator CLI, output goes to the terminal
"""``python -m mhvp.imports.kontakte``: contacts from the Immoware24 contact lists.

Immoware24 exports one list per contact group (owners, tenants, banks, others) with the columns
id, Name, Briefanrede, Benutzername, Adresse, Stadt, PLZ, Staat, Land, Landesvorwahl, Vorwahl,
Telefonnummer, E-Mail. This command creates the contacts of those lists for one tenant and sets
the operator role (Eigentümer, Mieter, Bank, Sonstiges) from the list. The Immoware24 id is kept
in ``external_ids["immoware24"]``; a contact that already carries the id is not created again,
it only receives the additional role. Names are split heuristically ("Nachname, Vorname" or
"Vorname Nachname"); everything unclear stays in the name fields as exported and is listed in
the report. No contract, receivable or bank account is created (rule 0.1.3); an IBAN column,
if the export carries one, is only reported masked as a proposal (M19-05, four eyes release of
bank accounts in ``mhvp.contacts``) and never stored.

The files are read with ``mhvp.imports.csvtext`` (encoding, delimiter, quoting, spacing, empty
and repeated header rows, column order and extra columns are tolerated and reported). Rows
without id or name and repeated ids within one file are reported and skipped, not created twice.

Default is a test run without database changes; ``--apply`` writes.
"""

from __future__ import annotations

import argparse
import asyncio
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
from mhvp.contacts.validation import InvalidValueError, mask_iban, normalise_iban
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import configure_logging, get_logger
from mhvp.imports import services as import_services
from mhvp.imports.csvtext import Row, Table, decode_csv, read_table
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
    r"ministerium|bezirk|kreis|landkreis|ndl|filiale|orga|extern|praktikant|azubi|firma|fa|"
    r"gbr|partg|ggmbh|kgaa|se|ltd|inc)\b",
    re.IGNORECASE,
)
# House number with addition ("12a", "12 a", "3-5", "1/2", "12a-14"), optional ", Whg. 3".
_HOUSE_NUMBER = re.compile(
    r"^(?P<street>.+?)\s+(?P<number>\d+(?:\s?[a-zA-Z]{1,2})?(?:\s?[-/]\s?\d+(?:\s?[a-zA-Z])?)?)"
    r"(?:\s*,\s*(?P<addition>.+?))?\s*$"
)
_TITLE = re.compile(
    r"^\s*((?:prof\.?\s*)?(?:dr\.?\s*)+(?:med\.?|jur\.?|rer\.?\s*nat\.?|h\.?\s*c\.?)?"
    r"|prof\.?|dipl\.?-?\s?(?:ing|kfm|kffr)\.?)\s+",
    re.IGNORECASE,
)
_LEGAL_FORM = re.compile(
    r"(?<![\w])(GmbH\s*&\s*Co\.?\s*KGaA|GmbH\s*&\s*Co\.?\s*KG|UG\s*\(haftungsbeschränkt\)|"
    r"gGmbH|GmbH|mbH|AG\s*&\s*Co\.?\s*KG|KGaA|AG|SE|KG|OHG|GbR|PartG(?:\s*mbB)?|e\.\s?V\.|"
    r"e\.\s?K\.|e\.\s?G\.|eG|UG|Ltd\.?|B\.\s?V\.|S\.\s?A\.|Inc\.?)(?![\w])",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+", re.UNICODE)
# Accepted header spellings per column (compared via ``csvtext.column_key``).
COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("id", "Nr", "Nummer", "Kontakt-ID", "Kontaktnummer"),
    "Name": ("Name", "Kontakt", "Bezeichnung"),
    "Briefanrede": ("Briefanrede", "Anrede"),
    "Benutzername": ("Benutzername", "Login"),
    "Adresse": ("Adresse", "Straße", "Strasse", "Straße und Hausnummer", "Anschrift"),
    "Hausnummer": ("Hausnummer", "Haus-Nr."),
    "Stadt": ("Stadt", "Ort", "Wohnort"),
    "PLZ": ("PLZ", "Postleitzahl"),
    "Staat": ("Staat", "Bundesland"),
    "Land": ("Land",),
    "Landesvorwahl": ("Landesvorwahl", "Ländervorwahl", "Landeskennzahl"),
    "Vorwahl": ("Vorwahl", "Ortsvorwahl"),
    "Telefonnummer": ("Telefonnummer", "Telefon", "Tel", "Tel.", "Rufnummer", "Mobil"),
    "E-Mail": ("E-Mail", "Email", "E-Mail-Adresse", "Mail"),
    "IBAN": ("IBAN", "Bankverbindung"),
}
REQUIRED = ("id", "Name")


@dataclass
class ContactRow:
    external_id: str
    name: str
    salutation_line: str | None
    username: str | None
    address: str | None
    house_number: str | None
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
    iban: str | None = None


@dataclass
class ParsedKontakte:
    """Rows of one or more lists plus what the reader tolerated (encoding, delimiter, lines)."""

    rows: list[ContactRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def extend(self, other: ParsedKontakte) -> None:
        self.rows.extend(other.rows)
        self.notes.extend(other.notes)


@dataclass
class Prepared:
    row: ContactRow
    data: cs.ContactIn | None
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    duplicate_of: int | None = None


def role_from_filename(path: str) -> ContactRoleCode | None:
    stem = Path(path).stem.lower()
    for keyword, role in ROLE_BY_KEYWORD.items():
        if keyword in stem:
            return role
    return None


def parse_kontakte(text: str, role: ContactRoleCode, source_file: str) -> ParsedKontakte:
    """Rows of one list; column order and extra columns do not matter, a missing required
    column raises a ``ValueError`` naming it, rows without id or name are reported and
    skipped."""
    table: Table = read_table(text, source_file)
    table.require({label: COLUMNS[label] for label in REQUIRED}, source_file)
    col = {label: table.column(*names) for label, names in COLUMNS.items()}

    def cell(row: Row, label: str) -> str | None:
        return table.cell(row, col[label])

    parsed = ParsedKontakte(notes=[f"{source_file}: {n}" for n in table.notes])
    skipped = 0
    for row in table.rows:
        external_id = cell(row, "id")
        name = cell(row, "Name")
        if external_id is None or name is None:
            missing = "id" if external_id is None else "Name"
            parsed.notes.append(f"{source_file} Zeile {row.line}: {missing} fehlt, übersprungen")
            skipped += 1
            continue
        parsed.rows.append(
            ContactRow(
                external_id=external_id,
                name=name,
                salutation_line=cell(row, "Briefanrede"),
                username=cell(row, "Benutzername"),
                address=cell(row, "Adresse"),
                house_number=cell(row, "Hausnummer"),
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
                line=row.line,
                iban=cell(row, "IBAN"),
            )
        )
    if skipped:
        parsed.notes.append(f"{source_file}: {skipped} Zeile(n) ohne id oder Name übersprungen")
    return parsed


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


def split_title(name: str) -> tuple[str | None, str]:
    """Academic title at the start of a name ("Dr. Hans Müller", "Prof. Dr. med. Ute Kern")."""
    match = _TITLE.match(name)
    if not match:
        return None, name.strip()
    title = " ".join(match.group(1).split())
    return title, name[match.end() :].strip()


def legal_form(company_name: str) -> str | None:
    """Legal form contained in a company name ("Lotta Center GmbH & Co. KG")."""
    forms = [" ".join(m.group(1).split()) for m in _LEGAL_FORM.finditer(company_name)]
    if not forms:
        return None
    return max(forms, key=len)[:50]


def split_person_name(
    name: str, salutation_line: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """``(first_name, last_name, note)``. "Nachname, Vorname" is unambiguous; otherwise the
    family name named in the salutation line ("Sehr geehrte Frau Joachims") decides, and only
    as a last resort the final token counts as family name (noted as a guess)."""
    clean = " ".join(name.strip().strip(",").split())
    if "," in clean:
        last, first = (p.strip() for p in clean.split(",", 1))
        _, first = split_title(first)
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
    street, number, _ = split_address(address)
    return street, number


def split_address(address: str | None) -> tuple[str | None, str | None, str | None]:
    """``(street, house_number, addition)``; "Hauptstraße 12 a, Whg. 3" gives all three."""
    if not address:
        return None, None, None
    clean = " ".join(address.split())
    match = _HOUSE_NUMBER.match(clean)
    if (
        match
        and not re.fullmatch(r"\d.*", clean)
        and not re.search(r"\d\s*/", match.group("street"))
    ):
        number = " ".join(match.group("number").split())
        addition = match.group("addition")
        if len(number) <= 20:
            return match.group("street").strip(), number, (addition or None)
    # Two addresses in one field ("Venner Straße 16 / Annakirchenstraße 24"): keep as text.
    return clean[:200], None, None


def split_emails(raw: str | None) -> list[str]:
    """All addresses in a cell, lower case, in order and without repeats ("a@x.de; b@y.de",
    "Max Muster <max@x.de>", "mailto:max@x.de")."""
    if not raw:
        return []
    found: list[str] = []
    for match in _EMAIL.finditer(raw):
        email = match.group(0).lower().strip(".")
        if email not in found:
            found.append(email)
    return found


def _phone_digits(value: str | None) -> str:
    """Digits of a phone cell, a leading plus kept ("+49 (0) 2431 / 95 50 30-0")."""
    text = (value or "").strip()
    text = re.sub(r"\(\s*0\s*\)", "", text)  # (0) after the country code
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    return ("+" if plus else "") + digits


def compose_phone(
    country_code: str | None, area_code: str | None, number: str | None
) -> str | None:
    """One dial string from the three export columns, whatever spacing, slashes, dashes or
    brackets they use; a number that already carries + or 00 wins over the other columns."""
    local = _phone_digits(number)
    area = _phone_digits(area_code).lstrip("+")
    cc = _phone_digits(country_code)
    if not local and not area:
        return None
    if local.startswith("+"):
        return local
    if local.startswith("00") and len(local) > 4 and not area:
        return "+" + local[2:]
    international = cc.startswith(("+", "00")) or (cc.isdigit() and not cc.startswith("0"))
    if international:
        cc = cc.lstrip("+").removeprefix("00")
        rest = area.lstrip("0") + local if area else local.lstrip("0")
        return f"+{cc}{rest}"
    # A column "Landesvorwahl" holding "030" is an area code in the wrong column: domestic.
    domestic = f"{cc}{area}{local}"
    if domestic and not domestic.startswith("0"):
        domestic = "0" + domestic
    return domestic or None


def _iban_note(raw: str) -> str:
    """The IBAN of an export is a proposal only: reported masked, never stored (M19-05; a bank
    account needs a manual entry and the four eyes release of ``mhvp.contacts``)."""
    try:
        iban = normalise_iban(raw)
    except InvalidValueError as exc:
        return f"IBAN laut Altsystem ungültig ({exc}), nicht übernommen"
    return (
        f"IBAN laut Altsystem {mask_iban(iban)}: nur Vorschlag, nicht übernommen. "
        "Bankverbindung manuell erfassen und im Vier-Augen-Verfahren freigeben."
    )


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
        company_name = " ".join(row.name.strip().strip(",").split())[:200]
        data["company_name"] = company_name
        data["legal_form"] = legal_form(company_name)
    else:
        title, rest = split_title(row.name)
        first, last, note = split_person_name(rest, row.salutation_line)
        data["title"] = title
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
        if mapped is None and re.fullmatch(r"[A-Za-z]{2}", row.country.strip()):
            mapped = row.country.strip().upper()
        if mapped is None:
            notes.append(f"Land {row.country!r} nicht zugeordnet, DE angenommen")
        else:
            country = mapped
    street: str | None
    house_number: str | None
    addition: str | None
    if row.house_number:
        street, house_number, addition = row.address, row.house_number[:20], None
    else:
        street, house_number, addition = split_address(row.address)
    if any((street, row.postal_code, row.city)):
        data["addresses"] = [
            {
                "street": street,
                "house_number": house_number,
                "postal_code": row.postal_code,
                "city": row.city,
                "country": country,
                "addition": addition,
                "is_primary": True,
            }
        ]
    else:
        data["completeness"] = Completeness.INCOMPLETE.value
    source_notes: list[str] = []
    phone = compose_phone(row.country_code, row.area_code, row.phone)
    if phone:
        try:
            data["phones"] = [cs.PhoneIn.model_validate({"number": phone, "is_primary": True})]
        except ValueError:
            notes.append(f"Telefon {phone!r} ungültig, nur als Notiz übernommen")
            source_notes.append(f"Telefon laut Altsystem: {phone}")
    emails = split_emails(row.email)
    if row.email and not emails:
        notes.append(f"E-Mail {row.email!r} ungültig, nur als Notiz übernommen")
        source_notes.append(f"E-Mail laut Altsystem: {row.email}")
    elif emails:
        valid: list[cs.EmailIn] = []
        for i, email in enumerate(emails):
            try:
                valid.append(cs.EmailIn.model_validate({"email": email, "is_primary": i == 0}))
            except ValueError:
                notes.append(f"E-Mail {email!r} ungültig, nur als Notiz übernommen")
                source_notes.append(f"E-Mail laut Altsystem: {email}")
        if valid:
            valid[0].is_primary = True
            data["emails"] = valid
        if len(emails) > 1:
            notes.append(f"{len(emails)} E-Mail-Adressen übernommen, die erste als Hauptadresse")
    if row.iban:
        note = _iban_note(row.iban)
        notes.append(note)
        source_notes.append(note)
    if source_notes:
        data["notes"] = "\n".join(source_notes)
    try:
        contact_in = cs.ContactIn.model_validate(data)
    except ValueError as exc:
        problems.append(f"Kontakt ungültig: {exc}")
        return Prepared(row, None, notes, problems)
    return Prepared(row, contact_in, notes, problems)


def prepare(rows: list[ContactRow] | ParsedKontakte) -> list[Prepared]:
    """Prepared contacts; a repeated id within the same file is marked as duplicate of the
    first line and is not created again."""
    items = rows.rows if isinstance(rows, ParsedKontakte) else rows
    seen: dict[tuple[str, str], int] = {}
    out: list[Prepared] = []
    for row in items:
        key = (row.source_file, row.external_id)
        first_line = seen.get(key)
        if first_line is not None:
            out.append(
                Prepared(
                    row,
                    None,
                    [f"id {row.external_id} bereits in Zeile {first_line}, nicht erneut angelegt"],
                    [],
                    duplicate_of=first_line,
                )
            )
            continue
        seen[key] = row.line
        out.append(prepare_row(row))
    return out


class _DryRunError(Exception):
    pass


async def apply_prepared(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    prepared: list[Prepared],
    *,
    recorder: Any | None = None,
    file_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Create contacts in an open tenant session (CLI and API share this).

    The caller decides whether the transaction is committed (apply) or rolled back (test run).
    ``recorder`` (``mhvp.ai.imports.Recorder``) registers created rows for undo; ``file_notes``
    (encoding, delimiter, skipped lines) are passed through to the report."""
    counts: Counter[str] = Counter()
    lines: list[dict[str, Any]] = []
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
        if item.duplicate_of is not None:
            entry["status"] = "duplicate"
            counts["duplicate"] += 1
            continue
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
        party = await create_party(session, tenant_id, user_id, [contact])
        if recorder is not None:
            recorder.add("contact", contact.id)
            recorder.add("party", party.id)
        entry["status"] = "created"
        counts["created"] += 1
    await session.flush()
    return {"counts": dict(counts), "kontakte": lines, "datei_hinweise": list(file_notes or [])}


async def import_prepared(
    factory: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    prepared: list[Prepared],
    *,
    apply: bool,
    file_notes: list[str] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            report = await apply_prepared(
                session, tenant_id, user_id, prepared, file_notes=file_notes
            )
            if not apply:
                raise _DryRunError
    except _DryRunError:
        pass
    return {"apply": apply, **report}


def _read_file(path: str) -> tuple[str, str | None]:
    with open(path, "rb") as handle:
        return decode_csv(handle.read())


def load_files(specs: list[str]) -> ParsedKontakte:
    """``ROLE=PATH`` or a path whose file name carries the group (eigentuemer, mieter, bank,
    sonstige)."""
    parsed = ParsedKontakte()
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
        text, encoding_note = _read_file(path)
        if encoding_note:
            parsed.notes.append(f"{Path(path).name}: {encoding_note}")
        parsed.extend(parse_kontakte(text, role, Path(path).name))
    return parsed


def _print_report(report: dict[str, Any], verbose: bool) -> None:
    mode = "ÜBERNOMMEN" if report["apply"] else "TESTLAUF (nichts gespeichert)"
    print(f"Kontakt-Import: {mode}")
    for note in report.get("datei_hinweise", []):
        print(f"  Datei: {note}")
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
        help="CSV-Dateien (UTF-8 oder Windows-1252; Semikolon, Komma, Tab); Rolle aus dem "
        "Dateinamen (eigentuemer, mieter, bank, sonstige) oder als ROLLE=PFAD",
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
    try:
        parsed = load_files(args.files)
    except (ValueError, OSError) as exc:
        print(f"Datei nicht lesbar: {exc}", file=sys.stderr)
        return 2
    prepared = prepare(parsed)

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
        report = await import_prepared(
            factory, tenant_id, user_id, prepared, apply=args.apply, file_notes=parsed.notes
        )
        _print_report(report, args.verbose)
        log.info("kontakte_import", apply=args.apply, counts=report["counts"])
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
