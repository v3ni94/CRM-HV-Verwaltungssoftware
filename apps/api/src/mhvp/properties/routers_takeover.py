"""Checklist of the property takeover (10.2 step 6, M7-01).

One row per category (legitimation, bank authority, insurance, service contracts, meters,
reserves, open items of the previous management) with a status. Permissions equal the
property routes (``properties:read`` / ``properties:update``).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import TAKEOVER_CATEGORIES, Property, PropertyTakeoverItem
from mhvp.properties.routers import READ, UPDATE, _get

# M2-02/S16-02: path ids outside the property assignment answer 404.
router = APIRouter(tags=["Objekte"], dependencies=[Depends(property_path_guard)])

LABELS = {
    "legitimation": "Legitimationsunterlagen",
    "bank_authority": "Bankvollmachten",
    "insurance": "Versicherungen",
    "service_contracts": "Dienstleisterverträge",
    "meters": "Zähler",
    "reserves": "Rücklagenstände",
    "open_items": "Offene Posten der Vorverwaltung",
}


class TakeoverItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    label: str
    status: str
    note: str | None
    due_date: date | None
    document_id: uuid.UUID | None
    ticket_id: uuid.UUID | None = None


class TakeoverChecklistOut(BaseModel):
    property_id: uuid.UUID
    items: list[TakeoverItemOut]
    open_count: int
    complete: bool


class TakeoverTicketsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[str] | None = Field(
        default=None,
        max_length=len(TAKEOVER_CATEGORIES),
        description="nur diese Punkte; ohne Angabe alle fehlenden Punkte",
    )


class TakeoverTicketOut(BaseModel):
    category: str
    label: str
    ticket_id: uuid.UUID
    ticket_number: int


class TakeoverTicketsOut(BaseModel):
    created: list[TakeoverTicketOut]
    skipped: list[str]
    checklist: TakeoverChecklistOut


class TakeoverItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern="^(open|requested|received|not_applicable)$")
    note: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    document_id: uuid.UUID | None = None


def _out(row: PropertyTakeoverItem) -> TakeoverItemOut:
    return TakeoverItemOut(
        id=row.id,
        category=row.category,
        label=LABELS[row.category],
        status=row.status,
        note=row.note,
        due_date=row.due_date,
        document_id=row.document_id,
        ticket_id=row.ticket_id,
    )


async def _checklist(session: object, property_id: uuid.UUID) -> TakeoverChecklistOut:
    rows = (
        await session.scalars(  # type: ignore[attr-defined]
            select(PropertyTakeoverItem).where(PropertyTakeoverItem.property_id == property_id)
        )
    ).all()
    order = {c: i for i, c in enumerate(TAKEOVER_CATEGORIES)}
    items = [_out(r) for r in sorted(rows, key=lambda r: order[r.category])]
    open_count = sum(1 for i in items if i.status in ("open", "requested"))
    return TakeoverChecklistOut(
        property_id=property_id,
        items=items,
        open_count=open_count,
        complete=bool(items) and open_count == 0,
    )


@router.get(
    "/properties/{property_id}/takeover-checklist",
    summary="Checkliste Objektübernahme lesen",
)
async def get_checklist(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> TakeoverChecklistOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        return await _checklist(session, property_id)


@router.post(
    "/properties/{property_id}/takeover-checklist",
    summary="Checkliste Objektübernahme anlegen (ergänzt fehlende Punkte, idempotent)",
)
async def init_checklist(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> TakeoverChecklistOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        existing = set(
            await session.scalars(
                select(PropertyTakeoverItem.category).where(
                    PropertyTakeoverItem.property_id == property_id
                )
            )
        )
        for category in TAKEOVER_CATEGORIES:
            if category not in existing:
                session.add(
                    PropertyTakeoverItem(
                        tenant_id=principal.tenant_id,
                        created_by=principal.user_id,
                        property_id=property_id,
                        category=category,
                        status="open",
                    )
                )
        await session.flush()
        return await _checklist(session, property_id)


@router.patch(
    "/properties/{property_id}/takeover-checklist/{category}",
    summary="Punkt der Checkliste Objektübernahme ändern",
)
async def patch_item(
    property_id: uuid.UUID,
    category: str,
    body: TakeoverItemPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TakeoverItemOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        row = await session.scalar(
            select(PropertyTakeoverItem).where(
                PropertyTakeoverItem.property_id == property_id,
                PropertyTakeoverItem.category == category,
            )
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if data.get("status", "x") is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Status darf nicht leer sein.")
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_takeover_item.updated",
            entity_type="property_takeover_item",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"category": category, "fields": sorted(data)},
        )
        return _out(row)


@router.post(
    "/properties/{property_id}/takeover-checklist/tickets",
    status_code=201,
    summary="Aufgaben (Tickets) für fehlende Punkte der Checkliste anlegen (idempotent)",
)
async def create_tickets(
    property_id: uuid.UUID,
    body: TakeoverTicketsIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TakeoverTicketsOut:
    """One ticket per open or requested point that has none yet (M7-01, R03). Points that are
    received or not applicable, and points that already carry a ticket, are skipped, so a
    second call creates nothing. The tickets are internal (not released for portal users)."""
    from mhvp.ai import takeover_defaults
    from mhvp.tickets.models import Ticket
    from mhvp.tickets.routers import TicketIn, create_ticket_in_session
    from mhvp.tickets.status import assign_ticket

    if "tickets:create" not in principal.permissions:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="missing ['tickets:create']")
    unknown = set(body.categories or []) - set(TAKEOVER_CATEGORIES)
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Kategorie: {sorted(unknown)[0]}."
        )
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        rows = (
            await session.scalars(
                select(PropertyTakeoverItem)
                .where(PropertyTakeoverItem.property_id == property_id)
                .with_for_update()
            )
        ).all()
        order = {c: i for i, c in enumerate(TAKEOVER_CATEGORIES)}
        created: list[TakeoverTicketOut] = []
        skipped: list[str] = []
        defaults = await takeover_defaults.load(session)  # V06-01, empty means no assignment
        for row in sorted(rows, key=lambda r: order[r.category]):
            if body.categories is not None and row.category not in body.categories:
                continue
            if row.status not in ("open", "requested") or row.ticket_id is not None:
                skipped.append(row.category)
                continue
            label = LABELS[row.category]
            lines = [f"Punkt der Checkliste Objektübernahme: {label} (Status {row.status})."]
            if row.note:
                lines.append(f"Notiz: {row.note}")
            ticket = await create_ticket_in_session(
                session,
                TicketIn(
                    title=f"Objektübernahme {prop.number}: {label}"[:300],
                    property_id=property_id,
                    internal_description="\n".join(lines),
                    due_on=row.due_date,
                ),
                principal,
            )
            row.ticket_id = ticket["id"]
            row.updated_by = principal.user_id
            if defaults.team_id or defaults.assignee_user_id:
                new_ticket = await session.get(Ticket, ticket["id"])
                if new_ticket is not None:
                    if defaults.team_id and new_ticket.team_id is None:
                        new_ticket.team_id = defaults.team_id
                    if defaults.assignee_user_id:
                        await assign_ticket(
                            session,
                            new_ticket,
                            defaults.assignee_user_id,
                            principal.user_id,
                            reason="Standard Objektübernahme",
                        )
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="property_takeover_item.ticket_created",
                entity_type="property_takeover_item",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"category": row.category, "ticket_id": str(ticket["id"])},
            )
            created.append(
                TakeoverTicketOut(
                    category=row.category,
                    label=label,
                    ticket_id=ticket["id"],
                    ticket_number=ticket["number"],
                )
            )
        return TakeoverTicketsOut(
            created=created, skipped=skipped, checklist=await _checklist(session, property_id)
        )
