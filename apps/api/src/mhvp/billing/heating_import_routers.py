"""Heating cost import of the metering service (M17-09): create, edit, user mapping, CSV with
explicit column map, check (sums, CO2, duplicates) and feed into a draft operating cost
statement. Included into ``heating_routers.router``; issuing stays behind G3."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.billing import heating_import
from mhvp.billing.models import HeatingCostImport, Statement
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_property_allowed, session_allowed_property_ids
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(tags=["Abrechnung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
P = "/billing/heating-cost-imports"


class _HciIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeatingImportCo2In(_HciIn):
    mode: str = Field(default="apply", pattern="^(apply|not_applicable)$")
    building_kind: str = Field(
        default="unknown", pattern="^(residential|non_residential|mixed|self_supply|unknown)$"
    )
    costs: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    emissions_kg: Decimal | None = Field(default=None, ge=0)
    reference_area_m2: Decimal | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=2000)


class HeatingImportHeaderIn(_HciIn):
    property_id: uuid.UUID
    document_id: uuid.UUID | None = None
    provider_contact_id: uuid.UUID | None = None
    provider_name: str = Field(min_length=2, max_length=200)
    period_from: date
    period_to: date
    document_total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    co2: HeatingImportCo2In = Field(default_factory=HeatingImportCo2In)


class HeatingImportMappingEntryIn(_HciIn):
    unit_id: uuid.UUID
    contract_id: uuid.UUID | None = None


class HeatingImportMappingIn(_HciIn):
    mapping: dict[str, HeatingImportMappingEntryIn] = Field(max_length=5000)


class HeatingImportRowIn(_HciIn):
    user_number: str = Field(min_length=1, max_length=64)
    heating_base: Decimal = Field(ge=0, decimal_places=2)
    heating_consumption: Decimal = Field(ge=0, decimal_places=2)
    hot_water_base: Decimal = Field(ge=0, decimal_places=2)
    hot_water_consumption: Decimal = Field(ge=0, decimal_places=2)
    co2_landlord: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    co2_tenant: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)


class HeatingImportRowsIn(_HciIn):
    rows: list[HeatingImportRowIn] = Field(max_length=5000)


class HeatingImportCsvIn(_HciIn):
    content: str = Field(min_length=1, max_length=2_000_000)
    delimiter: str = Field(default=";", pattern="^(;|,|\t)$")
    decimal_comma: bool = True
    column_map: dict[str, str]
    file_name: str | None = Field(default=None, max_length=200)


class HeatingImportCheckIn(_HciIn):
    duplicate_ack_reason: str | None = Field(default=None, min_length=10, max_length=2000)


class HeatingImportApplyIn(_HciIn):
    statement_id: uuid.UUID


def _out(row: HeatingCostImport) -> dict[str, Any]:
    return {
        "id": row.id,
        "property_id": row.property_id,
        "statement_id": row.statement_id,
        "document_id": row.document_id,
        "provider_contact_id": row.provider_contact_id,
        "provider_name": row.provider_name,
        "period_from": row.period_from,
        "period_to": row.period_to,
        "document_total": row.document_total,
        "co2": row.co2,
        "user_mapping": row.user_mapping,
        "rows": row.rows,
        "csv_meta": row.csv_meta,
        "status": row.status,
        "check_result": row.check_result,
        "duplicate_ack_reason": row.duplicate_ack_reason,
        "checked_by": row.checked_by,
        "checked_at": row.checked_at,
        "applied_item_id": row.applied_item_id,
        "applied_at": row.applied_at,
    }


def _co2(body: HeatingImportCo2In) -> dict[str, Any]:
    return {
        k: (str(v) if isinstance(v, Decimal) else v)
        for k, v in body.model_dump().items()
        if v is not None
    }


async def _load(session: Any, import_id: uuid.UUID) -> HeatingCostImport:
    row: HeatingCostImport | None = await session.get(
        HeatingCostImport, import_id, with_for_update=True
    )
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_property_allowed(session, row.property_id)
    return row


async def _refs(session: Any, body: HeatingImportHeaderIn) -> None:
    from mhvp.contacts.models import Contact
    from mhvp.documents.models import Document
    from mhvp.properties.models import Property

    heating_import.period_ok(body.period_from, body.period_to)
    ensure_session_property_allowed(session, body.property_id)
    if await session.get(Property, body.property_id) is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if body.document_id and await session.get(Document, body.document_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument nicht gefunden.")
    if body.provider_contact_id and await session.get(Contact, body.provider_contact_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Messdienst (Kontakt) nicht gefunden.")


@router.get(P, summary="Messdienstimporte Heizkosten", dependencies=[Depends(strict_query)])
async def list_heating_cost_imports(
    request: Request,
    property_id: uuid.UUID | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        q = select(HeatingCostImport).order_by(HeatingCostImport.period_from.desc())
        if property_id is not None:
            q = q.where(HeatingCostImport.property_id == property_id)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            q = q.where(HeatingCostImport.property_id.in_(allowed))
        return [_out(r) for r in (await session.scalars(q)).all()]


@router.post(P, status_code=201, summary="Messdienstimport Heizkosten anlegen (Entwurf)")
async def create_heating_cost_import(
    body: HeatingImportHeaderIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _refs(session, body)
        row = HeatingCostImport(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=body.property_id,
            document_id=body.document_id,
            provider_contact_id=body.provider_contact_id,
            provider_name=body.provider_name.strip(),
            period_from=body.period_from,
            period_to=body.period_to,
            document_total=body.document_total,
            co2=_co2(body.co2),
            user_mapping={},
            rows=[],
            status="draft",
        )
        session.add(row)
        await session.flush()
        return _out(row)


@router.get(f"{P}/{{import_id}}", summary="Messdienstimport Heizkosten")
async def get_heating_cost_import(
    import_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _load(session, import_id))


@router.put(f"{P}/{{import_id}}", summary="Messdienstimport: Kopfdaten ändern")
async def update_heating_cost_import(
    import_id: uuid.UUID,
    body: HeatingImportHeaderIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        if body.property_id != row.property_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Objekt ist nicht änderbar.")
        await _refs(session, body)
        heating_import.reset(row)
        row.document_id = body.document_id
        row.provider_contact_id = body.provider_contact_id
        row.provider_name = body.provider_name.strip()
        row.period_from = body.period_from
        row.period_to = body.period_to
        row.document_total = body.document_total
        row.co2 = _co2(body.co2)
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.put(f"{P}/{{import_id}}/mapping", summary="Messdienstimport: Nutzernummern zuordnen")
async def put_heating_cost_import_mapping(
    import_id: uuid.UUID,
    body: HeatingImportMappingIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        heating_import.reset(row)
        merged = dict(row.user_mapping)
        for number, entry in body.mapping.items():
            merged[number.strip()] = {
                "unit_id": str(entry.unit_id),
                "contract_id": None if entry.contract_id is None else str(entry.contract_id),
            }
        row.user_mapping = merged
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.put(f"{P}/{{import_id}}/rows", summary="Messdienstimport: Kostenzeilen manuell erfassen")
async def put_heating_cost_import_rows(
    import_id: uuid.UUID,
    body: HeatingImportRowsIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        heating_import.reset(row)
        row.rows = heating_import.normalise_rows([r.model_dump() for r in body.rows])
        row.csv_meta = None
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post(f"{P}/{{import_id}}/csv", summary="Messdienstimport: CSV mit Spaltenzuordnung")
async def import_heating_cost_csv(
    import_id: uuid.UUID,
    body: HeatingImportCsvIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        heating_import.reset(row)
        row.rows = heating_import.parse_csv(
            body.content,
            delimiter=body.delimiter,
            decimal_comma=body.decimal_comma,
            column_map=body.column_map,
        )
        row.csv_meta = {
            "file_name": body.file_name,
            "delimiter": body.delimiter,
            "decimal_comma": body.decimal_comma,
            "column_map": body.column_map,
            "row_count": len(row.rows),
        }
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post(f"{P}/{{import_id}}/check", summary="Messdienstimport prüfen (Summen, CO2, Dubletten)")
async def check_heating_cost_import(
    import_id: uuid.UUID,
    body: HeatingImportCheckIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        await heating_import.check(session, row, principal.user_id, body.duplicate_ack_reason)
        return _out(row)


@router.post(f"{P}/{{import_id}}/apply", summary="Geprüften Messdienstimport übernehmen")
async def apply_heating_cost_import(
    import_id: uuid.UUID,
    body: HeatingImportApplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _load(session, import_id)
        st: Statement | None = await session.get(Statement, body.statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ensure_session_property_allowed(session, st.property_id)
        item = await heating_import.apply(session, st, row, principal.user_id)
        return _out(row) | {"item": {"id": item.id, "amount": item.amount, "label": item.label}}
