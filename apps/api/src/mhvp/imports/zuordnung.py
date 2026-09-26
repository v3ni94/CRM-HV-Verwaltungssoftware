# ruff: noqa: T201 - operator CLI, output goes to the terminal
"""``python -m mhvp.imports.zuordnung``: owners and tenants of the object list as contracts.

Third step after ``mhvp.imports.objektdaten`` (properties and units) and ``mhvp.imports.kontakte``
(contacts). For every unit of the Immoware24 object list the current owner and tenant are matched
by name against the imported contacts (only contacts carrying ``external_ids["immoware24"]``).
Per match the contact's party (role primary) is used or created and a contract is created:
ownership for "WEG-Verwaltung" and "WEG mit SE-Verwaltung", tenancy for "Mietverwaltung" and
"WEG mit SE-Verwaltung". The agreed amount becomes a monthly contract payment (Hausgeld
``hoa_fee`` or Miete ``rent``) with a monthly payment schedule. Start date is ``--start-date``
(default 1 January of the current year, an assumption shown in the report).

Nothing is overwritten: an active contract of the same kind with the same party counts as
already assigned, a different party is reported as conflict. Ambiguous names (several imported
contacts with the same normalised name) are reported, never guessed. Default is a test run
without database changes; ``--apply`` writes.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select

from mhvp.contacts.models import Contact, ContactRoleCode, Party, PartyMember, PartyRole
from mhvp.contacts.services import recompute_derived_roles
from mhvp.contracts import services as contract_services
from mhvp.contracts.models import (
    Contract,
    ContractKind,
    ContractPayment,
    DueDayRule,
    PaymentInterval,
    PaymentReason,
    PaymentSchedule,
)
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.logging import configure_logging, get_logger
from mhvp.core.problems import ProblemError
from mhvp.imports.objektdaten import (
    SOURCE_SYSTEM,
    PropertyRow,
    UnitRow,
    classify_name,
    parse_objektdaten,
)
from mhvp.platform.models import Tenant, User
from mhvp.properties.models import Property, PropertyStatus, Unit

OWNERSHIP_MANAGEMENT = frozenset({"WEG-Verwaltung", "WEG mit SE-Verwaltung"})
TENANCY_MANAGEMENT = frozenset({"Mietverwaltung", "WEG mit SE-Verwaltung"})
SEV_MANAGEMENT = "WEG mit SE-Verwaltung"
VACANT = "leerstand"
PAYMENT_TYPE = {ContractKind.OWNERSHIP: "hoa_fee", ContractKind.TENANCY: "rent"}
ROLE = {
    ContractKind.OWNERSHIP: ContactRoleCode.EIGENTUEMER,
    ContractKind.TENANCY: ContactRoleCode.MIETER,
}
LABEL = {ContractKind.OWNERSHIP: "Eigentümer", ContractKind.TENANCY: "Mieter"}

_AND = re.compile(r"(?<!\w)u\.(?=\s|$)|(?<!\w)u\.(?=\w)")
_SPACE = re.compile(r"\s+")


def normalise_name(name: str) -> str:
    """Comparison key: case, whitespace and "u." versus "&" do not matter."""
    text = name.casefold().strip().rstrip(",").strip()
    text = _AND.sub("&", text)
    text = re.sub(r"\s*&\s*", " & ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return _SPACE.sub(" ", text).strip()


def parse_amount(raw: str | None) -> Decimal | None:
    """German amount ("1.019,71") as Decimal with two places; None if empty or unreadable."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip().replace("EUR", "").replace("€", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def amount_cents(value: Decimal) -> int:
    return int((value * 100).to_integral_value())


def default_start_date(today: date | None = None) -> date:
    return date((today or datetime.now(UTC).date()).year, 1, 1)


@dataclass(frozen=True)
class ContactEntry:
    contact_id: uuid.UUID
    external_id: str
    display_name: str


class ContactIndex:
    """Normalised names of the imported contacts. The exported name and the display name are
    primary keys; reordered person names ("Vorname Nachname") only count if nothing else fits."""

    def __init__(self) -> None:
        self.primary: dict[str, dict[uuid.UUID, ContactEntry]] = {}
        self.secondary: dict[str, dict[uuid.UUID, ContactEntry]] = {}

    def add(
        self,
        entry: ContactEntry,
        *,
        source_name: str | None,
        first_name: str | None,
        last_name: str | None,
        company_name: str | None,
    ) -> None:
        for key in {source_name, entry.display_name, company_name}:
            if key:
                self.primary.setdefault(normalise_name(key), {})[entry.contact_id] = entry
        if first_name and last_name:
            for key in (f"{first_name} {last_name}", f"{last_name} {first_name}"):
                self.secondary.setdefault(normalise_name(key), {})[entry.contact_id] = entry

    def lookup(self, name: str) -> list[ContactEntry]:
        key = normalise_name(name)
        found = self.primary.get(key) or self.secondary.get(key) or {}
        return sorted(found.values(), key=lambda e: e.external_id)


class Decision:
    CREATE = "create"
    EXISTS = "exists"
    CONFLICT = "conflict"


def decide(existing_party_ids: list[uuid.UUID], party_id: uuid.UUID | None) -> str:
    """Idempotency rule for one unit and contract kind: no active contract, create; an active
    contract with the same party, nothing to do; any other party, conflict (never overwrite)."""
    if not existing_party_ids:
        return Decision.CREATE
    if party_id is not None and party_id in existing_party_ids:
        return Decision.EXISTS
    return Decision.CONFLICT


@dataclass
class Report:
    apply: bool
    start_date: date
    start_date_assumed: bool
    units_total: int = 0
    owners_assigned: int = 0
    tenants_assigned: int = 0
    vacant: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    not_found: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "start_date": self.start_date.isoformat(),
            "start_date_assumed": self.start_date_assumed,
            "einheiten_gesamt": self.units_total,
            "eigentuemer_zugeordnet": self.owners_assigned,
            "mieter_zugeordnet": self.tenants_assigned,
            "leerstand": self.vacant,
            "counts": dict(self.counts),
            "nicht_gefunden": self.not_found,
            "mehrdeutig": self.ambiguous,
            "konflikte": self.conflicts,
            "hinweise": self.notes,
        }


async def load_contact_index(session: Any) -> ContactIndex:
    index = ContactIndex()
    stmt = (
        select(
            Contact.id,
            Contact.external_ids,
            Contact.display_name,
            Contact.first_name,
            Contact.last_name,
            Contact.company_name,
        )
        .where(Contact.external_ids.has_key(SOURCE_SYSTEM), Contact.deleted_at.is_(None))
        .order_by(Contact.id)
        .execution_options(yield_per=1000)
    )
    result = await session.stream(stmt)
    async for cid, ext, display, first, last, company in result:
        index.add(
            ContactEntry(cid, str(ext.get(SOURCE_SYSTEM)), display or ""),
            source_name=ext.get("immoware24_name"),
            first_name=first,
            last_name=last,
            company_name=company,
        )
    return index


async def load_units(session: Any) -> dict[str, tuple[uuid.UUID, uuid.UUID]]:
    """Units of the object import by ``source_id`` ("<object>/<unit>")."""
    rows = await session.execute(
        select(Unit.source_id, Unit.id, Unit.property_id).where(
            Unit.source_system == SOURCE_SYSTEM, Unit.source_id.is_not(None)
        )
    )
    return {sid: (uid, pid) for sid, uid, pid in rows}


async def party_for(
    session: Any, tenant_id: uuid.UUID, user_id: uuid.UUID | None, contact_id: uuid.UUID
) -> tuple[Party, bool]:
    """The party whose only member is the contact in role primary; created if missing."""
    single = (
        select(PartyMember.party_id)
        .group_by(PartyMember.party_id)
        .having(func.count(PartyMember.id) == 1)
    )
    party: Party | None = await session.scalar(
        select(Party)
        .join(PartyMember, PartyMember.party_id == Party.id)
        .where(
            PartyMember.contact_id == contact_id,
            PartyMember.role == PartyRole.PRIMARY,
            Party.id.in_(single),
        )
        .order_by(Party.created_at, Party.id)
        .limit(1)
    )
    if party is not None:
        return party, False
    contact = await session.get(Contact, contact_id)
    party = Party(tenant_id=tenant_id, name=contact.display_name[:400], created_by=user_id)
    session.add(party)
    await session.flush()
    session.add(
        PartyMember(
            tenant_id=tenant_id, party_id=party.id, contact_id=contact_id, role=PartyRole.PRIMARY
        )
    )
    await session.flush()
    return party, True


async def active_contracts(
    session: Any, unit_id: uuid.UUID, kind: ContractKind, start: date
) -> list[Contract]:
    rows = await session.scalars(
        select(Contract)
        .where(
            Contract.unit_id == unit_id,
            Contract.kind == kind,
            or_(Contract.end_date.is_(None), Contract.end_date >= start),
        )
        .order_by(Contract.start_date)
    )
    return list(rows.all())


@dataclass
class _Ctx:
    session: Any
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    start: date
    index: ContactIndex
    report: Report
    touched_contacts: set[uuid.UUID] = field(default_factory=set)


def _where(prop: PropertyRow, unit: UnitRow) -> dict[str, Any]:
    return {"objekt": prop.source_number, "ve": unit.number, "zeile": unit.line}


def resolve(
    ctx: _Ctx, prop: PropertyRow, unit: UnitRow, kind: ContractKind, name: str
) -> ContactEntry | None:
    """Single contact for a name or None (reported as not found or ambiguous)."""
    found = ctx.index.lookup(name)
    where = {**_where(prop, unit), "rolle": LABEL[kind], "name": name}
    if not found:
        ctx.report.not_found.append(where)
        return None
    if len(found) > 1:
        ctx.report.ambiguous.append(
            {**where, "kandidaten": [f"{e.external_id} {e.display_name}" for e in found]}
        )
        return None
    return found[0]


async def assign(
    ctx: _Ctx,
    prop: PropertyRow,
    unit: UnitRow,
    unit_id: uuid.UUID,
    property_id: uuid.UUID,
    kind: ContractKind,
    entry: ContactEntry,
    raw_amount: str | None,
    *,
    sev: bool = False,
) -> bool:
    """Contract, payment and schedule for one match. True if the unit counts as assigned."""
    session, report = ctx.session, ctx.report
    where = {**_where(prop, unit), "rolle": LABEL[kind], "name": entry.display_name}
    party, party_created = await party_for(session, ctx.tenant_id, ctx.user_id, entry.contact_id)
    if party_created:
        report.counts["parties_angelegt"] += 1
    existing = await active_contracts(session, unit_id, kind, ctx.start)
    decision = decide([c.party_id for c in existing], party.id)
    if decision == Decision.EXISTS:
        report.counts["vertraege_vorhanden"] += 1
        if kind is ContractKind.OWNERSHIP and sev and not existing[0].sev_enabled:
            report.notes.append({**where, "hinweis": "Eigentum besteht ohne SEV"})
        return True
    if decision == Decision.CONFLICT:
        others = ", ".join(sorted(c.number for c in existing))
        report.conflicts.append(
            {**where, "grund": f"aktiver Vertrag {others} mit anderer Partei, nichts geändert"}
        )
        return False
    prop_row = await session.get(Property, property_id)
    unit_row = await session.get(Unit, unit_id)
    amount = parse_amount(raw_amount)
    try:
        async with session.begin_nested():
            creditor = await contract_services.creditor_entity(
                session, prop_row, unit_row, kind, ctx.start, None
            )
            account = await contract_services.debtor_account(
                session, ctx.tenant_id, creditor, party, unit_row
            )
            ownership = kind is ContractKind.OWNERSHIP
            contract = Contract(
                tenant_id=ctx.tenant_id,
                created_by=ctx.user_id,
                kind=kind,
                property_id=property_id,
                unit_id=unit_id,
                party_id=party.id,
                legal_entity_id=creditor,
                debtor_account_id=account.id,
                number=await contract_services.contract_number(session, ctx.tenant_id),
                start_date=ctx.start,
                title_transfer_date=ctx.start if ownership else None,
                sev_enabled=ownership and sev,
                sev_fee_debtor_party_id=party.id if ownership and sev else None,
                notes=(
                    f"Aus Immoware24 Objektdaten übernommen (Zeile {unit.line}). "
                    f"Beginn {ctx.start:%d.%m.%Y} ist eine Annahme des Imports."
                ),
            )
            session.add(contract)
            await session.flush()
            payment_created = False
            if amount is not None and amount > 0:
                code = PAYMENT_TYPE[kind]
                contract_services.check_amounts(code, amount, Decimal(0), amount)
                await contract_services.add_payment(
                    session,
                    contract,
                    ContractPayment(
                        tenant_id=ctx.tenant_id,
                        contract_id=contract.id,
                        payment_type_code=code,
                        net=amount,
                        vat_percent=Decimal(0),
                        gross=amount,
                        currency="EUR",
                        valid_from=ctx.start,
                        reason=PaymentReason.INITIAL,
                    ),
                )
                await contract_services.add_schedule(
                    session,
                    contract,
                    PaymentSchedule(
                        tenant_id=ctx.tenant_id,
                        contract_id=contract.id,
                        interval=PaymentInterval.MONTHLY,
                        due_day_rule=DueDayRule.DAY,
                        due_day=1,
                        valid_from=ctx.start,
                    ),
                )
                await session.flush()
                payment_created = True
            elif raw_amount:
                report.notes.append(
                    {**where, "hinweis": f"Zahlbetrag {raw_amount!r} nicht übernommen"}
                )
            else:
                report.notes.append({**where, "hinweis": "ohne Zahlbetrag angelegt"})
            await emit(
                session,
                tenant_id=ctx.tenant_id,
                type="contract.created",
                entity_type="contract",
                entity_id=contract.id,
                actor_user_id=ctx.user_id,
                payload={"kind": kind.value, "source": "import.zuordnung"},
            )
    except ProblemError as exc:
        report.conflicts.append({**where, "grund": exc.detail or str(exc)})
        return False
    report.counts["vertraege_angelegt"] += 1
    if payment_created and amount is not None:
        report.counts["zahlungen_angelegt"] += 1
        report.counts[f"zahlungen_cent_{PAYMENT_TYPE[kind]}"] += amount_cents(amount)
    contact = await session.get(Contact, entry.contact_id)
    role = ROLE[kind].value
    if role not in (contact.roles or []):
        contact.roles = sorted({*(contact.roles or []), role})
    ctx.touched_contacts.add(entry.contact_id)
    return True


async def apply_rows(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    rows: list[PropertyRow],
    *,
    apply: bool,
    start: date,
    start_assumed: bool,
    skip_handed_over: bool = False,
) -> Report:
    """Assign owners and tenants in an open tenant session; the caller commits or rolls back."""
    report = Report(apply=apply, start_date=start, start_date_assumed=start_assumed)
    ctx = _Ctx(session, tenant_id, user_id, start, await load_contact_index(session), report)
    units = await load_units(session)
    for prop in rows:
        _, status, _ = classify_name(prop.name)
        handed_over = status is PropertyStatus.TERMINATED
        for unit in prop.units:
            report.units_total += 1
            if skip_handed_over and handed_over:
                report.counts["uebersprungen_abgegeben"] += 1
                continue
            found = units.get(f"{prop.source_number}/{unit.number}")
            if found is None:
                report.counts["einheit_fehlt"] += 1
                report.notes.append(
                    {**_where(prop, unit), "hinweis": "Einheit nicht importiert (objektdaten)"}
                )
                continue
            unit_id, property_id = found
            tenant_vacant = bool(unit.tenant) and normalise_name(unit.tenant or "") == VACANT
            if tenant_vacant:
                report.vacant += 1
            wants_tenant = (
                prop.management in TENANCY_MANAGEMENT and bool(unit.tenant) and not tenant_vacant
            )
            if prop.management in OWNERSHIP_MANAGEMENT and unit.owner:
                owner = resolve(ctx, prop, unit, ContractKind.OWNERSHIP, unit.owner)
                if owner is not None and await assign(
                    ctx,
                    prop,
                    unit,
                    unit_id,
                    property_id,
                    ContractKind.OWNERSHIP,
                    owner,
                    unit.owner_amount,
                    sev=prop.management == SEV_MANAGEMENT and wants_tenant,
                ):
                    report.owners_assigned += 1
            if wants_tenant and unit.tenant:
                tenant = resolve(ctx, prop, unit, ContractKind.TENANCY, unit.tenant)
                if tenant is not None and await assign(
                    ctx,
                    prop,
                    unit,
                    unit_id,
                    property_id,
                    ContractKind.TENANCY,
                    tenant,
                    unit.tenant_amount,
                ):
                    report.tenants_assigned += 1
    for contact_id in sorted(ctx.touched_contacts):
        contact = await session.get(Contact, contact_id)
        await recompute_derived_roles(session, contact)
    await session.flush()
    return report


class _DryRunError(Exception):
    pass


async def import_rows(
    factory: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    rows: list[PropertyRow],
    *,
    apply: bool,
    start: date,
    start_assumed: bool,
    skip_handed_over: bool = False,
) -> dict[str, Any]:
    """Run the assignment; a test run rolls the transaction back."""
    report: Report | None = None
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            report = await apply_rows(
                session,
                tenant_id,
                user_id,
                rows,
                apply=apply,
                start=start,
                start_assumed=start_assumed,
                skip_handed_over=skip_handed_over,
            )
            if not apply:
                raise _DryRunError
    except _DryRunError:
        pass
    if report is None:  # pragma: no cover - apply_rows always returns
        raise RuntimeError("Zuordnung ohne Bericht")
    return report.as_dict()


def _euro(cents: int) -> str:
    whole, rest = divmod(abs(cents), 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}{whole:,}".replace(",", ".") + f",{rest:02d} EUR"


def print_report(report: dict[str, Any]) -> None:
    mode = "ÜBERNOMMEN" if report["apply"] else "TESTLAUF (nichts gespeichert)"
    start = date.fromisoformat(report["start_date"])
    print(f"Zuordnung Eigentümer und Mieter: {mode}")
    assumed = (
        " (Annahme, Standard 01.01. des laufenden Jahres)" if report["start_date_assumed"] else ""
    )
    print(f"  Vertragsbeginn: {start:%d.%m.%Y}{assumed}")
    counts = report["counts"]
    for label, value in (
        ("Einheiten gesamt", report["einheiten_gesamt"]),
        ("Eigentümer zugeordnet", report["eigentuemer_zugeordnet"]),
        ("Mieter zugeordnet", report["mieter_zugeordnet"]),
        ("Leerstand", report["leerstand"]),
        ("nicht gefunden", len(report["nicht_gefunden"])),
        ("mehrdeutig", len(report["mehrdeutig"])),
        ("Konflikte", len(report["konflikte"])),
        ("Parteien angelegt", counts.get("parties_angelegt", 0)),
        ("Verträge angelegt", counts.get("vertraege_angelegt", 0)),
        ("Verträge bereits vorhanden", counts.get("vertraege_vorhanden", 0)),
        ("Zahlungen angelegt", counts.get("zahlungen_angelegt", 0)),
        ("Einheiten nicht importiert", counts.get("einheit_fehlt", 0)),
        ("abgegeben übersprungen", counts.get("uebersprungen_abgegeben", 0)),
    ):
        print(f"  {label}: {value}")
    for code, text in (("hoa_fee", "Hausgeld monatlich"), ("rent", "Miete monatlich")):
        cents = counts.get(f"zahlungen_cent_{code}")
        if cents:
            print(f"  Summe {text}: {_euro(cents)}")
    for title, key in (
        ("Nicht gefunden", "nicht_gefunden"),
        ("Mehrdeutig", "mehrdeutig"),
        ("Konflikte", "konflikte"),
        ("Hinweise", "hinweise"),
    ):
        if not report[key]:
            continue
        print(f"{title}:")
        for item in report[key]:
            head = f"  {item['objekt']}/{item['ve']} (Zeile {item['zeile']})"
            who = f" {item['rolle']} {item['name']!r}" if "rolle" in item else ""
            detail = item.get("grund") or item.get("hinweis") or ""
            extra = f": {'; '.join(item['kandidaten'])}" if "kandidaten" in item else ""
            print(f"{head}{who}{': ' + detail if detail else ''}{extra}")


def _read_file(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8-sig", errors="strict")


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.imports.zuordnung",
        description="Eigentümer und Mieter der Immoware24-Objektliste als Verträge zuordnen.",
    )
    parser.add_argument("file", help="CSV (Semikolon, UTF-8) mit den Objektdaten")
    parser.add_argument("--tenant", required=True, help="Mandanten-Slug")
    parser.add_argument("--user", help="E-Mail des ausführenden Benutzers (Ersteller)")
    parser.add_argument(
        "--apply", action="store_true", help="wirklich speichern (Standard: Testlauf)"
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        help="Vertragsbeginn JJJJ-MM-TT (Standard: 01.01. des laufenden Jahres)",
    )
    parser.add_argument(
        "--skip-handed-over",
        action="store_true",
        help="Einheiten abgegebener Objekte (Präfix 'Z ABGEGEBEN') nicht zuordnen",
    )
    args = parser.parse_args(argv)
    rows = parse_objektdaten(_read_file(args.file))
    start = args.start_date or default_start_date()

    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.imports.zuordnung")
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
        report = await import_rows(
            factory,
            tenant_id,
            user_id,
            rows,
            apply=args.apply,
            start=start,
            start_assumed=args.start_date is None,
            skip_handed_over=args.skip_handed_over,
        )
        print_report(report)
        log.info("zuordnung_import", apply=args.apply, counts=report["counts"])
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
