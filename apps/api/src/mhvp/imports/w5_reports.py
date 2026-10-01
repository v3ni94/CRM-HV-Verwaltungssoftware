"""Further report types of the import assistant (13.1, M8-01, wave 5): deposits, allocation
keys with unit values, meters, energy certificates, service providers and portal user status.

Same pipeline as the other report types: the user maps the columns of the export to the
platform fields below (the real Immoware24 column names are not specified and not assumed,
M8-01 stays open for them), required fields are named, the test run is rolled back, a repeated
run creates nothing twice and nothing is overwritten (equal: ``unchanged``, different:
``conflict``). Undo goes through the import run recorder (``mhvp.ai.imports``).

Nothing here posts, collects money or invites a portal user: a deposit is recorded as an
agreement without movements, a portal user row only reports the platform status.
"""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contracts.models import Contract, ContractKind, Deposit, DepositKind, DepositMovement
from mhvp.core.problems import ProblemError
from mhvp.imports.fields import FIELDS, Field
from mhvp.imports.models import ReportType, RowStatus, StagingRow
from mhvp.imports.reconciliation import normalise_property_number
from mhvp.portal.models import PortalAccount
from mhvp.properties import services as property_services
from mhvp.properties.models import (
    AllocationKey,
    AllocationKind,
    Building,
    Meter,
    MeterChange,
    MeterConnection,
    MeterReading,
    Property,
    ReadingSource,
    ServiceProviderRelation,
    UnitAllocationValue,
    ValueSource,
)

Result = tuple[RowStatus, str | None, uuid.UUID | None, list[str]]
DEPOSIT_KINDS = tuple(k.value for k in DepositKind)
ALLOCATION_KINDS = tuple(k.value for k in AllocationKind)
CONNECTIONS = tuple(c.value for c in MeterConnection)
CERT_LAWS = ("geg", "enev_2014")
CERT_TYPES = ("bedarf", "verbrauch")
PORTAL_STATUSES = ("invited", "active", "inactive")
BOOLEAN = ("true", "false")
CENT = Decimal("0.01")

W5_FIELDS: dict[ReportType, tuple[Field, ...]] = {
    # Deposit agreement per tenancy; no movement, no posting (receipt of money is a bank matter).
    ReportType.DEPOSIT: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", True, label="Einheitennummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Mieter"),
        Field("kind", "choice", True, DEPOSIT_KINDS, "Art der Kaution"),
        Field("amount_due", "decimal", True, label="Kautionsbetrag (soll)"),
        Field("valid_from", "date", True, label="Gültig ab"),
        Field("installments", "decimal", label="Anzahl Raten (1 bis 12)"),
        Field("valid_to", "date", label="Gültig bis"),
        Field("interest_rule", "text", label="Verzinsung (Freitext)"),
    ),
    # Allocation key of a property; with unit and value also the time valid unit value.
    ReportType.ALLOCATION_KEY: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("code", "text", True, label="Schlüsselkürzel"),
        Field("name", "text", label="Bezeichnung (bei neuem Schlüssel)"),
        Field("unit_of_measure", "text", label="Maßeinheit (bei neuem Schlüssel)"),
        Field("kind", "choice", False, ALLOCATION_KINDS, "Schlüsselart (bei neuem Schlüssel)"),
        Field("unit_number", "text", label="Einheitennummer"),
        Field("value", "decimal", label="Wert der Einheit"),
        Field("valid_from", "date", label="Wert gültig ab"),
        Field("valid_to", "date", label="Wert gültig bis"),
    ),
    # Meter master data, optionally with one initial reading.
    ReportType.METER: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("meter_type_code", "text", True, label="Zählerart (Katalogcode der Plattform)"),
        Field("number", "text", True, label="Zählernummer"),
        Field("valid_from", "date", True, label="Gültig ab"),
        Field("unit_number", "text", label="Einheitennummer"),
        Field("name", "text", label="Bezeichnung"),
        Field("connection", "choice", False, CONNECTIONS, "Hauptzähler oder Unterzähler"),
        Field("location", "text", label="Standort"),
        Field("malo_id", "text", label="Marktlokations-ID"),
        Field("calibration_due_date", "date", label="Eichfrist bis"),
        Field("remote_readable", "choice", False, BOOLEAN, "Fernablesbar"),
        Field("valid_to", "date", label="Gültig bis"),
        Field("reading_date", "date", label="Ablesedatum des Anfangsstands"),
        Field("reading_value", "decimal", label="Anfangsstand"),
    ),
    # Energy certificate on the building (values from the certificate, never derived).
    ReportType.ENERGY_CERTIFICATE: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("valid_until", "date", True, label="Gültig bis"),
        Field("issued_on", "date", True, label="Ausgestellt am"),
        Field("building", "text", label="Gebäude (bei mehreren Gebäuden)"),
        Field("law", "choice", False, CERT_LAWS, "Rechtsgrundlage"),
        Field("certificate_type", "choice", False, CERT_TYPES, "Bedarfs- oder Verbrauchsausweis"),
        Field("energy_class", "text", label="Energieeffizienzklasse"),
        Field("construction_year", "decimal", label="Baujahr laut Ausweis"),
        Field("final_heat_kwh", "decimal", label="Endenergie Wärme kWh/(m²a)"),
    ),
    # Service provider relation of a property.
    ReportType.SERVICE_PROVIDER: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Dienstleister"),
        Field("contract_type_code", "text", True, label="Vertragsart (Katalogcode der Plattform)"),
        Field("valid_from", "date", True, label="Gültig ab"),
        Field("valid_to", "date", label="Gültig bis"),
        Field("notice_period", "text", label="Kündigungsfrist (Freitext)"),
        Field("customer_number", "text", label="Kundennummer beim Dienstleister"),
        Field("notes", "text", label="Bemerkung"),
    ),
    # Portal user status of the old system: report only, no account, no invitation.
    ReportType.PORTAL_USER: (
        Field("contact_external_id", "text", True, label="Kontakt-ID"),
        Field("portal_status", "choice", True, PORTAL_STATUSES, "Portalstatus im Altsystem"),
        Field("email", "text", label="E-Mail im Altsystem"),
    ),
}

FIELDS.update(W5_FIELDS)

AMOUNT_FIELD: dict[ReportType, str] = {ReportType.DEPOSIT: "amount_due"}
# Entity types created by these reports (registered with the import run for undo).
UNDOABLE_ENTITY_TYPES = frozenset(
    {
        "deposit",
        "allocation_key",
        "unit_allocation_value",
        "meter",
        "meter_reading",
        "building_energy_certificate",
        "service_provider_relation",
    }
)


def handles(report_type: ReportType) -> bool:
    return report_type in W5_FIELDS


def _extra(ctx: dict[str, Any], entity_type: str, entity_id: uuid.UUID) -> None:
    """Additional entity of the same row for the undo record (see ``services.run``)."""
    ctx.setdefault("extra_created", []).append((entity_type, entity_id))


async def _property(session: AsyncSession, number: Any) -> Property | None:
    row: Property | None = await session.scalar(
        select(Property).where(Property.number == (normalise_property_number(number) or ""))
    )
    return row


def _invalid(message: str) -> Result:
    return RowStatus.INVALID, None, None, [message]


def _int(value: Any, low: int, high: int) -> int | None:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if number != number.to_integral_value() or not low <= number <= high:
        return None
    return int(number)


# Deposit ----------------------------------------------------------------------------------


async def _deposit(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: tenancy of the tenant in the unit (start before valid-from) and valid-from of the
    deposit. Creates the agreement (status ``open``), never a movement or a posting."""
    from mhvp.imports import services as svc

    unit = await svc._unit(
        session, normalise_property_number(v["property_number"]) or "", v["unit_number"]
    )
    contact = await svc._contact(session, v["contact_external_id"])
    party = await svc._party_of(session, contact) if contact else None
    if unit is None or party is None:
        return _invalid("Einheit oder Mieter fehlt")
    valid_from = date.fromisoformat(v["valid_from"])
    contract = await session.scalar(
        select(Contract)
        .where(
            Contract.unit_id == unit.id,
            Contract.kind == ContractKind.TENANCY,
            Contract.party_id == party.id,
            Contract.start_date <= valid_from,
        )
        .order_by(Contract.start_date.desc())
        .limit(1)
    )
    if contract is None:
        return _invalid("Kein passendes Mietverhältnis zum Gültig-ab-Datum")
    amount = Decimal(v["amount_due"]).quantize(CENT)
    if amount <= 0:
        return _invalid("Kautionsbetrag muss größer als 0 sein")
    installments = 1
    if v.get("installments") is not None:
        parsed = _int(v["installments"], 1, 12)
        if parsed is None:
            return _invalid("Raten müssen eine ganze Zahl von 1 bis 12 sein")
        installments = parsed
    valid_to = date.fromisoformat(v["valid_to"]) if v.get("valid_to") else None
    if valid_to is not None and valid_to < valid_from:
        return _invalid("Gültig bis liegt vor Gültig ab")
    existing = await session.scalar(
        select(Deposit).where(Deposit.contract_id == contract.id, Deposit.valid_from == valid_from)
    )
    if existing is not None:
        same = existing.kind.value == v["kind"] and existing.amount_due == amount
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "deposit",
            existing.id,
            [] if same else ["Kaution vorhanden mit abweichender Art oder abweichendem Betrag"],
        )
    row = Deposit(
        tenant_id=principal.tenant_id,
        contract_id=contract.id,
        kind=DepositKind(v["kind"]),
        amount_due=amount,
        installments=installments,
        valid_from=valid_from,
        valid_to=valid_to,
        interest_rule=v.get("interest_rule"),
        status="open",
        documents=[],
    )
    session.add(row)
    await session.flush()
    return (
        RowStatus.CREATED,
        "deposit",
        row.id,
        ["Kein Kautionskonto zugeordnet; Zahlungseingänge erst nach Zuordnung des Kontos"],
    )


# Allocation keys --------------------------------------------------------------------------


async def _allocation_key(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object and key code. Creates the key (new keys need name, unit and kind) and, with
    unit, value and valid-from, the time valid unit value (key of the unit never overlaps)."""
    from mhvp.imports import services as svc

    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid(f"Objekt {v['property_number']} fehlt")
    given = [k for k in ("unit_number", "value", "valid_from") if v.get(k)]
    if given and len(given) != 3:
        return _invalid("Einheit, Wert und Gültig ab gehören zusammen")
    code = v["code"].strip()[:32]
    key = await session.scalar(
        select(AllocationKey).where(
            AllocationKey.property_id == prop.id, AllocationKey.code == code
        )
    )
    notes: list[str] = []
    key_status = RowStatus.UNCHANGED
    if key is None:
        missing = [k for k in ("name", "unit_of_measure", "kind") if not v.get(k)]
        if missing:
            return _invalid(f"Neuer Schlüssel, Angaben fehlen: {', '.join(missing)}")
        key = AllocationKey(
            tenant_id=principal.tenant_id,
            property_id=prop.id,
            code=code,
            name=v["name"].strip()[:200],
            unit_of_measure=v["unit_of_measure"].strip()[:16],
            kind=AllocationKind(v["kind"]),
            sort_order=100,
        )
        session.add(key)
        await session.flush()
        _extra(ctx, "allocation_key", key.id)
        key_status = RowStatus.CREATED
    elif v.get("kind") and key.kind.value != v["kind"]:
        return (
            RowStatus.CONFLICT,
            "allocation_key",
            key.id,
            ["Schlüssel vorhanden mit anderer Schlüsselart"],
        )
    if not given:
        return key_status, "allocation_key", key.id, notes
    unit = await svc._unit(session, prop.number, v["unit_number"])
    if unit is None:
        return RowStatus.INVALID, "allocation_key", key.id, ["Einheit fehlt"]
    value = Decimal(v["value"])
    valid_from = date.fromisoformat(v["valid_from"])
    valid_to = date.fromisoformat(v["valid_to"]) if v.get("valid_to") else None
    if valid_to is not None and valid_to < valid_from:
        return RowStatus.INVALID, "allocation_key", key.id, ["Gültig bis liegt vor Gültig ab"]
    current = await session.scalar(
        select(UnitAllocationValue).where(
            UnitAllocationValue.unit_id == unit.id,
            UnitAllocationValue.allocation_key_id == key.id,
            UnitAllocationValue.valid_from <= valid_from,
            (UnitAllocationValue.valid_to.is_(None)) | (UnitAllocationValue.valid_to >= valid_from),
        )
    )
    if current is not None:
        if current.valid_from == valid_from and current.value == value:
            return RowStatus.UNCHANGED, "unit_allocation_value", current.id, notes
        return (
            RowStatus.CONFLICT,
            "unit_allocation_value",
            current.id,
            ["Wert für diesen Zeitraum vorhanden mit anderen Angaben"],
        )
    try:
        async with session.begin_nested():
            row, _previous = await property_services.add_allocation_value(
                session,
                principal.tenant_id,
                unit.id,
                key.id,
                value,
                valid_from,
                valid_to,
                ValueSource.IMPORT,
            )
    except IntegrityError:
        return RowStatus.CONFLICT, "allocation_key", key.id, ["Wertzeitraum überschneidet sich"]
    return RowStatus.CREATED, "unit_allocation_value", row.id, notes


# Meters -----------------------------------------------------------------------------------


async def _meter(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object, meter type and number. An initial reading is added to new meters only."""
    from mhvp.imports import services as svc

    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid(f"Objekt {v['property_number']} fehlt")
    try:
        await property_services.check_catalog(session, "meter_type", v["meter_type_code"])
    except ProblemError as exc:
        return _invalid(str(exc.detail))
    if bool(v.get("reading_date")) != bool(v.get("reading_value")):
        return _invalid("Ablesedatum und Anfangsstand gehören zusammen")
    unit_id: uuid.UUID | None = None
    if v.get("unit_number"):
        unit = await svc._unit(session, prop.number, v["unit_number"])
        if unit is None:
            return _invalid(f"Einheit {v['unit_number']} fehlt")
        unit_id = unit.id
    valid_from = date.fromisoformat(v["valid_from"])
    valid_to = date.fromisoformat(v["valid_to"]) if v.get("valid_to") else None
    if valid_to is not None and valid_to < valid_from:
        return _invalid("Gültig bis liegt vor Gültig ab")
    number = v["number"].strip()
    existing = await session.scalar(
        select(Meter).where(
            Meter.property_id == prop.id,
            Meter.meter_type_code == v["meter_type_code"],
            Meter.number == number,
        )
    )
    if existing is not None:
        same = existing.unit_id == unit_id and existing.valid_from == valid_from
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "meter",
            existing.id,
            [] if same else ["Zähler vorhanden mit anderer Einheit oder anderem Gültig-ab"],
        )
    meter = Meter(
        tenant_id=principal.tenant_id,
        property_id=prop.id,
        unit_id=unit_id,
        meter_type_code=v["meter_type_code"],
        number=number[:100],
        malo_id=(v.get("malo_id") or None),
        name=v.get("name"),
        connection=MeterConnection(v.get("connection") or "sub"),
        location=v.get("location"),
        calibration_due_date=date.fromisoformat(v["calibration_due_date"])
        if v.get("calibration_due_date")
        else None,
        remote_readable=v.get("remote_readable") == "true",
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(meter)
    await session.flush()
    if v.get("reading_value"):
        reading = MeterReading(
            tenant_id=principal.tenant_id,
            meter_id=meter.id,
            read_at=date.fromisoformat(v["reading_date"]),
            value=Decimal(v["reading_value"]),
            estimated=False,
            source=ReadingSource.MANUAL,
        )
        session.add(reading)
        await session.flush()
        _extra(ctx, "meter_reading", reading.id)
    return RowStatus.CREATED, "meter", meter.id, []


# Energy certificate -----------------------------------------------------------------------

_CERT_ATTRS = {
    "law": "energy_certificate_law",
    "certificate_type": "energy_certificate_type",
    "energy_class": "energy_certificate_class",
    "construction_year": "energy_certificate_construction_year",
    "issued_on": "energy_certificate_issued_on",
    "valid_until": "energy_certificate_valid_until",
    "final_heat_kwh": "energy_final_heat_kwh",
}


def _cert_values(v: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    out: dict[str, Any] = {}
    for key, attr in _CERT_ATTRS.items():
        raw = v.get(key)
        if raw is None or raw == "":
            continue
        if key in ("issued_on", "valid_until"):
            out[attr] = date.fromisoformat(raw)
        elif key == "construction_year":
            year = _int(raw, 1000, 2100)
            if year is None:
                return {}, "Baujahr muss eine Jahreszahl sein"
            out[attr] = year
        elif key == "final_heat_kwh":
            out[attr] = Decimal(raw)
        elif key == "energy_class":
            out[attr] = str(raw).strip().upper()[:4]
        else:
            out[attr] = raw
    issued, until = (
        out.get("energy_certificate_issued_on"),
        out.get("energy_certificate_valid_until"),
    )
    if issued and until and until < issued:
        return {}, "Gültig bis liegt vor Ausstellungsdatum"
    return out, None


async def _energy_certificate(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: building of the object. Fills an empty certificate; a different one is a
    conflict and is never overwritten."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid(f"Objekt {v['property_number']} fehlt")
    buildings = (
        await session.scalars(select(Building).where(Building.property_id == prop.id))
    ).all()
    name = (v.get("building") or "").strip()
    if name:
        buildings = [b for b in buildings if b.name == name]
    if len(buildings) != 1:
        return _invalid(
            "Gebäude nicht eindeutig, bitte Gebäudebezeichnung zuordnen"
            if buildings
            else "Kein Gebäude zum Objekt gefunden"
        )
    building = buildings[0]
    values, error = _cert_values(v)
    if error:
        return _invalid(error)
    if (
        building.energy_certificate_valid_until is None
        and building.energy_certificate_issued_on is None
    ):
        for attr, value in values.items():
            setattr(building, attr, value)
        await session.flush()
        return RowStatus.CREATED, "building_energy_certificate", building.id, []
    same = all(getattr(building, attr) == value for attr, value in values.items())
    return (
        RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
        "building_energy_certificate",
        building.id,
        [] if same else ["Energieausweis vorhanden mit abweichenden Angaben"],
    )


# Service providers ------------------------------------------------------------------------


async def _service_provider(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object, provider contact, contract type and valid-from. The creditor account is
    not created here (account master data stays with the ledger of the object)."""
    from mhvp.imports import services as svc

    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid(f"Objekt {v['property_number']} fehlt")
    contact = await svc._contact(session, v["contact_external_id"])
    if contact is None:
        return _invalid(f"Kontakt {v['contact_external_id']} fehlt")
    try:
        await property_services.check_catalog(
            session, "provider_contract_type", v["contract_type_code"]
        )
    except ProblemError as exc:
        return _invalid(str(exc.detail))
    valid_from = date.fromisoformat(v["valid_from"])
    valid_to = date.fromisoformat(v["valid_to"]) if v.get("valid_to") else None
    if valid_to is not None and valid_to < valid_from:
        return _invalid("Gültig bis liegt vor Gültig ab")
    existing = await session.scalar(
        select(ServiceProviderRelation).where(
            ServiceProviderRelation.property_id == prop.id,
            ServiceProviderRelation.contact_id == contact.id,
            ServiceProviderRelation.contract_type_code == v["contract_type_code"],
            ServiceProviderRelation.valid_from == valid_from,
        )
    )
    if existing is not None:
        same = existing.valid_to == valid_to or valid_to is None
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "service_provider_relation",
            existing.id,
            [] if same else ["Dienstleisterverhältnis vorhanden mit anderem Ende"],
        )
    row = ServiceProviderRelation(
        tenant_id=principal.tenant_id,
        property_id=prop.id,
        contact_id=contact.id,
        contract_type_code=v["contract_type_code"],
        valid_from=valid_from,
        valid_to=valid_to,
        notice_period=v.get("notice_period"),
        customer_number=(v.get("customer_number") or None),
        notes=v.get("notes"),
        categories=[],
        custom_fields={},
    )
    session.add(row)
    await session.flush()
    return RowStatus.CREATED, "service_provider_relation", row.id, []


# Portal user status -----------------------------------------------------------------------


async def _portal_user(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Report only: compares the old status with the platform account of the contact. No
    account is created, no invitation sent, nothing is overwritten."""
    from mhvp.imports import services as svc

    contact = await svc._contact(session, v["contact_external_id"])
    if contact is None:
        return _invalid(f"Kontakt {v['contact_external_id']} fehlt")
    account = await session.scalar(
        select(PortalAccount).where(PortalAccount.contact_id == contact.id)
    )
    if account is None:
        return (
            RowStatus.STAGED_ONLY,
            None,
            None,
            ["Kein Portalkonto; Einladung über die Portalverwaltung nach Rechteprüfung"],
        )
    if account.status == v["portal_status"]:
        return RowStatus.UNCHANGED, "portal_account", account.id, []
    return (
        RowStatus.CONFLICT,
        "portal_account",
        account.id,
        [f"Portalstatus Altsystem {v['portal_status']}, Plattform {account.status}"],
    )


HANDLERS: dict[ReportType, Any] = {
    ReportType.DEPOSIT: _deposit,
    ReportType.ALLOCATION_KEY: _allocation_key,
    ReportType.METER: _meter,
    ReportType.ENERGY_CERTIFICATE: _energy_certificate,
    ReportType.SERVICE_PROVIDER: _service_provider,
    ReportType.PORTAL_USER: _portal_user,
}


async def apply_row(
    session: AsyncSession,
    principal: Any,
    report_type: ReportType,
    values: dict[str, Any],
    ctx: dict[str, Any],
) -> Result:
    result: Result = await HANDLERS[report_type](session, principal, values, ctx)
    return result


# Undo (called by mhvp.ai.imports) ---------------------------------------------------------


async def referenced(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> str | None:
    """Reason why an imported entity of these reports must stay, or None."""
    if entity_type == "deposit":
        deposit = await session.get(Deposit, entity_id)
        if deposit is None:
            return None
        if await session.scalar(
            select(DepositMovement.id).where(DepositMovement.deposit_id == entity_id).limit(1)
        ):
            return "Kautionsbewegungen vorhanden"
        if deposit.status != "open" or deposit.documents or deposit.property_bank_account_id:
            return "Kaution wurde nach dem Import bearbeitet"
    elif entity_type == "allocation_key":
        if await session.scalar(
            select(UnitAllocationValue.id)
            .where(UnitAllocationValue.allocation_key_id == entity_id)
            .limit(1)
        ):
            return "Einheitenwerte vorhanden"
    elif entity_type == "meter":
        if await session.scalar(
            select(MeterReading.id).where(MeterReading.meter_id == entity_id).limit(1)
        ) or await session.scalar(
            select(MeterChange.id).where(MeterChange.meter_id == entity_id).limit(1)
        ):
            return "Zählerstände oder Zählerwechsel vorhanden"
    elif entity_type == "service_provider_relation":
        row = await session.get(ServiceProviderRelation, entity_id)
        if row is not None and row.creditor_account_id is not None:
            return "Kreditorenkonto zugeordnet"
    elif entity_type == "building_energy_certificate":
        return await _certificate_edited(session, entity_id)
    return None


async def _certificate_edited(session: AsyncSession, building_id: uuid.UUID) -> str | None:
    building = await session.get(Building, building_id)
    if building is None:
        return None
    rows = (
        await session.scalars(
            select(StagingRow).where(
                StagingRow.entity_type == "building_energy_certificate",
                StagingRow.entity_id == building_id,
                StagingRow.status == RowStatus.CREATED,
            )
        )
    ).all()
    for row in rows:
        values, _ = _cert_values(row.values or {})
        if any(getattr(building, attr) != value for attr, value in values.items()):
            return "Energieausweis wurde nach dem Import geändert"
    return None


async def remove(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    if entity_type == "unit_allocation_value":
        row = await session.get(UnitAllocationValue, entity_id)
        if row is None:
            return
        from datetime import timedelta

        previous = await session.scalar(
            select(UnitAllocationValue).where(
                UnitAllocationValue.unit_id == row.unit_id,
                UnitAllocationValue.allocation_key_id == row.allocation_key_id,
                UnitAllocationValue.valid_to == row.valid_from - timedelta(days=1),
            )
        )
        await session.delete(row)
        await session.flush()
        if previous is not None:
            previous.valid_to = None  # reopen the value the import had closed
    elif entity_type == "building_energy_certificate":
        building = await session.get(Building, entity_id)
        if building is not None:
            for attr in _CERT_ATTRS.values():
                setattr(building, attr, None)
    elif entity_type == "meter":
        await session.execute(delete(Meter).where(Meter.id == entity_id))
    else:
        model: Any = {
            "deposit": Deposit,
            "allocation_key": AllocationKey,
            "meter_reading": MeterReading,
            "service_provider_relation": ServiceProviderRelation,
        }[entity_type]
        row_any = await session.get(model, entity_id)
        if row_any is not None:
            await session.delete(row_any)
    await session.flush()
