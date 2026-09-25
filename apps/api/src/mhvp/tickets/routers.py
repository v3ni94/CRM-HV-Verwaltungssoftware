"""Tickets and work orders (/api/v1/tickets, /api/v1/work-orders, M19): ticket to order to
invoice end to end. Payment stays in accounting (M14/M15); board status never pays."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
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


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeamIn(_In):
    name: str = Field(min_length=1, max_length=100)
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class TicketTemplateIn(_In):
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    default_priority: Priority = Priority.NORMAL
    default_team_id: uuid.UUID | None = None
    default_assignee_user_id: uuid.UUID | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=8760)


class TicketIn(_In):
    title: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)
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
            **body.model_dump(exclude={"title", "priority"}),
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


async def _queue_learn_playbook(session: AsyncSession, settings: Any, ticket: Ticket) -> None:
    """Playbook-Lernen beim Schließen eines Tickets (M20 Übernahme aus dem Immoware Hub):
    synchron in Tests und Entwicklung (``ai_inline``), sonst über die Queue ``ai``. Ein
    Fehler beim Lernen darf den Statuswechsel nie stören."""
    if settings.ai_inline:
        from mhvp.communication.suggest import learn_playbook_from_ticket

        try:
            await learn_playbook_from_ticket(session, settings, ticket)
        except Exception:
            return
    else:
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.communication.learn_playbook",
                args=[str(ticket.tenant_id), str(ticket.id)],
                queue="ai",
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "could not queue playbook learning", extra={"ticket_id": str(ticket.id)}
            )


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
            if body.status in (TicketStatus.DONE, TicketStatus.CLOSED):
                await _queue_learn_playbook(session, request.app.state.settings, ticket)
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
