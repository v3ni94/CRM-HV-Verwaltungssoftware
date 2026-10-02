"""Auftragsliste und Auftragsdetail, Teamverwaltung und Kommentarverwaltung (M19-01, M19-02,
M19-07, Spezifikation 6.6).

Reine Lese- und Verwaltungsendpunkte. Sie ändern keine Buchung und lösen keine Zahlung aus;
Kommentare werden archiviert (``removed_at``), nie physisch gelöscht, damit der Verlauf als
Nachweis erhalten bleibt.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.listparams import (
    ListParams,
    ListSpec,
    apply_filters,
    apply_sort,
    sparse,
    strict_query,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import (
    OrderStatus,
    Team,
    Ticket,
    TicketComment,
    TicketEvent,
    WorkOrder,
    WorkOrderEvent,
)
from mhvp.tickets.work_order_rating import WorkOrderRatingIn

router = APIRouter(tags=["Tickets und Aufträge"])
READ = require_permission("tickets:read")
UPDATE = require_permission("tickets:update")
APPROVE = require_permission("tickets:approve")


class TicketTeamPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    member_user_ids: list[uuid.UUID] | None = None


def _order_row(o: WorkOrder) -> dict[str, Any]:
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
            "approval_workflow_id",
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
            "created_at",
        )
    }


_WORK_ORDER_LIST = ListSpec(  # GA04-05
    filters={
        "status": WorkOrder.status,
        "property_id": WorkOrder.property_id,
        "provider_contact_id": WorkOrder.provider_contact_id,
        "ticket_id": WorkOrder.ticket_id,
        "requires_board_approval": WorkOrder.requires_board_approval,
    },
    sort={
        "created_at": WorkOrder.created_at,
        "scheduled_at": WorkOrder.scheduled_at,
        "status": WorkOrder.status,
    },
)


@router.get(
    "/work-orders",
    summary="Aufträge (Filter Status, Dienstleister, Objekt, Ticket)",
    dependencies=[Depends(strict_query)],
)
async def list_work_orders(
    request: Request,
    response: Response,
    status: OrderStatus | None = None,
    provider_contact_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    ticket_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    params: ListParams = Depends(_WORK_ORDER_LIST.dependency),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = apply_filters(select(WorkOrder), params, _WORK_ORDER_LIST.filters)
        for column, value in (
            (WorkOrder.status, status),
            (WorkOrder.provider_contact_id, provider_contact_id),
            (WorkOrder.property_id, property_id),
            (WorkOrder.ticket_id, ticket_id),
        ):
            if value is not None:
                query = query.where(column == value)
        total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = (
            await session.scalars(
                apply_sort(
                    query,
                    params,
                    _WORK_ORDER_LIST.sort,
                    (WorkOrder.created_at.desc(), WorkOrder.id),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        ticket_numbers: dict[uuid.UUID, int] = {}
        ids = {o.ticket_id for o in rows if o.ticket_id}
        if ids:
            ticket_numbers = {
                t.id: t.number
                for t in (await session.scalars(select(Ticket).where(Ticket.id.in_(ids)))).all()
            }
        result = [
            _order_row(o) | {"ticket_number": ticket_numbers.get(o.ticket_id or uuid.UUID(int=0))}
            for o in rows
        ]
        return sparse(result, params, None, response=response)  # type: ignore[no-any-return]


@router.get("/work-orders/{order_id}", summary="Auftrag mit Verlauf")
async def get_work_order(
    order_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.tickets.models import WorkOrderAppointmentProposal

    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        events = (
            await session.scalars(
                select(WorkOrderEvent)
                .where(WorkOrderEvent.work_order_id == order.id)
                .order_by(WorkOrderEvent.created_at)
            )
        ).all()
        proposals = (
            await session.scalars(
                select(WorkOrderAppointmentProposal)
                .where(WorkOrderAppointmentProposal.work_order_id == order.id)
                .order_by(WorkOrderAppointmentProposal.created_at)
            )
        ).all()
        ticket = await session.get(Ticket, order.ticket_id) if order.ticket_id else None
        return _order_row(order) | {
            "ticket_number": ticket.number if ticket else None,
            "ticket_title": ticket.title if ticket else None,
            "events": [
                {
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "user_id": e.user_id,
                    "note": e.note,
                    "created_at": e.created_at,
                }
                for e in events
            ],
            "appointment_proposals": [
                {
                    "id": p.id,
                    "starts_at": p.starts_at,
                    "note": p.note,
                    "status": p.status,
                }
                for p in proposals
            ],
        }


class OrderWorkflowRefIn(BaseModel):
    """GA04-07: set or clear the reference to the approval workflow of an order."""

    model_config = ConfigDict(extra="forbid")
    approval_workflow_id: uuid.UUID | None = None


@router.patch("/work-orders/{order_id}/approval-workflow", summary="Freigabe-Workflow des Auftrags")
async def set_order_workflow(
    order_id: uuid.UUID,
    body: OrderWorkflowRefIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Only a reference (AA05-01): there is no workflow table yet, so the id is not checked
    against one; the board vote stays the effective approval. Tenant isolation by RLS."""
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id, with_for_update=True)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        order.approval_workflow_id = body.approval_workflow_id
        await session.flush()
        return _order_row(order)


# Teams (M19-02) -------------------------------------------------------------------------


def _team_out(team: Team) -> dict[str, Any]:
    return {"id": team.id, "name": team.name, "member_user_ids": team.member_user_ids}


@router.get("/teams", summary="Teams", dependencies=[Depends(strict_query)])
async def list_teams(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = (await session.scalars(select(Team).order_by(Team.name))).all()
        return [_team_out(t) for t in rows]


@router.get("/teams/{team_id}", summary="Team")
async def get_team(
    team_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        team = await session.get(Team, team_id)
        if team is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        response.headers["ETag"] = etag_of(team.updated_at)  # GA04-06
        return _team_out(team)


@router.patch("/teams/{team_id}", summary="Team bearbeiten")
async def patch_team(
    team_id: uuid.UUID,
    body: TicketTeamPatchIn,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        team = await session.get(Team, team_id, with_for_update=True)
        if team is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        check_if_match(if_match, team.updated_at)  # GA04-06
        if body.name is not None and body.name != team.name:
            clash = await session.scalar(
                select(Team.id).where(Team.name == body.name, Team.id != team.id)
            )
            if clash is not None:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Ein Team mit diesem Namen besteht.")
            team.name = body.name
        if body.member_user_ids is not None:
            team.member_user_ids = list(dict.fromkeys(body.member_user_ids))
        await session.flush()
        await session.flush()
        await session.refresh(team, ["updated_at"])
        response.headers["ETag"] = etag_of(team.updated_at)
        return _team_out(team)


@router.delete("/teams/{team_id}", status_code=204, summary="Team löschen (nur ohne Tickets)")
async def delete_team(
    team_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    from mhvp.tickets.models import TicketTemplate

    async with tenant_tx(request, principal) as session:
        team = await session.get(Team, team_id, with_for_update=True)
        if team is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        in_use = await session.scalar(select(Ticket.id).where(Ticket.team_id == team.id).limit(1))
        in_template = await session.scalar(
            select(TicketTemplate.id).where(TicketTemplate.default_team_id == team.id).limit(1)
        )
        if in_use is not None or in_template is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Das Team ist Tickets oder Vorlagen zugeordnet, Löschen nicht möglich.",
            )
        await session.delete(team)
        await session.flush()
    return Response(status_code=204)


# Kommentare (M19-07) --------------------------------------------------------------------


def _comment_out(c: TicketComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "body": c.body,
        "internal": c.internal,
        "author_user_id": c.author_user_id,
        "author_contact_id": c.author_contact_id,
        "document_ids": c.document_ids,
        "created_at": c.created_at,
        "removed_at": c.removed_at,
    }


@router.get(
    "/tickets/{ticket_id}/comments",
    summary="Kommentare eines Tickets",
    dependencies=[Depends(strict_query)],
)
async def list_comments(
    ticket_id: uuid.UUID,
    request: Request,
    include_removed: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Ticket, ticket_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        query = select(TicketComment).where(TicketComment.ticket_id == ticket_id)
        if not include_removed:
            query = query.where(TicketComment.removed_at.is_(None))
        rows = (await session.scalars(query.order_by(TicketComment.created_at))).all()
        return [_comment_out(c) for c in rows]


@router.delete(
    "/tickets/{ticket_id}/comments/{comment_id}", status_code=204, summary="Kommentar archivieren"
)
async def archive_comment(
    ticket_id: uuid.UUID,
    comment_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    """Hides the comment in ticket view and portal; the text stays stored (evidence). A
    merged ticket is read only. Idempotent."""
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        comment = await session.get(TicketComment, comment_id)
        if ticket is None or comment is None or comment.ticket_id != ticket.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if ticket.merged_into_ticket_id is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Das Ticket wurde zusammengeführt.")
        if comment.removed_at is None:
            comment.removed_at = datetime.now(UTC)
            comment.removed_by = principal.user_id
            session.add(
                TicketEvent(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    kind="comment_removed",
                    user_id=principal.user_id,
                    data={"comment_id": str(comment.id)},
                )
            )
            await session.flush()
    return Response(status_code=204)


@router.post(
    "/work-orders/{order_id}/rating",
    status_code=201,
    summary="Auftrag bewerten (Verwaltung, nach Abschluss, einmalig)",
)
async def rate_work_order(
    order_id: uuid.UUID,
    body: WorkOrderRatingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.tickets.work_order_rating import add_rating, rating_out

    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id, with_for_update=True)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await add_rating(
            session,
            order,
            "staff",
            body,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            contact_id=None,
        )
        return rating_out(row, with_comment=True)


@router.get(
    "/work-orders/{order_id}/rating",
    summary="Bewertungen des Auftrags (nur gemäß Schalter provider_rating_display)",
    dependencies=[Depends(strict_query)],
)
async def get_work_order_rating(
    order_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Off (default): no ratings in the answer, only the flag whether staff has rated."""
    from mhvp.portal import features as portal_features
    from mhvp.tickets.models import WorkOrderRating
    from mhvp.tickets.work_order_rating import RATABLE, rating_out

    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id)
        if order is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        mode = (await portal_features.get_or_default(session)).provider_rating_display or "off"
        rows = (
            await session.scalars(
                select(WorkOrderRating)
                .where(WorkOrderRating.work_order_id == order.id)
                .order_by(WorkOrderRating.created_at)
            )
        ).all()
        return {
            "mode": mode,
            "can_rate": order.status in RATABLE,
            "staff_rated": any(r.party == "staff" for r in rows),
            "ratings": [rating_out(r, with_comment=True) for r in rows]
            if mode in ("staff", "all")
            else [],
        }
