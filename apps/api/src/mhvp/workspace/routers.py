"""Workspace endpoints (/api/v1/workspace, M9)."""

import datetime as dt
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    ColumnElement,
    cast,
    delete,
    func,
    literal,
    null,
    or_,
    select,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import gcal, gmail
from mhvp.communication.models import Mailbox, MailboxUser
from mhvp.core.auth.principal import TenantPrincipal, get_principal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace import jobs, links, services
from mhvp.workspace import ticket_analytics as ticket_analytics_module
from mhvp.workspace.models import (
    CalendarEntry,
    CalendarEvent,
    Notification,
    NotificationPreference,
    SavedFilter,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["Arbeitsplatz"])

FILTER_RESOURCES = (
    "contacts",
    "properties",
    "units",
    "contracts",
    "documents",
    "imports",
    "tickets",
    # M9-03: bank work list and invoice list.
    "bank_transactions",
    "invoices",
)
MAX_BULK = 500
MAX_RANGE_DAYS = 400
STATS_READ = require_permission("tickets:read")
STATS_RANGES = ("day", "week", "month", "quarter", "year")
STATS_RECENT_LIMIT = 10


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
        is_platform_admin=principal.is_platform_admin,
        platform_access_reason=principal.platform_access_reason,
        # A37 and M2-02/S16-02: the scopes of the membership travel with the principal.
        legal_entity_ids=principal.legal_entity_ids,
        property_ids=principal.property_ids,
    )


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hit(BaseModel):
    """Search hit. ``parent_id`` carries the context a jump needs (property of a building,
    ledger of a posting); the web app builds the route from it."""

    entity_type: str
    id: uuid.UUID
    title: str
    subtitle: str | None = None
    parent_id: uuid.UUID | None = None


class NotificationOut(BaseModel):
    """``target_type``/``target_id`` name the subject of the notification; ``href`` is the
    route to it in the CRM, derived on read (``workspace.links``). ``entity_type`` and
    ``entity_id`` carry the same values for existing clients."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    href: str | None = None
    read_at: datetime | None
    created_at: datetime


async def notification_out(
    session: AsyncSession, rows: list[Notification], *, portal: bool = False
) -> list[NotificationOut]:
    """Serialise notifications with their derived deep link (CRM or portal routes)."""
    dates, properties = await links.resolve_hints(session, rows)
    out: list[NotificationOut] = []
    for n in rows:
        item = NotificationOut.model_validate(n)
        item.target_type = n.entity_type
        item.target_id = n.entity_id
        item.href = links.target_href(
            n.entity_type,
            n.entity_id,
            portal=portal,
            appointment_date=dates.get(n.entity_id) if n.entity_id else None,
            property_id=properties.get(n.entity_id) if n.entity_id else None,
        )
        out.append(item)
    return out


class RecurrenceIn(_In):
    """Recurrence of a manual entry: weekly, monthly or yearly with an end date; the
    occurrences are expanded on read (``jobs.expand_occurrences``), never stored."""

    frequency: str = Field(pattern="^(weekly|monthly|yearly)$")
    interval: int = Field(default=1, ge=1, le=52)
    until: date


class CalendarEntryIn(_In):
    title: str = Field(min_length=1, max_length=300)
    starts_on: date
    ends_on: date | None = None
    all_day: bool = True
    shared: bool = False
    notes: str | None = Field(default=None, max_length=4000)
    property_id: uuid.UUID | None = None
    # Google Calendar (M23-02): time of day for non ganztägige Termine and the target calendar.
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target: str = Field(default="internal", pattern="^(internal|default|own)$")
    # M23-02 bidirectional: origin link, location and prospective attendees. Attendees are
    # stored on calendar_event but never sent to Google here (see rule M23-05); they are sent
    # only via the separate "Einladung senden" action after staff confirmation.
    location: str | None = Field(default=None, max_length=500)
    attendees: list[dict[str, str]] = Field(default_factory=list)
    source_type: str = Field(default="manual", pattern="^(manual|ticket|handover)$")
    source_id: uuid.UUID | None = None
    # Internal entries only (B.30): reminder codes and an optional recurrence rule.
    reminders: list[str] = Field(default_factory=list, max_length=8)
    recurrence: RecurrenceIn | None = None

    @field_validator("reminders")
    @classmethod
    def _known_reminders(cls, value: list[str]) -> list[str]:
        unknown = [code for code in value if code not in jobs.REMINDER_OFFSET_DAYS]
        if unknown:
            raise ValueError(f"Unbekannte Erinnerung: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class GoogleCalendarPatchIn(_In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starts_on: date | None = None
    ends_on: date | None = None
    all_day: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


class CalendarItem(BaseModel):
    kind: str
    title: str
    date: dt.date
    ends_on: dt.date | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    editable: bool = False
    # Google Calendar (M23-02): source/calendar label to colour and filter the entries in
    # /kalender; google_event_id and mailbox_id identify the event for patch/delete.
    source: str = "internal"
    calendar_label: str | None = None
    google_event_id: str | None = None
    mailbox_id: uuid.UUID | None = None
    # M23-02 bidirectional: set when a calendar_event link row exists for this Google event.
    calendar_event_id: uuid.UUID | None = None
    invite_status: str | None = None  # draft | invited, only for linked events
    attendees: list[dict[str, str]] = Field(default_factory=list)
    # True when Google's etag no longer matches the last synced etag on our link row: the
    # Google version is shown here, the CRM copy is marked stale, neither side is overwritten.
    is_stale: bool = False
    # P1 AP7: generated entries carry their category (deadline kind), reminder codes (B.30)
    # and the route to the source row; ``calendar_entry_id`` is the internal row.
    category: str = "appointment"
    reminders: list[str] = Field(default_factory=list)
    href: str | None = None
    calendar_entry_id: uuid.UUID | None = None
    # Recurrence rule of a manual entry (B.30); each occurrence in the range is one item.
    recurrence: dict[str, Any] | None = None


class CalendarNotice(BaseModel):
    source: str  # default | own
    address: str
    connected: bool  # calendar_enabled and a refresh token is stored
    # Set when the Google calendar of this mailbox could not be read (expired or revoked
    # refresh token, missing calendar scope, Google unreachable). The rest of the calendar is
    # still returned (operator report 27.09.2026: a GCalError turned the whole page into 500).
    error: str | None = None
    # Registered problem code of the failure (MHVP-COMM-0004 reconnect, MHVP-COMM-0005
    # transient, MHVP-PLAT-0002 other refusal or missing OAuth client) and whether only a new
    # Google connection of the mailbox helps (hotfix 28.09.2026).
    error_code: str | None = None
    reconnect_required: bool = False


class CalendarOut(BaseModel):
    items: list[CalendarItem]
    notices: list[CalendarNotice] = Field(default_factory=list)


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


class WorkspaceBulkIn(_In):
    action: str = Field(
        pattern=(
            "^(contacts.add_tag|contacts.remove_tag|maintenance.done|tickets.assign"
            "|documents.set_category|documents.link_property|deadline_entries.done)$"
        )
    )
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)
    tag: str | None = Field(default=None, min_length=1, max_length=63)
    assignee_user_id: uuid.UUID | None = None
    # M9-04: target category (documents.set_category) and property (documents.link_property).
    category_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    # maintenance.done: completion date (default today); with an interval the due date moves on.
    done_on: date | None = None


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
        # All tiles in one statement (scalar subqueries) instead of one count per tile
        # (performance review 26.09.2026): one round trip regardless of the permissions.
        def count(model: Any, *where: Any) -> Any:
            return select(func.count()).select_from(model).where(*where).scalar_subquery()

        wanted: dict[str, Any] = {}
        if principal.has("properties:read"):
            wanted["properties"] = count(Property)
            wanted["units"] = count(Unit)
            wanted["maintenance_due_30d"] = count(
                MaintenanceItem,
                MaintenanceItem.status == "open",
                MaintenanceItem.due_date <= today + timedelta(days=30),
            )
        if principal.has("contacts:read"):
            wanted["contacts"] = count(Contact, Contact.deleted_at.is_(None))
        if principal.has("contracts:read"):
            wanted["active_contracts"] = count(
                Contract, or_(Contract.end_date.is_(None), Contract.end_date >= today)
            )
            wanted["contracts_ending_90d"] = count(
                Contract, Contract.end_date.between(today, today + timedelta(days=90))
            )
        if principal.has("documents:read"):
            wanted["documents"] = count(Document)
        if principal.has("ai:read"):
            wanted["open_ai_proposals"] = count(AiProposal, AiProposal.decision == Decision.PENDING)
        wanted["unread_notifications"] = count(
            Notification, Notification.user_id == principal.user_id, Notification.read_at.is_(None)
        )
        row = (await session.execute(select(*(q.label(k) for k, q in wanted.items())))).one()
        tiles: dict[str, int] = {k: int(v or 0) for k, v in zip(wanted, row, strict=True)}
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


def _stats_bounds(range_key: str, today: date) -> tuple[date, date]:
    """Rolling window ending today, inclusive (orientation only, no legal cut-off date)."""
    days = {"day": 0, "week": 6, "month": 29, "quarter": 89, "year": 364}[range_key]
    return today - timedelta(days=days), today


def _bucket_key(d: date, range_key: str) -> str:
    """day/week/month range -> day bucket; quarter -> week bucket; year -> month bucket."""
    if range_key == "quarter":
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if range_key == "year":
        return f"{d.year}-{d.month:02d}"
    return d.isoformat()


def _bucket_series(start: date, end: date, range_key: str) -> list[str]:
    keys: list[str] = []
    step = timedelta(days=1)
    cursor = start
    seen: set[str] = set()
    while cursor <= end:
        key = _bucket_key(cursor, range_key)
        if key not in seen:
            seen.add(key)
            keys.append(key)
        cursor += step
    return keys


@router.get(
    "/dashboard/stats",
    summary="Ticket-Auswertung der Startseite (Zeitraum, je Bearbeiter)",
)
async def dashboard_stats(
    request: Request,
    range: str = Query(default="week", pattern="^(" + "|".join(STATS_RANGES) + ")$"),
    user_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(STATS_READ),
) -> dict[str, Any]:
    from mhvp.tickets.activity import (
        activity_out,
        last_inbound_expression,
        last_staff_activity_expression,
    )
    from mhvp.tickets.models import Ticket, TicketStatus

    today = services.local_today()
    start, end = _stats_bounds(range, today)
    start_dt = datetime.combine(start, dt.time.min, tzinfo=UTC)
    end_dt = datetime.combine(end + timedelta(days=1), dt.time.min, tzinfo=UTC)
    async with tenant_tx(request, principal) as session:
        # Letzte Aktivität je Ticket in derselben Abfrage (M19-09, Farbcodierung der
        # Startseite, kein N+1).
        base = select(Ticket, last_staff_activity_expression(), last_inbound_expression())
        if user_id is not None:
            base = base.where(Ticket.assignee_user_id == user_id)
        rows = (await session.execute(base)).all()
        tickets = [t for t, _, _ in rows]
        activity = {t.id: (staff_at, inbound_at) for t, staff_at, inbound_at in rows}
        now = datetime.now(UTC)

        resolved_statuses = {TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED}
        open_count = sum(1 for t in tickets if t.status not in resolved_statuses)
        in_progress_count = sum(1 for t in tickets if t.status == TicketStatus.IN_PROGRESS)
        created_in_range = [t for t in tickets if start_dt <= t.created_at < end_dt]
        done_in_range = [
            t for t in tickets if t.resolved_at is not None and start_dt <= t.resolved_at < end_dt
        ]

        bucket_order = _bucket_series(start, end, range)
        buckets: dict[str, dict[str, int]] = {
            k: {"created": 0, "resolved": 0} for k in bucket_order
        }
        for t in created_in_range:
            key = _bucket_key(services.local_date(t.created_at), range)
            buckets.setdefault(key, {"created": 0, "resolved": 0})["created"] += 1
        for t in done_in_range:
            resolved_at = t.resolved_at
            if resolved_at is None:
                continue
            key = _bucket_key(services.local_date(resolved_at), range)
            buckets.setdefault(key, {"created": 0, "resolved": 0})["resolved"] += 1

        by_assignee: dict[uuid.UUID, dict[str, Any]] = {}
        for t in tickets:
            if t.assignee_user_id is None:
                continue
            row = by_assignee.setdefault(
                t.assignee_user_id, {"open": 0, "resolved_in_range": 0, "_hours": []}
            )
            if t.status not in resolved_statuses:
                row["open"] += 1
        for t in done_in_range:
            if t.assignee_user_id is None:
                continue
            row = by_assignee.setdefault(
                t.assignee_user_id, {"open": 0, "resolved_in_range": 0, "_hours": []}
            )
            row["resolved_in_range"] += 1
            resolved_at = t.resolved_at
            if resolved_at is not None:
                row["_hours"].append((resolved_at - t.created_at).total_seconds() / 3600)

        assignees = []
        for uid, row in sorted(by_assignee.items(), key=lambda kv: str(kv[0])):
            hours = row.pop("_hours")
            row["average_resolution_hours"] = round(sum(hours) / len(hours), 1) if hours else None
            assignees.append({"user_id": uid, **row})

        return {
            "range": range,
            "start": start,
            "end": end,
            "totals": {
                "open": open_count,
                "in_progress": in_progress_count,
                "done_in_range": len(done_in_range),
                "created_in_range": len(created_in_range),
            },
            "buckets": [{"key": k, **buckets[k]} for k in bucket_order],
            "assignees": assignees,
            # Offene Tickets der Startseite (operator 26.09.2026): jede Zeile verlinkt auf
            # /tickets/{id}; neueste zuerst, höchstens STATS_RECENT_LIMIT Einträge.
            "tickets": [
                {
                    "id": t.id,
                    "number": t.number,
                    "title": t.title,
                    "status": t.status.value,
                    "priority": t.priority.value,
                    "assignee_user_id": t.assignee_user_id,
                    "created_at": t.created_at,
                    "sla_due_at": t.sla_due_at,
                    **activity_out(t, *activity[t.id], now),
                }
                for t in sorted(
                    (t for t in tickets if t.status not in resolved_statuses),
                    key=lambda t: t.created_at,
                    reverse=True,
                )[:STATS_RECENT_LIMIT]
            ],
        }


# Global search -------------------------------------------------------------------------


@router.get("/search", summary="Globale Suche über alle Bereiche (Strg+K)")
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=8, ge=1, le=25),
    principal: TenantPrincipal = Depends(member),
) -> list[Hit]:
    """Every hit type is guarded by its own read permission (contacts, properties incl.
    buildings and units, contracts, documents, tickets, postings); postings additionally
    respect the legal entity scope of the principal (ADR 0005)."""
    from mhvp.accounting.models import Invoice, JournalEntry, Ledger
    from mhvp.contacts.models import Contact, PartyMember
    from mhvp.contacts.services import search_filter
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.core.auth.scope import allowed_legal_entity_ids, allowed_property_ids
    from mhvp.documents.models import Document
    from mhvp.documents.routers import _property_scope_filter
    from mhvp.properties.models import Building, Meter, Property, Unit
    from mhvp.tickets.models import Ticket

    like = f"%{q.strip()}%"
    # "#12" and "TNR#12" address a ticket number (M19-06), digits alone match numbers too.
    number_text = q.strip().upper().removeprefix("TNR").lstrip("#").strip()
    number = int(number_text) if number_text.isdigit() else None
    hits: list[Hit] = []
    # M2-02/S16-02: property bound hits follow the membership's property assignment.
    property_scope = allowed_property_ids(principal)

    def assigned(column: Any) -> list[ColumnElement[bool]]:
        return [] if property_scope is None else [column.in_(property_scope)]

    async with tenant_tx(request, principal) as session:
        if principal.has("contacts:read"):
            sim = func.similarity(Contact.search_text, q.lower())
            query = search_filter(select(Contact).where(Contact.deleted_at.is_(None)), q)
            for c in (await session.scalars(query.order_by(sim.desc()).limit(limit))).all():
                hits.append(Hit(entity_type="contact", id=c.id, title=c.display_name))
        if principal.has("properties:read"):
            # Properties, units and buildings in one statement (query budget of
            # tests/integration/test_perf_queries.py): per type at most ``limit`` hits.
            no_parent = cast(null(), UUID(as_uuid=True))
            props = select(
                literal("property").label("kind"),
                Property.id.label("id"),
                func.concat(Property.number, " ", Property.name).label("title"),
                func.concat_ws(" ", Property.street, Property.house_number, Property.city).label(
                    "subtitle"
                ),
                no_parent.label("parent_id"),
                Property.number.label("sort1"),
                literal("").label("sort2"),
            ).where(
                or_(
                    Property.number.ilike(like),
                    Property.name.ilike(like),
                    Property.street.ilike(like),
                    Property.city.ilike(like),
                ),
                *assigned(Property.id),
            )
            units = (
                select(
                    literal("unit"),
                    Unit.id,
                    func.concat(Property.number, "/", Unit.number),
                    Unit.label,
                    no_parent,
                    Property.number,
                    Unit.number,
                )
                .join(Property, Property.id == Unit.property_id)
                .where(
                    or_(
                        Unit.number.ilike(like),
                        Unit.label.ilike(like),
                        Property.street.ilike(like),
                    ),
                    *assigned(Property.id),
                )
            )
            buildings = (
                select(
                    literal("building"),
                    Building.id,
                    func.concat(Property.number, " ", Building.name),
                    func.concat_ws(" ", Building.street, Building.house_number),
                    Building.property_id,
                    Property.number,
                    Building.name,
                )
                .join(Property, Property.id == Building.property_id)
                .where(
                    or_(Building.name.ilike(like), Building.street.ilike(like)),
                    *assigned(Property.id),
                )
            )
            # Q04-02: meter and MaLo numbers lead to the property (type "meter" is mapped to
            # "property" below), in the same statement.
            meters = (
                select(
                    literal("meter"),
                    Meter.property_id,
                    func.concat("Zähler ", Meter.number),
                    func.concat_ws(" ", Property.number, Property.name, Meter.location),
                    no_parent,
                    Property.number,
                    Meter.number,
                )
                .join(Property, Property.id == Meter.property_id)
                .where(
                    or_(Meter.number.ilike(like), Meter.malo_id.ilike(like)),
                    *assigned(Property.id),
                )
            )
            combined = union_all(props, units, buildings, meters).subquery()
            rows = await session.execute(
                select(combined)
                .order_by(combined.c.kind, combined.c.sort1, combined.c.sort2)
                .limit(3 * limit)
            )
            seen: dict[str, int] = {}
            for row in rows.all():
                seen[row.kind] = seen.get(row.kind, 0) + 1
                if seen[row.kind] > limit:
                    continue
                hits.append(
                    Hit(
                        entity_type="property" if row.kind == "meter" else row.kind,
                        id=row.id,
                        title=row.title,
                        subtitle=row.subtitle or None,
                        parent_id=row.parent_id,
                    )
                )
        if principal.has("contracts:read"):
            # M3-05: a contract is also found by the name of a party member (tenant, owner).
            party_hit = (
                select(PartyMember.party_id)
                .join(Contact, Contact.id == PartyMember.contact_id)
                .where(Contact.search_text.ilike(like.lower()), Contact.deleted_at.is_(None))
            )
            # Q04-02: a tenancy is also found by the address of its property.
            address_hit = select(Property.id).where(
                or_(Property.street.ilike(like), Property.city.ilike(like))
            )
            contracts = await session.scalars(
                select(Contract)
                .where(
                    or_(
                        Contract.number.ilike(like),
                        Contract.party_id.in_(party_hit),
                        (Contract.kind == ContractKind.TENANCY)
                        & Contract.property_id.in_(address_hit),
                    ),
                    *assigned(Contract.property_id),
                )
                .order_by(Contract.number)
                .limit(limit)
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
            doc_query = select(Document).where(
                or_(
                    Document.search_vector.op("@@")(func.plainto_tsquery("german", q)),
                    Document.title.ilike(like),
                    Document.filename.ilike(like),
                )
            )
            doc_scope = _property_scope_filter(session)
            if doc_scope is not None:
                doc_query = doc_query.where(Document.id.in_(doc_scope))
            docs = await session.scalars(doc_query.limit(limit))
            for d in docs.all():
                hits.append(
                    Hit(entity_type="document", id=d.id, title=d.title, subtitle=d.filename)
                )
        if principal.has("tickets:read"):
            conditions: list[ColumnElement[bool]] = [Ticket.title.ilike(like)]
            if number is not None:
                conditions.append(Ticket.number == number)
            tickets = await session.scalars(
                select(Ticket)
                .where(or_(*conditions), *assigned(Ticket.property_id))
                .order_by(Ticket.number.desc())
                .limit(limit)
            )
            for t in tickets.all():
                hits.append(
                    Hit(
                        entity_type="ticket",
                        id=t.id,
                        title=f"#{t.number} {t.title}",
                        subtitle=t.status.value,
                    )
                )
        if principal.has("accounting:read"):
            conditions = [JournalEntry.text.ilike(like), JournalEntry.reference.ilike(like)]
            if number is not None:
                conditions.append(JournalEntry.number == number)
            query = (
                select(JournalEntry)
                .join(Ledger, Ledger.id == JournalEntry.ledger_id)
                .where(or_(*conditions))
            )
            scope = allowed_legal_entity_ids(principal)
            if scope is not None:
                query = query.where(Ledger.legal_entity_id.in_(scope))
            query = query.where(*assigned(Ledger.property_id))
            entries = await session.scalars(
                query.order_by(JournalEntry.booking_date.desc(), JournalEntry.number.desc()).limit(
                    limit
                )
            )
            # Q04-02: incoming invoices by the number of the creditor, same legal entity scope.
            inv_query = (
                select(Invoice)
                .join(Ledger, Ledger.id == Invoice.ledger_id)
                .where(Invoice.number.ilike(like))
            )
            if scope is not None:
                inv_query = inv_query.where(Ledger.legal_entity_id.in_(scope))
            inv_query = inv_query.where(*assigned(Ledger.property_id))
            for inv in (
                await session.scalars(
                    inv_query.order_by(Invoice.invoice_date.desc(), Invoice.number).limit(limit)
                )
            ).all():
                hits.append(
                    Hit(
                        entity_type="invoice",
                        id=inv.id,
                        title=f"Rechnung {inv.number}",
                        subtitle=f"{inv.invoice_date.isoformat()} {inv.gross} EUR",
                    )
                )
            for e in entries.all():
                title = f"Buchung {e.number}" if e.number is not None else "Buchung (Entwurf)"
                hits.append(
                    Hit(
                        entity_type="posting",
                        id=e.id,
                        title=f"{title} {e.text}",
                        subtitle=f"{e.booking_date.isoformat()} {e.status.value}",
                        parent_id=e.ledger_id,
                    )
                )
    return hits


# Digest and deadlines (A40, A41) ------------------------------------------------------

APPOINTMENT_KIND = "appointment"
APPOINTMENT_HORIZON_DAYS = 365


class JobSettingsOut(BaseModel):
    digest_mail_enabled: bool
    deadline_lead_days: int
    deadline_lead_days_default: int = jobs.DEFAULT_LEAD_DAYS


class JobSettingsIn(_In):
    digest_mail_enabled: bool | None = None
    deadline_lead_days: int | None = Field(default=None, ge=0, le=730)


class DeadlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    source_type: str
    source_id: uuid.UUID
    reference: str
    due_on: date
    lead_days: int
    status: str
    property_id: uuid.UUID | None
    notified_at: datetime | None
    done_at: datetime | None
    updated_at: datetime
    # Route to the source row (P1 AP7, "Sprung in die Quelle"); None without a page.
    href: str | None = None


def _deadline_out(row: Any) -> DeadlineOut:
    out = DeadlineOut.model_validate(row)
    out.href = links.target_href(row.source_type, row.source_id, property_id=row.property_id)
    return out


@router.get("/digest", summary="Tagesübersicht des angemeldeten Benutzers (A40)")
async def digest(
    request: Request,
    day: date | None = None,
    principal: TenantPrincipal = Depends(member),
) -> dict[str, Any]:
    """Same data as the daily job ``tasks.digest``, computed live for the caller."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Tenant user required.")
    async with tenant_tx(request, principal) as session:
        return await jobs.build_digest(
            session,
            principal.tenant_id,
            principal.user_id,
            principal.permissions,
            day or services.local_today(),
        )


@router.get("/approvals", summary="Offene Freigaben des angemeldeten Benutzers (Startseite)")
async def approvals(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> dict[str, int]:
    """Counts per approval kind, only for kinds the caller may decide (operator 27.09.2026,
    start page column "Freigaben"). Read only; every count follows the same rules as the
    approving endpoint: mail replies (communication:approve, otherwise own submissions),
    IBAN four eyes release (contacts:approve), release gate requests (release_gates:approve),
    dunning runs in preview and direct debit runs in draft without an own approval
    (accounting:approve) and checked metering transmissions (transmission write rights).
    A kind the caller may not decide is left out of the response."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Tenant user required.")
    from mhvp.accounting.direct_debit_models import (
        DirectDebitApproval,
        DirectDebitRun,
        DirectDebitRunStatus,
    )
    from mhvp.accounting.models import DunningRun
    from mhvp.communication.models import Message
    from mhvp.contacts.models import (
        BankAccountApproval,
        ContactBankAccount,
        ContactBankAccountChange,
    )
    from mhvp.metering import transmissions as metering_transmissions
    from mhvp.metering.models import MeteringTransmission, TransmissionStatus
    from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest

    def count(model: Any, *where: Any) -> Any:
        return select(func.count()).select_from(model).where(*where).scalar_subquery()

    user_id = principal.user_id
    wanted: dict[str, Any] = {}
    if principal.has("communication:approve") or principal.has("communication:create"):
        where = [
            Message.direction == "out",
            Message.submitted_at.is_not(None),
            Message.approved_at.is_(None),
            Message.sent_at.is_(None),
            Message.rejection_note.is_(None),
        ]
        if not principal.has("communication:approve"):
            where.append(Message.submitted_by == user_id)
        wanted["mail"] = count(Message, *where)
    if principal.has("contacts:approve"):
        # Pending IBANs plus pending change requests (end) of the CRM screen (M5-01 addendum).
        wanted["bank_accounts"] = count(
            ContactBankAccount, ContactBankAccount.approval_status == BankAccountApproval.PENDING
        ) + count(
            ContactBankAccountChange,
            ContactBankAccountChange.status == BankAccountApproval.PENDING,
        )
    if principal.has("release_gates:approve"):
        wanted["release_gates"] = count(
            ReleaseGateRequest, ReleaseGateRequest.status == GateRequestStatus.REQUESTED
        )
    if principal.has("accounting:approve"):
        wanted["dunning_runs"] = count(DunningRun, DunningRun.status == "preview")
        mine = select(DirectDebitApproval.run_id).where(DirectDebitApproval.user_id == user_id)
        wanted["direct_debits"] = count(
            DirectDebitRun,
            DirectDebitRun.status == DirectDebitRunStatus.DRAFT,
            DirectDebitRun.id.not_in(mine),
        )
    kinds = [
        kind
        for kind, permission in metering_transmissions.KIND_PERMISSION.items()
        if principal.has(permission)
    ]
    if kinds:
        wanted["metering_transmissions"] = count(
            MeteringTransmission,
            MeteringTransmission.status == TransmissionStatus.CHECKED,
            MeteringTransmission.kind.in_([str(k) for k in kinds]),
        )
    if not wanted:
        return {}
    async with tenant_tx(request, principal) as session:
        row = (await session.execute(select(*(q.label(k) for k, q in wanted.items())))).one()
        return {k: int(v or 0) for k, v in zip(wanted, row, strict=True)}


@router.get("/deadlines", summary="Fristenliste des Mandanten (A41, Orientierung, zu prüfen)")
async def deadlines(
    request: Request,
    kind: str | None = Query(
        default=None, pattern="^(" + "|".join((*jobs.DEADLINE_KINDS, APPOINTMENT_KIND)) + ")$"
    ),
    status: str = Query(default="open", pattern="^(open|done|all)$"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(member),
) -> list[DeadlineOut]:
    """Only kinds the caller may read (contracts, properties, accounting, documents). Own and
    shared manual calendar entries with reminders appear as kind ``appointment`` (recurring
    ones once per occurrence, computed on read); they are appointments, not deadlines of
    the source data, and are never notified by the lead time of the list."""
    from mhvp.workspace.models import ComplianceDeadline

    appointments: list[DeadlineOut] = []
    if kind in (None, APPOINTMENT_KIND) and status != "done":
        async with tenant_tx(request, principal) as session:
            appointments = await _appointment_deadlines(
                session, principal.user_id, from_date, to_date, limit
            )
    allowed = [k for k, (read, _u) in jobs.DEADLINE_PERMISSIONS.items() if principal.has(read)]
    if kind is not None:
        allowed = [k for k in allowed if k == kind]
    if not allowed:
        return appointments
    query = select(ComplianceDeadline).where(ComplianceDeadline.kind.in_(allowed))
    if status != "all":
        query = query.where(ComplianceDeadline.status == status)
    if from_date is not None:
        query = query.where(ComplianceDeadline.due_on >= from_date)
    if to_date is not None:
        query = query.where(ComplianceDeadline.due_on <= to_date)
    query = query.order_by(ComplianceDeadline.due_on, ComplianceDeadline.reference).limit(limit)
    async with tenant_tx(request, principal) as session:
        rows = (await session.scalars(query)).all()
    out = [_deadline_out(r) for r in rows] + appointments
    out.sort(key=lambda d: (d.due_on, d.reference))
    return out[:limit]


async def _appointment_deadlines(
    session: Any,
    user_id: uuid.UUID | None,
    from_date: date | None,
    to_date: date | None,
    limit: int,
) -> list[DeadlineOut]:
    """Virtual deadline rows of manual calendar entries (own or shared) with at least one
    reminder, expanded per occurrence for recurring entries; nothing is persisted."""
    lower = from_date or services.local_today()
    upper = to_date or (lower + timedelta(days=APPOINTMENT_HORIZON_DAYS))
    rows = (
        await session.scalars(
            select(CalendarEntry).where(
                CalendarEntry.owner_user_id.is_not(None),
                or_(CalendarEntry.owner_user_id == user_id, CalendarEntry.shared),
                func.jsonb_array_length(CalendarEntry.reminders) > 0,
                CalendarEntry.starts_on <= upper,
            )
        )
    ).all()
    out: list[DeadlineOut] = []
    for e in rows:
        codes = [str(c) for c in e.reminders]
        lead = max((jobs.REMINDER_OFFSET_DAYS.get(c, 0) for c in codes), default=0)
        for occurrence in jobs.expand_occurrences(e.starts_on, e.recurrence, lower, upper):
            out.append(
                DeadlineOut(
                    id=e.id,
                    kind=APPOINTMENT_KIND,
                    source_type="calendar_entry",
                    source_id=e.id,
                    reference=e.title,
                    due_on=occurrence,
                    lead_days=lead,
                    status="open",
                    property_id=e.property_id,
                    notified_at=None,
                    done_at=None,
                    updated_at=e.updated_at,
                    href=links.target_href("calendar_entry", e.id, appointment_date=occurrence),
                )
            )
            if len(out) >= limit:
                return out
    return out


@router.get("/job-settings", summary="Schalter der Tagesjobs (Digest-Mail, Vorfrist)")
async def get_job_settings(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> JobSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await jobs.job_settings(session, principal.tenant_id)
        return JobSettingsOut(
            digest_mail_enabled=row.digest_mail_enabled,
            deadline_lead_days=row.deadline_lead_days,
        )


@router.put("/job-settings", summary="Schalter der Tagesjobs ändern")
async def put_job_settings(
    request: Request,
    body: JobSettingsIn,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> JobSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await jobs.save_job_settings(
            session,
            principal.tenant_id,
            digest_mail_enabled=body.digest_mail_enabled,
            deadline_lead_days=body.deadline_lead_days,
            actor_user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="workspace.job_settings_changed",
            entity_type="workspace_job_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "digest_mail_enabled": row.digest_mail_enabled,
                "deadline_lead_days": row.deadline_lead_days,
            },
        )
        return JobSettingsOut(
            digest_mail_enabled=row.digest_mail_enabled,
            deadline_lead_days=row.deadline_lead_days,
        )


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
        return await notification_out(session, list(rows.all()))


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


# Notification preferences (M23-04) -------------------------------------------------------------


class NotificationPreferenceItem(BaseModel):
    kind: str
    in_app: bool
    email: bool
    muted_until: datetime | None = None
    # Mandatory kinds (legal or money relevant reminders, SLA escalation) ignore every switch.
    mandatory: bool = False


class NotificationPreferencesOut(BaseModel):
    items: list[NotificationPreferenceItem]


class NotificationPreferenceIn(_In):
    kind: str = Field(min_length=1, max_length=64)
    in_app: bool = True
    email: bool = False
    muted_until: datetime | None = None


class NotificationPreferencesIn(_In):
    items: list[NotificationPreferenceIn] = Field(min_length=1, max_length=64)


def _own_user(principal: TenantPrincipal) -> uuid.UUID:
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Notification settings need a user."
        )
    return principal.user_id


async def _preferences_out(session: AsyncSession, user_id: uuid.UUID) -> NotificationPreferencesOut:
    from mhvp.workspace import notification_prefs as prefs

    rows = {
        r.kind: r
        for r in (
            await session.scalars(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            )
        ).all()
    }
    items: list[NotificationPreferenceItem] = []
    for kind in (prefs.DEFAULT_KIND, *prefs.CATALOGUE):
        row = rows.get(kind)
        mandatory = kind in prefs.MANDATORY_KINDS
        items.append(
            NotificationPreferenceItem(
                kind=kind,
                in_app=True if mandatory else (row.in_app if row else True),
                email=False if mandatory else (row.email if row else False),
                muted_until=None if mandatory or row is None else row.muted_until,
                mandatory=mandatory,
            )
        )
    return NotificationPreferencesOut(items=items)


@router.get(
    "/notification-preferences",
    summary="Eigene Benachrichtigungseinstellungen (Kanal je Art, Stummschaltung)",
)
async def notification_preferences(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> NotificationPreferencesOut:
    async with tenant_tx(request, principal) as session:
        return await _preferences_out(session, _own_user(principal))


@router.put(
    "/notification-preferences",
    summary="Eigene Benachrichtigungseinstellungen speichern",
)
async def save_notification_preferences(
    body: NotificationPreferencesIn,
    request: Request,
    principal: TenantPrincipal = Depends(member),
) -> NotificationPreferencesOut:
    """Own settings only. ``*`` is the default for kinds without an own row. Mandatory kinds
    cannot be switched (422); a mute needs a future moment."""
    from mhvp.workspace import notification_prefs as prefs

    allowed = {prefs.DEFAULT_KIND, *prefs.CATALOGUE}
    now = datetime.now(UTC)
    for item in body.items:
        if item.kind not in allowed:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannte Art {item.kind!r}.")
        if item.kind in prefs.MANDATORY_KINDS:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Diese Benachrichtigung ist verpflichtend und nicht abschaltbar.",
            )
        if item.muted_until is not None and item.muted_until <= now:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Stummschaltung braucht einen Zeitpunkt in der Zukunft.",
            )
    async with tenant_tx(request, principal) as session:
        rows = {
            r.kind: r
            for r in (
                await session.scalars(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == _own_user(principal)
                    )
                )
            ).all()
        }
        for item in body.items:
            row = rows.get(item.kind)
            if row is None:
                row = NotificationPreference(
                    tenant_id=principal.tenant_id, user_id=_own_user(principal), kind=item.kind
                )
                session.add(row)
                rows[item.kind] = row
            row.in_app, row.email, row.muted_until = item.in_app, item.email, item.muted_until
        await session.flush()
        return await _preferences_out(session, _own_user(principal))


class NotificationMuteIn(_In):
    # None lifts the mute; otherwise a moment in the future.
    muted_until: datetime | None = None


@router.post(
    "/notifications/mute",
    summary="Alle Benachrichtigungen stummschalten oder die Stummschaltung aufheben",
)
async def mute_notifications(
    body: NotificationMuteIn,
    request: Request,
    principal: TenantPrincipal = Depends(member),
) -> NotificationPreferencesOut:
    """Bulk action on the own user default (kind ``*``): silences every kind that is not
    mandatory; mandatory kinds (SLA escalation, compliance reminders) ignore it."""
    from mhvp.workspace import notification_prefs as prefs

    user_id = _own_user(principal)
    if body.muted_until is not None and body.muted_until <= datetime.now(UTC):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Die Stummschaltung braucht einen Zeitpunkt in der Zukunft.",
        )
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.kind == prefs.DEFAULT_KIND,
            )
        )
        if row is None:
            row = NotificationPreference(
                tenant_id=principal.tenant_id, user_id=user_id, kind=prefs.DEFAULT_KIND
            )
            session.add(row)
        row.muted_until = body.muted_until
        await session.flush()
        return await _preferences_out(session, user_id)


# Calendar ------------------------------------------------------------------------------
#
# Operator decision (25.09.2026, M23-02): the CRM calendar is Google Calendar. The tenant's
# default calendar is the Google account of the default mailbox (source "default"); a user with
# a mailbox assigned to them (mailbox_user) additionally sees and writes to that mailbox's
# calendar (source "own"). Internal entries (calendar_entry) and data derived deadlines keep
# source "internal". Google events are fetched on demand (no periodic sync job) and cached in
# Redis for 5 minutes per tenant, mailbox and range; a write bumps a version key so the next
# read misses the cache instead of scanning for keys to delete.

GCAL_CACHE_TTL = 300


def _google_label(source: str, address: str) -> str:
    return f"{'Standardkalender' if source == 'default' else 'Eigener Kalender'} ({address})"


async def _resolve_calendars(
    session: Any, principal: TenantPrincipal
) -> tuple[Mailbox | None, Mailbox | None]:
    """(default mailbox, own assigned mailbox), each only if it carries a Google account."""
    default = await session.scalar(select(Mailbox).where(Mailbox.is_default.is_(True)))
    own_mailbox_id = await session.scalar(
        select(MailboxUser.mailbox_id).where(MailboxUser.user_id == principal.user_id)
    )
    own = None
    if own_mailbox_id and (default is None or own_mailbox_id != default.id):
        own = await session.get(Mailbox, own_mailbox_id)
    return default, own


def _cache_key(
    tenant_id: uuid.UUID, mailbox_id: uuid.UUID, version: str, start: date, end: date
) -> str:
    return f"gcal:items:{tenant_id}:{mailbox_id}:{version}:{start.isoformat()}:{end.isoformat()}"


async def _version(request: Request, tenant_id: uuid.UUID, mailbox_id: uuid.UUID) -> str:
    redis = request.app.state.resources.redis
    v = await redis.get(f"gcal:v:{tenant_id}:{mailbox_id}")
    return v.decode() if v else "0"


async def _bump_version(request: Request, tenant_id: uuid.UUID, mailbox_id: uuid.UUID) -> None:
    await request.app.state.resources.redis.incr(f"gcal:v:{tenant_id}:{mailbox_id}")


def _event_dates(event: dict[str, Any]) -> tuple[date, date | None]:
    s = event.get("start", {})
    e = event.get("end", {})
    start_raw = s.get("date") or s.get("dateTime")
    end_raw = e.get("date") or e.get("dateTime")
    start = date.fromisoformat(start_raw[:10])
    end = date.fromisoformat(end_raw[:10]) if end_raw else None
    if end is not None and "date" in e and end > start:
        # Google's all day end date is exclusive.
        end = end - timedelta(days=1)
    if end == start:
        end = None
    return start, end


def _google_item(
    event: dict[str, Any],
    source: str,
    label: str,
    mailbox_id: uuid.UUID,
    link: CalendarEvent | None = None,
) -> CalendarItem:
    start, end = _event_dates(event)
    is_stale = bool(link and link.etag and event.get("etag") and event["etag"] != link.etag)
    return CalendarItem(
        kind="appointment",
        # Rule M23-05: on a conflict the Google version wins for display, the CRM copy is
        # only flagged stale, never silently overwritten in either direction.
        title=event.get("summary") or "(ohne Titel)",
        date=start,
        ends_on=end,
        editable=True,
        source=source,
        calendar_label=label,
        google_event_id=event["id"],
        mailbox_id=mailbox_id,
        calendar_event_id=link.id if link else None,
        invite_status=link.status if link else None,
        attendees=link.attendees if link else [],
        is_stale=is_stale,
    )


async def _link_rows(
    session: Any, tenant_id: uuid.UUID, mailbox_id: uuid.UUID
) -> dict[str, CalendarEvent]:
    rows = await session.scalars(
        select(CalendarEvent).where(CalendarEvent.mailbox_id == mailbox_id)
    )
    return {row.google_event_id: row for row in rows.all()}


GCAL_UNREACHABLE = "Google Kalender ist derzeit nicht erreichbar."
GCAL_RECONNECT_HINT = "Bitte das Postfach unter Einstellungen, Postfächer neu mit Google verbinden."
GCAL_RETRY_HINT = "Bitte später erneut versuchen."


def _google_problem(exc: Exception) -> ProblemError:
    """Registered problem for a failed Google calendar call (ADR 0004, hotfix 28.09.2026).

    Expired or revoked grant, missing scope or refresh token: 409 MHVP-COMM-0004 with the
    reconnect hint (never 401, which the CRM reads as an expired session). Rate limit, Google
    server error or network failure: 502 MHVP-COMM-0005. Other refusals (event not found,
    request not accepted) and a missing OAuth client stay 409 MHVP-PLAT-0002 with the reason.
    The GCalError text carries the HTTP status only, never a token or response body.
    """
    if isinstance(exc, gcal.GCalError) and exc.kind == gcal.AUTH:
        return ProblemError(
            ErrorCodes.GOOGLE_CALENDAR_RECONNECT,
            detail=f"{exc} {GCAL_RECONNECT_HINT}",
            extensions={"reconnect_required": True},
        )
    if isinstance(exc, gcal.GCalError) and exc.kind == gcal.UNAVAILABLE:
        return ProblemError(
            ErrorCodes.GOOGLE_CALENDAR_UNAVAILABLE, detail=f"{exc} {GCAL_RETRY_HINT}"
        )
    if isinstance(exc, httpx.HTTPError):
        return ProblemError(
            ErrorCodes.GOOGLE_CALENDAR_UNAVAILABLE, detail=f"{GCAL_UNREACHABLE} {GCAL_RETRY_HINT}"
        )
    return ProblemError(ErrorCodes.CONFLICT, detail=str(exc))


async def _write_client(session: Any, settings: Any, mailbox: Mailbox) -> gcal.GCalClient:
    """Google client for a write; a missing OAuth client or refresh token is a registered
    problem with the reason instead of an unhandled 500 (operator report 27.09.2026)."""
    try:
        client_id, client_secret = await gmail.oauth_client(session, settings)
        return gcal.make_client(client_id, client_secret, mailbox)
    except (gcal.GCalError, gmail.GmailError) as exc:
        raise _google_problem(exc) from exc


async def _fetch_google_items(
    request: Request,
    session: Any,
    settings: Any,
    tenant_id: uuid.UUID,
    mailbox: Mailbox,
    source: str,
    start: date,
    end: date,
) -> tuple[list[CalendarItem], CalendarNotice]:
    address, label = mailbox.address, _google_label(source, mailbox.address)
    notice = CalendarNotice(
        source=source, address=address, connected=bool(mailbox.calendar_enabled)
    )
    if not mailbox.calendar_enabled:
        return [], notice
    redis = request.app.state.resources.redis
    version = await _version(request, tenant_id, mailbox.id)
    key = _cache_key(tenant_id, mailbox.id, version, start, end)
    cached = await redis.get(key)
    if cached:
        events = json.loads(cached)
    else:
        try:
            client_id, client_secret = await gmail.oauth_client(session, settings)
            client = gcal.make_client(client_id, client_secret, mailbox)
            try:
                time_min = datetime.combine(start, dt.time.min, tzinfo=UTC)
                time_max = datetime.combine(end + timedelta(days=1), dt.time.min, tzinfo=UTC)
                events = await client.list_events(mailbox.calendar_id, time_min, time_max)
            finally:
                await client.aclose()
        except (gcal.GCalError, gmail.GmailError, httpx.HTTPError) as exc:
            # The rest of the calendar stays; the notice carries the registered problem.
            # Logged: mailbox, kind and upstream status only, never the message or a token.
            problem = _google_problem(exc)
            log.warning(
                "google_calendar_unavailable",
                extra={
                    "mailbox_id": str(mailbox.id),
                    "error_type": type(exc).__name__,
                    "kind": getattr(exc, "kind", None),
                    "upstream_status": getattr(exc, "status", None),
                    "code": problem.error.code,
                },
            )
            notice.error = GCAL_UNREACHABLE if isinstance(exc, httpx.HTTPError) else str(exc)
            notice.error_code = problem.error.code
            notice.reconnect_required = problem.error is ErrorCodes.GOOGLE_CALENDAR_RECONNECT
            return [], notice
        await redis.set(key, json.dumps(events), ex=GCAL_CACHE_TTL)
    links = await _link_rows(session, tenant_id, mailbox.id)
    items = []
    for e in events:
        link = links.get(e["id"])
        item = _google_item(e, source, label, mailbox.id, link)
        if link is not None and item.is_stale and not link.is_stale:
            link.is_stale = True
            link.last_synced_at = datetime.now(UTC)
        items.append(item)
    return items, notice


@router.get("/calendar", summary="Kalender: eigene Termine, geteilte Termine, Fristen aus Daten")
async def calendar(
    request: Request,
    start: date,
    end: date,
    principal: TenantPrincipal = Depends(member),
) -> CalendarOut:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig (höchstens 400 Tage).")
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        entries = await session.scalars(
            select(CalendarEntry).where(
                or_(CalendarEntry.owner_user_id == principal.user_id, CalendarEntry.shared),
                CalendarEntry.starts_on <= end,
                or_(
                    func.coalesce(CalendarEntry.ends_on, CalendarEntry.starts_on) >= start,
                    CalendarEntry.recurrence.is_not(None),
                ),
            )
        )
        items = []
        generated: set[tuple[str | None, uuid.UUID | None, date]] = set()
        for e in entries.all():
            if e.owner_user_id is not None and e.recurrence:
                # Recurring manual entry (B.30): one item per occurrence in the range,
                # computed on read, nothing persisted.
                length = (e.ends_on - e.starts_on) if e.ends_on else None
                for occurrence in jobs.expand_occurrences(e.starts_on, e.recurrence, start, end):
                    items.append(
                        CalendarItem(
                            kind="appointment",
                            title=e.title,
                            date=occurrence,
                            ends_on=occurrence + length if length is not None else None,
                            entity_type="calendar_entry",
                            entity_id=e.id,
                            property_id=e.property_id,
                            editable=e.owner_user_id == principal.user_id,
                            source="internal",
                            reminders=[str(r) for r in e.reminders],
                            calendar_entry_id=e.id,
                            recurrence=e.recurrence,
                        )
                    )
                continue
            if e.owner_user_id is None:
                # Generated from a date field (P1 AP7): visible with the read permission of
                # its kind, jumps to the source row, never editable here.
                read_permission = jobs.DEADLINE_PERMISSIONS.get(e.category, ("", ""))[0]
                if read_permission and not principal.has(read_permission):
                    continue
                generated.add((e.source_type, e.source_id, e.starts_on))
                items.append(
                    CalendarItem(
                        kind=e.category,
                        title=e.title,
                        date=e.starts_on,
                        ends_on=e.ends_on,
                        entity_type=e.source_type,
                        entity_id=e.source_id,
                        property_id=e.property_id,
                        editable=False,
                        source="internal",
                        category=e.category,
                        reminders=[str(r) for r in e.reminders],
                        href=links.target_href(
                            e.source_type, e.source_id, property_id=e.property_id
                        ),
                        calendar_entry_id=e.id,
                    )
                )
                continue
            items.append(
                CalendarItem(
                    kind="appointment",
                    title=e.title,
                    date=e.starts_on,
                    ends_on=e.ends_on,
                    entity_type="calendar_entry",
                    entity_id=e.id,
                    property_id=e.property_id,
                    editable=e.owner_user_id == principal.user_id,
                    source="internal",
                    reminders=[str(r) for r in e.reminders],
                    calendar_entry_id=e.id,
                )
            )
        # Live derived dates stay for sources the nightly job has not yet materialised;
        # a generated entry of the same source and date replaces them.
        derived = await services.derived_dates(
            session,
            start,
            end,
            contracts=principal.has("contracts:read"),
            properties=principal.has("properties:read"),
        )
        for d in derived:
            if (d["entity_type"], d["entity_id"], d["date"]) in generated:
                continue
            items.append(
                CalendarItem(
                    **d,
                    source="internal",
                    href=links.target_href(
                        d["entity_type"], d["entity_id"], property_id=d.get("property_id")
                    ),
                )
            )

        notices: list[CalendarNotice] = []
        default_mailbox, own_mailbox = await _resolve_calendars(session, principal)
        for mailbox, source in ((default_mailbox, "default"), (own_mailbox, "own")):
            if mailbox is None:
                continue
            google_items, notice = await _fetch_google_items(
                request, session, settings, principal.tenant_id, mailbox, source, start, end
            )
            items += google_items
            notices.append(notice)

        items.sort(key=lambda i: (i.date, i.title))
        return CalendarOut(items=items, notices=notices)


@router.post("/calendar/refresh", summary="Google-Kalender jetzt neu abrufen")
async def refresh_calendar(
    request: Request, principal: TenantPrincipal = Depends(member)
) -> dict[str, bool]:
    async with tenant_tx(request, principal) as session:
        default_mailbox, own_mailbox = await _resolve_calendars(session, principal)
    for mailbox in (default_mailbox, own_mailbox):
        if mailbox is not None:
            await _bump_version(request, principal.tenant_id, mailbox.id)
    return {"refreshed": True}


def _entry_body(body: CalendarEntryIn) -> dict[str, Any]:
    if body.all_day or (body.starts_at is None and body.ends_at is None):
        end_exclusive = (body.ends_on or body.starts_on) + timedelta(days=1)
        out = {
            "summary": body.title,
            "description": body.notes,
            "start": {"date": body.starts_on.isoformat()},
            "end": {"date": end_exclusive.isoformat()},
        }
    else:
        starts_at = body.starts_at or datetime.combine(body.starts_on, dt.time(9, 0), tzinfo=UTC)
        ends_at = body.ends_at or (starts_at + timedelta(hours=1))
        out = {
            "summary": body.title,
            "description": body.notes,
            "start": {"dateTime": starts_at.isoformat()},
            "end": {"dateTime": ends_at.isoformat()},
        }
    if body.location:
        out["location"] = body.location
    return out


@router.post("/calendar", status_code=201, summary="Termin anlegen")
async def create_entry(
    body: CalendarEntryIn, request: Request, principal: TenantPrincipal = Depends(member)
) -> CalendarItem:
    if body.ends_on and body.ends_on < body.starts_on:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ende liegt vor dem Beginn.")
    if body.target == "internal":
        async with tenant_tx(request, principal) as session:
            fields = body.model_dump(
                exclude={
                    "starts_at",
                    "ends_at",
                    "target",
                    "location",
                    "attendees",
                    "source_type",
                    "source_id",
                    "recurrence",
                }
            )
            if body.recurrence is not None and body.recurrence.until < body.starts_on:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Ende der Wiederholung liegt vor dem Beginn."
                )
            fields["recurrence"] = (
                body.recurrence.model_dump(mode="json") if body.recurrence else None
            )
            entry = CalendarEntry(
                tenant_id=principal.tenant_id,
                owner_user_id=principal.user_id,
                created_by=principal.user_id,
                **fields,
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
                source="internal",
                reminders=[str(r) for r in entry.reminders],
                calendar_entry_id=entry.id,
                recurrence=entry.recurrence,
            )

    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        default_mailbox, own_mailbox = await _resolve_calendars(session, principal)
        mailbox = default_mailbox if body.target == "default" else own_mailbox
        if mailbox is None or not mailbox.calendar_enabled:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für dieses Ziel ist kein verbundener Google-Kalender vorhanden.",
            )
        client = await _write_client(session, settings, mailbox)
        try:
            # Rule M23-05 ("Einladungen nur nach Bestätigung"): created without attendees and
            # sendUpdates=none regardless; attendees are only ever sent via the separate,
            # explicitly confirmed invite endpoint below.
            event = await client.insert_event(
                mailbox.calendar_id, _entry_body(body), send_updates="none"
            )
        except (gcal.GCalError, httpx.HTTPError) as exc:
            raise _google_problem(exc) from exc
        finally:
            await client.aclose()
        start, _end = _event_dates(event)
        link = CalendarEvent(
            tenant_id=principal.tenant_id,
            mailbox_id=mailbox.id,
            google_event_id=event["id"],
            source_type=body.source_type,
            source_id=body.source_id,
            title=body.title,
            starts_at=body.starts_at or datetime.combine(start, dt.time(9, 0), tzinfo=UTC),
            ends_at=body.ends_at,
            location=body.location,
            attendees=body.attendees,
            status="draft",
            etag=event.get("etag"),
            last_synced_at=datetime.now(UTC),
            created_by=principal.user_id,
        )
        session.add(link)
        await session.flush()
        await _bump_version(request, principal.tenant_id, mailbox.id)
        return _google_item(
            event, body.target, _google_label(body.target, mailbox.address), mailbox.id, link
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


async def _google_mailbox_for(session: Any, principal: TenantPrincipal, source: str) -> Mailbox:
    if source not in ("default", "own"):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Kalenderquelle.")
    default_mailbox, own_mailbox = await _resolve_calendars(session, principal)
    mailbox = default_mailbox if source == "default" else own_mailbox
    if mailbox is None or not mailbox.calendar_enabled:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return mailbox


async def _link_for(session: Any, mailbox_id: uuid.UUID, event_id: str) -> CalendarEvent | None:
    result = await session.scalar(
        select(CalendarEvent).where(
            CalendarEvent.mailbox_id == mailbox_id, CalendarEvent.google_event_id == event_id
        )
    )
    return result  # type: ignore[no-any-return]


class CalendarInviteIn(_In):
    confirm: bool = Field(description="Muss true sein: ausdrückliche Bestätigung des Nutzers.")


@router.post(
    "/calendar/google/{source}/{event_id}/invite",
    summary="Einladung an externe Teilnehmer senden (nur nach Bestätigung)",
)
async def send_invite(
    source: str,
    event_id: str,
    body: CalendarInviteIn,
    request: Request,
    principal: TenantPrincipal = Depends(member),
) -> CalendarItem:
    # Rule M23-05: no automatic invitations. This endpoint is the only path that sets
    # sendUpdates=all, and only after the staff user's explicit confirmation, recorded below.
    if not body.confirm:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Bestätigung erforderlich.")
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        mailbox = await _google_mailbox_for(session, principal, source)
        link = await _link_for(session, mailbox.id, event_id)
        if link is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND,
                detail="Kein verknüpfter Termin für Einladungen gefunden.",
            )
        if not link.attendees:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Teilnehmer hinterlegt.")
        client = await _write_client(session, settings, mailbox)
        try:
            event = await client.patch_event(
                mailbox.calendar_id,
                event_id,
                {"attendees": link.attendees},
                send_updates="all",
            )
        except (gcal.GCalError, httpx.HTTPError) as exc:
            raise _google_problem(exc) from exc
        finally:
            await client.aclose()
        link.status = "invited"
        link.invite_confirmed_by = principal.user_id
        link.invite_confirmed_at = datetime.now(UTC)
        link.etag = event.get("etag")
        link.last_synced_at = datetime.now(UTC)
        link.is_stale = False
        await _bump_version(request, principal.tenant_id, mailbox.id)
        return _google_item(event, source, _google_label(source, mailbox.address), mailbox.id, link)


@router.patch("/calendar/google/{source}/{event_id}", summary="Google-Termin ändern")
async def patch_google_entry(
    source: str,
    event_id: str,
    body: GoogleCalendarPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(member),
) -> CalendarItem:
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        mailbox = await _google_mailbox_for(session, principal, source)
        link = await _link_for(session, mailbox.id, event_id)
        if link is not None and link.is_stale:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    "Termin wurde extern geändert (abweichender Google-Stand). Bitte zuerst "
                    "die Google-Version prüfen, keine automatische Überschreibung."
                ),
            )
        patch: dict[str, Any] = {}
        if body.title is not None:
            patch["summary"] = body.title
        if body.notes is not None:
            patch["description"] = body.notes
        if body.starts_at is not None:
            patch["start"] = {"dateTime": body.starts_at.isoformat()}
        elif body.starts_on is not None:
            if body.all_day is False:
                patch["start"] = {
                    "dateTime": datetime.combine(
                        body.starts_on, dt.time(9, 0), tzinfo=UTC
                    ).isoformat()
                }
            else:
                patch["start"] = {"date": body.starts_on.isoformat()}
        if body.ends_at is not None:
            patch["end"] = {"dateTime": body.ends_at.isoformat()}
        elif body.ends_on is not None:
            if body.all_day is False:
                patch["end"] = {
                    "dateTime": datetime.combine(
                        body.ends_on, dt.time(10, 0), tzinfo=UTC
                    ).isoformat()
                }
            else:
                patch["end"] = {"date": (body.ends_on + timedelta(days=1)).isoformat()}
        if not patch:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Änderung angegeben.")
        client = await _write_client(session, settings, mailbox)
        try:
            event = await client.patch_event(
                mailbox.calendar_id, event_id, patch, send_updates="none"
            )
        except (gcal.GCalError, httpx.HTTPError) as exc:
            raise _google_problem(exc) from exc
        finally:
            await client.aclose()
        if link is not None:
            link.etag = event.get("etag")
            link.last_synced_at = datetime.now(UTC)
        await _bump_version(request, principal.tenant_id, mailbox.id)
        return _google_item(event, source, _google_label(source, mailbox.address), mailbox.id, link)


@router.delete(
    "/calendar/google/{source}/{event_id}", status_code=204, summary="Google-Termin löschen"
)
async def delete_google_entry(
    source: str, event_id: str, request: Request, principal: TenantPrincipal = Depends(member)
) -> None:
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        mailbox = await _google_mailbox_for(session, principal, source)
        # Cancelling notifies attendees only when invitations were actually sent before.
        link = await _link_for(session, mailbox.id, event_id)
        send_updates = "all" if link is not None and link.status == "invited" else "none"
        client = await _write_client(session, settings, mailbox)
        try:
            await client.delete_event(mailbox.calendar_id, event_id, send_updates=send_updates)
        except (gcal.GCalError, httpx.HTTPError) as exc:
            raise _google_problem(exc) from exc
        finally:
            await client.aclose()
        if link is not None:
            await session.delete(link)
        await _bump_version(request, principal.tenant_id, mailbox.id)


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
    body: WorkspaceBulkIn, request: Request, principal: TenantPrincipal = Depends(member)
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
        elif body.action == "tickets.assign":
            # M9-04: primary assignee for several tickets, through the ticket service so that
            # history, notification and domain event stay as with a single assignment.
            from mhvp.platform.models import Membership, MembershipStatus
            from mhvp.tickets.models import Ticket
            from mhvp.tickets.status import assign_ticket

            _need(principal, "tickets:update")
            if body.assignee_user_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Bearbeiter fehlt.")
            tickets = (
                await session.scalars(select(Ticket).where(Ticket.id.in_(ids)).with_for_update())
            ).all()
            if len(tickets) != len(ids):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Tickets.")
            member = await session.scalar(
                select(Membership.id).where(
                    Membership.tenant_id == principal.tenant_id,
                    Membership.user_id == body.assignee_user_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
            if member is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Bearbeiter ist kein Mitglied.")
            if any(t.merged_into_ticket_id is not None for t in tickets):
                raise ProblemError(ErrorCodes.CONFLICT, detail="Ticket ist zusammengeführt.")
            changed = 0
            for ticket in tickets:
                if await assign_ticket(
                    session, ticket, body.assignee_user_id, principal.user_id, reason="sammelaktion"
                ):
                    changed += 1
        elif body.action.startswith("documents."):
            # M9-04: several documents at once; same checks and side effects as the single
            # PATCH and link endpoints (retention profile of the category, mirror refresh).
            changed = await _bulk_documents(session, principal, body, ids)
        elif body.action == "deadline_entries.done":
            # M9-04: tasks (user created deadlines) to done; same effect as the single action.
            from mhvp.workspace import deadlines
            from mhvp.workspace.models import DeadlineEntry

            _need(principal, "tickets:update")
            entries = (
                await session.scalars(
                    select(DeadlineEntry).where(DeadlineEntry.id.in_(ids)).with_for_update()
                )
            ).all()
            if len(entries) != len(ids):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Fristen.")
            changed = 0
            for entry in entries:
                if entry.status != "done":
                    entry.status = "done"
                    entry.done_at = datetime.now(UTC)
                    entry.done_by = principal.user_id
                    entry.updated_by = principal.user_id
                    await deadlines.close_mirror(session, entry)
                    changed += 1
        else:
            _need(principal, "properties:update")
            items = (
                await session.scalars(select(MaintenanceItem).where(MaintenanceItem.id.in_(ids)))
            ).all()
            if len(items) != len(ids):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Wartungen.")
            from mhvp.properties import services as property_services

            # Same rule as the single completion (C2-01): with an interval the item stays open
            # and the due date moves to done_on plus the interval, otherwise it is closed.
            done_on = body.done_on or services.local_today()
            changed = 0
            for item in items:
                if item.status == "done":
                    continue
                previous_due = item.due_date
                item.done_at = property_services.done_at_for(done_on)
                next_due = None
                if item.interval_months:
                    next_due = property_services.add_months(done_on, item.interval_months)
                    item.due_date = next_due
                else:
                    item.status = "done"
                item.updated_by = principal.user_id
                changed += 1
                await emit(
                    session,
                    tenant_id=principal.tenant_id,
                    type="maintenance.done",
                    entity_type="maintenance_item",
                    entity_id=item.id,
                    actor_user_id=principal.user_id,
                    payload={
                        "done_on": done_on.isoformat(),
                        "previous_due_date": previous_due.isoformat() if previous_due else None,
                        "next_due_date": next_due.isoformat() if next_due else None,
                        "status": item.status,
                        "bulk": True,
                    },
                )
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


async def _bulk_documents(
    session: AsyncSession, principal: TenantPrincipal, body: WorkspaceBulkIn, ids: list[uuid.UUID]
) -> int:
    from mhvp.documents import retention
    from mhvp.documents import services as document_services
    from mhvp.documents.models import (
        Document,
        DocumentCategory,
        DocumentLink,
        LinkRole,
    )
    from mhvp.properties.models import Property

    _need(principal, "documents:update")
    documents = (
        await session.scalars(select(Document).where(Document.id.in_(ids)).with_for_update())
    ).all()
    if len(documents) != len(ids):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Dokumente.")
    changed = 0
    if body.action == "documents.set_category":
        if body.category_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kategorie fehlt.")
        if await session.get(DocumentCategory, body.category_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannte Kategorie.")
        profile = await retention.profile_for_category(session, body.category_id)
        for document in documents:
            if document.category_id == body.category_id:
                continue
            document.category_id = body.category_id
            document.updated_by = principal.user_id
            if profile is not None:
                await retention.assign_profile(session, document, profile)
            await document_services.mark_mirrors_dirty(session, document.id)
            changed += 1
    elif body.action == "documents.link_property":
        if body.property_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Objekt fehlt.")
        if await session.get(Property, body.property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekanntes Objekt.")
        linked = set(
            await session.scalars(
                select(DocumentLink.document_id).where(
                    DocumentLink.document_id.in_(ids),
                    DocumentLink.entity_type == "property",
                    DocumentLink.entity_id == body.property_id,
                    DocumentLink.role == LinkRole.ATTACHMENT,
                )
            )
        )
        for document in documents:
            if document.id in linked:
                continue
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=document.id,
                    entity_type="property",
                    entity_id=body.property_id,
                    role=LinkRole.ATTACHMENT,
                )
            )
            await document_services.mark_mirrors_dirty(session, document.id)
            changed += 1
    else:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Aktion.")
    return changed


# Ticket analytics (operator 26.09.2026) -----------------------------------------------------


async def _analytics_admin(principal: TenantPrincipal = Depends(STATS_READ)) -> TenantPrincipal:
    """Operator 27.09.2026: the ticket analytics are visible to tenant administrators only.
    Administrator marker is the existing rule M2-07 (``tickets:delete`` is held by
    ``tenant_admin``, ``administrator`` and the platform administrator after a tenant switch,
    see ``mhvp.tickets.routers._may_skip_flow``); a platform administrator is always included."""
    if not (principal.has("tickets:delete") or principal.is_platform_admin):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Die Auswertung Tickets ist Mandantenadministratoren vorbehalten.",
            developer_message="Missing permission tickets:delete (tenant administrator).",
        )
    return principal


ANALYTICS_READ = _analytics_admin

_TA_RANGE_PATTERN = "^(" + "|".join(ticket_analytics_module.RANGES) + ")$"
_TA_BUCKET_PATTERN = "^(" + "|".join(ticket_analytics_module.BUCKETS) + ")$"
_TA_KIND_PATTERN = "^(" + "|".join(ticket_analytics_module.MAILBOX_KINDS) + ")$"


@router.get(
    "/ticket-analytics",
    summary="Auswertung Tickets und Mails: Durchsatz, Rückstand, Reaktionszeiten",
)
async def ticket_analytics(
    request: Request,
    range: str = Query(default="week", pattern=_TA_RANGE_PATTERN),
    bucket: str = Query(default="auto", pattern=_TA_BUCKET_PATTERN),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    user_id: uuid.UUID | None = None,
    mailbox_id: uuid.UUID | None = None,
    mailbox_kind: str = Query(default="all", pattern=_TA_KIND_PATTERN),
    principal: TenantPrincipal = Depends(ANALYTICS_READ),
) -> dict[str, Any]:
    """Orientierungswerte je Zeitscheibe (Europe/Berlin) und in Summe; Definitionen im
    Modul ``mhvp.workspace.ticket_analytics`` und im Handbuchkapitel Auswertung Tickets.
    ``from``/``to`` nur bei ``range=custom`` (höchstens 400 Tage). Nur für
    Mandantenadministratoren (``tickets:delete`` nach Regel M2-07) und Plattformadministratoren
    (Betreiber 27.09.2026)."""
    try:
        window = ticket_analytics_module.build_window(
            range, services.local_today(), unit=bucket, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    async with tenant_tx(request, principal) as session:
        mailboxes = await ticket_analytics_module.resolve_mailboxes(session)
        mailbox_ids: set[uuid.UUID] | None = None
        if mailbox_kind != "all":
            mailbox_ids = {m["mailbox_id"] for m in mailboxes if m["kind"] == mailbox_kind}
        if mailbox_id is not None:
            mailbox_ids = {mailbox_id} & (mailbox_ids if mailbox_ids is not None else {mailbox_id})
        filters = ticket_analytics_module.Filters(user_id=user_id, mailbox_ids=mailbox_ids)
        return await ticket_analytics_module.compute(session, window, filters, mailboxes)
