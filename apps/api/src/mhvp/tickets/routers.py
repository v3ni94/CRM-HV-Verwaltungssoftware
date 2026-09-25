"""Tickets and work orders (/api/v1/tickets, /api/v1/work-orders, M19): ticket to order to
invoice end to end. Payment stays in accounting (M14/M15); board status never pays."""

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, cast, func, select, update
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import (
    OrderStatus,
    Priority,
    Team,
    Ticket,
    TicketComment,
    TicketEvent,
    TicketSource,
    TicketStatus,
    TicketTemplate,
    WorkOrder,
    WorkOrderEvent,
)
from mhvp.workspace.services import notify

router = APIRouter(tags=["Tickets und Aufträge"])
READ = require_permission("tickets:read")
CREATE = require_permission("tickets:create")
UPDATE = require_permission("tickets:update")
APPROVE = require_permission("tickets:approve")

# SLA default per priority in hours when no template sets one (product standard, A-031).
SLA_HOURS = {
    Priority.IMMEDIATE: 4,
    Priority.URGENT: 24,
    Priority.HIGH: 72,
    Priority.NORMAL: 168,
    Priority.LOW: 336,
}
TICKET_FLOW = {
    TicketStatus.NEW: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING,
        TicketStatus.REJECTED,
        TicketStatus.DONE,
    },
    TicketStatus.IN_PROGRESS: {TicketStatus.WAITING, TicketStatus.DONE, TicketStatus.REJECTED},
    TicketStatus.WAITING: {TicketStatus.IN_PROGRESS, TicketStatus.DONE, TicketStatus.REJECTED},
    TicketStatus.DONE: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.CLOSED: set(),
    TicketStatus.REJECTED: {TicketStatus.IN_PROGRESS},
}
ORDER_FLOW = {
    OrderStatus.DRAFT: {OrderStatus.REQUESTED, OrderStatus.CANCELLED},
    OrderStatus.REQUESTED: {
        OrderStatus.QUOTED,
        OrderStatus.APPROVED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.QUOTED: {OrderStatus.APPROVED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.APPROVED: {OrderStatus.SCHEDULED, OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED},
    OrderStatus.SCHEDULED: {OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED},
    OrderStatus.IN_PROGRESS: {OrderStatus.DONE},
    OrderStatus.DONE: {OrderStatus.INVOICED, OrderStatus.ACCEPTED},
    OrderStatus.INVOICED: {OrderStatus.ACCEPTED},
    OrderStatus.ACCEPTED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
}


def _valid_iban(value: str) -> bool:
    """Rein formale Prüfung (Struktur + Mod 97, ISO 13616), keine Existenzprüfung."""
    v = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", v):
        return False
    digits = "".join(str(int(c, 36)) for c in v[4:] + v[:4])
    return int(digits) % 97 == 1


def _check_extra_fields(tpl: TicketTemplate | None, extra: dict[str, str]) -> dict[str, str]:
    """Validate the template's configured extra fields (e.g. IBAN on a deposit ticket) and
    return the normalized values; unknown keys are rejected to keep the data deliberate."""
    fields = {f["key"]: f for f in (tpl.required_fields if tpl else [])}
    unknown = sorted(set(extra) - set(fields))
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Zusatzfelder: {', '.join(unknown)}."
        )
    out: dict[str, str] = {}
    for key, field in fields.items():
        value = (extra.get(key) or "").strip()
        if not value:
            if field.get("required", True):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Pflichtfeld fehlt: {field.get('label', key)}.",
                )
            continue
        if field.get("kind") == "iban":
            if not _valid_iban(value):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"{field.get('label', key)}: keine gültige IBAN (formale Prüfung).",
                )
            value = re.sub(r"\s+", "", value).upper()
        out[key] = value[:500]
    return out


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeamIn(_In):
    name: str = Field(min_length=1, max_length=100)
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class TemplateField(_In):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["text", "iban"] = "text"
    required: bool = True


class TicketTemplateIn(_In):
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    default_priority: Priority = Priority.NORMAL
    default_team_id: uuid.UUID | None = None
    default_assignee_user_id: uuid.UUID | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=8760)
    required_fields: list[TemplateField] = Field(default_factory=list, max_length=20)


class TicketIn(_In):
    title: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    extra_fields: dict[str, str] = Field(default_factory=dict)
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    public_description: str | None = Field(default=None, max_length=20000)
    internal_description: str | None = Field(default=None, max_length=20000)
    priority: Priority | None = None
    initiator_contact_id: uuid.UUID | None = None
    source: TicketSource = TicketSource.MANUAL
    visible_for: list[str] = Field(default_factory=list)


class TicketPatch(_In):
    status: TicketStatus | None = None
    priority: Priority | None = None
    assignee_user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    time_spent_minutes: int | None = Field(default=None, ge=0)
    checklist_done: list[int] | None = None


class CommentIn(_In):
    body: str = Field(min_length=1, max_length=20000)
    internal: bool = True
    document_ids: list[uuid.UUID] = Field(default_factory=list)


class WorkOrderIn(_In):
    ticket_id: uuid.UUID | None = None
    property_id: uuid.UUID
    provider_contact_id: uuid.UUID
    description: str = Field(min_length=3, max_length=20000)
    budget_limit: Decimal | None = Field(default=None, ge=0)
    requires_board_approval: bool = False


class OrderStep(_In):
    status: OrderStatus
    note: str | None = Field(default=None, max_length=4000)
    quote_amount: Decimal | None = Field(default=None, ge=0)
    quote_document_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    completion_report: str | None = Field(default=None, max_length=20000)
    photo_document_ids: list[uuid.UUID] | None = None
    invoice_id: uuid.UUID | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    rating_comment: str | None = Field(default=None, max_length=4000)


class TicketMergeIn(_In):
    ticket_ids: list[uuid.UUID] = Field(min_length=2)
    title: str | None = Field(default=None, max_length=300)


def _ticket_out(t: Ticket) -> dict[str, Any]:
    return {
        k: getattr(t, k)
        for k in (
            "id",
            "number",
            "property_id",
            "unit_id",
            "category",
            "title",
            "public_description",
            "status",
            "priority",
            "assignee_user_id",
            "team_id",
            "initiator_contact_id",
            "source",
            "checklist",
            "sla_due_at",
            "resolved_at",
            "time_spent_minutes",
            "merged_into_ticket_id",
            "extra_fields",
            "created_at",
        )
    } | {
        "sla_breached": bool(
            t.sla_due_at and not t.resolved_at and datetime.now(UTC) > t.sla_due_at
        )
    }


def _order_out(o: WorkOrder) -> dict[str, Any]:
    return {
        k: getattr(o, k)
        for k in (
            "id",
            "ticket_id",
            "property_id",
            "provider_contact_id",
            "description",
            "budget_limit",
            "requires_board_approval",
            "status",
            "quote_amount",
            "quote_document_id",
            "approved_by",
            "scheduled_at",
            "completion_report",
            "photo_document_ids",
            "invoice_id",
            "rating",
            "rating_comment",
        )
    }


async def _event(
    session: AsyncSession, ticket: Ticket, kind: str, user: uuid.UUID | None, data: dict[str, Any]
) -> None:
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id, ticket_id=ticket.id, kind=kind, user_id=user, data=data
        )
    )


@router.post("/teams", status_code=201, summary="Team anlegen")
async def create_team(
    body: TeamIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        team = Team(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(team)
        await session.flush()
        return {"id": team.id, "name": team.name}


@router.post("/ticket-templates", status_code=201, summary="Ticketvorlage mit Routing und SLA")
async def create_template(
    body: TicketTemplateIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = TicketTemplate(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(tpl)
        await session.flush()
        return {"id": tpl.id, "category": tpl.category}


def _template_out(tpl: TicketTemplate) -> dict[str, Any]:
    return {
        k: getattr(tpl, k)
        for k in (
            "id",
            "category",
            "title",
            "checklist",
            "default_priority",
            "default_team_id",
            "default_assignee_user_id",
            "sla_hours",
            "required_fields",
        )
    }


@router.get("/ticket-templates", summary="Ticketvorlagen")
async def list_templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(TicketTemplate).order_by(TicketTemplate.category))
        ).all()
        return [_template_out(t) for t in rows]


@router.patch("/ticket-templates/{template_id}", summary="Ticketvorlage ändern")
async def patch_template(
    template_id: uuid.UUID,
    body: TicketTemplateIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketTemplate, template_id, with_for_update=True)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump().items():
            setattr(tpl, key, value)
        await session.flush()
        return _template_out(tpl)


@router.delete("/ticket-templates/{template_id}", status_code=204, summary="Ticketvorlage löschen")
async def delete_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> None:
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketTemplate, template_id, with_for_update=True)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        used = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.template_id == template_id)
        )
        if used:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    f"Vorlage wird von {used} Tickets verwendet und bleibt aus "
                    "Nachvollziehbarkeitsgründen erhalten."
                ),
            )
        await session.delete(tpl)


@router.post("/tickets", status_code=201, summary="Ticket anlegen (Vorlage, Routing, SLA)")
async def create_ticket(
    body: TicketIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = (
            await session.scalar(
                select(TicketTemplate).where(TicketTemplate.category == body.category)
            )
            if body.category
            else None
        )
        title = body.title or (tpl.title if tpl else None)
        if not title:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Titel fehlt.")
        extra_fields = _check_extra_fields(tpl, body.extra_fields)
        priority = body.priority or (tpl.default_priority if tpl else Priority.NORMAL)
        hours = tpl.sla_hours if tpl and tpl.sla_hours else SLA_HOURS[priority]
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            template_id=tpl.id if tpl else None,
            title=title,
            priority=priority,
            team_id=tpl.default_team_id if tpl else None,
            assignee_user_id=tpl.default_assignee_user_id if tpl else None,
            checklist=[{"text": c, "done": False} for c in (tpl.checklist if tpl else [])],
            sla_due_at=datetime.now(UTC) + timedelta(hours=hours),
            extra_fields=extra_fields,
            **body.model_dump(exclude={"title", "priority", "extra_fields"}),
        )
        session.add(ticket)
        await session.flush()
        await _event(
            session,
            ticket,
            "created",
            principal.user_id,
            {"routing": "template" if tpl else "manual"},
        )
        if ticket.assignee_user_id:
            await notify(
                session,
                tenant_id=principal.tenant_id,
                user_id=ticket.assignee_user_id,
                kind="ticket_assigned",
                title=f"Ticket {ticket.number}: {ticket.title}",
                entity_type="ticket",
                entity_id=ticket.id,
            )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.created",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=principal.user_id,
            payload={"number": ticket.number, "source": ticket.source.value},
        )
        await session.flush()
        return _ticket_out(ticket)


@router.post("/tickets/merge", status_code=201, summary="Tickets zusammenführen")
async def merge_tickets(
    body: TicketMergeIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    from mhvp.communication.models import Message

    ids = list(dict.fromkeys(body.ticket_ids))
    async with tenant_tx(request, principal) as session:
        sources = (
            await session.scalars(select(Ticket).where(Ticket.id.in_(ids)).with_for_update())
        ).all()
        if len(sources) != len(ids):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Ticket nicht gefunden.")
        by_id = {t.id: t for t in sources}
        sources = [by_id[i] for i in ids]
        if len({t.tenant_id for t in sources}) != 1:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Tickets gehören zu unterschiedlichen Mandanten."
            )
        for t in sources:
            if t.status is TicketStatus.CLOSED or t.merged_into_ticket_id is not None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=f"Ticket {t.number} ist bereits geschlossen oder zusammengeführt.",
                )
        oldest = min(sources, key=lambda t: t.created_at)
        priority = max((t.priority for t in sources), key=list(Priority).index)
        due_candidates = [t.sla_due_at for t in sources if t.sla_due_at is not None]
        sla_due_at = min(due_candidates) if due_candidates else None

        def _first(field: str) -> Any:
            value = getattr(oldest, field)
            if value is not None:
                return value
            for t in sources:
                value = getattr(t, field)
                if value is not None:
                    return value
            return None

        merged = Ticket(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            property_id=_first("property_id"),
            unit_id=_first("unit_id"),
            template_id=_first("template_id"),
            category=_first("category"),
            title=body.title or oldest.title,
            public_description=_first("public_description"),
            internal_description=_first("internal_description"),
            status=TicketStatus.NEW,
            priority=priority,
            assignee_user_id=_first("assignee_user_id"),
            team_id=_first("team_id"),
            initiator_contact_id=_first("initiator_contact_id"),
            source=oldest.source,
            # Union: whoever could see any source must still see the merged ticket.
            visible_for=sorted({v for t in sources for v in t.visible_for}),
            sla_due_at=sla_due_at,
        )
        session.add(merged)
        await session.flush()

        for t in sources:
            await session.execute(
                update(TicketComment)
                .where(TicketComment.ticket_id == t.id)
                .values(ticket_id=merged.id)
            )
            await session.execute(
                update(TicketEvent).where(TicketEvent.ticket_id == t.id).values(ticket_id=merged.id)
            )
            await session.execute(
                update(Message).where(Message.ticket_id == t.id).values(ticket_id=merged.id)
            )
            await _event(
                session,
                merged,
                "merged_from",
                principal.user_id,
                {"ticket_id": str(t.id), "number": t.number},
            )
            await _event(
                session,
                t,
                "merged_into",
                principal.user_id,
                {"ticket_id": str(merged.id), "number": merged.number},
            )
            t.status = TicketStatus.CLOSED
            t.resolved_at = datetime.now(UTC)
            t.merged_into_ticket_id = merged.id

        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.merged",
            entity_type="ticket",
            entity_id=merged.id,
            actor_user_id=principal.user_id,
            payload={"number": merged.number, "source_ticket_ids": [str(t.id) for t in sources]},
        )
        await session.flush()
        return _ticket_out(merged) | {"merged_ticket_ids": [t.id for t in sources]}


@router.get("/tickets", summary="Tickets")
async def list_tickets(
    request: Request,
    status: TicketStatus | None = None,
    property_id: uuid.UUID | None = None,
    mine: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Ticket).order_by(Ticket.number.desc())
        if status:
            query = query.where(Ticket.status == status)
        if property_id:
            query = query.where(Ticket.property_id == property_id)
        if mine:
            query = query.where(Ticket.assignee_user_id == principal.user_id)
        return [_ticket_out(t) for t in (await session.scalars(query.limit(limit))).all()]


OPEN_STATUSES = (TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING)
STATS_TZ = "Europe/Berlin"


def _bucket_start(interval: str, day: date) -> date:
    if interval == "day":
        return day
    if interval == "week":
        return day - timedelta(days=day.weekday())
    if interval == "month":
        return day.replace(day=1)
    if interval == "quarter":
        return day.replace(month=((day.month - 1) // 3) * 3 + 1, day=1)
    return day.replace(month=1, day=1)


def _bucket_back(interval: str, start: date, steps: int) -> date:
    if interval == "day":
        return start - timedelta(days=steps)
    if interval == "week":
        return start - timedelta(weeks=steps)
    if interval == "quarter":
        steps *= 3
    if interval == "year":
        return start.replace(year=start.year - steps)
    months = (start.year * 12 + start.month - 1) - steps
    return date(months // 12, months % 12 + 1, 1)


@router.get("/tickets/stats", summary="Ticketauswertung: Bestand, Zeitreihe, je Bearbeiter")
async def ticket_stats(
    request: Request,
    interval: Literal["day", "week", "month", "quarter", "year"] = "week",
    periods: int = Query(default=12, ge=1, le=60),
    assignee_user_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Dashboard numbers: current stock by status, created/resolved per period (local time,
    Europe/Berlin) and totals per assignee for the whole tenant. assignee_user_id narrows the
    stock and the series; the per-user comparison always covers the tenant."""
    today = datetime.now(UTC).astimezone(ZoneInfo(STATS_TZ)).date()
    window_start = _bucket_back(interval, _bucket_start(interval, today), periods - 1)
    starts = sorted(
        _bucket_back(interval, _bucket_start(interval, today), i) for i in range(periods)
    )

    def scoped(*where: Any) -> Any:
        query = select(func.count()).select_from(Ticket).where(*where)
        if assignee_user_id:
            query = query.where(Ticket.assignee_user_id == assignee_user_id)
        return query

    def local_day(column: Any) -> Any:
        return cast(func.date_trunc(interval, func.timezone(STATS_TZ, column)), Date)

    async with tenant_tx(request, principal) as session:
        by_status = {s.value: 0 for s in TicketStatus}
        rows = await session.execute(
            scoped().with_only_columns(Ticket.status, func.count()).group_by(Ticket.status)
        )
        for status, count in rows:
            by_status[status.value] = int(count)

        series = {d: {"created": 0, "resolved": 0} for d in starts}
        created_rows = await session.execute(
            scoped(func.timezone(STATS_TZ, Ticket.created_at) >= window_start)
            .with_only_columns(local_day(Ticket.created_at), func.count())
            # GROUP BY 1: the truncation carries bind parameters, so a repeated expression
            # would not compare equal on the server (SQLSTATE 42803).
            .group_by(sql_text("1"))
        )
        for day, count in created_rows:
            if day in series:
                series[day]["created"] = int(count)
        resolved_rows = await session.execute(
            scoped(
                Ticket.resolved_at.is_not(None),
                func.timezone(STATS_TZ, Ticket.resolved_at) >= window_start,
            )
            .with_only_columns(local_day(Ticket.resolved_at), func.count())
            .group_by(sql_text("1"))
        )
        for day, count in resolved_rows:
            if day in series:
                series[day]["resolved"] = int(count)

        # Comparison per assignee over the whole tenant (open stock and resolved in window).
        per_user: dict[uuid.UUID | None, dict[str, int]] = {}
        open_rows = await session.execute(
            select(Ticket.assignee_user_id, func.count())
            .where(Ticket.status.in_(OPEN_STATUSES))
            .group_by(Ticket.assignee_user_id)
        )
        for user_id, count in open_rows:
            per_user.setdefault(user_id, {"open": 0, "resolved": 0})["open"] = int(count)
        user_resolved = await session.execute(
            select(Ticket.assignee_user_id, func.count())
            .where(
                Ticket.resolved_at.is_not(None),
                func.timezone(STATS_TZ, Ticket.resolved_at) >= window_start,
            )
            .group_by(Ticket.assignee_user_id)
        )
        for user_id, count in user_resolved:
            per_user.setdefault(user_id, {"open": 0, "resolved": 0})["resolved"] = int(count)

        # Display names come from the platform user table (no RLS, section 5.3).
        from mhvp.platform.models import User

        ids = [u for u in per_user if u is not None]
        names: dict[uuid.UUID, str] = {}
        if ids:
            name_rows = await session.execute(
                select(User.id, User.display_name).where(User.id.in_(ids))
            )
            for row_id, display_name in name_rows:
                names[row_id] = display_name

    return {
        "interval": interval,
        "periods": periods,
        "window_start": window_start.isoformat(),
        "open_total": sum(by_status[s.value] for s in OPEN_STATUSES),
        "by_status": by_status,
        "series": [{"start": d.isoformat(), **series[d]} for d in starts],
        "by_user": sorted(
            (
                {
                    "user_id": str(u) if u else None,
                    "name": names.get(u) if u else None,
                    "open": v["open"],
                    "resolved": v["resolved"],
                }
                for u, v in per_user.items()
            ),
            key=lambda r: (-r["resolved"], -r["open"]),
        ),
    }


@router.patch("/tickets/{ticket_id}", summary="Status, Zuweisung, Checkliste")
async def patch_ticket(
    ticket_id: uuid.UUID,
    body: TicketPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id, with_for_update=True)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.status and body.status is not ticket.status:
            if body.status not in TICKET_FLOW[ticket.status]:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=f"Wechsel {ticket.status.value} nach {body.status.value} unzulässig.",
                )
            await _event(
                session,
                ticket,
                "status",
                principal.user_id,
                {"from": ticket.status.value, "to": body.status.value},
            )
            ticket.status = body.status
            ticket.resolved_at = (
                datetime.now(UTC)
                if body.status in (TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED)
                else None
            )
        if body.assignee_user_id and body.assignee_user_id != ticket.assignee_user_id:
            ticket.assignee_user_id = body.assignee_user_id
            await _event(
                session,
                ticket,
                "assigned",
                principal.user_id,
                {"user_id": str(body.assignee_user_id)},
            )
            await notify(
                session,
                tenant_id=principal.tenant_id,
                user_id=body.assignee_user_id,
                kind="ticket_assigned",
                title=f"Ticket {ticket.number}: {ticket.title}",
                entity_type="ticket",
                entity_id=ticket.id,
            )
        if body.priority:
            ticket.priority = body.priority
        if body.team_id:
            ticket.team_id = body.team_id
        if body.time_spent_minutes is not None:
            ticket.time_spent_minutes = body.time_spent_minutes
        if body.checklist_done is not None:
            ticket.checklist = [
                {**c, "done": i in body.checklist_done} for i, c in enumerate(ticket.checklist)
            ]
        await session.flush()
        return _ticket_out(ticket)


BULK_LIMIT_NON_ADMIN = 10


class TicketBulkStatus(_In):
    ticket_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: TicketStatus


@router.post("/tickets/bulk-status", summary="Status für markierte Tickets setzen")
async def bulk_status(
    body: TicketBulkStatus, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Bulk action of the ticket list. Non-admins may change at most 10 tickets per call
    (product rule); tenant admins are unlimited. Invalid transitions are skipped and
    reported, they never abort the rest of the selection."""
    ids = list(dict.fromkeys(body.ticket_ids))
    if not principal.has("tenant_settings:update") and len(ids) > BULK_LIMIT_NON_ADMIN:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                f"Zu viele Tickets ausgewählt ({len(ids)}): höchstens {BULK_LIMIT_NON_ADMIN} "
                "gleichzeitig. Administratoren sind nicht begrenzt."
            ),
        )
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(Ticket).where(Ticket.id.in_(ids)).with_for_update())
        ).all()
        found = {t.id: t for t in rows}
        updated = 0
        skipped: list[dict[str, str]] = []
        for ticket_id in ids:
            ticket = found.get(ticket_id)
            if ticket is None:
                skipped.append({"id": str(ticket_id), "reason": "Ticket nicht gefunden"})
                continue
            if body.status is ticket.status:
                skipped.append(
                    {"id": str(ticket_id), "reason": f"Status ist bereits {ticket.status.value}"}
                )
                continue
            if body.status not in TICKET_FLOW[ticket.status]:
                skipped.append(
                    {
                        "id": str(ticket_id),
                        "reason": (
                            f"Wechsel {ticket.status.value} nach {body.status.value} unzulässig"
                        ),
                    }
                )
                continue
            await _event(
                session,
                ticket,
                "status",
                principal.user_id,
                {"from": ticket.status.value, "to": body.status.value, "bulk": True},
            )
            ticket.status = body.status
            ticket.resolved_at = (
                datetime.now(UTC)
                if body.status in (TicketStatus.DONE, TicketStatus.CLOSED, TicketStatus.REJECTED)
                else None
            )
            updated += 1
        await session.flush()
        return {"updated": updated, "skipped": skipped}


@router.post(
    "/tickets/{ticket_id}/comments", status_code=201, summary="Kommentar (intern oder extern)"
)
async def comment(
    ticket_id: uuid.UUID,
    body: CommentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = TicketComment(
            tenant_id=principal.tenant_id,
            ticket_id=ticket.id,
            author_user_id=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "internal": row.internal}


@router.get("/tickets/{ticket_id}", summary="Ticket mit Verlauf und Aufträgen")
async def get_ticket(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        comments = (
            await session.scalars(
                select(TicketComment)
                .where(TicketComment.ticket_id == ticket.id)
                .order_by(TicketComment.created_at)
            )
        ).all()
        events = (
            await session.scalars(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .order_by(TicketEvent.created_at)
            )
        ).all()
        orders = (
            await session.scalars(select(WorkOrder).where(WorkOrder.ticket_id == ticket.id))
        ).all()
        return _ticket_out(ticket) | {
            "comments": [
                {"body": c.body, "internal": c.internal, "created_at": c.created_at}
                for c in comments
            ],
            "events": [{"kind": e.kind, "data": e.data, "at": e.created_at} for e in events],
            "work_orders": [_order_out(o) for o in orders],
        }


@router.post("/work-orders", status_code=201, summary="Auftrag anlegen")
async def create_order(
    body: WorkOrderIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        order = WorkOrder(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(order)
        await session.flush()
        return _order_out(order)


@router.post(
    "/work-orders/{order_id}/steps",
    summary="Auftragsschritt (Angebot, Freigabe, Termin, Ausführung, Rechnung, Bewertung)",
)
async def order_step(
    order_id: uuid.UUID,
    body: OrderStep,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.accounting.models import Invoice

    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id, with_for_update=True)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.status not in ORDER_FLOW[order.status]:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Schritt {order.status.value} nach {body.status.value} nicht zulässig.",
            )
        if body.status is OrderStatus.QUOTED:
            if body.quote_amount is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Angebotsbetrag fehlt.")
            order.quote_amount, order.quote_document_id = body.quote_amount, body.quote_document_id
        if body.status is OrderStatus.APPROVED:
            if not principal.has("tickets:approve"):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN, developer_message="Missing tickets:approve."
                )
            amount = order.quote_amount
            if (
                order.budget_limit is not None
                and amount is not None
                and amount > order.budget_limit
            ):
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Angebot über dem Budget: neue Freigabegrundlage nötig.",
                )
            if order.requires_board_approval and not body.note:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Beiratsbeteiligung ist zu dokumentieren (Vermerk).",
                )
            order.approved_by = principal.user_id
        if body.status is OrderStatus.SCHEDULED:
            if body.scheduled_at is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Termin fehlt.")
            order.scheduled_at = body.scheduled_at
        if body.status is OrderStatus.DONE:
            order.completion_report = body.completion_report
            order.photo_document_ids = body.photo_document_ids or []
        if body.status is OrderStatus.INVOICED:
            invoice = await session.get(Invoice, body.invoice_id) if body.invoice_id else None
            if invoice is None or invoice.provider_contact_id != order.provider_contact_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Rechnung desselben Dienstleisters erforderlich."
                )
            order.invoice_id = invoice.id
            if invoice.order_reference is None:
                invoice.order_reference = str(order.id)
        if body.status is OrderStatus.ACCEPTED:
            order.rating, order.rating_comment = body.rating, body.rating_comment
        session.add(
            WorkOrderEvent(
                tenant_id=order.tenant_id,
                work_order_id=order.id,
                from_status=order.status.value,
                to_status=body.status.value,
                user_id=principal.user_id,
                note=body.note,
            )
        )
        order.status = body.status
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"work_order.{body.status.value}",
            entity_type="work_order",
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={},
        )
        await session.flush()
        return _order_out(order)
