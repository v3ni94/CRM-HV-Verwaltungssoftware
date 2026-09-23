"""Workspace endpoints (/api/v1/workspace, M9)."""

import datetime as dt
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select, update

from mhvp.core.auth.principal import TenantPrincipal, get_principal, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace import services
from mhvp.workspace.models import CalendarEntry, Notification, SavedFilter

router = APIRouter(prefix="/workspace", tags=["Arbeitsplatz"])

FILTER_RESOURCES = ("contacts", "properties", "units", "contracts", "documents", "imports")
MAX_BULK = 500
MAX_RANGE_DAYS = 400


async def member(request: Request) -> TenantPrincipal:
    """Any user acting inside a tenant; entries are always scoped to that user."""
    principal = await get_principal(request)
    if principal.tenant_id is None or principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Tenant user required.")
    return TenantPrincipal(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        permissions=principal.permissions,
        roles=principal.roles,
    )


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hit(BaseModel):
    entity_type: str
    id: uuid.UUID
    title: str
    subtitle: str | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class EntryIn(_In):
    title: str = Field(min_length=1, max_length=300)
    starts_on: date
    ends_on: date | None = None
    all_day: bool = True
    shared: bool = False
    notes: str | None = Field(default=None, max_length=4000)
    property_id: uuid.UUID | None = None


class CalendarItem(BaseModel):
    kind: str
    title: str
    date: dt.date
    ends_on: dt.date | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    editable: bool = False


class FilterIn(_In):
    resource: str = Field(pattern="^(" + "|".join(FILTER_RESOURCES) + ")$")
    name: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class FilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resource: str
    name: str
    params: dict[str, Any]


class BulkIn(_In):
    action: str = Field(pattern="^(contacts.add_tag|contacts.remove_tag|maintenance.done)$")
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)
    tag: str | None = Field(default=None, min_length=1, max_length=63)


def _need(principal: TenantPrincipal, permission: str) -> None:
    if not principal.has(permission):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message=f"Missing {permission}.")


# Dashboard -----------------------------------------------------------------------------


@router.get("/dashboard", summary="Kennzahlen und Aufgaben der Startseite")
async def dashboard(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> dict[str, Any]:
    from mhvp.ai.models import AiProposal, Decision
    from mhvp.contacts.models import Contact
    from mhvp.contracts.models import Contract
    from mhvp.documents.models import Document
    from mhvp.properties.models import MaintenanceItem, Property, Unit

    today = services.local_today()
    async with tenant_tx(request, principal) as session:

        async def count(model: Any, *where: Any) -> int:
            query = select(func.count()).select_from(model).where(*where)
            return int(await session.scalar(query) or 0)

        tiles: dict[str, int] = {}
        if principal.has("properties:read"):
            tiles["properties"] = await count(Property)
            tiles["units"] = await count(Unit)
            tiles["maintenance_due_30d"] = await count(
                MaintenanceItem,
                MaintenanceItem.status == "open",
                MaintenanceItem.due_date <= today + timedelta(days=30),
            )
        if principal.has("contacts:read"):
            tiles["contacts"] = await count(Contact, Contact.deleted_at.is_(None))
        if principal.has("contracts:read"):
            tiles["active_contracts"] = await count(
                Contract, or_(Contract.end_date.is_(None), Contract.end_date >= today)
            )
            tiles["contracts_ending_90d"] = await count(
                Contract, Contract.end_date.between(today, today + timedelta(days=90))
            )
        if principal.has("documents:read"):
            tiles["documents"] = await count(Document)
        if principal.has("ai:read"):
            tiles["open_ai_proposals"] = await count(
                AiProposal, AiProposal.decision == Decision.PENDING
            )
        tiles["unread_notifications"] = await count(
            Notification, Notification.user_id == principal.user_id, Notification.read_at.is_(None)
        )
        # Includes the last 30 days so that overdue open items stay visible.
        upcoming = await services.derived_dates(
            session,
            today - timedelta(days=30),
            today + timedelta(days=30),
            contracts=principal.has("contracts:read"),
            properties=principal.has("properties:read"),
        )
        upcoming.sort(key=lambda i: i["date"])
        # Money figures stay out until the ledger is released (G1).
        return {"tiles": tiles, "upcoming": upcoming[:10], "accounting": "locked_until_g1"}


# Global search -------------------------------------------------------------------------


@router.get("/search", summary="Globale Suche über alle Bereiche (Strg+K)")
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=8, ge=1, le=25),
    principal: TenantPrincipal = Depends(member),
) -> list[Hit]:
    from mhvp.contacts.models import Contact
    from mhvp.contacts.services import search_filter
    from mhvp.contracts.models import Contract
    from mhvp.documents.models import Document
    from mhvp.properties.models import Property, Unit

    like = f"%{q.strip()}%"
    hits: list[Hit] = []
    async with tenant_tx(request, principal) as session:
        if principal.has("contacts:read"):
            sim = func.similarity(Contact.search_text, q.lower())
            query = search_filter(select(Contact).where(Contact.deleted_at.is_(None)), q)
            for c in (await session.scalars(query.order_by(sim.desc()).limit(limit))).all():
                hits.append(Hit(entity_type="contact", id=c.id, title=c.display_name))
        if principal.has("properties:read"):
            props = await session.scalars(
                select(Property)
                .where(
                    or_(
                        Property.number.ilike(like),
                        Property.name.ilike(like),
                        Property.street.ilike(like),
                        Property.city.ilike(like),
                    )
                )
                .order_by(Property.number)
                .limit(limit)
            )
            for p in props.all():
                address = " ".join(x for x in (p.street, p.house_number, p.city) if x)
                hits.append(
                    Hit(
                        entity_type="property",
                        id=p.id,
                        title=f"{p.number} {p.name}",
                        subtitle=address or None,
                    )
                )
            units = await session.execute(
                select(Unit, Property.number)
                .join(Property, Property.id == Unit.property_id)
                .where(or_(Unit.number.ilike(like), Unit.label.ilike(like)))
                .order_by(Property.number, Unit.number)
                .limit(limit)
            )
            for u, number in units.all():
                hits.append(
                    Hit(
                        entity_type="unit",
                        id=u.id,
                        title=f"{number}/{u.number}",
                        subtitle=u.label,
                    )
                )
        if principal.has("contracts:read"):
            contracts = await session.scalars(
                select(Contract).where(Contract.number.ilike(like)).limit(limit)
            )
            for k in contracts.all():
                hits.append(
                    Hit(
                        entity_type="contract",
                        id=k.id,
                        title=f"Vertrag {k.number}",
                        subtitle=k.kind.value,
                    )
                )
        if principal.has("documents:read"):
            docs = await session.scalars(
                select(Document)
                .where(Document.search_vector.op("@@")(func.plainto_tsquery("german", q)))
                .limit(limit)
            )
            for d in docs.all():
                hits.append(
                    Hit(entity_type="document", id=d.id, title=d.title, subtitle=d.filename)
                )
    return hits


# Notifications -------------------------------------------------------------------------


@router.get("/notifications", summary="Eigene Benachrichtigungen")
async def notifications(
    request: Request,
    unread: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(member),
) -> list[NotificationOut]:
    async with tenant_tx(request, principal) as session:
        query = select(Notification).where(Notification.user_id == principal.user_id)
        if unread:
            query = query.where(Notification.read_at.is_(None))
        rows = await session.scalars(query.order_by(Notification.created_at.desc()).limit(limit))
        return [NotificationOut.model_validate(n) for n in rows.all()]


@router.post("/notifications/read", status_code=204, summary="Als gelesen markieren")
async def mark_read(
    request: Request,
    ids: list[uuid.UUID] | None = None,
    principal: TenantPrincipal = Depends(member),
) -> None:
    """Without ids all unread notifications of the user are marked as read."""
    async with tenant_tx(request, principal) as session:
        query = update(Notification).where(
            Notification.user_id == principal.user_id, Notification.read_at.is_(None)
        )
        if ids:
            query = query.where(Notification.id.in_(ids))
        await session.execute(query.values(read_at=datetime.now(UTC)))


# Calendar ------------------------------------------------------------------------------


@router.get("/calendar", summary="Kalender: eigene Termine, geteilte Termine, Fristen aus Daten")
async def calendar(
    request: Request,
    start: date,
    end: date,
    principal: TenantPrincipal = Depends(member),
) -> list[CalendarItem]:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig (höchstens 400 Tage).")
    async with tenant_tx(request, principal) as session:
        entries = await session.scalars(
            select(CalendarEntry).where(
                or_(CalendarEntry.owner_user_id == principal.user_id, CalendarEntry.shared),
                CalendarEntry.starts_on <= end,
                func.coalesce(CalendarEntry.ends_on, CalendarEntry.starts_on) >= start,
            )
        )
        items = [
            CalendarItem(
                kind="appointment",
                title=e.title,
                date=e.starts_on,
                ends_on=e.ends_on,
                entity_type="calendar_entry",
                entity_id=e.id,
                property_id=e.property_id,
                editable=e.owner_user_id == principal.user_id,
            )
            for e in entries.all()
        ]
        derived = await services.derived_dates(
            session,
            start,
            end,
            contracts=principal.has("contracts:read"),
            properties=principal.has("properties:read"),
        )
        items += [CalendarItem(**d) for d in derived]
        return sorted(items, key=lambda i: (i.date, i.title))


@router.post("/calendar", status_code=201, summary="Termin anlegen")
async def create_entry(
    body: EntryIn, request: Request, principal: TenantPrincipal = Depends(member)
) -> CalendarItem:
    if body.ends_on and body.ends_on < body.starts_on:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ende liegt vor dem Beginn.")
    async with tenant_tx(request, principal) as session:
        entry = CalendarEntry(
            tenant_id=principal.tenant_id,
            owner_user_id=principal.user_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(entry)
        await session.flush()
        return CalendarItem(
            kind="appointment",
            title=entry.title,
            date=entry.starts_on,
            ends_on=entry.ends_on,
            entity_type="calendar_entry",
            entity_id=entry.id,
            property_id=entry.property_id,
            editable=True,
        )


@router.delete("/calendar/{entry_id}", status_code=204, summary="Eigenen Termin löschen")
async def delete_entry(
    entry_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(member)
) -> None:
    async with tenant_tx(request, principal) as session:
        result = await session.execute(
            delete(CalendarEntry).where(
                CalendarEntry.id == entry_id, CalendarEntry.owner_user_id == principal.user_id
            )
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


# Saved list filters --------------------------------------------------------------------


@router.get("/filters", summary="Gespeicherte Listenfilter")
async def list_filters(
    request: Request, resource: str | None = None, principal: TenantPrincipal = Depends(member)
) -> list[FilterOut]:
    async with tenant_tx(request, principal) as session:
        query = select(SavedFilter).where(SavedFilter.user_id == principal.user_id)
        if resource:
            query = query.where(SavedFilter.resource == resource)
        rows = await session.scalars(query.order_by(SavedFilter.resource, SavedFilter.name))
        return [FilterOut.model_validate(f) for f in rows.all()]


@router.put("/filters", summary="Listenfilter speichern (gleicher Name ersetzt)")
async def save_filter(
    body: FilterIn, request: Request, principal: TenantPrincipal = Depends(member)
) -> FilterOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(SavedFilter).where(
                SavedFilter.user_id == principal.user_id,
                SavedFilter.resource == body.resource,
                SavedFilter.name == body.name,
            )
        )
        if row is None:
            row = SavedFilter(
                tenant_id=principal.tenant_id, user_id=principal.user_id, **body.model_dump()
            )
            session.add(row)
        else:
            row.params = body.params
        await session.flush()
        return FilterOut.model_validate(row)


@router.delete("/filters/{filter_id}", status_code=204, summary="Listenfilter löschen")
async def delete_filter(
    filter_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(member)
) -> None:
    async with tenant_tx(request, principal) as session:
        result = await session.execute(
            delete(SavedFilter).where(
                SavedFilter.id == filter_id, SavedFilter.user_id == principal.user_id
            )
        )
        if not result.rowcount:  # type: ignore[attr-defined]
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


# Bulk actions --------------------------------------------------------------------------


@router.post("/bulk", summary="Massenaktion (Stammdaten, keine Geldwirkung)")
async def bulk(
    body: BulkIn, request: Request, principal: TenantPrincipal = Depends(member)
) -> dict[str, Any]:
    """All or nothing: unknown ids abort the whole action (rule 0.1.4 for bulk actions)."""
    from mhvp.contacts.models import Contact, ContactTag, ContactTagLink
    from mhvp.properties.models import MaintenanceItem

    ids = sorted(set(body.ids))
    async with tenant_tx(request, principal) as session:
        if body.action.startswith("contacts."):
            _need(principal, "contacts:update")
            if not body.tag:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Schlagwort fehlt.")
            found = set(
                await session.scalars(
                    select(Contact.id).where(Contact.id.in_(ids), Contact.deleted_at.is_(None))
                )
            )
            if len(found) != len(ids):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Kontakte.")
            tag = await session.scalar(select(ContactTag).where(ContactTag.name == body.tag))
            changed = 0
            if body.action == "contacts.add_tag":
                if tag is None:
                    tag = ContactTag(tenant_id=principal.tenant_id, name=body.tag)
                    session.add(tag)
                    await session.flush()
                linked = set(
                    await session.scalars(
                        select(ContactTagLink.contact_id).where(
                            ContactTagLink.tag_id == tag.id, ContactTagLink.contact_id.in_(ids)
                        )
                    )
                )
                for cid in ids:
                    if cid not in linked:
                        session.add(
                            ContactTagLink(
                                tenant_id=principal.tenant_id, contact_id=cid, tag_id=tag.id
                            )
                        )
                        changed += 1
            elif tag is not None:
                result = await session.execute(
                    delete(ContactTagLink).where(
                        ContactTagLink.tag_id == tag.id, ContactTagLink.contact_id.in_(ids)
                    )
                )
                changed = int(result.rowcount or 0)  # type: ignore[attr-defined]
        else:
            _need(principal, "properties:update")
            items = (
                await session.scalars(select(MaintenanceItem).where(MaintenanceItem.id.in_(ids)))
            ).all()
            if len(items) != len(ids):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Wartungen.")
            now = datetime.now(UTC)
            changed = 0
            for item in items:
                if item.status != "done":
                    item.status, item.done_at, item.updated_by = "done", now, principal.user_id
                    changed += 1
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="workspace.bulk_action",
            entity_type="bulk",
            entity_id=None,
            actor_user_id=principal.user_id,
            payload={"action": body.action, "count": len(ids), "changed": changed},
        )
        await session.flush()
        return {"action": body.action, "requested": len(ids), "changed": changed}
