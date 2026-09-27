"""Contract lists of the full import (M8-01, M8-02): Mietverträge and Eigentümerverträge.

The two export types extend ``mhvp.imports.vollimport``: pre-check with the expected columns,
dry run and idempotent apply, and a reconciliation per contract kind with per object counts
and target rent / fee sums (reference figures of the file against the platform).

Keys: the Immoware24 contract number (kept in ``import_external_key``) or, without one, object
number, unit number, contract kind and start date. The party is found via the contact id of
the contact lists (``external_ids["immoware24"]``), the unit via object number and unit
number. Rent and Hausgeld become contract payments (``rent`` / ``hoa_fee``, tax rate 0) with a
monthly schedule; nothing is posted (rule 0.1.1, B01) and imported contracts wait for the
management approval (``approval_status = pending``, migration 0133).

Domain limits follow ``mhvp.contracts.services.creditor_entity``: a tenancy in a pure WEG
object is rejected (M5-03), a tenancy in a WEG mit SEV object needs an ownership with SEV
(derived here: SEV column or a tenancy row of the same unit in the uploaded Mietverträge), an
ownership row in a Mietverwaltung object records the landlord (property owner) instead of a
contract, and a tenancy in a Mietverwaltung object needs that landlord.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.contacts.models import Contact, Party, PartyMember
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
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError
from mhvp.imports import objektdaten
from mhvp.imports.csvtext import Table
from mhvp.imports.fields import parse_date, parse_decimal
from mhvp.imports.models import ImportExternalKey
from mhvp.imports.zuordnung import party_for
from mhvp.properties import services as property_services
from mhvp.properties.models import ManagementType, Property, PropertyOwner, Unit

if TYPE_CHECKING:
    from mhvp.imports.vollimport import EntityReport

SOURCE_SYSTEM = "immoware24"
CONTRACT_SOURCE = "immoware24:vollimport"
KEY_ENTITY = "contract"
KEY_ENTITY_OWNER = "property_owner"
CENT = Decimal("0.01")
PAYMENT_TYPE = {ContractKind.OWNERSHIP: "hoa_fee", ContractKind.TENANCY: "rent"}
ENTITY = {ContractKind.TENANCY: "mietvertraege", ContractKind.OWNERSHIP: "eigentuemervertraege"}
KIND_OF = {v: k for k, v in ENTITY.items()}
_YES = {"ja", "j", "x", "1", "true", "wahr", "sev"}

# Column labels follow the target fields of the staging assistant (``mhvp.imports.fields``,
# report types tenancies and ownerships); the exported header names are not specified (13.1)
# and the alternatives are tolerated spellings, not a statement about the real export.
_COMMON: dict[str, tuple[str, ...]] = {
    "Vertragsnummer": ("Vertragsnummer", "Vertrags-Nr", "Vertrags-Nr.", "Vertrag", "Vertrags-ID"),
    "Objektnummer": ("Objektnummer", "Objekt-Nummer", "Objekt Nr", "Objekt"),
    "Einheitennummer": ("Einheitennummer", "VE-Nummer", "Einheit", "VE", "Einheiten-Nr"),
}
MIET_COLUMNS: dict[str, tuple[str, ...]] = {
    **_COMMON,
    "Kontakt-ID Mieter": ("Kontakt-ID Mieter", "Kontakt-ID", "Mieter-ID", "Mieter", "Kontakt"),
    "Mietbeginn": ("Mietbeginn", "Beginn", "Vertragsbeginn", "Von", "Einzug"),
    "Mietende": ("Mietende", "Ende", "Vertragsende", "Bis", "Auszug"),
    "Miete": ("Miete", "Sollmiete", "Kaltmiete", "vereinbarter Zahlbetrag", "Zahlbetrag", "Betrag"),
}
MIET_REQUIRED = ("Objektnummer", "Einheitennummer", "Kontakt-ID Mieter", "Mietbeginn")
EIG_COLUMNS: dict[str, tuple[str, ...]] = {
    **_COMMON,
    "Kontakt-ID Eigentümer": (
        "Kontakt-ID Eigentümer",
        "Kontakt-ID",
        "Eigentümer-ID",
        "Eigentümer",
        "Kontakt",
    ),
    "Beginn": ("Beginn", "Vertragsbeginn", "Von", "Eigentum seit"),
    "Eigentumsübergang (Grundbuch)": (
        "Eigentumsübergang (Grundbuch)",
        "Eigentumsübergang",
        "Grundbuch",
        "Grundbucheintrag",
    ),
    "Nutzen-/Lastenwechsel": ("Nutzen-/Lastenwechsel", "Nutzen-Lasten-Wechsel", "Lastenwechsel"),
    "Ende": ("Ende", "Vertragsende", "Bis"),
    "Hausgeld": ("Hausgeld", "Sollhausgeld", "vereinbarter Zahlbetrag", "Zahlbetrag", "Betrag"),
    "SEV": ("SEV", "Sondereigentumsverwaltung", "SE-Verwaltung", "SEV-Verwaltung"),
}
EIG_REQUIRED = ("Objektnummer", "Einheitennummer", "Kontakt-ID Eigentümer", "Beginn")
KEY_COLUMNS = ("Objektnummer", "Einheitennummer")


@dataclass
class ContractRow:
    line: int
    kind: ContractKind
    contract_no: str | None
    object_raw: str
    unit_no: str
    contact_id: str
    start: date | None
    end: date | None = None
    title_transfer: date | None = None
    benefit_burden: date | None = None
    amount: Decimal | None = None
    sev: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def unit_key(self) -> str:
        return f"{self.object_raw}/{self.unit_no}"

    def where(self) -> dict[str, Any]:
        return {
            "zeile": self.line,
            "vertragsnummer": self.contract_no,
            "objekt": self.object_raw,
            "ve": self.unit_no,
            "kontakt": self.contact_id,
            "beginn": self.start.isoformat() if self.start else None,
        }


@dataclass
class ParsedContracts:
    kind: ContractKind
    rows: list[ContractRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _date(raw: str | None, label: str, problems: list[str], required: bool) -> date | None:
    if raw is None or not raw.strip():
        if required:
            problems.append(f"{label} fehlt")
        return None
    try:
        return parse_date(raw)
    except ValueError as exc:
        problems.append(f"{label}: {exc}")
        return None


def _amount(raw: str | None, label: str, problems: list[str]) -> Decimal | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = parse_decimal(raw).quantize(CENT)
    except (InvalidOperation, ValueError):
        problems.append(f"{label} {raw!r} nicht lesbar")
        return None
    if value < 0:
        problems.append(f"{label} {raw!r} ist negativ")
        return None
    return value


def parse_contracts(table: Table, kind: ContractKind) -> ParsedContracts:
    """Rows of a Mietverträge or Eigentümerverträge export; unreadable values are problems of
    the row (reported, never guessed)."""
    spec = MIET_COLUMNS if kind is ContractKind.TENANCY else EIG_COLUMNS
    col = {label: table.column(*names) for label, names in spec.items()}
    parsed = ParsedContracts(kind)
    tenancy = kind is ContractKind.TENANCY
    for row in table.rows:
        problems: list[str] = []
        obj = table.cell(row, col["Objektnummer"]) or ""
        unit_no = table.cell(row, col["Einheitennummer"]) or ""
        contact = table.cell(row, col["Kontakt-ID Mieter" if tenancy else "Kontakt-ID Eigentümer"])
        if not obj:
            problems.append("Objektnummer fehlt")
        if not unit_no:
            problems.append("Einheitennummer fehlt")
        if not contact:
            problems.append("Kontakt-ID fehlt")
        start = _date(
            table.cell(row, col["Mietbeginn" if tenancy else "Beginn"]),
            "Mietbeginn" if tenancy else "Beginn",
            problems,
            True,
        )
        end = _date(
            table.cell(row, col["Mietende" if tenancy else "Ende"]), "Ende", problems, False
        )
        if start and end and end < start:
            problems.append("Ende liegt vor dem Beginn")
        item = ContractRow(
            row.line,
            kind,
            (table.cell(row, col["Vertragsnummer"]) or "").strip()[:100] or None,
            obj.strip(),
            unit_no.strip()[:20],
            (contact or "").strip(),
            start,
            end,
            amount=_amount(
                table.cell(row, col["Miete" if tenancy else "Hausgeld"]),
                "Miete" if tenancy else "Hausgeld",
                problems,
            ),
            problems=problems,
        )
        if not tenancy:
            item.title_transfer = _date(
                table.cell(row, col["Eigentumsübergang (Grundbuch)"]),
                "Eigentumsübergang",
                problems,
                False,
            )
            item.benefit_burden = _date(
                table.cell(row, col["Nutzen-/Lastenwechsel"]),
                "Nutzen-/Lastenwechsel",
                problems,
                False,
            )
            item.sev = (table.cell(row, col["SEV"]) or "").strip().casefold() in _YES
        parsed.rows.append(item)
    if not tenancy and col["Eigentumsübergang (Grundbuch)"] is None:
        parsed.notes.append(
            "Spalte Eigentumsübergang (Grundbuch) fehlt: der Beginn wird als Eigentumsübergang "
            "übernommen (Annahme, je Vertrag zu prüfen)."
        )
    return parsed


# Lookup helpers ----------------------------------------------------------------------------


async def _properties(session: Any, tenant_id: uuid.UUID) -> dict[str, Property]:
    rows = (
        await session.execute(select(Property).where(Property.tenant_id == tenant_id))
    ).scalars()
    return {p.number: p for p in rows}


async def _units(session: Any, tenant_id: uuid.UUID) -> dict[tuple[uuid.UUID, str], Unit]:
    rows = (await session.execute(select(Unit).where(Unit.tenant_id == tenant_id))).scalars()
    return {(u.property_id, u.number): u for u in rows}


async def _contacts_by_external_id(
    session: Any, tenant_id: uuid.UUID, ids: set[str]
) -> dict[str, list[Contact]]:
    out: dict[str, list[Contact]] = defaultdict(list)
    ordered = sorted(ids)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start : start + 500]
        rows = (
            await session.execute(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.external_ids["immoware24"].astext.in_(chunk),
                    Contact.deleted_at.is_(None),
                )
            )
        ).scalars()
        for c in rows:
            out[str(c.external_ids.get("immoware24"))].append(c)
    return out


async def _external_keys(
    session: Any, tenant_id: uuid.UUID, entity_type: str
) -> dict[str, uuid.UUID]:
    rows = (
        await session.execute(
            select(ImportExternalKey).where(
                ImportExternalKey.tenant_id == tenant_id,
                ImportExternalKey.source_system == SOURCE_SYSTEM,
                ImportExternalKey.entity_type == entity_type,
            )
        )
    ).scalars()
    return {r.external_key: r.entity_id for r in rows}


async def _party_contact_ids(session: Any, party_id: uuid.UUID) -> set[str]:
    rows = (
        await session.execute(
            select(Contact.external_ids)
            .join(PartyMember, PartyMember.contact_id == Contact.id)
            .where(PartyMember.party_id == party_id)
        )
    ).scalars()
    return {str(e.get("immoware24")) for e in rows if e and e.get("immoware24") is not None}


async def _contract_by_natural_key(
    session: Any, unit_id: uuid.UUID, kind: ContractKind, start: date
) -> Contract | None:
    row: Contract | None = await session.scalar(
        select(Contract).where(
            Contract.unit_id == unit_id, Contract.kind == kind, Contract.start_date == start
        )
    )
    return row


async def _payment_at(session: Any, contract: Contract, as_of: date) -> ContractPayment | None:
    row: ContractPayment | None = await session.scalar(
        select(ContractPayment)
        .where(
            ContractPayment.contract_id == contract.id,
            ContractPayment.payment_type_code == PAYMENT_TYPE[contract.kind],
            ContractPayment.valid_from <= as_of,
            or_(ContractPayment.valid_to.is_(None), ContractPayment.valid_to >= as_of),
        )
        .order_by(ContractPayment.valid_from.desc())
        .limit(1)
    )
    return row


@dataclass
class _Ctx:
    session: Any
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    number_map: dict[str, str]
    props: dict[str, Property]
    units: dict[tuple[uuid.UUID, str], Unit]
    contacts: dict[str, list[Contact]]
    keys: dict[str, uuid.UUID]
    owner_keys: dict[str, uuid.UUID]
    tenant_units: set[str]
    recorder: Any | None


def _resolve(ctx: _Ctx, row: ContractRow) -> tuple[Property | None, Unit | None, str | None]:
    number, note = objektdaten.normalise_number(row.object_raw, ctx.number_map)
    prop = ctx.props.get(number or "")
    if prop is None:
        return None, None, note or "Objekt fehlt"
    unit = ctx.units.get((prop.id, row.unit_no))
    if unit is None:
        return prop, None, "Einheit fehlt"
    return prop, unit, None


# Apply -------------------------------------------------------------------------------------


async def _register_key(
    ctx: _Ctx, entity_type: str, key: str | None, entity_id: uuid.UUID, store: dict[str, uuid.UUID]
) -> None:
    if key is None or key in store:
        return
    ctx.session.add(
        ImportExternalKey(
            tenant_id=ctx.tenant_id,
            source_system=SOURCE_SYSTEM,
            entity_type=entity_type,
            external_key=key,
            entity_id=entity_id,
            created_by=ctx.user_id,
        )
    )
    await ctx.session.flush()
    store[key] = entity_id


async def _apply_owner_of_rental(
    ctx: _Ctx, row: ContractRow, prop: Property, party: Party, counts: Counter[str]
) -> dict[str, Any] | None:
    """Ownership row in a Mietverwaltung object: landlord of the property, no contract."""
    existing = ctx.owner_keys.get(row.contract_no or "")
    owner: PropertyOwner | None = None
    if existing is not None:
        owner = await ctx.session.get(PropertyOwner, existing)
    if owner is None:
        owner = await ctx.session.scalar(
            select(PropertyOwner).where(
                PropertyOwner.property_id == prop.id, PropertyOwner.party_id == party.id
            )
        )
    if owner is not None:
        if owner.party_id != party.id:
            counts["conflict"] += 1
            return {**row.where(), "grund": "Vermieter mit anderer Partei vorhanden"}
        counts["unchanged"] += 1
        await _register_key(ctx, KEY_ENTITY_OWNER, row.contract_no, owner.id, ctx.owner_keys)
        return None
    assert row.start is not None  # noqa: S101 - checked by the parser
    owner = PropertyOwner(
        tenant_id=ctx.tenant_id,
        property_id=prop.id,
        party_id=party.id,
        valid_from=row.start,
        valid_to=row.end,
    )
    ctx.session.add(owner)
    await ctx.session.flush()
    await property_services.owner_entity(ctx.session, prop, party.id)
    if ctx.recorder:
        ctx.recorder.add("property_owner", owner.id)
    await _register_key(ctx, KEY_ENTITY_OWNER, row.contract_no, owner.id, ctx.owner_keys)
    counts["created"] += 1
    return None


async def _create_contract(
    ctx: _Ctx, row: ContractRow, prop: Property, unit: Unit, party: Party, sev: bool
) -> Contract:
    assert row.start is not None  # noqa: S101 - checked by the parser
    session = ctx.session
    creditor = await contract_services.creditor_entity(
        session, prop, unit, row.kind, row.start, None
    )
    account = await contract_services.debtor_account(session, ctx.tenant_id, creditor, party, unit)
    ownership = row.kind is ContractKind.OWNERSHIP
    contract = Contract(
        tenant_id=ctx.tenant_id,
        created_by=ctx.user_id,
        kind=row.kind,
        property_id=prop.id,
        unit_id=unit.id,
        party_id=party.id,
        legal_entity_id=creditor,
        debtor_account_id=account.id,
        number=await contract_services.contract_number(session, ctx.tenant_id),
        start_date=row.start,
        end_date=row.end,
        title_transfer_date=(row.title_transfer or row.start) if ownership else None,
        benefit_burden_date=row.benefit_burden if ownership else None,
        sev_enabled=ownership and sev,
        sev_fee_debtor_party_id=party.id if ownership and sev else None,
        source=CONTRACT_SOURCE,
        approval_status="pending",
        notes=(
            f"Vollimport Immoware24, Zeile {row.line}"
            + (f", Vertragsnummer {row.contract_no}" if row.contract_no else "")
            + "."
        ),
    )
    session.add(contract)
    try:
        await session.flush()
    except IntegrityError:
        raise contract_services.invalid(
            "Für die Einheit besteht im Zeitraum bereits ein Vertrag dieser Art."
        ) from None
    if row.amount is not None and row.amount > 0:
        code = PAYMENT_TYPE[row.kind]
        contract_services.check_amounts(code, row.amount, Decimal(0), row.amount)
        await contract_services.add_payment(
            session,
            contract,
            ContractPayment(
                tenant_id=ctx.tenant_id,
                contract_id=contract.id,
                payment_type_code=code,
                net=row.amount,
                vat_percent=Decimal(0),
                gross=row.amount,
                currency="EUR",
                valid_from=row.start,
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
                valid_from=row.start,
            ),
        )
        await session.flush()
    await emit(
        session,
        tenant_id=ctx.tenant_id,
        type="contract.created",
        entity_type="contract",
        entity_id=contract.id,
        actor_user_id=ctx.user_id,
        payload={"kind": row.kind.value, "source": CONTRACT_SOURCE},
    )
    return contract


async def _apply_row(ctx: _Ctx, row: ContractRow, counts: Counter[str]) -> dict[str, Any] | None:
    """Returns the problem entry of the row, or None when created or unchanged."""
    if row.problems:
        counts["invalid"] += 1
        return {**row.where(), "grund": "; ".join(row.problems)}
    prop, unit, reason = _resolve(ctx, row)
    if prop is None or unit is None:
        counts["invalid"] += 1
        return {**row.where(), "grund": reason}
    contacts = ctx.contacts.get(row.contact_id) or []
    if not contacts:
        counts["invalid"] += 1
        return {**row.where(), "grund": "Kontakt fehlt"}
    party, _created = await party_for(ctx.session, ctx.tenant_id, ctx.user_id, contacts[0].id)
    if row.kind is ContractKind.OWNERSHIP and prop.management_type is ManagementType.RENTAL:
        return await _apply_owner_of_rental(ctx, row, prop, party, counts)
    assert row.start is not None  # noqa: S101 - checked by the parser
    existing: Contract | None = None
    if row.contract_no and row.contract_no in ctx.keys:
        existing = await ctx.session.get(Contract, ctx.keys[row.contract_no])
    if existing is None:
        existing = await _contract_by_natural_key(ctx.session, unit.id, row.kind, row.start)
    if existing is not None:
        if existing.party_id != party.id:
            counts["conflict"] += 1
            return {**row.where(), "grund": "Vertrag mit anderer Partei vorhanden"}
        counts["unchanged"] += 1
        await _register_key(ctx, KEY_ENTITY, row.contract_no, existing.id, ctx.keys)
        return None
    sev = (
        row.kind is ContractKind.OWNERSHIP
        and prop.management_type is ManagementType.HOA_WITH_SEV
        and (row.sev or row.unit_key in ctx.tenant_units)
    )
    try:
        async with ctx.session.begin_nested():
            contract = await _create_contract(ctx, row, prop, unit, party, sev)
    except ProblemError as exc:
        counts["invalid"] += 1
        return {**row.where(), "grund": str(exc.detail)}
    if ctx.recorder:
        ctx.recorder.add("contract", contract.id)
    await _register_key(ctx, KEY_ENTITY, row.contract_no, contract.id, ctx.keys)
    counts["created"] += 1
    return None


async def apply_contracts(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    parsed: dict[ContractKind, ParsedContracts],
    *,
    number_map: dict[str, str],
    recorder: Any | None = None,
) -> dict[str, Any]:
    """Idempotent import of the contract lists in the caller's session (ownerships first, so
    that landlords and SEV exist before the tenancies). Report: counts per kind (created,
    unchanged, conflict, invalid) and the problem entries."""
    ids = {r.contact_id for p in parsed.values() for r in p.rows if r.contact_id}
    tenant_units = {
        r.unit_key
        for r in parsed.get(ContractKind.TENANCY, ParsedContracts(ContractKind.TENANCY)).rows
    }
    ctx = _Ctx(
        session,
        tenant_id,
        user_id,
        number_map,
        await _properties(session, tenant_id),
        await _units(session, tenant_id),
        await _contacts_by_external_id(session, tenant_id, ids),
        await _external_keys(session, tenant_id, KEY_ENTITY),
        await _external_keys(session, tenant_id, KEY_ENTITY_OWNER),
        tenant_units,
        recorder,
    )
    report: dict[str, Any] = {"counts": {}, "probleme": {}, "hinweise": []}
    for kind in (ContractKind.OWNERSHIP, ContractKind.TENANCY):
        item = parsed.get(kind)
        if item is None:
            continue
        counts: Counter[str] = Counter()
        problems: list[dict[str, Any]] = []
        for row in item.rows:
            entry = await _apply_row(ctx, row, counts)
            if entry is not None:
                problems.append(entry)
        report["counts"][ENTITY[kind]] = dict(counts)
        report["probleme"][ENTITY[kind]] = problems[:500]
        report["hinweise"].extend(item.notes)
    return report


# Reconciliation ------------------------------------------------------------------------------


def _eur(value: Decimal) -> str:
    return str(value.quantize(CENT))


async def reconcile_contracts(
    session: Any,
    tenant_id: uuid.UUID,
    parsed: ParsedContracts,
    number_map: dict[str, str],
    cutoff: date,
) -> EntityReport:
    """Rows of a contract list against the platform: per row missing, duplicate or deviating
    (party, end date, amount); per object the count and the target sum of rent or Hausgeld of
    the file against the contracts and their payments valid at the cut-off date."""
    from mhvp.imports.vollimport import EntityReport

    kind = parsed.kind
    report = EntityReport(ENTITY[kind])
    report.target = len(parsed.rows)
    props = await _properties(session, tenant_id)
    units = await _units(session, tenant_id)
    keys = await _external_keys(session, tenant_id, KEY_ENTITY)
    owner_keys = await _external_keys(session, tenant_id, KEY_ENTITY_OWNER)
    party_cache: dict[uuid.UUID, set[str]] = {}

    async def party_ids(party_id: uuid.UUID) -> set[str]:
        if party_id not in party_cache:
            party_cache[party_id] = await _party_contact_ids(session, party_id)
        return party_cache[party_id]

    # Target per object from the file and actual per object from the platform.
    per_object: dict[str, dict[str, Any]] = {}
    file_props: dict[str, Property] = {}
    for row in parsed.rows:
        number, _ = objektdaten.normalise_number(row.object_raw, number_map)
        key = number or row.object_raw
        item = per_object.setdefault(
            key,
            {
                "objekt": key,
                "soll_anzahl": 0,
                "ist_anzahl": 0,
                "soll_summe": Decimal(0),
                "ist_summe": Decimal(0),
            },
        )
        item["soll_anzahl"] += 1
        item["soll_summe"] += row.amount or Decimal(0)
        if number and number in props:
            file_props[number] = props[number]
    all_contracts: list[Contract] = []
    if file_props:
        all_contracts = list(
            (
                await session.execute(
                    select(Contract).where(
                        Contract.tenant_id == tenant_id,
                        Contract.kind == kind,
                        Contract.property_id.in_([p.id for p in file_props.values()]),
                    )
                )
            ).scalars()
        )
    prop_number = {p.id: p.number for p in props.values()}
    for c in all_contracts:
        found_item = per_object.get(prop_number.get(c.property_id, ""))
        if found_item is None:
            continue
        found_item["ist_anzahl"] += 1
        payment = await _payment_at(session, c, cutoff)
        if payment is not None:
            found_item["ist_summe"] += payment.gross
    if kind is ContractKind.OWNERSHIP:
        rental_ids = [
            p.id for p in file_props.values() if p.management_type is ManagementType.RENTAL
        ]
        if rental_ids:
            owners = (
                await session.execute(
                    select(PropertyOwner).where(PropertyOwner.property_id.in_(rental_ids))
                )
            ).scalars()
            for o in owners:
                owner_item = per_object.get(prop_number.get(o.property_id, ""))
                if owner_item is not None:
                    owner_item["ist_anzahl"] += 1
    report.actual = sum(int(i["ist_anzahl"]) for i in per_object.values())
    matched_ids: set[uuid.UUID] = set()
    for row in parsed.rows:
        where = row.where()
        if row.problems:
            report.missing.append(
                {"schluessel": row.unit_key, **where, "grund": "; ".join(row.problems)}
            )
            continue
        number, note = objektdaten.normalise_number(row.object_raw, number_map)
        prop = props.get(number or "")
        unit = units.get((prop.id, row.unit_no)) if prop else None
        if prop is None or unit is None:
            report.missing.append(
                {
                    "schluessel": row.unit_key,
                    **where,
                    "grund": note or ("Objekt fehlt" if prop is None else "Einheit fehlt"),
                }
            )
            continue
        if kind is ContractKind.OWNERSHIP and prop.management_type is ManagementType.RENTAL:
            owner_id = owner_keys.get(row.contract_no or "")
            found_owner: PropertyOwner | None = None
            if owner_id is not None:
                found_owner = await session.get(PropertyOwner, owner_id)
            if found_owner is None:
                candidates = list(
                    (
                        await session.execute(
                            select(PropertyOwner).where(PropertyOwner.property_id == prop.id)
                        )
                    ).scalars()
                )
                for o in candidates:
                    if row.contact_id in await party_ids(o.party_id):
                        found_owner = o
                        break
            if found_owner is None:
                report.missing.append(
                    {"schluessel": row.unit_key, **where, "grund": "Vermieter nicht erfasst"}
                )
            else:
                report.matched += 1
            continue
        assert row.start is not None  # noqa: S101 - checked by the parser
        found: list[Contract] = []
        key_id = keys.get(row.contract_no or "")
        if key_id is not None:
            by_key = await session.get(Contract, key_id)
            if by_key is not None:
                found.append(by_key)
        if not found:
            found = [c for c in all_contracts if c.unit_id == unit.id and c.start_date == row.start]
        if not found:
            report.missing.append({"schluessel": row.unit_key, **where, "grund": "nicht angelegt"})
            continue
        if len(found) > 1:
            report.duplicate.append(
                {
                    "schluessel": row.unit_key,
                    **where,
                    "anzahl": len(found),
                    "ids": [str(c.id) for c in found],
                }
            )
        contract = found[0]
        matched_ids.add(contract.id)
        fields: list[dict[str, Any]] = []
        if row.contact_id not in await party_ids(contract.party_id):
            fields.append({"feld": "partei", "soll": row.contact_id, "ist": str(contract.party_id)})
        if row.end != contract.end_date:
            fields.append(
                {
                    "feld": "end_date",
                    "soll": row.end.isoformat() if row.end else None,
                    "ist": contract.end_date.isoformat() if contract.end_date else None,
                }
            )
        if row.amount is not None:
            payment = await _payment_at(session, contract, max(cutoff, row.start))
            actual = payment.gross if payment is not None else None
            if actual is None or actual != row.amount:
                fields.append(
                    {
                        "feld": PAYMENT_TYPE[kind],
                        "soll": _eur(row.amount),
                        "ist": _eur(actual) if actual is not None else None,
                    }
                )
        if fields:
            report.deviating.append({"schluessel": row.unit_key, **where, "felder": fields})
        else:
            report.matched += 1
    for c in all_contracts:
        if c.id not in matched_ids and c.source == CONTRACT_SOURCE:
            report.extra.append({"schluessel": c.number, "unit_id": str(c.unit_id)})
    for item in per_object.values():
        item["soll_summe"] = _eur(item["soll_summe"])
        item["ist_summe"] = _eur(item["ist_summe"])
        item["abweichung"] = (
            item["soll_anzahl"] != item["ist_anzahl"] or item["soll_summe"] != item["ist_summe"]
        )
    report.per_object = sorted(per_object.values(), key=lambda i: str(i["objekt"]))
    deviating_objects = sum(1 for i in report.per_object if i["abweichung"])
    if deviating_objects:
        report.notes.append(
            f"{deviating_objects} Objekte mit abweichender Anzahl oder Summe "
            f"({'Sollmieten' if kind is ContractKind.TENANCY else 'Hausgeld'}) gegen die Datei."
        )
    if report.extra:
        report.notes.append(
            "Zusätzliche Verträge stammen aus früheren Vollimporten und sind keine Differenz "
            "der Datei."
        )
    return report
