"""Endpoints of the deadline type catalogue, user created deadline entries, the notice period
orientation and property checklists (rule WS-01, ``/api/v1/workspace/...``).

Permissions reuse existing scopes: the catalogue is read by every tenant member and
maintained with ``tenant_settings:update``; entries follow the ticket scopes (read, create,
update); the notice period needs ``contracts:read``; checklists follow the property scopes.
Every computed date carries ``verify=True`` and is orientation only (rule 0.1.3, M1-09).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Membership, MembershipStatus, User
from mhvp.workspace import deadlines, jobs
from mhvp.workspace.models import DeadlineEntry, DeadlineType, PropertyChecklist
from mhvp.workspace.routers import member

router = APIRouter(prefix="/workspace", tags=["Arbeitsplatz"])

TRIGGER_PATTERN = "^(" + "|".join(deadlines.TRIGGERS) + ")$"
SOURCE_PATTERN = "^(" + "|".join(deadlines.SOURCE_TYPES) + ")$"
CHECKLIST_PATTERN = "^(" + "|".join(deadlines.CHECKLIST_TEMPLATES) + ")$"
SOURCE_ROUTES: dict[str, str] = {
    "ticket": "/tickets",
    "contract": "/vertraege",
    "unit": "/vermietung/einheit",
    "property": "/objekte",
    "rent_increase_case": "/vermietung/mieterhoehung",
}
VERIFY_NOTE = (
    "Orientierung, zu verifizieren. Die Dauer stammt aus dem Fristtypkatalog des Mandanten "
    "beziehungsweise der Eingabe, nicht aus einer rechtlichen Regel (M1-09)."
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Catalogue ------------------------------------------------------------------------------


class DeadlineTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    trigger: str
    duration_months: int | None
    duration_days: int | None
    responsible_role: str | None
    source_note: str | None
    is_system: bool
    is_active: bool
    updated_at: datetime


class DeadlineTypeIn(_In):
    code: str = Field(min_length=2, max_length=63, pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=200)
    trigger: str = Field(pattern=TRIGGER_PATTERN)
    duration_months: int | None = Field(default=None, ge=0, le=120)
    duration_days: int | None = Field(default=None, ge=0, le=3660)
    responsible_role: str | None = Field(default=None, max_length=63)
    source_note: str | None = Field(default=None, max_length=2000)


class DeadlineTypePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    trigger: str | None = Field(default=None, pattern=TRIGGER_PATTERN)
    # Explicit nulls clear the duration: the field is sent as null, missing keeps the value.
    duration_months: int | None = Field(default=None, ge=0, le=120)
    duration_days: int | None = Field(default=None, ge=0, le=3660)
    responsible_role: str | None = Field(default=None, max_length=63)
    source_note: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


@router.get("/deadline-types", summary="Fristtypen des Mandanten (WS-01, Dauer zu verifizieren)")
async def list_deadline_types(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> list[DeadlineTypeOut]:
    async with tenant_tx(request, principal) as session:
        await deadlines.ensure_system_types(session, principal.tenant_id, principal.user_id)
        rows = (
            await session.scalars(
                select(DeadlineType).order_by(DeadlineType.name, DeadlineType.code)
            )
        ).all()
        return [DeadlineTypeOut.model_validate(r) for r in rows]


@router.post("/deadline-types", status_code=201, summary="Fristtyp anlegen")
async def create_deadline_type(
    body: DeadlineTypeIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> DeadlineTypeOut:
    async with tenant_tx(request, principal) as session:
        await deadlines.ensure_system_types(session, principal.tenant_id, principal.user_id)
        exists = await session.scalar(select(DeadlineType.id).where(DeadlineType.code == body.code))
        if exists is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Code ist bereits vergeben.")
        row = DeadlineType(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return DeadlineTypeOut.model_validate(row)


@router.patch("/deadline-types/{type_id}", summary="Fristtyp ändern")
async def update_deadline_type(
    type_id: uuid.UUID,
    body: DeadlineTypePatch,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> DeadlineTypeOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(DeadlineType, type_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_by = principal.user_id
        await session.flush()
        await session.refresh(row)
        return DeadlineTypeOut.model_validate(row)


# Assignable users -------------------------------------------------------------------------


class AssignableUserOut(BaseModel):
    user_id: uuid.UUID
    display_name: str


@router.get("/assignable-users", summary="Aktive Mitglieder als Verantwortliche (ES-10)")
async def assignable_users(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> list[AssignableUserOut]:
    """Names only, for the responsible person select; no roles or contact data."""
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(User.id, User.display_name)
                .join(Membership, Membership.user_id == User.id)
                # membership is a platform table without RLS: filter the tenant explicitly.
                .where(
                    Membership.tenant_id == principal.tenant_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
                .order_by(User.display_name)
            )
        ).all()
    return [AssignableUserOut(user_id=r.id, display_name=r.display_name) for r in rows]


# Entries ----------------------------------------------------------------------------------


class DeadlineEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type_id: uuid.UUID
    type_name: str = ""
    title: str
    trigger_on: date
    due_on: date
    due_computed: bool
    verify: bool = True
    responsible_user_id: uuid.UUID | None
    responsible_name: str | None = None
    source_type: str
    source_id: uuid.UUID
    href: str | None = None
    property_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    note: str | None
    status: str
    done_at: datetime | None
    done_by: uuid.UUID | None
    created_at: datetime
    # ES-10: "ES-10" when no responsible person is set (advisory, never blocking).
    warnings: list[str] = Field(default_factory=list)


class DeadlineEntryIn(_In):
    type_id: uuid.UUID
    source_type: str = Field(pattern=SOURCE_PATTERN)
    source_id: uuid.UUID
    trigger_on: date
    # Entered due date; when missing it is computed from the type's duration.
    due_on: date | None = None
    responsible_user_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=4000)


class DeadlineComputeOut(BaseModel):
    type_id: uuid.UUID
    trigger_on: date
    due_on: date | None
    duration_months: int | None
    duration_days: int | None
    verify: bool = True
    note: str = VERIFY_NOTE


async def _entry_out(session: Any, entry: DeadlineEntry) -> DeadlineEntryOut:
    out = DeadlineEntryOut.model_validate(entry)
    out.type_name = (
        await session.scalar(select(DeadlineType.name).where(DeadlineType.id == entry.type_id))
    ) or ""
    if entry.responsible_user_id is not None:
        out.responsible_name = await session.scalar(
            select(User.display_name).where(User.id == entry.responsible_user_id)
        )
    else:
        out.warnings = ["ES-10"]
    route = SOURCE_ROUTES.get(entry.source_type)
    out.href = f"{route}/{entry.source_id}" if route else None
    return out


@router.get("/deadline-entries", summary="Eigene Fristen (WS-01)")
async def list_deadline_entries(
    request: Request,
    source_type: str | None = Query(default=None, pattern=SOURCE_PATTERN),
    source_id: uuid.UUID | None = None,
    status: str = Query(default="open", pattern="^(open|done|all)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(require_permission("tickets:read")),
) -> list[DeadlineEntryOut]:
    query = select(DeadlineEntry)
    if source_type is not None:
        query = query.where(DeadlineEntry.source_type == source_type)
    if source_id is not None:
        query = query.where(DeadlineEntry.source_id == source_id)
    if status != "all":
        query = query.where(DeadlineEntry.status == status)
    query = query.order_by(DeadlineEntry.due_on, DeadlineEntry.title).limit(limit)
    async with tenant_tx(request, principal) as session:
        rows = (await session.scalars(query)).all()
        return [await _entry_out(session, r) for r in rows]


@router.get(
    "/deadline-entries/compute", summary="Fälligkeit aus Fristtyp und Auslöser (Orientierung)"
)
async def compute_deadline(
    request: Request,
    type_id: uuid.UUID,
    trigger_on: date,
    principal: TenantPrincipal = Depends(require_permission("tickets:read")),
) -> DeadlineComputeOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(DeadlineType, type_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return DeadlineComputeOut(
        type_id=row.id,
        trigger_on=trigger_on,
        due_on=deadlines.compute_due(trigger_on, row.duration_months, row.duration_days),
        duration_months=row.duration_months,
        duration_days=row.duration_days,
    )


@router.post(
    "/deadline-entries",
    status_code=201,
    summary="Frist aus Ticket, Vertrag, Einheit oder Objekt anlegen",
)
async def create_deadline_entry(
    body: DeadlineEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tickets:create")),
) -> DeadlineEntryOut:
    async with tenant_tx(request, principal) as session:
        kind = await session.get(DeadlineType, body.type_id)
        if kind is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if not kind.is_active:
            raise ProblemError(ErrorCodes.DEADLINE_TYPE_INACTIVE)
        due_on = body.due_on
        computed = False
        if due_on is None:
            due_on = deadlines.compute_due(
                body.trigger_on, kind.duration_months, kind.duration_days
            )
            if due_on is None:
                raise ProblemError(ErrorCodes.DEADLINE_DURATION_MISSING)
            computed = True
        source = await deadlines.resolve_source(session, body.source_type, body.source_id)
        if body.responsible_user_id is not None:
            active = await session.scalar(
                select(Membership.id).where(
                    Membership.tenant_id == principal.tenant_id,
                    Membership.user_id == body.responsible_user_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
            if active is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Verantwortliche Person ist kein aktives Mitglied.",
                )
        entry = DeadlineEntry(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            type_id=kind.id,
            title=(body.title or f"{kind.name} {source.reference}")[:300],
            trigger_on=body.trigger_on,
            due_on=due_on,
            due_computed=computed,
            responsible_user_id=body.responsible_user_id,
            source_type=body.source_type,
            source_id=body.source_id,
            property_id=source.property_id,
            unit_id=source.unit_id,
            contract_id=source.contract_id,
            ticket_id=source.ticket_id,
            note=body.note,
            status="open",
        )
        session.add(entry)
        await session.flush()
        settings_row = await jobs.job_settings(session, principal.tenant_id)
        await deadlines.materialize(
            session,
            entry,
            kind.name,
            jobs.lead_days_for(deadlines.CUSTOM_KIND, settings_row.deadline_lead_days),
        )
        return await _entry_out(session, entry)


@router.post("/deadline-entries/{entry_id}/done", summary="Frist als erledigt markieren")
async def finish_deadline_entry(
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tickets:update")),
) -> DeadlineEntryOut:
    async with tenant_tx(request, principal) as session:
        entry = await session.get(DeadlineEntry, entry_id, with_for_update=True)
        if entry is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if entry.status != "done":
            entry.status = "done"
            entry.done_at = datetime.now(UTC)
            entry.done_by = principal.user_id
            entry.updated_by = principal.user_id
            await deadlines.close_mirror(session, entry)
            await session.refresh(entry)
        return await _entry_out(session, entry)


# Notice period (orientation) ----------------------------------------------------------------


class NoticePeriodOut(BaseModel):
    termination_on: date
    months: int
    days: int
    to_month_end: bool
    end_on: date
    # End date of the contract when ``contract_id`` was given, for the comparison hint.
    contract_end_date: date | None = None
    # True when the entered contract end lies on or after the computed end, False when it lies
    # before it, None without a contract end. Advisory only.
    contract_end_covers: bool | None = None
    verify: bool = True
    note: str = (
        "Orientierung, zu verifizieren. Die Kündigungsfrist stammt aus dem Vertrag oder der "
        "Eingabe, nicht aus einer rechtlichen Regel; die Prüfung blockiert nichts (M1-09)."
    )


@router.get("/notice-period", summary="Kündigungsfrist als Orientierung (zu verifizieren)")
async def notice_period(
    request: Request,
    termination_on: date,
    months: int = Query(default=0, ge=0, le=120),
    days: int = Query(default=0, ge=0, le=3660),
    to_month_end: bool = False,
    contract_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(require_permission("contracts:read")),
) -> NoticePeriodOut:
    """The contract model carries no notice period field today (ASSUMPTIONS), so the values
    are entered; a contract id only adds its end date for the comparison hint."""
    end_on = deadlines.notice_period_end(termination_on, months, days, to_month_end=to_month_end)
    contract_end: date | None = None
    if contract_id is not None:
        from mhvp.contracts.models import Contract

        async with tenant_tx(request, principal) as session:
            contract = await session.get(Contract, contract_id)
            if contract is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            contract_end = contract.end_date
    return NoticePeriodOut(
        termination_on=termination_on,
        months=months,
        days=days,
        to_month_end=to_month_end,
        end_on=end_on,
        contract_end_date=contract_end,
        contract_end_covers=None if contract_end is None else contract_end >= end_on,
    )


# Property checklists --------------------------------------------------------------------------


class PropertyChecklistItemOut(BaseModel):
    code: str
    label: str
    done_at: datetime | None = None
    done_by: uuid.UUID | None = None
    done_by_name: str | None = None


class PropertyChecklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    property_id: uuid.UUID
    kind: str
    status: str
    items: list[PropertyChecklistItemOut]
    note: str | None
    done_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PropertyChecklistIn(_In):
    property_id: uuid.UUID
    kind: str = Field(default="manager_change", pattern=CHECKLIST_PATTERN)
    note: str | None = Field(default=None, max_length=4000)


class PropertyChecklistItemIn(_In):
    done: bool


@router.get("/checklists", summary="Checklisten eines Objekts (Verwalterwechsel)")
async def list_checklists(
    request: Request,
    property_id: uuid.UUID,
    principal: TenantPrincipal = Depends(require_permission("properties:read")),
) -> list[PropertyChecklistOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PropertyChecklist)
                .where(PropertyChecklist.property_id == property_id)
                .order_by(PropertyChecklist.created_at.desc())
            )
        ).all()
        return [PropertyChecklistOut.model_validate(r) for r in rows]


@router.get("/checklists/templates", summary="Vorlagen der Checklisten")
async def checklist_templates(
    principal: TenantPrincipal = Depends(member),
) -> dict[str, list[PropertyChecklistItemOut]]:
    return {
        kind: [PropertyChecklistItemOut(code=c, label=label) for c, label in items]
        for kind, items in deadlines.CHECKLIST_TEMPLATES.items()
    }


@router.post("/checklists", status_code=201, summary="Checkliste für ein Objekt starten")
async def start_checklist(
    body: PropertyChecklistIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("properties:update")),
) -> PropertyChecklistOut:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        if await session.get(Property, body.property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        open_row = await session.scalar(
            select(PropertyChecklist.id).where(
                PropertyChecklist.property_id == body.property_id,
                PropertyChecklist.kind == body.kind,
                PropertyChecklist.status == "open",
            )
        )
        if open_row is not None:
            raise ProblemError(ErrorCodes.CHECKLIST_ALREADY_OPEN)
        row = PropertyChecklist(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=body.property_id,
            kind=body.kind,
            status="open",
            items=deadlines.checklist_items(body.kind),
            note=body.note,
        )
        session.add(row)
        await session.flush()
        return PropertyChecklistOut.model_validate(row)


@router.post("/checklists/{checklist_id}/items/{code}", summary="Schritt abhaken oder zurücksetzen")
async def tick_checklist_item(
    checklist_id: uuid.UUID,
    code: str,
    body: PropertyChecklistItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("properties:update")),
) -> PropertyChecklistOut:
    """Records date and user of the tick; when every step is done the checklist closes,
    resetting a step reopens it."""
    async with tenant_tx(request, principal) as session:
        row = await session.get(PropertyChecklist, checklist_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        items = [dict(i) for i in row.items]
        target = next((i for i in items if i.get("code") == code), None)
        if target is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannter Schritt.")
        if body.done:
            name = await session.scalar(
                select(User.display_name).where(User.id == principal.user_id)
            )
            target["done_at"] = datetime.now(UTC).isoformat()
            target["done_by"] = str(principal.user_id)
            target["done_by_name"] = name
        else:
            target["done_at"] = target["done_by"] = target["done_by_name"] = None
        row.items = items
        all_done = all(i.get("done_at") for i in items)
        row.status = "done" if all_done else "open"
        row.done_at = datetime.now(UTC) if all_done else None
        row.updated_by = principal.user_id
        await session.flush()
        await session.refresh(row)
        return PropertyChecklistOut.model_validate(row)
