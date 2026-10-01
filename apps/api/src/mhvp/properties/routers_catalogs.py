"""Catalogue and custom field endpoints (/api/v1/catalogs, /api/v1/custom-fields).

Section 4.11 and annex B (P1 AP4): every annex B list is a catalogue per tenant with
system entries. Reading needs ``properties:read`` (the lists feed select boxes everywhere),
maintenance needs ``tenant_settings:update``. System entries can be relabelled, reordered
and deactivated but not deleted (rows reference their codes); tenant entries can be
deleted. Custom field definitions carry the attributes of 4.11; entity, key and field type
are immutable after creation because stored values depend on them. Every change is
recorded as a domain event (audit).
"""

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties import schemas as s
from mhvp.properties.catalogs import ANNEX_B_CATALOGS
from mhvp.properties.models import CatalogEntry, CustomFieldDefinition

router = APIRouter(tags=["Kataloge"])
READ = require_permission("properties:read")
MANAGE = require_permission("tenant_settings:update")
_CATALOG_NAME = r"^[a-z][a-z0-9_]{0,62}$"
_ENTRY_FIELDS = ("code", "label", "sort_order", "active", "is_system")
_FIELD_FIELDS = (
    "entity_type",
    "key",
    "label",
    "field_type",
    "required",
    "group",
    "valid_for_management_types",
    "valid_for_contract_kinds",
    "uniqueness",
    "visible_in_main",
    "min_value",
    "max_value",
    "default_value",
    "options",
    "description",
    "sort_order",
)


def _snapshot(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in fields:
        value = getattr(row, name)
        out[name] = str(value) if hasattr(value, "quantize") else value
    return out


async def _unique(session: Any, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ProblemError(ErrorCodes.CONFLICT, detail=message) from None


def _check_catalog_name(catalog: str) -> None:
    if not re.match(_CATALOG_NAME, catalog):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ungültiger Katalogname.")


async def _entry(session: AsyncSession, catalog: str, entry_id: uuid.UUID) -> CatalogEntry:
    row = await session.scalar(
        select(CatalogEntry).where(CatalogEntry.id == entry_id, CatalogEntry.catalog == catalog)
    )
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Katalogeintrag nicht gefunden.")
    return row


async def _field(session: AsyncSession, field_id: uuid.UUID) -> CustomFieldDefinition:
    row = await session.get(CustomFieldDefinition, field_id)
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Zusatzfeld nicht gefunden.")
    return row


# Catalogues ---------------------------------------------------------------------------------


@router.get("/catalogs", summary="Kataloge", dependencies=[Depends(strict_query)])
async def list_catalogs(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.CatalogSummaryOut]:
    """All catalogues of the tenant with counts; annex B catalogues without entries (after a
    tenant deactivated nothing they still exist) appear with their seeded rows."""
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(
                    CatalogEntry.catalog,
                    func.count(),
                    func.count().filter(CatalogEntry.active.is_(True)),
                    func.count().filter(CatalogEntry.is_system.is_(True)),
                )
                .group_by(CatalogEntry.catalog)
                .order_by(CatalogEntry.catalog)
            )
        ).all()
        known = {r[0] for r in rows}
        out = [
            s.CatalogSummaryOut(catalog=r[0], entries=r[1], active=r[2], system=r[3]) for r in rows
        ]
        out.extend(
            s.CatalogSummaryOut(catalog=name, entries=0, active=0, system=0)
            for name in ANNEX_B_CATALOGS
            if name not in known
        )
        return sorted(out, key=lambda c: c.catalog)


@router.get("/catalogs/{catalog}", summary="Katalog", dependencies=[Depends(strict_query)])
async def list_catalog(
    catalog: str,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    include_inactive: bool = False,
) -> list[s.CatalogEntryOut]:
    _check_catalog_name(catalog)
    async with tenant_tx(request, principal) as session:
        stmt = select(CatalogEntry).where(CatalogEntry.catalog == catalog)
        if not include_inactive:
            stmt = stmt.where(CatalogEntry.active.is_(True))
        rows = (
            await session.scalars(stmt.order_by(CatalogEntry.sort_order, CatalogEntry.code))
        ).all()
        return [s.CatalogEntryOut.model_validate(c) for c in rows]


@router.post("/catalogs/{catalog}", status_code=201, summary="Katalogeintrag anlegen")
async def add_catalog_entry(
    catalog: str,
    body: s.CatalogEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> s.CatalogEntryOut:
    _check_catalog_name(catalog)
    async with tenant_tx(request, principal) as session:
        row = CatalogEntry(tenant_id=principal.tenant_id, catalog=catalog, **body.model_dump())
        session.add(row)
        await _unique(session, f"Eintrag {body.code} existiert bereits.")
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="catalog_entry.created",
            entity_type="catalog_entry",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"catalog": catalog, "code": row.code},
        )
        return s.CatalogEntryOut.model_validate(row)


@router.patch("/catalogs/{catalog}/{entry_id}", summary="Katalogeintrag ändern")
async def update_catalog_entry(
    catalog: str,
    entry_id: uuid.UUID,
    body: s.CatalogEntryPatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> s.CatalogEntryOut:
    _check_catalog_name(catalog)
    async with tenant_tx(request, principal) as session:
        row = await _entry(session, catalog, entry_id)
        before = _snapshot(row, _ENTRY_FIELDS)
        for name, value in body.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, name, value)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="catalog_entry.updated",
            entity_type="catalog_entry",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"catalog": catalog, "code": row.code},
            changes=diff(before, _snapshot(row, _ENTRY_FIELDS)),
        )
        await session.refresh(row)
        return s.CatalogEntryOut.model_validate(row)


@router.delete("/catalogs/{catalog}/{entry_id}", status_code=204, summary="Katalogeintrag löschen")
async def delete_catalog_entry(
    catalog: str,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> Response:
    """Tenant entries only. System entries (annex B) are deactivated instead; rows may
    reference their codes."""
    _check_catalog_name(catalog)
    async with tenant_tx(request, principal) as session:
        row = await _entry(session, catalog, entry_id)
        if row.is_system:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Systemeinträge können nur deaktiviert, nicht gelöscht werden.",
            )
        payload = {"catalog": catalog, "code": row.code}
        await session.delete(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="catalog_entry.deleted",
            entity_type="catalog_entry",
            entity_id=entry_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    return Response(status_code=204)


# Custom fields ------------------------------------------------------------------------------


@router.get("/custom-fields", summary="Zusatzfelder", dependencies=[Depends(strict_query)])
async def list_custom_fields(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    entity_type: str | None = None,
) -> list[s.CustomFieldOut]:
    async with tenant_tx(request, principal) as session:
        stmt = select(CustomFieldDefinition)
        if entity_type:
            stmt = stmt.where(CustomFieldDefinition.entity_type == entity_type)
        rows = (
            await session.scalars(
                stmt.order_by(
                    CustomFieldDefinition.entity_type,
                    CustomFieldDefinition.sort_order,
                    CustomFieldDefinition.key,
                )
            )
        ).all()
        return [s.CustomFieldOut.model_validate(c) for c in rows]


@router.post("/custom-fields", status_code=201, summary="Zusatzfeld definieren")
async def add_custom_field(
    body: s.CustomFieldIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> s.CustomFieldOut:
    async with tenant_tx(request, principal) as session:
        row = CustomFieldDefinition(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(row)
        await _unique(session, f"Zusatzfeld {body.key} existiert bereits.")
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="custom_field.created",
            entity_type="custom_field_definition",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"entity_type": row.entity_type, "key": row.key},
        )
        return s.CustomFieldOut.model_validate(row)


@router.patch("/custom-fields/{field_id}", summary="Zusatzfeld ändern")
async def update_custom_field(
    field_id: uuid.UUID,
    body: s.CustomFieldPatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> s.CustomFieldOut:
    async with tenant_tx(request, principal) as session:
        row = await _field(session, field_id)
        before = _snapshot(row, _FIELD_FIELDS)
        patch = body.model_dump(exclude_unset=True)
        for name, value in patch.items():
            setattr(row, name, value)
        if row.field_type == "choice" and not row.options:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Einzelauswahl benötigt Auswahlwerte.")
        if (
            row.min_value is not None
            and row.max_value is not None
            and row.max_value < row.min_value
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Maximum darf nicht kleiner als Minimum sein."
            )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="custom_field.updated",
            entity_type="custom_field_definition",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"entity_type": row.entity_type, "key": row.key},
            changes=diff(before, _snapshot(row, _FIELD_FIELDS)),
        )
        await session.refresh(row)
        return s.CustomFieldOut.model_validate(row)


@router.delete("/custom-fields/{field_id}", status_code=204, summary="Zusatzfeld löschen")
async def delete_custom_field(
    field_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> Response:
    """Removes the definition. Values already stored under the key stay in the JSONB of the
    rows (no data loss); a later full update of such a row must omit the key."""
    async with tenant_tx(request, principal) as session:
        row = await _field(session, field_id)
        payload = {"entity_type": row.entity_type, "key": row.key}
        await session.delete(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="custom_field.deleted",
            entity_type="custom_field_definition",
            entity_id=field_id,
            actor_user_id=principal.user_id,
            payload=payload,
        )
    return Response(status_code=204)
