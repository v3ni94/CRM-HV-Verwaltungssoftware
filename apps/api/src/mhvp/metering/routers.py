"""Messdienstleister module API (``/api/v1/metering``, master prompt sections 2 to 10).

Permissions (section 9): ``metering_connections:manage`` (credentials, connections),
``metering_assignments:update`` (property and unit assignments, clearing, import),
``metering_sync:run`` (manual fetch), ``metering_data:read`` (everything readable),
``metering_users:submit`` (user and role submission workflow) and ``metering_billing:order``
(billing input workflow). "Daten prüfen" (``POST /transmissions/check``) and the binding
order (``POST /transmissions/{id}/order``) are separate endpoints (section 12); a release in
between (``/release``) is tied to the payload fingerprint.
Every write endpoint is additionally locked by ``tenant_settings.metering_module_enabled``.
Secrets are accepted on create and on ``PUT .../secrets`` only and are never returned.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.core.auth.permissions import (
    METERING_ASSIGNMENTS_UPDATE,
    METERING_CONNECTIONS_MANAGE,
    METERING_DATA_READ,
    METERING_SYNC_RUN,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.listparams import ListParams, ListSpec, sparse, strict_query
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_limited
from mhvp.metering import csv_io, services, transmissions
from mhvp.metering.models import (
    AssignmentStatus,
    ClearingStatus,
    ConnectionStatus,
    DataKind,
    Environment,
    MeteringBillingResult,
    MeteringClearingItem,
    MeteringConnection,
    MeteringConsumptionValue,
    MeteringExternalBillingUnit,
    MeteringPropertyAssignment,
    MeteringSyncJob,
    MeteringTransmission,
    MeteringUnitAssignment,
    OccupancyStatus,
    ServiceScope,
    SyncStatus,
    TransmissionKind,
)
from mhvp.metering.providers import (
    DOCUMENTED_SUPPORT_LABELS,
    PROVIDERS,
    SOURCES,
    Function,
)
from mhvp.properties.models import Property

router = APIRouter(prefix="/metering", tags=["Messdienstleister"])
READ = require_permission(METERING_DATA_READ)
MANAGE = require_permission(METERING_CONNECTIONS_MANAGE)
ASSIGN = require_permission(METERING_ASSIGNMENTS_UPDATE)
SYNC = require_permission(METERING_SYNC_RUN)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Providers -------------------------------------------------------------------------------


class ProviderFunctionOut(BaseModel):
    function: str
    documented_support: str
    label: str
    source: str
    note: str
    adapter_implemented: bool


class MeteringProviderOut(BaseModel):
    code: str
    name: str
    manual_only: bool
    functions: list[ProviderFunctionOut]
    sources: dict[str, str]
    research_note: str
    auth_note: str


@router.get(
    "/providers", summary="Anbieterkatalog mit Recherchestand", dependencies=[Depends(strict_query)]
)
async def list_providers(principal: TenantPrincipal = Depends(READ)) -> list[MeteringProviderOut]:
    from mhvp.metering.adapters import adapter_for

    out: list[MeteringProviderOut] = []
    for provider in PROVIDERS:
        adapter = adapter_for(provider.code, {})
        out.append(
            MeteringProviderOut(
                code=provider.code,
                name=provider.name,
                manual_only=provider.manual_only,
                functions=[
                    ProviderFunctionOut(
                        function=f.value,
                        documented_support=provider.support(f).documented.value,
                        label=DOCUMENTED_SUPPORT_LABELS[provider.support(f).documented],
                        source=provider.support(f).source,
                        note=provider.support(f).note,
                        adapter_implemented=f in adapter.implemented,
                    )
                    for f in Function
                ],
                sources={k: SOURCES[k] for k in provider.sources},
                research_note=provider.research_note,
                auth_note=provider.auth_note,
            )
        )
    return out


# Connections -----------------------------------------------------------------------------


class MeteringConnectionIn(_In):
    display_name: str = Field(min_length=1, max_length=200)
    provider_code: str = Field(min_length=1, max_length=32)
    environment: Environment = Environment.TEST
    customer_references: list[str] = Field(default_factory=list, max_length=50)
    contracting_company: str | None = Field(default=None, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] | None = Field(
        default=None, description="Nur setzen; wird nie zurückgegeben."
    )
    account_release: dict[str, bool] | None = None


class ConnectionPatch(_In):
    version: int
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConnectionStatus | None = None
    environment: Environment | None = None
    customer_references: list[str] | None = Field(default=None, max_length=50)
    contracting_company: str | None = Field(default=None, max_length=200)
    config: dict[str, Any] | None = None
    account_release: dict[str, bool] | None = None
    scheduled_sync_enabled: bool | None = None
    write_sync_enabled: bool | None = Field(
        default=None,
        description="Freigabe der kontrollierten schreibenden Vorgänge (Rollen, Billing Input) "
        "für diese Verbindung; Standard aus.",
    )


class SecretsIn(_In):
    secrets: dict[str, str] = Field(
        description="Name zu Wert; leerer Wert entfernt das Geheimnis. Nie auslesbar."
    )


class CapabilityOut(BaseModel):
    function: str
    documented_support: str
    documented_source: str
    documented_note: str
    adapter_implemented: bool
    supported_version: str | None
    spec_source: str | None
    account_release: bool
    property_release: Any = None
    last_test_result: Any = None
    last_test_at: datetime | None
    test_stale: bool
    released_by_last_test: bool
    available: bool
    reason: str | None
    label: str


class MeteringConnectionOut(BaseModel):
    id: uuid.UUID
    display_name: str
    provider_code: str
    contracting_company: str | None
    environment: str
    status: str
    customer_references: list[str]
    config: dict[str, Any]
    secret_names: list[str]
    capabilities: list[CapabilityOut]
    last_test_status: str | None
    last_test_at: datetime | None
    last_test_detail: str | None
    test_stale: bool
    scheduled_sync_enabled: bool
    write_sync_enabled: bool
    last_sync: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


def _connection_out(row: MeteringConnection) -> MeteringConnectionOut:
    config = {k: v for k, v in (row.config or {}).items() if not k.startswith("_")}
    return MeteringConnectionOut(
        id=row.id,
        display_name=row.display_name,
        provider_code=row.provider_code,
        contracting_company=row.contracting_company,
        environment=row.environment,
        status=row.status,
        customer_references=list(row.customer_references or []),
        config=config,
        secret_names=list(row.secret_names or []),
        capabilities=[CapabilityOut(**c) for c in services.capability_matrix(row)],
        last_test_status=row.last_test_status,
        last_test_at=row.last_test_at,
        last_test_detail=row.last_test_detail,
        test_stale=row.test_stale,
        scheduled_sync_enabled=row.scheduled_sync_enabled,
        write_sync_enabled=row.write_sync_enabled,
        last_sync=dict(row.last_sync or {}),
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/connections", summary="Verbindungen des Mandanten", dependencies=[Depends(strict_query)]
)
async def list_connections(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[MeteringConnectionOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(MeteringConnection).order_by(MeteringConnection.display_name)
        )
        return [_connection_out(r) for r in rows]


@router.post("/connections", status_code=201, summary="Verbindung anlegen")
async def create_connection(
    body: MeteringConnectionIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> MeteringConnectionOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.create_connection(
            session,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            display_name=body.display_name,
            provider_code=body.provider_code,
            environment=body.environment.value,
            customer_references=body.customer_references,
            config=body.config,
            contracting_company=body.contracting_company,
            secrets=body.secrets,
            account_release=body.account_release,
        )
        return _connection_out(row)


@router.get("/connections/{connection_id}", summary="Verbindung lesen")
async def get_connection(
    connection_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> MeteringConnectionOut:
    async with tenant_tx(request, principal) as session:
        return _connection_out(await services.get_connection(session, connection_id))


@router.patch("/connections/{connection_id}", summary="Verbindung ändern")
async def patch_connection(
    connection_id: uuid.UUID,
    body: ConnectionPatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> MeteringConnectionOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_connection(session, connection_id)
        changes = body.model_dump(exclude={"version"}, exclude_unset=True)
        for key in ("status", "environment"):
            if changes.get(key) is not None:
                changes[key] = changes[key].value
        row = await services.update_connection(
            session, row, actor=principal.user_id, version=body.version, changes=changes
        )
        return _connection_out(row)


@router.put("/connections/{connection_id}/secrets", summary="Geheimnisse setzen oder ersetzen")
async def put_secrets(
    connection_id: uuid.UUID,
    body: SecretsIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> MeteringConnectionOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_connection(session, connection_id)
        services.set_secrets(row, body.secrets, actor=principal.user_id)
        await session.flush()
        await session.refresh(row)
        return _connection_out(row)


class TestOut(BaseModel):
    outcome: str
    detail: str
    functions_released: list[str]
    connection: MeteringConnectionOut


@router.post("/connections/{connection_id}/test", summary="Verbindungstest (nur Anmeldung)")
async def run_connection_test(
    connection_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> TestOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_connection(session, connection_id)
        result = await services.test_connection(session, row, actor=principal.user_id)
        return TestOut(
            outcome=result.outcome,
            detail=result.detail,
            functions_released=list(result.functions_released),
            connection=_connection_out(row),
        )


# Property assignments --------------------------------------------------------------------


class AssignmentIn(_In):
    connection_id: uuid.UUID
    property_id: uuid.UUID
    external_number: str = Field(min_length=1, max_length=64)
    service_scope: ServiceScope
    valid_from: date
    valid_to: date | None = None
    is_primary: bool = False
    group_id: uuid.UUID | None = None
    unit_scope: list[uuid.UUID] = Field(default_factory=list)
    external_name: str | None = Field(default=None, max_length=200)
    external_address: str | None = Field(default=None, max_length=400)
    expected_unit_count: int | None = Field(default=None, ge=0)
    note: str | None = None


class AssignmentPatch(_In):
    version: int
    valid_from: date | None = None
    valid_to: date | None = None
    service_scope: ServiceScope | None = None
    status: AssignmentStatus | None = None
    is_primary: bool | None = None
    group_id: uuid.UUID | None = None
    unit_scope: list[uuid.UUID] | None = None
    verification_basis: str | None = None
    note: str | None = None
    error_hint: str | None = None


class RemoteConfirmIn(_In):
    version: int
    verification_basis: str = Field(min_length=1)


class ProviderChangeIn(_In):
    version: int
    change_date: date
    new_connection_id: uuid.UUID
    new_external_number: str = Field(min_length=1, max_length=64)
    unit_scope: list[uuid.UUID] | None = None


class AssignmentOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    connection_name: str
    provider_code: str
    environment: str
    property_id: uuid.UUID
    property_number: str
    property_name: str
    property_address: str | None
    external_billing_unit_id: uuid.UUID
    external_number: str
    external_name: str | None
    expected_unit_count: int | None
    service_scope: str
    valid_from: date
    valid_to: date | None
    status: str
    origin: str
    is_primary: bool
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    verification_basis: str | None
    remote_confirmed: bool
    remote_confirmed_at: datetime | None
    group_id: uuid.UUID | None
    unit_scope: list[str]
    assigned_unit_count: int
    conflict_reason: str | None
    error_hint: str | None
    last_success_at: datetime | None
    note: str | None
    version: int
    created_at: datetime
    updated_at: datetime


async def _assignment_out(session: Any, row: MeteringPropertyAssignment) -> AssignmentOut:
    prop = await session.get(Property, row.property_id)
    unit = await session.get(MeteringExternalBillingUnit, row.external_billing_unit_id)
    conn = await session.get(MeteringConnection, row.connection_id)
    count = await session.scalar(
        select(func.count(MeteringUnitAssignment.id)).where(
            MeteringUnitAssignment.property_assignment_id == row.id,
            MeteringUnitAssignment.status != AssignmentStatus.ARCHIVED,
        )
    )
    address = None
    if prop is not None and prop.street:
        address = f"{prop.street} {prop.house_number or ''}".strip()
        if prop.postal_code or prop.city:
            address += f", {prop.postal_code or ''} {prop.city or ''}".rstrip()
    return AssignmentOut(
        id=row.id,
        connection_id=row.connection_id,
        connection_name=conn.display_name if conn else "",
        provider_code=conn.provider_code if conn else "",
        environment=conn.environment if conn else "",
        property_id=row.property_id,
        property_number=prop.number if prop else "",
        property_name=prop.name if prop else "",
        property_address=address,
        external_billing_unit_id=row.external_billing_unit_id,
        external_number=unit.external_number if unit else "",
        external_name=unit.external_name if unit else None,
        expected_unit_count=unit.expected_unit_count if unit else None,
        service_scope=row.service_scope,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        status=row.status,
        origin=row.origin,
        is_primary=row.is_primary,
        confirmed_by=row.confirmed_by,
        confirmed_at=row.confirmed_at,
        verification_basis=row.verification_basis,
        remote_confirmed=row.remote_confirmed,
        remote_confirmed_at=row.remote_confirmed_at,
        group_id=row.group_id,
        unit_scope=list(row.unit_scope or []),
        assigned_unit_count=int(count or 0),
        conflict_reason=row.conflict_reason,
        error_hint=row.error_hint,
        last_success_at=row.last_success_at,
        note=row.note,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/assignments",
    summary="Objektzuordnungen (Objektreiter und zentrale Übersicht)",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_assignments(
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
    property_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    status: AssignmentStatus | None = None,
    service_scope: ServiceScope | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    include_archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=500)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[AssignmentOut]:
    async with tenant_tx(request, principal) as session:
        query = services.assignment_query(
            property_id=property_id,
            connection_id=connection_id,
            status=status.value if status else None,
            service_scope=service_scope.value if service_scope else None,
            search=search,
            include_archived=include_archived,
        )
        rows = await paginate(session, query, response, page=page, page_size=page_size, limit=limit)
        return [await _assignment_out(session, r) for r in rows]


@router.post("/assignments", status_code=201, summary="Objektzuordnung anlegen")
async def create_assignment(
    body: AssignmentIn, request: Request, principal: TenantPrincipal = Depends(ASSIGN)
) -> AssignmentOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.create_assignment(
            session,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            connection_id=body.connection_id,
            property_id=body.property_id,
            external_number=body.external_number,
            service_scope=body.service_scope.value,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            is_primary=body.is_primary,
            group_id=body.group_id,
            unit_scope=[str(u) for u in body.unit_scope],
            external_name=body.external_name,
            external_address=body.external_address,
            expected_unit_count=body.expected_unit_count,
            note=body.note,
        )
        return await _assignment_out(session, row)


@router.get("/assignments/{assignment_id}", summary="Objektzuordnung lesen")
async def get_assignment(
    assignment_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> AssignmentOut:
    async with tenant_tx(request, principal) as session:
        return await _assignment_out(session, await services.get_assignment(session, assignment_id))


@router.patch("/assignments/{assignment_id}", summary="Objektzuordnung ändern (Versionsprüfung)")
async def patch_assignment(
    assignment_id: uuid.UUID,
    body: AssignmentPatch,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> AssignmentOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_assignment(session, assignment_id)
        changes = body.model_dump(exclude={"version"}, exclude_unset=True)
        for key in ("service_scope", "status"):
            if changes.get(key) is not None:
                changes[key] = changes[key].value
        if changes.get("unit_scope") is not None:
            changes["unit_scope"] = [str(u) for u in changes["unit_scope"]]
        row = await services.update_assignment(
            session, row, actor=principal.user_id, version=body.version, changes=changes
        )
        return await _assignment_out(session, row)


@router.post(
    "/assignments/{assignment_id}/remote-confirm", summary="Technische Bestätigung erfassen"
)
async def remote_confirm(
    assignment_id: uuid.UUID,
    body: RemoteConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> AssignmentOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_assignment(session, assignment_id)
        row = await services.confirm_remote(
            session,
            row,
            actor=principal.user_id,
            version=body.version,
            verification_basis=body.verification_basis,
        )
        return await _assignment_out(session, row)


class ProviderChangeOut(BaseModel):
    previous: AssignmentOut
    current: AssignmentOut


@router.post("/assignments/{assignment_id}/change-provider", summary="Anbieterwechsel")
async def change_provider(
    assignment_id: uuid.UUID,
    body: ProviderChangeIn,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> ProviderChangeOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await services.get_assignment(session, assignment_id)
        old, new = await services.change_provider(
            session,
            row,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            version=body.version,
            change_date=body.change_date,
            new_connection_id=body.new_connection_id,
            new_external_number=body.new_external_number,
            unit_scope=None if body.unit_scope is None else [str(u) for u in body.unit_scope],
        )
        return ProviderChangeOut(
            previous=await _assignment_out(session, old),
            current=await _assignment_out(session, new),
        )


# Unit assignments ------------------------------------------------------------------------


class UnitAssignmentIn(_In):
    unit_id: uuid.UUID
    external_unit_number: str = Field(min_length=1, max_length=64)
    valid_from: date
    valid_to: date | None = None
    billing_recipient_contact_id: uuid.UUID | None = None
    consumption_info_recipient_contact_id: uuid.UUID | None = None
    occupancy_status: OccupancyStatus = OccupancyStatus.UNCLEAR
    external_partner_ref: str | None = Field(default=None, max_length=64)
    note: str | None = None


class UnitAssignmentPatch(_In):
    version: int
    valid_from: date | None = None
    valid_to: date | None = None
    billing_recipient_contact_id: uuid.UUID | None = None
    consumption_info_recipient_contact_id: uuid.UUID | None = None
    occupancy_status: OccupancyStatus | None = None
    status: AssignmentStatus | None = None
    external_partner_ref: str | None = None
    note: str | None = None


class UnitAssignmentOut(BaseModel):
    id: uuid.UUID
    property_assignment_id: uuid.UUID
    unit_id: uuid.UUID
    unit_number: str
    unit_location: str | None
    unit_floor: str | None
    external_unit_number: str
    valid_from: date
    valid_to: date | None
    billing_recipient_contact_id: uuid.UUID | None
    consumption_info_recipient_contact_id: uuid.UUID | None
    occupancy_status: str
    status: str
    external_partner_ref: str | None
    note: str | None
    version: int


async def _unit_out(session: Any, row: MeteringUnitAssignment) -> UnitAssignmentOut:
    from mhvp.properties.models import Unit

    unit = await session.get(Unit, row.unit_id)
    return UnitAssignmentOut(
        id=row.id,
        property_assignment_id=row.property_assignment_id,
        unit_id=row.unit_id,
        unit_number=unit.number if unit else "",
        unit_location=unit.location if unit else None,
        unit_floor=unit.floor if unit else None,
        external_unit_number=row.external_unit_number,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        billing_recipient_contact_id=row.billing_recipient_contact_id,
        consumption_info_recipient_contact_id=row.consumption_info_recipient_contact_id,
        occupancy_status=row.occupancy_status,
        status=row.status,
        external_partner_ref=row.external_partner_ref,
        note=row.note,
        version=row.version,
    )


@router.get(
    "/assignments/{assignment_id}/units",
    summary="Einheitenzuordnungen einer Objektzuordnung",
    dependencies=[Depends(strict_query)],
)
async def list_unit_assignments(
    assignment_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[UnitAssignmentOut]:
    async with tenant_tx(request, principal) as session:
        await services.get_assignment(session, assignment_id)
        rows = await session.scalars(
            select(MeteringUnitAssignment)
            .where(MeteringUnitAssignment.property_assignment_id == assignment_id)
            .order_by(
                MeteringUnitAssignment.external_unit_number, MeteringUnitAssignment.valid_from
            )
        )
        return [await _unit_out(session, r) for r in rows]


@router.post(
    "/assignments/{assignment_id}/units", status_code=201, summary="Einheitenzuordnung anlegen"
)
async def create_unit_assignment(
    assignment_id: uuid.UUID,
    body: UnitAssignmentIn,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> UnitAssignmentOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        assignment = await services.get_assignment(session, assignment_id)
        row = await services.create_unit_assignment(
            session,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            property_assignment=assignment,
            unit_id=body.unit_id,
            external_unit_number=body.external_unit_number,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            billing_recipient_contact_id=body.billing_recipient_contact_id,
            consumption_info_recipient_contact_id=body.consumption_info_recipient_contact_id,
            occupancy_status=body.occupancy_status.value,
            external_partner_ref=body.external_partner_ref,
            note=body.note,
        )
        return await _unit_out(session, row)


@router.patch("/unit-assignments/{unit_assignment_id}", summary="Einheitenzuordnung ändern")
async def patch_unit_assignment(
    unit_assignment_id: uuid.UUID,
    body: UnitAssignmentPatch,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> UnitAssignmentOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await session.get(MeteringUnitAssignment, unit_assignment_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        changes = body.model_dump(exclude={"version"}, exclude_unset=True)
        for key in ("occupancy_status", "status"):
            if changes.get(key) is not None:
                changes[key] = changes[key].value
        row = await services.update_unit_assignment(
            session, row, actor=principal.user_id, version=body.version, changes=changes
        )
        return await _unit_out(session, row)


# Sync jobs -------------------------------------------------------------------------------


class SyncJobIn(_In):
    connection_id: uuid.UUID
    data_kind: DataKind
    property_ids: list[uuid.UUID] = Field(default_factory=list)
    period_from: date | None = None
    period_to: date | None = None


class SyncJobOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    data_kind: str
    scope: dict[str, Any]
    period_from: date | None
    period_to: date | None
    assignment_version: int | None
    status: str
    parts: list[dict[str, Any]]
    error_summary: str | None
    requested_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime


def _job_out(row: MeteringSyncJob) -> SyncJobOut:
    return SyncJobOut(
        id=row.id,
        connection_id=row.connection_id,
        data_kind=row.data_kind,
        scope=dict(row.scope or {}),
        period_from=row.period_from,
        period_to=row.period_to,
        assignment_version=row.assignment_version,
        status=row.status,
        parts=list(row.parts or []),
        error_summary=row.error_summary,
        requested_by=row.requested_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        last_success_at=row.last_success_at,
        created_at=row.created_at,
    )


_SYNC_JOB_LIST = ListSpec(  # GA04-05
    filters={
        "connection_id": MeteringSyncJob.connection_id,
        "property_assignment_id": MeteringSyncJob.property_assignment_id,
        "status": MeteringSyncJob.status,
        "data_kind": MeteringSyncJob.data_kind,
    },
    sort={
        "created_at": MeteringSyncJob.created_at,
        "started_at": MeteringSyncJob.started_at,
        "finished_at": MeteringSyncJob.finished_at,
    },
)


@router.get(
    "/sync-jobs",
    summary="Abrufaufträge",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_sync_jobs(
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
    connection_id: uuid.UUID | None = None,
    status: SyncStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    params: ListParams = Depends(_SYNC_JOB_LIST.dependency),
) -> list[SyncJobOut]:
    async with tenant_tx(request, principal) as session:
        query = _SYNC_JOB_LIST.apply(
            select(MeteringSyncJob), params, (MeteringSyncJob.created_at.desc(),)
        )
        if connection_id is not None:
            query = query.where(MeteringSyncJob.connection_id == connection_id)
        if status is not None:
            query = query.where(MeteringSyncJob.status == status.value)
        rows = await paginate(session, query, response, page=page, page_size=page_size, limit=limit)
        return sparse(  # type: ignore[no-any-return]
            [_job_out(r) for r in rows], params, SyncJobOut, response=response
        )


@router.post("/sync-jobs", status_code=202, summary="Jetzt abrufen (nur lesend)")
async def create_sync_job(
    body: SyncJobIn, request: Request, principal: TenantPrincipal = Depends(SYNC)
) -> SyncJobOut:
    from mhvp.metering.tasks import run_sync_job_task

    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        connection = await services.get_connection(session, body.connection_id)
        job = await services.create_sync_job(
            session,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            connection=connection,
            data_kind=body.data_kind.value,
            scope={"property_ids": [str(p) for p in body.property_ids]},
            period_from=body.period_from,
            period_to=body.period_to,
        )
        out = _job_out(job)
    run_sync_job_task.delay(str(principal.tenant_id), str(out.id))
    return out


@router.get("/sync-jobs/{job_id}", summary="Abrufauftrag lesen")
async def get_sync_job(
    job_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> SyncJobOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(MeteringSyncJob, job_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _job_out(row)


# Clearing --------------------------------------------------------------------------------


class ClearingItemOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    sync_job_id: uuid.UUID | None
    entity_type: str
    external_identifier: str
    reason: str
    payload: dict[str, Any]
    status: str
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    property_assignment_id: uuid.UUID | None
    created_at: datetime


class ClearingResolveIn(_In):
    status: ClearingStatus = ClearingStatus.RESOLVED
    note: str | None = None
    property_assignment_id: uuid.UUID | None = None


def _clearing_out(row: MeteringClearingItem) -> ClearingItemOut:
    return ClearingItemOut(
        id=row.id,
        connection_id=row.connection_id,
        sync_job_id=row.sync_job_id,
        entity_type=row.entity_type,
        external_identifier=row.external_identifier,
        reason=row.reason,
        payload=dict(row.payload or {}),
        status=row.status,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        resolution_note=row.resolution_note,
        property_assignment_id=row.property_assignment_id,
        created_at=row.created_at,
    )


@router.get(
    "/clearing-items",
    summary="Klärungsbereich",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_clearing_items(
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
    status: ClearingStatus | None = ClearingStatus.OPEN,
    connection_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ClearingItemOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MeteringClearingItem).order_by(MeteringClearingItem.created_at.desc())
        if status is not None:
            query = query.where(MeteringClearingItem.status == status.value)
        if connection_id is not None:
            query = query.where(MeteringClearingItem.connection_id == connection_id)
        rows = await paginate(session, query, response, page=page, page_size=page_size, limit=limit)
        return [_clearing_out(r) for r in rows]


@router.post("/clearing-items/{item_id}/resolve", summary="Klärungsfall abschließen")
async def resolve_clearing_item(
    item_id: uuid.UUID,
    body: ClearingResolveIn,
    request: Request,
    principal: TenantPrincipal = Depends(ASSIGN),
) -> ClearingItemOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await session.get(MeteringClearingItem, item_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.status == ClearingStatus.OPEN:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Status muss resolved oder dismissed sein."
            )
        row = await services.resolve_clearing_item(
            session,
            row,
            actor=principal.user_id,
            status=body.status.value,
            note=body.note,
            property_assignment_id=body.property_assignment_id,
        )
        return _clearing_out(row)


# Data (consumption values, billing results) ----------------------------------------------


class ConsumptionOut(BaseModel):
    id: uuid.UUID
    property_assignment_id: uuid.UUID
    unit_assignment_id: uuid.UUID | None
    period_from: date
    period_to: date
    kind: str
    unit_of_measure: str
    reading_type: str
    source: str
    version: int
    value: Decimal | None
    value_kind: str
    external_ref: str | None


class BillingResultOut(BaseModel):
    id: uuid.UUID
    property_assignment_id: uuid.UUID
    unit_assignment_id: uuid.UUID | None
    period_from: date
    period_to: date
    amount: Decimal
    currency: str
    version: int
    external_document_ref: str
    document_id: uuid.UUID | None
    review_status: str


@router.get(
    "/assignments/{assignment_id}/consumption",
    summary="Verbrauchswerte (zeitlich filterbar)",
    dependencies=[Depends(strict_query)],
)
async def list_consumption(
    assignment_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    period_from: date | None = None,
    period_to: date | None = None,
) -> list[ConsumptionOut]:
    async with tenant_tx(request, principal) as session:
        await services.get_assignment(session, assignment_id)
        query = select(MeteringConsumptionValue).where(
            MeteringConsumptionValue.property_assignment_id == assignment_id
        )
        if period_from is not None:
            query = query.where(MeteringConsumptionValue.period_to >= period_from)
        if period_to is not None:
            query = query.where(MeteringConsumptionValue.period_from <= period_to)
        rows = await session.scalars(
            query.order_by(MeteringConsumptionValue.period_from, MeteringConsumptionValue.version)
        )
        return [ConsumptionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get(
    "/assignments/{assignment_id}/billing-results",
    summary="Abrechnungsergebnisse (prüfbare Fremddaten)",
    dependencies=[Depends(strict_query)],
)
async def list_billing_results(
    assignment_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    period_from: date | None = None,
    period_to: date | None = None,
) -> list[BillingResultOut]:
    async with tenant_tx(request, principal) as session:
        await services.get_assignment(session, assignment_id)
        query = select(MeteringBillingResult).where(
            MeteringBillingResult.property_assignment_id == assignment_id
        )
        if period_from is not None:
            query = query.where(MeteringBillingResult.period_to >= period_from)
        if period_to is not None:
            query = query.where(MeteringBillingResult.period_from <= period_to)
        rows = await session.scalars(
            query.order_by(MeteringBillingResult.period_from, MeteringBillingResult.version)
        )
        return [BillingResultOut.model_validate(r, from_attributes=True) for r in rows]


# CSV import / export ---------------------------------------------------------------------


class MeteringImportRowOut(BaseModel):
    line: int
    status: str
    messages: list[str]
    values: dict[str, str]


class ImportPreviewOut(BaseModel):
    ok_count: int
    error_count: int
    duplicate_count: int
    rows: list[MeteringImportRowOut]
    created_ids: list[uuid.UUID] = Field(default_factory=list)


def _preview_out(preview: csv_io.Preview, created: list[uuid.UUID]) -> ImportPreviewOut:
    return ImportPreviewOut(
        ok_count=preview.ok_count,
        error_count=preview.error_count,
        duplicate_count=preview.duplicate_count,
        rows=[
            MeteringImportRowOut(line=r.line, status=r.status, messages=r.messages, values=r.values)
            for r in preview.rows
        ],
        created_ids=created,
    )


HEIWAKO_MAX_FILE_BYTES = 20 * 1024 * 1024


async def _read_csv(file: UploadFile) -> str:
    raw = await read_limited(file, 2_000_000, detail="Datei größer als 2 MB.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ProblemError(
        ErrorCodes.VALIDATION, detail="Datei ist nicht als UTF-8 oder CP1252 lesbar."
    )


@router.get("/assignments-import/template", summary="CSV-Vorlage für Zuordnungen")
async def import_template(principal: TenantPrincipal = Depends(READ)) -> PlainTextResponse:
    return PlainTextResponse(
        csv_io.template(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(
                "attachment", "messdienstleister-zuordnungen-vorlage.csv"
            )
        },
    )


@router.post("/assignments-import/preview", summary="CSV-Import prüfen (keine Änderung)")
async def import_preview(
    request: Request,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(ASSIGN),
) -> ImportPreviewOut:
    content = await _read_csv(file)
    async with tenant_tx(request, principal) as session:
        preview = await csv_io.preview(session, principal.tenant_id, content)
        return _preview_out(preview, [])


@router.post("/assignments-import/apply", summary="CSV-Import übernehmen (bewusst ausgelöst)")
async def import_apply(
    request: Request,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(ASSIGN),
) -> ImportPreviewOut:
    content = await _read_csv(file)
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        preview, created = await csv_io.apply(
            session, tenant_id=principal.tenant_id, actor=principal.user_id, content=content
        )
        return _preview_out(preview, [c.id for c in created])


@router.get("/assignments-export", summary="CSV-Export der Zuordnungen (Nummern als Text)")
async def export_assignments(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    property_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> PlainTextResponse:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            services.assignment_query(
                property_id=property_id,
                connection_id=connection_id,
                include_archived=include_archived,
            )
        )
        data = []
        for row in rows:
            out = await _assignment_out(session, row)
            data.append(
                {
                    "property_number": out.property_number,
                    "connection_name": out.connection_name,
                    "external_number": out.external_number,
                    "service_scope": out.service_scope,
                    "valid_from": out.valid_from.isoformat(),
                    "valid_to": out.valid_to.isoformat() if out.valid_to else "",
                    "external_name": out.external_name or "",
                    "external_address": "",
                    "expected_unit_count": ""
                    if out.expected_unit_count is None
                    else str(out.expected_unit_count),
                    "note": out.note or "",
                    "status": out.status,
                    "assignment_id": str(out.id),
                }
            )
    return PlainTextResponse(
        csv_io.export(data),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(
                "attachment", "messdienstleister-zuordnungen.csv"
            )
        },
    )


# bved 3.10 file exchange (M40-02): preview only, nothing is stored ------------------------


class HeiwakoFileOut(BaseModel):
    name: str
    kind: str | None
    record_counts: dict[str, int]
    errors: list[str]
    undocumented_record_types: list[str]


class HeiwakoBillingResultOut(BaseModel):
    external_billing_unit: str
    external_unit_number: str | None
    period_from: date
    period_to: date
    amount: Decimal
    currency: str
    external_document_ref: str
    cost_type_key: str | None
    balance_gross: Decimal | None
    prepayment_gross: Decimal | None


class HeiwakoUserOut(BaseModel):
    external_billing_unit: str | None
    external_unit_number: str | None
    client_ref: str | None
    name: str | None
    occupancy_from: date | None
    occupancy_to: date | None
    vacancy_flag: int | None


class HeiwakoPreviewOut(BaseModel):
    adapter: str
    spec_version: str
    files: list[HeiwakoFileOut]
    billing_results: list[HeiwakoBillingResultOut]
    users: list[HeiwakoUserOut]
    property_count: int
    reference_count: int
    image_count: int
    errors: list[str]
    stored: bool = False


@router.post(
    "/connections/{connection_id}/heiwako-import/preview",
    summary="bved 3.10 Austauschdateien prüfen (keine Speicherung)",
)
async def heiwako_import_preview(
    connection_id: uuid.UUID,
    request: Request,
    files: list[UploadFile] = File(),
    period_from: date | None = None,
    principal: TenantPrincipal = Depends(SYNC),
) -> HeiwakoPreviewOut:
    """Parses DTA310, DTM310, DTD310 and DTE898 files of a file exchange provider (Techem,
    Brunata Minol, BRUNATA-METRONA) and reports the records. Nothing is stored: the transfer
    into billing results waits for an operator supplied example file (M40-02)."""
    from mhvp.metering.adapters_heiwako import HeiwakoFileAdapter

    if len(files) > 10:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Höchstens 10 Dateien je Aufruf.")
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        connection = await services.get_connection(session, connection_id)
    adapter = services._adapter(connection)
    if not isinstance(adapter, HeiwakoFileAdapter):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Anbieter dieser Verbindung nutzt keinen Dateiaustausch nach bved 3.10.",
        )
    contents: dict[str, bytes] = {}
    for upload in files:
        raw = await read_limited(upload, HEIWAKO_MAX_FILE_BYTES)
        contents[upload.filename or f"datei-{len(contents) + 1}"] = raw
    currency = str(connection.config.get("currency") or "EUR")
    result = adapter.import_files(contents, period_from=period_from, default_currency=currency)
    return HeiwakoPreviewOut(
        adapter=adapter.code,
        spec_version=adapter.spec_version,
        files=[HeiwakoFileOut(**f) for f in result.files],
        billing_results=[
            HeiwakoBillingResultOut(
                external_billing_unit=b.external_billing_unit,
                external_unit_number=b.external_unit_number,
                period_from=b.period_from,
                period_to=b.period_to,
                amount=b.amount,
                currency=b.currency,
                external_document_ref=b.external_document_ref,
                cost_type_key=b.payload.get("cost_type_key"),
                balance_gross=_decimal_or_none(b.payload.get("balance_gross")),
                prepayment_gross=_decimal_or_none(b.payload.get("prepayment_gross")),
            )
            for b in result.billing_results
        ],
        users=[
            HeiwakoUserOut(
                external_billing_unit=m.header.provider_property_number,
                external_unit_number=m.header.provider_unit_number,
                client_ref=m.client_ref,
                name=m.user_names[0],
                occupancy_from=m.occupancy_from,
                occupancy_to=m.occupancy_to,
                vacancy_flag=m.vacancy_flag,
            )
            for m in result.users
        ],
        property_count=len(result.properties),
        reference_count=len(result.references),
        image_count=len(result.images),
        errors=result.errors,
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


# Controlled write workflows (section 12) ---------------------------------------------------


async def _transmission_writer(principal: TenantPrincipal = Depends(READ)) -> TenantPrincipal:
    """Dependency: any of the transmission write rights before the body is parsed, so a
    reader gets 403 and never a body validation error (D50 matrix)."""
    if not any(principal.has(p) for p in set(transmissions.KIND_PERMISSION.values())):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing transmission right.")
    return principal


def _require_kind_permission(principal: TenantPrincipal, kind: str) -> None:
    permission = transmissions.KIND_PERMISSION[kind]
    if not principal.has(permission):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message=f"Missing permission {permission}."
        )


class TransmissionCheckIn(_In):
    assignment_id: uuid.UUID
    kind: TransmissionKind
    period_from: date | None = None
    period_to: date | None = None
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Billing Input: ancillary_invoices, heating_system_invoices, energy_sources, "
        "allocations (je externer Nutzeinheit), currency und expectedvat als Ersatz, wenn keine "
        "Anbietervorlage geladen werden kann. Ordnungsbegriffsabgleich (billing_unit_setup): "
        "customer_number als Ersatz für die erste customer_reference der Verbindung.",
    )


class TransmissionStepIn(_In):
    version: int
    fingerprint: str = Field(min_length=64, max_length=64)
    acknowledge_warnings: bool = False


class TransmissionOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    property_assignment_id: uuid.UUID
    kind: str
    period_from: date | None
    period_to: date | None
    status: str
    fingerprint: str
    assignment_version: int
    validation: dict[str, Any]
    diff: dict[str, Any]
    summary: dict[str, Any]
    payload: dict[str, Any]
    released_by: uuid.UUID | None
    released_at: datetime | None
    warnings_acknowledged: bool
    ordered_by: uuid.UUID | None
    ordered_at: datetime | None
    provider_transaction_id: str | None
    provider_response: dict[str, Any]
    log: list[dict[str, Any]]
    version: int
    created_at: datetime


def _transmission_out(row: MeteringTransmission) -> TransmissionOut:
    return TransmissionOut(
        id=row.id,
        connection_id=row.connection_id,
        property_assignment_id=row.property_assignment_id,
        kind=row.kind,
        period_from=row.period_from,
        period_to=row.period_to,
        status=row.status,
        fingerprint=row.fingerprint,
        assignment_version=row.assignment_version,
        validation=row.validation,
        diff=row.diff,
        summary=transmissions.summarize(row),
        payload=row.payload,
        released_by=row.released_by,
        released_at=row.released_at,
        warnings_acknowledged=row.warnings_acknowledged,
        ordered_by=row.ordered_by,
        ordered_at=row.ordered_at,
        provider_transaction_id=row.provider_transaction_id,
        provider_response=row.provider_response,
        log=row.log,
        version=row.version,
        created_at=row.created_at,
    )


@router.get(
    "/transmissions",
    summary="Übermittlungen (Rollen, Abrechnungsdaten, Ordnungsbegriffsabgleich)",
    dependencies=[Depends(strict_query)],
)
async def list_transmissions(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    assignment_id: uuid.UUID | None = None,
    connection_id: uuid.UUID | None = None,
    kind: TransmissionKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TransmissionOut]:
    async with tenant_tx(request, principal) as session:
        rows = await transmissions.list_for(
            session,
            assignment_id=assignment_id,
            connection_id=connection_id,
            kind=kind.value if kind else None,
            limit=limit,
        )
        return [_transmission_out(r) for r in rows]


@router.get("/transmissions/{transmission_id}", summary="Übermittlung lesen")
async def get_transmission(
    transmission_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> TransmissionOut:
    async with tenant_tx(request, principal) as session:
        return _transmission_out(await transmissions.get(session, transmission_id))


@router.post(
    "/transmissions/check",
    status_code=201,
    summary="Daten prüfen (keine Beauftragung, beim Anbieter nur VALIDATE)",
)
async def check_transmission(
    body: TransmissionCheckIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> TransmissionOut:
    _require_kind_permission(principal, body.kind.value)
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        assignment = await services.get_assignment(session, body.assignment_id)
        row = await transmissions.check(
            session,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            assignment=assignment,
            kind=body.kind.value,
            period_from=body.period_from,
            period_to=body.period_to,
            inputs=body.inputs,
        )
        return _transmission_out(row)


@router.post("/transmissions/{transmission_id}/release", summary="Geprüfte Daten freigeben")
async def release_transmission(
    transmission_id: uuid.UUID,
    body: TransmissionStepIn,
    request: Request,
    principal: TenantPrincipal = Depends(_transmission_writer),
) -> TransmissionOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await transmissions.get(session, transmission_id)
        _require_kind_permission(principal, row.kind)
        row = await transmissions.release(
            session,
            row,
            actor=principal.user_id,
            version=body.version,
            given_fingerprint=body.fingerprint,
            acknowledge_warnings=body.acknowledge_warnings,
        )
        return _transmission_out(row)


@router.post(
    "/transmissions/{transmission_id}/order",
    summary="Verbindlich beauftragen (Abrechnung) beziehungsweise Rollen übermitteln",
)
async def order_transmission(
    transmission_id: uuid.UUID,
    body: TransmissionStepIn,
    request: Request,
    principal: TenantPrincipal = Depends(_transmission_writer),
) -> TransmissionOut:
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await transmissions.get(session, transmission_id)
        _require_kind_permission(principal, row.kind)
        row = await transmissions.order(
            session,
            row,
            actor=principal.user_id,
            version=body.version,
            given_fingerprint=body.fingerprint,
        )
        return _transmission_out(row)


@router.post(
    "/transmissions/{transmission_id}/poll",
    summary="Bearbeitungsstatus beim Anbieter abrufen (Ordnungsbegriffsabgleich, nur lesend)",
)
async def poll_transmission(
    transmission_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(_transmission_writer),
) -> TransmissionOut:
    """Fetches the asynchronous processing status (Q8). ``waiting_provider`` stays until the
    provider reports ``COMPLETED``; the fetched result is stored on the external billing unit
    and confirms the assignment technically when every sent unit was matched."""
    async with tenant_tx(request, principal) as session:
        await services.ensure_module_enabled(session, principal.tenant_id)
        row = await transmissions.get(session, transmission_id)
        _require_kind_permission(principal, row.kind)
        row = await transmissions.poll(session, row, actor=principal.user_id)
        return _transmission_out(row)
