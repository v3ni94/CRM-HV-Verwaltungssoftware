"""Workspace endpoints (/api/v1/workspace, M9)."""

import datetime as dt
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select, update

from mhvp.communication import gcal, gmail
from mhvp.communication.models import Mailbox, MailboxUser
from mhvp.core.auth.principal import TenantPrincipal, get_principal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace import jobs, services
from mhvp.workspace.models import CalendarEntry, CalendarEvent, Notification, SavedFilter

router = APIRouter(prefix="/workspace", tags=["Arbeitsplatz"])

FILTER_RESOURCES = ("contacts", "properties", "units", "contracts", "documents", "imports")
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


class CalendarNotice(BaseModel):
    source: str  # default | own
    address: str
    connected: bool  # calendar_enabled and a refresh token is stored


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
    from mhvp.tickets.models import Ticket, TicketStatus

    today = services.local_today()
    start, end = _stats_bounds(range, today)
    start_dt = datetime.combine(start, dt.time.min, tzinfo=UTC)
    end_dt = datetime.combine(end + timedelta(days=1), dt.time.min, tzinfo=UTC)
    async with tenant_tx(request, principal) as session:
        base = select(Ticket)
        if user_id is not None:
            base = base.where(Ticket.assignee_user_id == user_id)
        tickets = (await session.scalars(base)).all()

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


# Digest and deadlines (A40, A41) ------------------------------------------------------


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


@router.get("/deadlines", summary="Fristenliste des Mandanten (A41, Orientierung, zu prüfen)")
async def deadlines(
    request: Request,
    kind: str | None = Query(default=None, pattern="^(" + "|".join(jobs.DEADLINE_KINDS) + ")$"),
    status: str = Query(default="open", pattern="^(open|done|all)$"),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(member),
) -> list[DeadlineOut]:
    """Only kinds the caller may read (contracts, properties, accounting, documents)."""
    from mhvp.workspace.models import ComplianceDeadline

    allowed = [k for k, (read, _u) in jobs.DEADLINE_PERMISSIONS.items() if principal.has(read)]
    if kind is not None:
        allowed = [k for k in allowed if k == kind]
    if not allowed:
        return []
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
        return [DeadlineOut.model_validate(r) for r in rows]


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
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gcal.make_client(client_id, client_secret, mailbox)
        try:
            time_min = datetime.combine(start, dt.time.min, tzinfo=UTC)
            time_max = datetime.combine(end + timedelta(days=1), dt.time.min, tzinfo=UTC)
            events = await client.list_events(mailbox.calendar_id, time_min, time_max)
        finally:
            await client.aclose()
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
                source="internal",
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
        items += [CalendarItem(**d, source="internal") for d in derived]

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
                }
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
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gcal.make_client(client_id, client_secret, mailbox)
        try:
            # Rule M23-05 ("Einladungen nur nach Bestätigung"): created without attendees and
            # sendUpdates=none regardless; attendees are only ever sent via the separate,
            # explicitly confirmed invite endpoint below.
            event = await client.insert_event(
                mailbox.calendar_id, _entry_body(body), send_updates="none"
            )
        except gcal.GCalError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
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
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gcal.make_client(client_id, client_secret, mailbox)
        try:
            event = await client.patch_event(
                mailbox.calendar_id,
                event_id,
                {"attendees": link.attendees},
                send_updates="all",
            )
        except gcal.GCalError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
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
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gcal.make_client(client_id, client_secret, mailbox)
        try:
            event = await client.patch_event(
                mailbox.calendar_id, event_id, patch, send_updates="none"
            )
        except gcal.GCalError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
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
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gcal.make_client(client_id, client_secret, mailbox)
        try:
            await client.delete_event(mailbox.calendar_id, event_id, send_updates=send_updates)
        except gcal.GCalError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
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
