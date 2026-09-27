"""Shared business service of the Messdienstleister module (master prompt sections 2 to 10).

The object tab and the central overview call the same functions here: one storage, one
validation, one permission check (section 2). No function here posts, creates receivables or
changes statements (section 11); write endpoints are additionally locked by the per tenant
switch ``tenant_settings.metering_module_enabled`` (default off).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.escaping import escape_like
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentSource, LinkRole
from mhvp.metering.adapters import (
    ConnectionTestResult,
    DocumentRecord,
    ExternalBillingUnitData,
    FetchResult,
    MeteringAdapter,
    TestOutcome,
    adapter_for,
)
from mhvp.metering.models import (
    AssignmentStatus,
    ConnectionStatus,
    DataKind,
    MeteringBillingResult,
    MeteringClearingItem,
    MeteringConnection,
    MeteringConsumptionValue,
    MeteringExternalBillingUnit,
    MeteringPropertyAssignment,
    MeteringSyncJob,
    MeteringTransmission,
    MeteringUnitAssignment,
    SyncStatus,
    TransmissionStatus,
    ValueKind,
)
from mhvp.metering.providers import (
    DOCUMENTED_SUPPORT_LABELS,
    DocumentedSupport,
    Function,
    get_provider,
)
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Property, Unit

# Data kind of a sync job to the provider function it needs (section 3: per function checks).
DATA_KIND_FUNCTION: dict[str, Function] = {
    DataKind.DOCUMENTS: Function.DOCUMENTS,
    DataKind.CONSUMPTION: Function.CONSUMPTION,
    DataKind.BILLING_RESULT: Function.BILLING_RESULT,
    DataKind.BILLING_UNIT_DATA: Function.BILLING_UNIT_DATA,
}

# Functions that would write at the provider. Stage 1 never calls them; a sync job is read only.
WRITING_FUNCTIONS: frozenset[Function] = frozenset({Function.ROLES, Function.BILLING_INPUT})

# Configuration keys whose change invalidates a previous connection test (section 4).
TEST_RELEVANT_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "base_url",
        "base_urls",
        "token_url",
        "config_environment",
        "api_family",
        "api_version",
        "adapter",
        "client_id",
        "tenant_ref",
        "mtls",
        "consumption_auth",
        "documents_auth",
        "billing_unit_data_auth",
        "billing_result_auth",
    }
)

# Provenance of provider documents in the document store (section 11).
DOCUMENT_SOURCE_SYSTEM = "metering"
# Key inside ``MeteringConnection.last_sync`` holding the per data kind cursor; advanced only
# after the job's results are durably stored (section 10).
CURSOR_KEY = "_cursors"


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


# Module switch ---------------------------------------------------------------------------


async def module_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(TenantSettings.metering_module_enabled).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


async def ensure_module_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if not await module_enabled(session, tenant_id):
        raise ProblemError(
            ErrorCodes.METERING_MODULE_DISABLED,
            detail="Das Messdienstleister-Modul ist für diesen Mandanten nicht freigeschaltet "
            "(Einstellungen, Mandant).",
        )


# Controlled write workflows (section 12): a change of a relevant assignment supersedes every
# checked or released transmission of that assignment. Called by the assignment services below;
# the workflow itself lives in ``mhvp.metering.transmissions``.
OPEN_TRANSMISSION_STATUSES: tuple[str, ...] = (
    TransmissionStatus.CHECKED,
    TransmissionStatus.RELEASED,
)


async def invalidate_transmissions(
    session: AsyncSession, assignment_id: uuid.UUID, *, actor: uuid.UUID | None, reason: str
) -> int:
    rows = list(
        await session.scalars(
            select(MeteringTransmission).where(
                MeteringTransmission.property_assignment_id == assignment_id,
                MeteringTransmission.status.in_(OPEN_TRANSMISSION_STATUSES),
            )
        )
    )
    for row in rows:
        row.status = TransmissionStatus.SUPERSEDED
        row.version += 1
        row.updated_by = actor
        row.log = [
            *row.log,
            {
                "action": "superseded",
                "user_id": str(actor) if actor else None,
                "at": _now().isoformat(),
                "fingerprint": row.fingerprint,
                "data_version": row.assignment_version,
                "reason": reason,
            },
        ]
    if rows:
        await session.flush()
    return len(rows)


# Connections -----------------------------------------------------------------------------


def _adapter(connection: MeteringConnection) -> MeteringAdapter:
    config = dict(connection.config)
    config["_environment"] = connection.environment
    return adapter_for(connection.provider_code, config)


def connection_secrets(connection: MeteringConnection) -> dict[str, str]:
    """Decrypted secrets for adapter calls only. Never returned by the API, never logged."""
    if not connection.secrets:
        return {}
    data = json.loads(connection.secrets)
    return {str(k): str(v) for k, v in data.items()}


def capability_matrix(connection: MeteringConnection) -> list[dict[str, Any]]:
    """Honest per function state with the four dimensions of section 3 plus the last test.
    ``available`` is true only when every dimension is fulfilled and the last test is a
    non stale success; otherwise ``reason`` explains what is missing."""
    provider = get_provider(connection.provider_code)
    adapter = _adapter(connection)
    stored = connection.capabilities or {}
    test_ok = connection.last_test_status == TestOutcome.OK and not connection.test_stale
    rows: list[dict[str, Any]] = []
    for function in Function:
        support = (
            provider.support(function)
            if provider
            else None  # unknown provider code cannot happen after validation
        )
        documented = support.documented if support else DocumentedSupport.UNCLEAR
        implemented = function in adapter.implemented
        entry = stored.get(function.value, {})
        account_release = bool(entry.get("account_release", False))
        property_release = entry.get("property_release")
        released_by_test = function.value in tuple(entry.get("last_test_result") or ())
        reason: str | None = None
        if documented == DocumentedSupport.NO:
            reason = "Keine API vorhanden (bestätigt)."
        elif documented != DocumentedSupport.YES:
            reason = DOCUMENTED_SUPPORT_LABELS[documented]
        elif not implemented:
            reason = "Adapter im CRM nicht implementiert (Stufe 2, nach Anbieterdokumentation)."
        elif not account_release:
            reason = "Ja, Freischaltung ausstehend (Kundenkonto nicht freigegeben)."
        elif not test_ok:
            reason = (
                "Verbindungstest veraltet, bitte erneut prüfen."
                if connection.test_stale
                else "Verbindung noch nicht erfolgreich geprüft."
            )
        elif function in WRITING_FUNCTIONS and not connection.write_sync_enabled:
            reason = (
                "Schreibende Vorgänge sind für diese Verbindung nicht freigegeben "
                "(write_sync_enabled)."
            )
        label = (
            "Verbindung erfolgreich geprüft"
            if reason is None
            or (test_ok and function in WRITING_FUNCTIONS and implemented and account_release)
            else "Ja, Freischaltung ausstehend"
            if documented == DocumentedSupport.YES and implemented and not account_release
            else DOCUMENTED_SUPPORT_LABELS.get(documented, "Ungeklärt")
        )
        rows.append(
            {
                "function": function.value,
                "documented_support": documented.value,
                "documented_source": support.source if support else "",
                "documented_note": support.note if support else "",
                "adapter_implemented": implemented,
                "supported_version": adapter.spec_version if implemented else None,
                "spec_source": adapter.spec_source if implemented else None,
                "account_release": account_release,
                "property_release": property_release,
                "last_test_result": entry.get("last_test_result"),
                "last_test_at": connection.last_test_at,
                "test_stale": connection.test_stale,
                "released_by_last_test": released_by_test,
                "available": reason is None,
                "reason": reason,
                "label": label,
            }
        )
    return rows


def function_available(connection: MeteringConnection, function: Function) -> tuple[bool, str]:
    for row in capability_matrix(connection):
        if row["function"] == function.value:
            return bool(row["available"]), str(row["reason"] or "")
    return False, "Unbekannte Funktion."


async def create_connection(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    display_name: str,
    provider_code: str,
    environment: str,
    customer_references: Sequence[str],
    config: Mapping[str, Any],
    contracting_company: str | None,
    secrets: Mapping[str, str] | None,
    account_release: Mapping[str, bool] | None,
) -> MeteringConnection:
    if get_provider(provider_code) is None:
        raise ProblemError(ErrorCodes.METERING_PROVIDER_UNKNOWN)
    row = MeteringConnection(
        tenant_id=tenant_id,
        display_name=display_name,
        provider_code=provider_code,
        contracting_company=contracting_company,
        environment=environment,
        status=ConnectionStatus.ACTIVE,
        customer_references=[str(r) for r in customer_references],
        config=dict(config),
        capabilities={
            f.value: {"account_release": bool((account_release or {}).get(f.value, False))}
            for f in Function
        },
        created_by=actor,
        updated_by=actor,
    )
    session.add(row)
    await session.flush()
    if secrets:
        set_secrets(row, secrets, actor=actor)
        await session.flush()
    await session.refresh(row)
    await emit(
        session,
        tenant_id=tenant_id,
        type="metering.connection.created",
        entity_type="metering_connection",
        entity_id=row.id,
        actor_user_id=actor,
        payload={"provider_code": provider_code, "environment": environment},
    )
    return row


def set_secrets(
    connection: MeteringConnection, secrets: Mapping[str, str], *, actor: uuid.UUID | None
) -> None:
    """Set or replace secrets by name (never read back). Marks the last test as stale."""
    current = connection_secrets(connection)
    for name, value in secrets.items():
        if value == "":
            current.pop(name, None)
        else:
            current[name] = value
    connection.secrets = json.dumps(current, sort_keys=True) if current else None
    connection.secret_names = sorted(current)
    connection.test_stale = connection.last_test_status is not None
    connection.version += 1
    connection.updated_by = actor


async def update_connection(
    session: AsyncSession,
    connection: MeteringConnection,
    *,
    actor: uuid.UUID | None,
    version: int,
    changes: Mapping[str, Any],
) -> MeteringConnection:
    if connection.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    stale = False
    for key, value in changes.items():
        if value is None:
            continue
        if key == "config":
            new = dict(value)
            old = connection.config or {}
            if any(old.get(k) != new.get(k) for k in TEST_RELEVANT_CONFIG_KEYS):
                stale = True
            connection.config = new
        elif key == "environment":
            if connection.environment != value:
                stale = True
            connection.environment = value
        elif key == "account_release":
            caps = dict(connection.capabilities or {})
            for function, released in dict(value).items():
                if function not in {f.value for f in Function}:
                    raise ProblemError(
                        ErrorCodes.VALIDATION, detail=f"Unbekannte Funktion: {function}"
                    )
                entry = dict(caps.get(function, {}))
                entry["account_release"] = bool(released)
                caps[function] = entry
            connection.capabilities = caps
        elif key in {
            "display_name",
            "status",
            "customer_references",
            "contracting_company",
            "scheduled_sync_enabled",
            "write_sync_enabled",
        }:
            setattr(connection, key, value)
        else:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekanntes Feld: {key}")
    if stale and connection.last_test_status is not None:
        connection.test_stale = True
    connection.version += 1
    connection.updated_by = actor
    await session.flush()
    await session.refresh(connection)
    await emit(
        session,
        tenant_id=connection.tenant_id,
        type="metering.connection.updated",
        entity_type="metering_connection",
        entity_id=connection.id,
        actor_user_id=actor,
        changes={k: "changed" for k, v in changes.items() if v is not None},
    )
    return connection


async def test_connection(
    session: AsyncSession, connection: MeteringConnection, *, actor: uuid.UUID | None
) -> ConnectionTestResult:
    """Read only authentication check through the adapter. Never orders anything, never
    changes user data, never acknowledges documents (section 4). A missing credential is
    reported as such and is never a success."""
    if connection.status != ConnectionStatus.ACTIVE:
        raise ProblemError(ErrorCodes.METERING_CONNECTION_PAUSED)
    adapter = _adapter(connection)
    secrets = connection_secrets(connection)
    missing = sorted(adapter.required_secrets - set(secrets))
    if missing:
        result = ConnectionTestResult(
            TestOutcome.CREDENTIALS_MISSING,
            "Zugangsdaten fehlen: " + ", ".join(missing) + ".",
        )
    else:
        result = adapter.test_connection(
            config=connection.config, secrets=secrets, environment=connection.environment
        )
    connection.last_test_status = result.outcome
    connection.last_test_at = _now()
    connection.last_test_detail = result.detail
    connection.test_stale = False
    caps = dict(connection.capabilities or {})
    for function in Function:
        entry = dict(caps.get(function.value, {}))
        entry["last_test_result"] = (
            list(result.functions_released) if result.outcome == "ok" else []
        )
        caps[function.value] = entry
    connection.capabilities = caps
    connection.updated_by = actor
    await session.flush()
    await session.refresh(connection)
    await emit(
        session,
        tenant_id=connection.tenant_id,
        type="metering.connection.tested",
        entity_type="metering_connection",
        entity_id=connection.id,
        actor_user_id=actor,
        payload={"outcome": result.outcome},
    )
    return result


async def get_connection(session: AsyncSession, connection_id: uuid.UUID) -> MeteringConnection:
    row = await session.get(MeteringConnection, connection_id)
    if row is None:
        raise _not_found()
    return row


# External billing units ------------------------------------------------------------------


async def get_or_create_billing_unit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connection: MeteringConnection,
    external_number: str,
    external_name: str | None = None,
    external_address: str | None = None,
    expected_unit_count: int | None = None,
    origin: str = "manual",
) -> MeteringExternalBillingUnit:
    number = external_number.strip()
    if not number:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Externe Nummer fehlt.")
    row = await session.scalar(
        select(MeteringExternalBillingUnit).where(
            MeteringExternalBillingUnit.connection_id == connection.id,
            MeteringExternalBillingUnit.external_number == number,
        )
    )
    if row is None:
        row = MeteringExternalBillingUnit(
            tenant_id=tenant_id,
            connection_id=connection.id,
            external_number=number,
            external_name=external_name,
            external_address=external_address,
            expected_unit_count=expected_unit_count,
            origin=origin,
        )
        session.add(row)
        await session.flush()
    else:
        if external_name and not row.external_name:
            row.external_name = external_name
        if external_address and not row.external_address:
            row.external_address = external_address
        if expected_unit_count is not None:
            row.expected_unit_count = expected_unit_count
    return row


# Property assignments --------------------------------------------------------------------


def _overlaps(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    return (a_to is None or a_to >= b_from) and (b_to is None or b_to >= a_from)


async def _conflicting_assignments(
    session: AsyncSession, candidate: MeteringPropertyAssignment
) -> list[tuple[MeteringPropertyAssignment, str]]:
    """Assignments contradicting ``candidate`` (section 5): same units, service scope and
    period. Compared are units (explicit unit scope or the whole property), scope and validity,
    not only the provider. Members of the same explicit group are not duplicates."""
    query = select(MeteringPropertyAssignment).where(
        MeteringPropertyAssignment.service_scope == candidate.service_scope,
        MeteringPropertyAssignment.status != AssignmentStatus.ARCHIVED,
        MeteringPropertyAssignment.id != candidate.id,
        or_(
            MeteringPropertyAssignment.property_id == candidate.property_id,
            MeteringPropertyAssignment.external_billing_unit_id
            == candidate.external_billing_unit_id,
        ),
    )
    conflicts: list[tuple[MeteringPropertyAssignment, str]] = []
    for other in await session.scalars(query):
        if not _overlaps(
            candidate.valid_from, candidate.valid_to, other.valid_from, other.valid_to
        ):
            continue
        same_group = (
            candidate.group_id is not None
            and other.group_id == candidate.group_id
            and candidate.unit_scope
            and other.unit_scope
            and not set(candidate.unit_scope) & set(other.unit_scope)
        )
        if same_group:
            continue
        if other.property_id == candidate.property_id:
            if (
                candidate.unit_scope
                and other.unit_scope
                and not set(candidate.unit_scope) & set(other.unit_scope)
            ):
                continue  # disjoint explicit unit scopes within one property
            conflicts.append(
                (
                    other,
                    "Derselbe Versorgungsumfang ist im Zeitraum bereits zugeordnet "
                    f"(Zuordnung {other.id}).",
                )
            )
        else:
            conflicts.append(
                (
                    other,
                    "Die externe Abrechnungseinheit ist im Zeitraum bereits einem anderen "
                    "Objekt zugeordnet; objektübergreifend nur mit ausdrücklicher Gruppierung "
                    "und eindeutigem Einheitenumfang.",
                )
            )
    return conflicts


async def _check_unit_scope(
    session: AsyncSession, property_id: uuid.UUID, unit_scope: Sequence[str]
) -> list[str]:
    ids: list[uuid.UUID] = []
    for raw in unit_scope:
        try:
            ids.append(uuid.UUID(str(raw)))
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Ungültige Einheit: {raw}") from exc
    if not ids:
        return []
    found = set(
        await session.scalars(
            select(Unit.id).where(Unit.property_id == property_id, Unit.id.in_(ids))
        )
    )
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Einheiten gehören nicht zum Objekt: " + ", ".join(missing),
        )
    return [str(i) for i in ids]


async def create_assignment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    connection_id: uuid.UUID,
    property_id: uuid.UUID,
    external_number: str,
    service_scope: str,
    valid_from: date,
    valid_to: date | None,
    origin: str = "manual",
    status: str = AssignmentStatus.OPEN,
    is_primary: bool = False,
    group_id: uuid.UUID | None = None,
    unit_scope: Sequence[str] = (),
    external_name: str | None = None,
    external_address: str | None = None,
    expected_unit_count: int | None = None,
    note: str | None = None,
) -> MeteringPropertyAssignment:
    connection = await get_connection(session, connection_id)
    prop = await session.get(Property, property_id)
    if prop is None:
        raise _not_found()
    if valid_to is not None and valid_to < valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gültig bis liegt vor Gültig ab.")
    unit = await get_or_create_billing_unit(
        session,
        tenant_id=tenant_id,
        connection=connection,
        external_number=external_number,
        external_name=external_name,
        external_address=external_address,
        expected_unit_count=expected_unit_count,
        origin=origin,
    )
    scope = await _check_unit_scope(session, property_id, unit_scope)
    if group_id is not None and not scope:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Eine objektübergreifende Gruppierung braucht einen ausdrücklichen "
            "Einheitenumfang.",
        )
    row = MeteringPropertyAssignment(
        tenant_id=tenant_id,
        connection_id=connection.id,
        property_id=property_id,
        external_billing_unit_id=unit.id,
        service_scope=service_scope,
        valid_from=valid_from,
        valid_to=valid_to,
        status=status,
        origin=origin,
        is_primary=is_primary,
        group_id=group_id,
        unit_scope=scope,
        note=note,
        created_by=actor,
        updated_by=actor,
    )
    conflicts = await _conflicting_assignments(session, row)
    if conflicts:
        raise ProblemError(
            ErrorCodes.METERING_ASSIGNMENT_CONFLICT,
            detail=conflicts[0][1],
            extensions={"conflicting_assignment_ids": [str(c.id) for c, _ in conflicts]},
        )
    if unit.group_id is None and group_id is not None:
        unit.group_id = group_id
    session.add(row)
    await session.flush()
    await session.refresh(row)
    await emit(
        session,
        tenant_id=tenant_id,
        type="metering.assignment.created",
        entity_type="metering_property_assignment",
        entity_id=row.id,
        actor_user_id=actor,
        payload={"property_id": str(property_id), "external_number": unit.external_number},
    )
    return row


async def get_assignment(
    session: AsyncSession, assignment_id: uuid.UUID
) -> MeteringPropertyAssignment:
    row = await session.get(MeteringPropertyAssignment, assignment_id)
    if row is None:
        raise _not_found()
    return row


async def update_assignment(
    session: AsyncSession,
    row: MeteringPropertyAssignment,
    *,
    actor: uuid.UUID | None,
    version: int,
    changes: Mapping[str, Any],
) -> MeteringPropertyAssignment:
    """Optimistic locking (section 8): ``version`` must match, else 409 and no silent loss."""
    if row.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    before = {k: getattr(row, k) for k in ("valid_from", "valid_to", "status", "group_id")}
    for key, value in changes.items():
        if value is None and key not in {"valid_to"}:
            continue
        if key == "unit_scope":
            row.unit_scope = await _check_unit_scope(session, row.property_id, value)
        elif key == "status":
            if value == AssignmentStatus.CONFIRMED:
                row.confirmed_by = actor
                row.confirmed_at = _now()
                row.conflict_reason = None
            row.status = value
        elif key in {
            "valid_from",
            "valid_to",
            "service_scope",
            "is_primary",
            "group_id",
            "verification_basis",
            "note",
            "error_hint",
        }:
            setattr(row, key, value)
        else:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekanntes Feld: {key}")
    if row.valid_to is not None and row.valid_to < row.valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gültig bis liegt vor Gültig ab.")
    if row.group_id is not None and not row.unit_scope:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Gruppierung braucht einen ausdrücklichen Einheitenumfang.",
        )
    if row.status != AssignmentStatus.ARCHIVED:
        conflicts = await _conflicting_assignments(session, row)
        if conflicts:
            raise ProblemError(
                ErrorCodes.METERING_ASSIGNMENT_CONFLICT,
                detail=conflicts[0][1],
                extensions={"conflicting_assignment_ids": [str(c.id) for c, _ in conflicts]},
            )
    row.version += 1
    row.updated_by = actor
    await session.flush()
    await session.refresh(row)
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="metering.assignment.updated",
        entity_type="metering_property_assignment",
        entity_id=row.id,
        actor_user_id=actor,
        changes={
            k: {"before": str(before[k]), "after": str(getattr(row, k))}
            for k in before
            if before[k] != getattr(row, k)
        },
    )
    await invalidate_transmissions(session, row.id, actor=actor, reason="Objektzuordnung geändert.")
    return row


async def confirm_remote(
    session: AsyncSession,
    row: MeteringPropertyAssignment,
    *,
    actor: uuid.UUID | None,
    version: int,
    verification_basis: str,
) -> MeteringPropertyAssignment:
    """Technical confirmation by the provider (distinct from the human confirmation). Stage 1
    records it only from an explicit, documented basis (e.g. a provider answer entered by the
    user); no adapter can set it yet."""
    if row.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    row.remote_confirmed = True
    row.remote_confirmed_at = _now()
    row.verification_basis = verification_basis
    row.version += 1
    row.updated_by = actor
    await session.flush()
    await session.refresh(row)
    return row


async def change_provider(
    session: AsyncSession,
    old: MeteringPropertyAssignment,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    version: int,
    change_date: date,
    new_connection_id: uuid.UUID,
    new_external_number: str,
    unit_scope: Sequence[str] | None = None,
) -> tuple[MeteringPropertyAssignment, MeteringPropertyAssignment]:
    """Provider change (section 5): end the old assignment the day before ``change_date`` and
    create the new one from ``change_date``. The old row keeps its history and remains the
    reference of documents and results of its period."""
    if old.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    if change_date <= old.valid_from:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Wechseldatum muss nach dem Beginn der alten Zuordnung liegen.",
        )
    old.valid_to = change_date - timedelta(days=1)
    old.is_primary = False
    old.version += 1
    old.updated_by = actor
    await session.flush()
    await session.refresh(old)
    await invalidate_transmissions(session, old.id, actor=actor, reason="Anbieterwechsel.")
    new = await create_assignment(
        session,
        tenant_id=tenant_id,
        actor=actor,
        connection_id=new_connection_id,
        property_id=old.property_id,
        external_number=new_external_number,
        service_scope=old.service_scope,
        valid_from=change_date,
        valid_to=None,
        is_primary=True,
        group_id=old.group_id,
        unit_scope=list(old.unit_scope) if unit_scope is None else unit_scope,
        note=f"Anbieterwechsel, Vorgänger {old.id}",
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type="metering.assignment.provider_changed",
        entity_type="metering_property_assignment",
        entity_id=new.id,
        actor_user_id=actor,
        payload={"previous_assignment_id": str(old.id), "change_date": change_date.isoformat()},
    )
    return old, new


def assignment_query(
    *,
    property_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    status: str | None = None,
    service_scope: str | None = None,
    search: str | None = None,
    include_archived: bool = False,
) -> Select[Any]:
    """One query for the object tab and the central overview (section 2)."""
    query = (
        select(MeteringPropertyAssignment)
        .join(Property, Property.id == MeteringPropertyAssignment.property_id)
        .join(
            MeteringExternalBillingUnit,
            MeteringExternalBillingUnit.id == MeteringPropertyAssignment.external_billing_unit_id,
        )
        .join(MeteringConnection, MeteringConnection.id == MeteringPropertyAssignment.connection_id)
    )
    if property_id is not None:
        query = query.where(MeteringPropertyAssignment.property_id == property_id)
    if connection_id is not None:
        query = query.where(MeteringPropertyAssignment.connection_id == connection_id)
    if status is not None:
        query = query.where(MeteringPropertyAssignment.status == status)
    elif not include_archived:
        query = query.where(MeteringPropertyAssignment.status != AssignmentStatus.ARCHIVED)
    if service_scope is not None:
        query = query.where(MeteringPropertyAssignment.service_scope == service_scope)
    if search:
        pattern = f"%{escape_like(search.strip())}%"
        query = query.where(
            or_(
                Property.number.ilike(pattern),
                Property.name.ilike(pattern),
                func.coalesce(Property.street, "").ilike(pattern),
                MeteringExternalBillingUnit.external_number.ilike(pattern),
                MeteringConnection.display_name.ilike(pattern),
            )
        )
    return query.order_by(Property.number, MeteringPropertyAssignment.valid_from.desc())


# Unit assignments ------------------------------------------------------------------------


async def create_unit_assignment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    property_assignment: MeteringPropertyAssignment,
    unit_id: uuid.UUID,
    external_unit_number: str,
    valid_from: date,
    valid_to: date | None,
    billing_recipient_contact_id: uuid.UUID | None,
    consumption_info_recipient_contact_id: uuid.UUID | None,
    occupancy_status: str,
    external_partner_ref: str | None = None,
    note: str | None = None,
) -> MeteringUnitAssignment:
    unit = await session.get(Unit, unit_id)
    if unit is None or unit.property_id != property_assignment.property_id:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Einheit gehört nicht zum Objekt.")
    if property_assignment.unit_scope and str(unit_id) not in property_assignment.unit_scope:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Einheit liegt außerhalb des Einheitenumfangs."
        )
    number = external_unit_number.strip()
    if not number:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Externe Nutzeinheitsnummer fehlt.")
    others = await session.scalars(
        select(MeteringUnitAssignment).where(
            MeteringUnitAssignment.property_assignment_id == property_assignment.id,
            MeteringUnitAssignment.status != AssignmentStatus.ARCHIVED,
            or_(
                MeteringUnitAssignment.unit_id == unit_id,
                MeteringUnitAssignment.external_unit_number == number,
            ),
        )
    )
    for other in others:
        if _overlaps(valid_from, valid_to, other.valid_from, other.valid_to):
            raise ProblemError(
                ErrorCodes.METERING_ASSIGNMENT_CONFLICT,
                detail="Einheit oder externe Nutzeinheit ist im Zeitraum bereits zugeordnet.",
                extensions={"conflicting_assignment_ids": [str(other.id)]},
            )
    row = MeteringUnitAssignment(
        tenant_id=tenant_id,
        property_assignment_id=property_assignment.id,
        unit_id=unit_id,
        external_unit_number=number,
        valid_from=valid_from,
        valid_to=valid_to,
        billing_recipient_contact_id=billing_recipient_contact_id,
        consumption_info_recipient_contact_id=consumption_info_recipient_contact_id,
        occupancy_status=occupancy_status,
        external_partner_ref=external_partner_ref,
        note=note,
        created_by=actor,
        updated_by=actor,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    await invalidate_transmissions(
        session, property_assignment.id, actor=actor, reason="Einheitenzuordnung angelegt."
    )
    return row


async def update_unit_assignment(
    session: AsyncSession,
    row: MeteringUnitAssignment,
    *,
    actor: uuid.UUID | None,
    version: int,
    changes: Mapping[str, Any],
) -> MeteringUnitAssignment:
    """Occupant changes touch only recipients and occupancy; the physical mapping
    (``unit_id``, ``external_unit_number``) is not changeable here (section 7). A corrected
    mapping is a new row with its own validity."""
    if row.version != version:
        raise ProblemError(ErrorCodes.METERING_VERSION_CONFLICT)
    for key, value in changes.items():
        if key in {"unit_id", "external_unit_number"}:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Physische Einheitenzuordnung wird nicht geändert; neue Zuordnung anlegen.",
            )
        if key in {
            "valid_to",
            "billing_recipient_contact_id",
            "consumption_info_recipient_contact_id",
            "occupancy_status",
            "status",
            "external_partner_ref",
            "note",
        }:
            setattr(row, key, value)
        elif key == "valid_from" and value is not None:
            row.valid_from = value
        else:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekanntes Feld: {key}")
    if row.valid_to is not None and row.valid_to < row.valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gültig bis liegt vor Gültig ab.")
    row.version += 1
    row.updated_by = actor
    await session.flush()
    await session.refresh(row)
    await invalidate_transmissions(
        session, row.property_assignment_id, actor=actor, reason="Einheitenzuordnung geändert."
    )
    return row


# Sync jobs -------------------------------------------------------------------------------


async def _assignments_in_scope(
    session: AsyncSession, connection: MeteringConnection, scope: Mapping[str, Any]
) -> list[MeteringPropertyAssignment]:
    query = select(MeteringPropertyAssignment).where(
        MeteringPropertyAssignment.connection_id == connection.id,
        MeteringPropertyAssignment.status != AssignmentStatus.ARCHIVED,
    )
    property_ids = [uuid.UUID(str(p)) for p in scope.get("property_ids", [])]
    if property_ids:
        query = query.where(MeteringPropertyAssignment.property_id.in_(property_ids))
    return list(await session.scalars(query))


async def create_sync_job(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    connection: MeteringConnection,
    data_kind: str,
    scope: Mapping[str, Any],
    period_from: date | None,
    period_to: date | None,
) -> MeteringSyncJob:
    """Manual "Jetzt abrufen" (section 10): read only. Refused when the function is not
    available (capability matrix), when an assignment in scope is in conflict, or when the
    same job is already queued or running (double click protection)."""
    if connection.status != ConnectionStatus.ACTIVE:
        raise ProblemError(ErrorCodes.METERING_CONNECTION_PAUSED)
    function = DATA_KIND_FUNCTION[data_kind]
    if function in WRITING_FUNCTIONS:  # defensive: DataKind never maps to a writing function
        raise ProblemError(ErrorCodes.METERING_CAPABILITY_MISSING)
    available, reason = function_available(connection, function)
    if not available:
        raise ProblemError(ErrorCodes.METERING_CAPABILITY_MISSING, detail=reason)
    assignments = await _assignments_in_scope(session, connection, scope)
    conflicts = [a for a in assignments if a.status == AssignmentStatus.CONFLICT]
    if conflicts:
        raise ProblemError(
            ErrorCodes.METERING_CONFLICT_BLOCKS_WRITE,
            extensions={"assignment_ids": [str(a.id) for a in conflicts]},
        )
    running = await session.scalar(
        select(func.count())
        .select_from(MeteringSyncJob)
        .where(
            MeteringSyncJob.connection_id == connection.id,
            MeteringSyncJob.data_kind == data_kind,
            MeteringSyncJob.scope == dict(scope),
            MeteringSyncJob.status.in_([SyncStatus.QUEUED, SyncStatus.RUNNING]),
        )
    )
    if running:
        raise ProblemError(ErrorCodes.METERING_SYNC_ALREADY_RUNNING)
    last_success = (connection.last_sync or {}).get(data_kind)
    job = MeteringSyncJob(
        tenant_id=tenant_id,
        connection_id=connection.id,
        scope=dict(scope),
        data_kind=data_kind,
        period_from=period_from,
        period_to=period_to,
        assignment_version=sum(a.version for a in assignments),
        status=SyncStatus.QUEUED,
        requested_by=actor,
        last_success_at=datetime.fromisoformat(last_success) if last_success else None,
        created_by=actor,
        updated_by=actor,
    )
    session.add(job)
    await session.flush()
    await session.refresh(job)
    return job


def _find_assignment(
    assignments: Iterable[MeteringPropertyAssignment],
    units: Mapping[uuid.UUID, MeteringExternalBillingUnit],
    external_number: str,
    period_from: date,
    period_to: date,
) -> MeteringPropertyAssignment | None:
    """Late imports are assigned by their business period, not by today's provider
    (section 5). Ambiguous matches (grouped units) return ``None`` and go to clearing."""
    hits = [
        a
        for a in assignments
        if units[a.external_billing_unit_id].external_number == external_number
        and _overlaps(a.valid_from, a.valid_to, period_from, period_to)
    ]
    return hits[0] if len(hits) == 1 else None


async def run_sync_job(
    session: AsyncSession,
    job: MeteringSyncJob,
    *,
    blobs: Any | None = None,
    max_document_bytes: int = 50 * 1024 * 1024,
) -> MeteringSyncJob:
    """Executes a queued job through the adapter (worker context). Re-checks the assignment
    version so a changed configuration never redirects a running job to another data set.
    ``blobs`` is the document store (``BlobStore``) for document jobs; without it a document
    job reports the intake part as failed instead of storing anything unsafe."""
    if job.status != SyncStatus.QUEUED:
        return job
    connection = await get_connection(session, job.connection_id)
    job.status = SyncStatus.RUNNING
    job.started_at = _now()
    await session.flush()
    parts: list[dict[str, Any]] = []
    assignments = await _assignments_in_scope(session, connection, job.scope)
    if sum(a.version for a in assignments) != job.assignment_version:
        job.status = SyncStatus.FAILED
        job.error_summary = (
            "Zuordnungen wurden seit Auftragserstellung geändert; bitte neu starten."
        )
        job.finished_at = _now()
        return job
    units = {
        u.id: u
        for u in await session.scalars(
            select(MeteringExternalBillingUnit).where(
                MeteringExternalBillingUnit.connection_id == connection.id
            )
        )
    }
    function = DATA_KIND_FUNCTION[job.data_kind]
    adapter = _adapter(connection)
    secrets = connection_secrets(connection)
    if adapter.required_secrets - set(secrets):
        job.status = SyncStatus.FAILED
        job.error_summary = "Zugangsdaten fehlen."
        job.finished_at = _now()
        return job
    cursor = ((connection.last_sync or {}).get(CURSOR_KEY) or {}).get(job.data_kind)
    result: FetchResult = adapter.fetch(
        function=function,
        config=connection.config,
        secrets=secrets,
        environment=connection.environment,
        external_billing_units=[
            units[a.external_billing_unit_id].external_number for a in assignments
        ],
        period_from=job.period_from,
        period_to=job.period_to,
        cursor=cursor,
    )
    if result.unclear:
        job.status = SyncStatus.UNCLEAR
        job.error_summary = "; ".join(result.errors) or "Ergebnis unklar."
        job.finished_at = _now()
        return job
    stored = 0
    cleared = 0
    part_errors: list[str] = []
    for record in result.consumption:
        assignment = _find_assignment(
            assignments, units, record.external_billing_unit, record.period_from, record.period_to
        )
        if assignment is None:
            await _clear(
                session,
                job,
                connection,
                "consumption",
                record.external_billing_unit,
                "Keine eindeutige Zuordnung für Abrechnungseinheit und Zeitraum.",
                record.__dict__,
            )
            cleared += 1
            continue
        unit_assignment = await _unit_assignment_for(
            session, assignment, record.external_unit_number, record.period_from, record.period_to
        )
        if record.external_unit_number and unit_assignment is None:
            await _clear(
                session,
                job,
                connection,
                "consumption_unit",
                f"{record.external_billing_unit}/{record.external_unit_number}",
                "Externe Nutzeinheit ist keiner internen Einheit zugeordnet.",
                record.__dict__,
            )
            cleared += 1
            continue
        if record.value_kind == ValueKind.MISSING and record.value is not None:
            record = record.__class__(**{**record.__dict__, "value": None})
        if record.value_kind != ValueKind.MISSING and record.value is None:
            await _clear(
                session,
                job,
                connection,
                "consumption",
                record.external_billing_unit,
                "Wert fehlt, obwohl die Wertart nicht 'fehlend' ist; keine Nullsetzung.",
                record.__dict__,
            )
            cleared += 1
            continue
        stored += await _store_consumption(session, job, assignment, unit_assignment, record)
        assignment.last_success_at = _now()
    for billing in result.billing_results:
        assignment = _find_assignment(
            assignments,
            units,
            billing.external_billing_unit,
            billing.period_from,
            billing.period_to,
        )
        if assignment is None:
            await _clear(
                session,
                job,
                connection,
                "billing_result",
                billing.external_document_ref,
                "Keine eindeutige Zuordnung für Abrechnungseinheit und Zeitraum.",
                {**billing.__dict__, "amount": str(billing.amount)},
            )
            cleared += 1
            continue
        unit_assignment = await _unit_assignment_for(
            session,
            assignment,
            billing.external_unit_number,
            billing.period_from,
            billing.period_to,
        )
        stored += await _store_billing_result(session, job, assignment, unit_assignment, billing)
        assignment.last_success_at = _now()
    for external in result.billing_units:
        outcome = await _store_billing_unit_result(session, job, connection, units, external)
        if outcome is None:
            cleared += 1
        else:
            stored += outcome
    if result.documents:
        if blobs is None:
            part_errors.append("Dokumentablage nicht verfügbar; keine Dokumente übernommen.")
        else:
            for document in result.documents:
                outcome_doc = await _intake_document(
                    session,
                    job,
                    connection,
                    adapter,
                    secrets,
                    assignments,
                    units,
                    document,
                    blobs=blobs,
                    max_bytes=max_document_bytes,
                )
                if outcome_doc == "cleared":
                    cleared += 1
                elif outcome_doc == "stored":
                    stored += 1
                elif outcome_doc.startswith("error:"):
                    part_errors.append(outcome_doc[6:])
    if wait := result.waiting_provider:
        parts.append(
            {
                "part": "provider",
                "status": "waiting",
                "error": "Der Anbieter verarbeitet den Abgleich noch (asynchron).",
            }
        )
    parts.append(
        {
            "part": "fetch",
            "status": "ok" if not result.errors else "error",
            "error": "; ".join(result.errors) or None,
        }
    )
    parts.append(
        {
            "part": "store",
            "status": "ok" if not part_errors else "error",
            "error": "; ".join(part_errors) or None,
            "stored": stored,
        }
    )
    parts.append(
        {
            "part": "clearing",
            "status": "ok" if not cleared else "warning",
            "error": None if not cleared else f"{cleared} Datensätze im Klärungsbereich",
        }
    )
    job.parts = parts
    errors = list(result.errors) + part_errors
    if wait and not errors:
        job.status = SyncStatus.WAITING_PROVIDER
    elif errors and (stored or cleared):
        job.status = SyncStatus.PARTIAL
    elif errors:
        job.status = SyncStatus.FAILED
    else:
        job.status = SyncStatus.SUCCEEDED  # "no data" is not an error (section 10)
    job.error_summary = "; ".join(errors) or None
    job.finished_at = _now()
    if job.status in {SyncStatus.SUCCEEDED, SyncStatus.PARTIAL, SyncStatus.WAITING_PROVIDER}:
        last = dict(connection.last_sync or {})
        last[job.data_kind] = job.finished_at.isoformat()
        if job.status == SyncStatus.SUCCEEDED and job.data_kind in {
            DataKind.BILLING_UNIT_DATA,
            DataKind.BILLING_RESULT,
        }:
            # Cursor advanced only after complete, durable processing (section 10); a
            # partial run keeps the old cursor so the failed part is fetched again.
            cursors = dict(last.get(CURSOR_KEY) or {})
            cursors[job.data_kind] = job.started_at.isoformat() if job.started_at else None
            last[CURSOR_KEY] = cursors
        connection.last_sync = last
    await session.flush()
    return job


async def _store_billing_unit_result(
    session: AsyncSession,
    job: MeteringSyncJob,
    connection: MeteringConnection,
    units: Mapping[uuid.UUID, MeteringExternalBillingUnit],
    external: ExternalBillingUnitData,
) -> int | None:
    """Result of the asynchronous Ordnungsbegriffsabgleich (Q8): status and matched external
    unit numbers are stored on the known external billing unit as remote payload (reviewable,
    no assignment is created or changed automatically). Unknown numbers go to clearing."""
    row = next((u for u in units.values() if u.external_number == external.external_number), None)
    if row is None:
        await _clear(
            session,
            job,
            connection,
            "billing_unit",
            external.external_number,
            "Abrechnungseinheit des Anbieters ist keinem Objekt zugeordnet.",
            {"name": external.name, "address": external.address, **external.payload},
        )
        return None
    payload = {
        **external.payload,
        "matched_units": [
            {"external_unit_number": u.external_unit_number, "label": u.label}
            for u in external.units
        ],
        "fetched_at": _now().isoformat(),
        "sync_job_id": str(job.id),
    }
    previous = dict(row.remote_payload or {})
    previous.pop("fetched_at", None)
    previous.pop("sync_job_id", None)
    compare = {k: v for k, v in payload.items() if k not in {"fetched_at", "sync_job_id"}}
    if previous == compare:
        return 0
    row.remote_payload = json.loads(json.dumps(payload, default=str))
    if external.name and not row.external_name:
        row.external_name = external.name[:200]
    if external.address and not row.external_address:
        row.external_address = external.address[:400]
    if external.units:
        row.expected_unit_count = len(external.units)
    return 1


async def _intake_document(
    session: AsyncSession,
    job: MeteringSyncJob,
    connection: MeteringConnection,
    adapter: MeteringAdapter,
    secrets: Mapping[str, str],
    assignments: Sequence[MeteringPropertyAssignment],
    units: Mapping[uuid.UUID, MeteringExternalBillingUnit],
    document: DocumentRecord,
    *,
    blobs: Any,
    max_bytes: int,
) -> str:
    """Section 11: assignment before download, no duplicate on re download (same connection,
    external id and version), changed billing as a new version, validation with the
    document store's checks, provider receipt only after commit (``acknowledge_documents``).
    Returns ``stored``, ``skipped``, ``cleared`` or ``error:<text>``."""
    from mhvp.documents.services import check_upload, store_document

    if not document.external_billing_unit:
        await _clear(
            session,
            job,
            connection,
            "document",
            document.external_id,
            "Dokument ohne Referenz auf eine Abrechnungseinheit; keine Ablage nach Ähnlichkeit.",
            _document_payload(document),
        )
        return "cleared"
    period_from = document.period_from or job.period_from or date.min
    period_to = document.period_to or job.period_to or date.max
    assignment = _find_assignment(
        assignments, units, document.external_billing_unit, period_from, period_to
    )
    if assignment is None:
        await _clear(
            session,
            job,
            connection,
            "document",
            document.external_id,
            "Keine eindeutige Zuordnung für Abrechnungseinheit und Zeitraum.",
            _document_payload(document),
        )
        return "cleared"
    version = document.version or "1"
    source_id = _document_source_id(connection, document.external_id, version)
    existing = await session.scalar(
        select(Document).where(
            Document.tenant_id == job.tenant_id,
            Document.source_system == DOCUMENT_SOURCE_SYSTEM,
            Document.source_id == source_id,
        )
    )
    if existing is not None:
        return "skipped"  # re download never duplicates
    earlier = list(
        await session.scalars(
            select(Document).where(
                Document.tenant_id == job.tenant_id,
                Document.source_system == DOCUMENT_SOURCE_SYSTEM,
                Document.source_id.like(
                    escape_like(_document_source_id(connection, document.external_id, "")) + "%",
                    escape="\\",
                ),
            )
        )
    )
    try:
        data = adapter.download_document(
            config=connection.config,
            secrets=secrets,
            environment=connection.environment,
            document=document,
        )
    except Exception as exc:  # adapter errors are already sanitised
        return f"error:Dokument {document.external_id}: Download fehlgeschlagen ({exc})"
    mime_type = document.mime_type or "application/pdf"
    try:
        check_upload(mime_type, data, max_bytes)
    except ProblemError as exc:
        await _clear(
            session,
            job,
            connection,
            "document",
            document.external_id,
            f"Datei abgewiesen: {exc.detail or exc.error.code}",
            _document_payload(document),
        )
        return "cleared"
    unit_assignment = None
    if document.external_unit_number:
        unit_assignment = await _unit_assignment_for(
            session, assignment, document.external_unit_number, period_from, period_to
        )
    links: list[tuple[str, uuid.UUID, LinkRole]] = [
        ("property", assignment.property_id, LinkRole.ORIGINAL)
    ]
    if unit_assignment is not None:
        links.append(("unit", unit_assignment.unit_id, LinkRole.ORIGINAL))
    title = f"{connection.provider_code} {document.doctype} {document.filename}"
    stored = await store_document(
        session,
        blobs,
        tenant_id=job.tenant_id,
        data=data,
        title=title,
        filename=document.filename,
        mime_type=mime_type,
        source=DocumentSource.IMPORT,
        category_id=None,
        links=links,
        created_by=None,
        visibility=["tenant"],  # never released to residents by the import alone
    )
    stored.source_system = DOCUMENT_SOURCE_SYSTEM
    stored.source_id = source_id
    stored.source_meta = json.loads(
        json.dumps(
            {
                "provider_code": connection.provider_code,
                "connection_id": str(connection.id),
                "environment": connection.environment,
                "external_id": document.external_id,
                "version": version,
                "doctype": document.doctype,
                "period_from": document.period_from,
                "period_to": document.period_to,
                "external_billing_unit": document.external_billing_unit,
                "external_unit_number": document.external_unit_number,
                "property_assignment_id": str(assignment.id),
                "unit_assignment_id": str(unit_assignment.id) if unit_assignment else None,
                "sync_job_id": str(job.id),
                "fetched_at": _now(),
                "file_date": document.file_date,
                "supersedes": [str(d.id) for d in earlier],
                "acknowledged_at": None,
                "acknowledge_pending": True,
            },
            default=str,
        )
    )
    await session.flush()
    assignment.last_success_at = _now()
    return "stored"


def _document_source_id(connection: MeteringConnection, external_id: str, version: str) -> str:
    return f"{connection.id}:{external_id}:{version}"[:64]


def _document_payload(document: DocumentRecord) -> dict[str, Any]:
    payload = dict(document.__dict__)
    payload.pop("payload", None)
    return payload


async def pending_document_receipts(
    session: AsyncSession, connection_id: uuid.UUID
) -> list[Document]:
    return list(
        await session.scalars(
            select(Document).where(
                Document.source_system == DOCUMENT_SOURCE_SYSTEM,
                Document.source_meta["connection_id"].astext == str(connection_id),
                Document.source_meta["acknowledge_pending"].astext == "true",
            )
        )
    )


async def acknowledge_documents(session: AsyncSession, connection_id: uuid.UUID) -> int:
    """Provider receipt for documents that are committed in the store (section 11: "erst nach
    sicherer Speicherung"). Called by the worker in a separate transaction after the sync
    job committed. A failed or unclear receipt leaves ``acknowledge_pending`` set; the next
    job repeats it (the document itself is never downloaded twice)."""
    connection = await get_connection(session, connection_id)
    adapter = _adapter(connection)
    secrets = connection_secrets(connection)
    done = 0
    for document in await pending_document_receipts(session, connection_id):
        meta = dict(document.source_meta or {})
        record = DocumentRecord(
            external_id=str(meta.get("external_id")),
            filename=document.filename,
            doctype=str(meta.get("doctype") or "OTHER"),
            mime_type=document.mime_type,
            version=meta.get("version"),
            file_date=None,
            external_billing_unit=meta.get("external_billing_unit"),
            external_unit_number=meta.get("external_unit_number"),
            period_from=None,
            period_to=None,
        )
        try:
            adapter.acknowledge_document(
                config=connection.config,
                secrets=secrets,
                environment=connection.environment,
                document=record,
            )
        except Exception as exc:  # kept pending, reported on the document
            meta["acknowledge_error"] = str(exc)[:500]
            document.source_meta = meta
            continue
        meta["acknowledge_pending"] = False
        meta["acknowledged_at"] = _now().isoformat()
        meta.pop("acknowledge_error", None)
        document.source_meta = meta
        done += 1
    await session.flush()
    return done


async def _clear(
    session: AsyncSession,
    job: MeteringSyncJob,
    connection: MeteringConnection,
    entity_type: str,
    identifier: str,
    reason: str,
    payload: Mapping[str, Any],
) -> None:
    session.add(
        MeteringClearingItem(
            tenant_id=job.tenant_id,
            connection_id=connection.id,
            sync_job_id=job.id,
            entity_type=entity_type,
            external_identifier=identifier[:128],
            reason=reason,
            payload=json.loads(json.dumps(dict(payload), default=str)),
        )
    )


async def _unit_assignment_for(
    session: AsyncSession,
    assignment: MeteringPropertyAssignment,
    external_unit_number: str | None,
    period_from: date,
    period_to: date,
) -> MeteringUnitAssignment | None:
    if not external_unit_number:
        return None
    rows = list(
        await session.scalars(
            select(MeteringUnitAssignment).where(
                MeteringUnitAssignment.property_assignment_id == assignment.id,
                MeteringUnitAssignment.external_unit_number == external_unit_number,
                MeteringUnitAssignment.status != AssignmentStatus.ARCHIVED,
            )
        )
    )
    hits = [r for r in rows if _overlaps(r.valid_from, r.valid_to, period_from, period_to)]
    return hits[0] if len(hits) == 1 else None


async def _store_consumption(
    session: AsyncSession,
    job: MeteringSyncJob,
    assignment: MeteringPropertyAssignment,
    unit_assignment: MeteringUnitAssignment | None,
    record: Any,
) -> int:
    """Idempotent: an identical value is not stored twice; a changed value becomes a new
    version (section 11), the old one is never overwritten."""
    existing = list(
        await session.scalars(
            select(MeteringConsumptionValue)
            .where(
                MeteringConsumptionValue.property_assignment_id == assignment.id,
                MeteringConsumptionValue.unit_assignment_id
                == (unit_assignment.id if unit_assignment else None),
                MeteringConsumptionValue.period_from == record.period_from,
                MeteringConsumptionValue.period_to == record.period_to,
                MeteringConsumptionValue.kind == record.kind,
                MeteringConsumptionValue.reading_type == record.reading_type,
                MeteringConsumptionValue.source == "provider",
            )
            .order_by(MeteringConsumptionValue.version.desc())
        )
    )
    if existing:
        latest = existing[0]
        if (
            latest.value == record.value
            and latest.value_kind == record.value_kind
            and latest.unit_of_measure == record.unit_of_measure
        ):
            return 0
        version = latest.version + 1
        value_kind = (
            ValueKind.CORRECTED if record.value_kind == ValueKind.ACTUAL else record.value_kind
        )
    else:
        version = 1
        value_kind = record.value_kind
    session.add(
        MeteringConsumptionValue(
            tenant_id=job.tenant_id,
            property_assignment_id=assignment.id,
            unit_assignment_id=unit_assignment.id if unit_assignment else None,
            sync_job_id=job.id,
            period_from=record.period_from,
            period_to=record.period_to,
            kind=record.kind,
            unit_of_measure=record.unit_of_measure,
            reading_type=record.reading_type,
            source="provider",
            version=version,
            value=record.value,
            value_kind=value_kind,
            external_ref=record.external_ref,
        )
    )
    await session.flush()
    return 1


async def _store_billing_result(
    session: AsyncSession,
    job: MeteringSyncJob,
    assignment: MeteringPropertyAssignment,
    unit_assignment: MeteringUnitAssignment | None,
    record: Any,
) -> int:
    existing = list(
        await session.scalars(
            select(MeteringBillingResult)
            .where(
                MeteringBillingResult.property_assignment_id == assignment.id,
                MeteringBillingResult.unit_assignment_id
                == (unit_assignment.id if unit_assignment else None),
                MeteringBillingResult.period_from == record.period_from,
                MeteringBillingResult.period_to == record.period_to,
                MeteringBillingResult.external_document_ref == record.external_document_ref,
            )
            .order_by(MeteringBillingResult.version.desc())
        )
    )
    if existing and existing[0].amount == record.amount and existing[0].currency == record.currency:
        return 0
    session.add(
        MeteringBillingResult(
            tenant_id=job.tenant_id,
            property_assignment_id=assignment.id,
            unit_assignment_id=unit_assignment.id if unit_assignment else None,
            sync_job_id=job.id,
            period_from=record.period_from,
            period_to=record.period_to,
            amount=record.amount,
            currency=record.currency,
            version=(existing[0].version + 1) if existing else 1,
            external_document_ref=record.external_document_ref,
            payload=json.loads(json.dumps(dict(record.payload), default=str)),
        )
    )
    await session.flush()
    return 1


# Clearing --------------------------------------------------------------------------------


async def resolve_clearing_item(
    session: AsyncSession,
    item: MeteringClearingItem,
    *,
    actor: uuid.UUID | None,
    status: str,
    note: str | None,
    property_assignment_id: uuid.UUID | None,
) -> MeteringClearingItem:
    """Marks an item as resolved or dismissed. Resolution never moves data automatically: the
    user records the link and the next fetch stores the data through the corrected assignment."""
    if property_assignment_id is not None:
        await get_assignment(session, property_assignment_id)
    item.status = status
    item.resolved_by = actor
    item.resolved_at = _now()
    item.resolution_note = note
    item.property_assignment_id = property_assignment_id
    await session.flush()
    await session.refresh(item)
    return item
