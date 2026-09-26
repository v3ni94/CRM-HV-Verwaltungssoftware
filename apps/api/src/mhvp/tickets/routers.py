"""Tickets and work orders (/api/v1/tickets, /api/v1/work-orders, M19): ticket to order to
invoice end to end. Payment stays in accounting (M14/M15); board status never pays."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.validation import InvalidValueError, normalise_iban
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets import reply_templates, tnr
from mhvp.tickets.competences import is_known_code
from mhvp.tickets.merge import assert_mergeable, assignees_to_carry, origin_data
from mhvp.tickets.models import (
    OrderStatus,
    Priority,
    Team,
    Ticket,
    TicketAssignee,
    TicketComment,
    TicketEvent,
    TicketReplyTemplate,
    TicketSource,
    TicketStatus,
    TicketTemplate,
    WorkOrder,
    WorkOrderEvent,
)
from mhvp.tickets.status import (
    CLOSING_STATUSES,
    transition_status,
)
from mhvp.workspace.services import notify

router = APIRouter(tags=["Tickets und Aufträge"])
READ = require_permission("tickets:read")
CREATE = require_permission("tickets:create")
UPDATE = require_permission("tickets:update")
APPROVE = require_permission("tickets:approve")

# Bulk status change (M19 bulk actions, 25.09.2026): a user without tickets:approve or an
# admin role may change at most this many tickets per call.
BULK_LIMIT_STANDARD = 10
_ADMIN_ROLES = {"tenant_admin", "administrator"}
_EXTRA_FIELD_TYPES = {"text", "iban", "date", "number", "select"}


def _is_bulk_unlimited(principal: TenantPrincipal) -> bool:
    return principal.has("tickets:approve") or bool(_ADMIN_ROLES.intersection(principal.roles))


def _can_manage_templates(principal: TenantPrincipal) -> bool:
    return principal.has("tickets:approve") or principal.has("tenant_settings:update")


# SLA default per priority in hours when no template sets one (product standard, A-031).
SLA_HOURS = {
    Priority.IMMEDIATE: 4,
    Priority.URGENT: 24,
    Priority.HIGH: 72,
    Priority.NORMAL: 168,
    Priority.LOW: 336,
}


def _may_skip_flow(principal: TenantPrincipal) -> bool:
    """Betreiber 26.09.2026: Mandantenadministratoren setzen jeden Status in jeden anderen,
    ohne Zwischenschritte. Kennzeichen ist ``tickets:delete`` (nur tenant_admin und
    Plattform-Admin, Regel M2-07). Alle anderen bleiben an TICKET_FLOW gebunden."""
    return principal.has("tickets:delete")


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


class ChecklistItemIn(_In):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    required: bool = False


class ExtraFieldIn(_In):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    type: str = Field(default="text")
    required: bool = False
    options: list[str] | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if value not in _EXTRA_FIELD_TYPES:
            raise ValueError(f"Unbekannter Feldtyp: {value}")
        return value


class TicketTemplateIn(_In):
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    checklist: list[ChecklistItemIn] = Field(default_factory=list, max_length=50)
    extra_fields: list[ExtraFieldIn] = Field(default_factory=list, max_length=50)
    default_priority: Priority = Priority.NORMAL
    # Thema (operator 25.09.2026): Code aus dem Kompetenzkatalog, s. mhvp.tickets.competences.
    topic: str | None = Field(default=None, max_length=32)
    default_team_id: uuid.UUID | None = None
    default_assignee_user_id: uuid.UUID | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=8760)
    active: bool = True


class TicketTemplatePatch(_In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    checklist: list[ChecklistItemIn] | None = Field(default=None, max_length=50)
    extra_fields: list[ExtraFieldIn] | None = Field(default=None, max_length=50)
    default_priority: Priority | None = None
    topic: str | None = Field(default=None, max_length=32)
    default_team_id: uuid.UUID | None = None
    default_assignee_user_id: uuid.UUID | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=8760)
    active: bool | None = None


class TicketIn(_In):
    title: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)
    template_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    topic: str | None = Field(default=None, max_length=32)
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
    extra_fields: dict[str, Any] | None = None
    topic: str | None = Field(default=None, max_length=32)
    contact_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None


class AssigneeIn(_In):
    user_id: uuid.UUID
    reason: str = Field(default="manuell", max_length=64)
    primary: bool = False


class BulkStatusIn(_In):
    ticket_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: TicketStatus


class ChecklistTogglePatch(_In):
    done: bool = True


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
    ticket_ids: list[uuid.UUID] = Field(min_length=1)
    title: str | None = Field(default=None, max_length=300)
    # M36: merge the sources into this existing ticket instead of creating a new one.
    target_ticket_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_counts(self) -> "TicketMergeIn":
        distinct = set(self.ticket_ids)
        if self.target_ticket_id is None and len(distinct) < 2:
            raise ValueError("Mindestens zwei Tickets oder ein Zielticket angeben.")
        if self.target_ticket_id is not None and self.target_ticket_id in distinct:
            raise ValueError("Das Zielticket darf nicht unter den Quelltickets sein.")
        return self


def _ticket_out(t: Ticket) -> dict[str, Any]:
    return {
        k: getattr(t, k)
        for k in (
            "id",
            "number",
            "property_id",
            "unit_id",
            "contact_id",
            "template_id",
            "category",
            "topic",
            "title",
            "public_description",
            "status",
            "priority",
            "assignee_user_id",
            "team_id",
            "initiator_contact_id",
            "source",
            "checklist",
            "extra_fields",
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


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _assert_not_merged(ticket: Ticket) -> None:
    """A merged source is read only (M36); work continues on the target."""
    if ticket.merged_into_ticket_id is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Ticket ist zusammengeführt und kann nicht mehr bearbeitet werden.",
        )


async def _assert_known_topic(
    session: AsyncSession, tenant_id: uuid.UUID, topic: str | None
) -> None:
    if topic is None:
        return
    from mhvp.platform.models import TenantSettings

    extra = await session.scalar(
        select(TenantSettings.competence_catalogue_extra).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    if not is_known_code(topic, list(extra or [])):
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekanntes Thema: {topic}")


def _assignee_out(row: TicketAssignee) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "primary": row.primary,
        "reason": row.reason,
        "created_at": row.created_at,
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


def _require_template_manage(principal: TenantPrincipal) -> None:
    if not _can_manage_templates(principal):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            developer_message="Missing tickets:approve or tenant_settings:update.",
        )


def _template_out(tpl: TicketTemplate) -> dict[str, Any]:
    return {
        k: getattr(tpl, k)
        for k in (
            "id",
            "category",
            "title",
            "description",
            "checklist",
            "extra_fields",
            "default_priority",
            "topic",
            "default_team_id",
            "default_assignee_user_id",
            "sla_hours",
            "active",
        )
    }


def _validate_extra_field_value(field: dict[str, Any], value: Any) -> Any:
    if value is None or value == "":
        return None
    if field.get("type") == "iban":
        try:
            return normalise_iban(str(value))
        except InvalidValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    return value


@router.post("/ticket-templates", status_code=201, summary="Ticketvorlage mit Routing und SLA")
async def create_template(
    body: TicketTemplateIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _assert_known_topic(session, principal.tenant_id, body.topic)
        tpl = TicketTemplate(
            tenant_id=principal.tenant_id,
            **body.model_dump(exclude={"checklist", "extra_fields"}),
            checklist=[c.model_dump() for c in body.checklist],
            extra_fields=[f.model_dump() for f in body.extra_fields],
        )
        session.add(tpl)
        await session.flush()
        return {"id": tpl.id, "category": tpl.category}


@router.get("/tickets/templates", summary="Ticketvorlagen")
async def list_templates(
    request: Request,
    active: bool | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(TicketTemplate).order_by(TicketTemplate.category)
        if active is not None:
            query = query.where(TicketTemplate.active == active)
        return [_template_out(t) for t in (await session.scalars(query)).all()]


@router.post("/tickets/templates", status_code=201, summary="Ticketvorlage anlegen")
async def create_template_v2(
    body: TicketTemplateIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    _require_template_manage(principal)
    async with tenant_tx(request, principal) as session:
        await _assert_known_topic(session, principal.tenant_id, body.topic)
        tpl = TicketTemplate(
            tenant_id=principal.tenant_id,
            **body.model_dump(exclude={"checklist", "extra_fields"}),
            checklist=[c.model_dump() for c in body.checklist],
            extra_fields=[f.model_dump() for f in body.extra_fields],
        )
        session.add(tpl)
        await session.flush()
        return _template_out(tpl)


@router.get("/tickets/templates/{template_id}", summary="Ticketvorlage")
async def get_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketTemplate, template_id)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _template_out(tpl)


@router.patch("/tickets/templates/{template_id}", summary="Ticketvorlage bearbeiten")
async def patch_template(
    template_id: uuid.UUID,
    body: TicketTemplatePatch,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _require_template_manage(principal)
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketTemplate, template_id, with_for_update=True)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if "topic" in body.model_fields_set:
            await _assert_known_topic(session, principal.tenant_id, body.topic)
        data = body.model_dump(exclude_unset=True)
        if "checklist" in data and data["checklist"] is not None:
            tpl.checklist = [c.model_dump() for c in body.checklist]  # type: ignore[union-attr]
            data.pop("checklist")
        if "extra_fields" in data and data["extra_fields"] is not None:
            tpl.extra_fields = [f.model_dump() for f in body.extra_fields]  # type: ignore[union-attr]
            data.pop("extra_fields")
        for key, value in data.items():
            setattr(tpl, key, value)
        await session.flush()
        return _template_out(tpl)


# Antwortvorlagen (operator 26.09.2026): vorgefertigte Antworten je Mandant. Versand nur über
# den bestehenden Antwortweg des Tickets (Entwurf, Einreichung, Vier-Augen-Freigabe, Postfach
# des Tickets) und nur nach ausdrücklicher Bestätigung im Aufruf, nie automatisch.


def _can_manage_reply_templates(principal: TenantPrincipal) -> bool:
    return (
        principal.has("tickets:update")
        or principal.has("tenant_settings:update")
        or bool(_ADMIN_ROLES.intersection(principal.roles))
    )


def _require_reply_template_manage(principal: TenantPrincipal) -> None:
    if not _can_manage_reply_templates(principal):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            developer_message="Missing tickets:update or tenant_settings:update.",
        )


class ReplyTemplateIn(_In):
    name: str = Field(min_length=1, max_length=150)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    topic: str | None = Field(default=None, max_length=32)
    attachment_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    active: bool = True


class ReplyTemplatePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    topic: str | None = Field(default=None, max_length=32)
    attachment_document_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    active: bool | None = None


class TicketReplyIn(_In):
    """Antwort aus dem Ticket: der Text ist bereits bearbeitet und vollständig ausgefüllt.
    ``confirm`` ist die ausdrückliche Bestätigung des Versandwunsches (Klick auf "Antwort
    senden"); ohne sie wird nichts angelegt."""

    template_id: uuid.UUID | None = None
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=100000)
    # Validated addresses (422), so approval never fails on a malformed header (review 26.09.2026).
    to_addresses: list[EmailStr] | None = Field(default=None, max_length=20)
    cc_addresses: list[EmailStr] = Field(default_factory=list, max_length=20)
    # Antwort auf eine bestimmte Nachricht des Tickets (Thread-Kopfzeilen, Vorbelegung);
    # ohne Angabe gilt die letzte eingehende Nachricht.
    reply_to_message_id: uuid.UUID | None = None
    attachment_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    confirm: bool = False


def _reply_template_out(tpl: TicketReplyTemplate) -> dict[str, Any]:
    return {
        k: getattr(tpl, k)
        for k in (
            "id",
            "name",
            "subject",
            "body",
            "topic",
            "attachment_document_ids",
            "active",
            "created_at",
            "updated_at",
        )
    }


def _assert_known_placeholders(*texts: str | None) -> None:
    unknown = [p for text in texts for p in reply_templates.unknown_placeholders(text)]
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Unbekannte Platzhalter: "
            + ", ".join(f"{{{p}}}" for p in dict.fromkeys(unknown)),
        )


async def _attachments_out(session: AsyncSession, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Dokumente des Mandanten zu den Verweisen; fehlende (gelöscht oder fremder Mandant)
    werden als ``missing`` gekennzeichnet statt stillschweigend übergangen."""
    from mhvp.documents.models import Document

    out: list[dict[str, Any]] = []
    for document_id in ids:
        doc = await session.get(Document, document_id)
        if doc is None:
            out.append(
                {"document_id": document_id, "title": None, "filename": None, "missing": True}
            )
        else:
            out.append(
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "filename": doc.filename,
                    "missing": False,
                }
            )
    return out


async def _assert_documents_exist(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    for entry in await _attachments_out(session, ids):
        if entry["missing"]:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND,
                detail=f"Anhang nicht gefunden: {entry['document_id']}",
            )


@router.get("/tickets/reply-templates", summary="Antwortvorlagen")
async def list_reply_templates(
    request: Request,
    active: bool | None = None,
    topic: str | None = Query(default=None, max_length=32),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(TicketReplyTemplate).order_by(TicketReplyTemplate.name)
        if active is not None:
            query = query.where(TicketReplyTemplate.active == active)
        if topic:
            query = query.where(TicketReplyTemplate.topic == topic)
        return [_reply_template_out(t) for t in (await session.scalars(query)).all()]


@router.get("/tickets/reply-templates/placeholders", summary="Platzhalter der Antwortvorlagen")
async def list_reply_placeholders(principal: TenantPrincipal = Depends(READ)) -> list[str]:
    return list(reply_templates.PLACEHOLDERS)


@router.post("/tickets/reply-templates", status_code=201, summary="Antwortvorlage anlegen")
async def create_reply_template(
    body: ReplyTemplateIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    _require_reply_template_manage(principal)
    _assert_known_placeholders(body.subject, body.body)
    async with tenant_tx(request, principal) as session:
        await _assert_known_topic(session, principal.tenant_id, body.topic)
        await _assert_documents_exist(session, body.attachment_document_ids)
        exists = await session.scalar(
            select(TicketReplyTemplate.id).where(TicketReplyTemplate.name == body.name)
        )
        if exists is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Eine Antwortvorlage mit diesem Namen besteht bereits."
            )
        tpl = TicketReplyTemplate(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(tpl)
        await session.flush()
        return _reply_template_out(tpl)


@router.get("/tickets/reply-templates/{template_id}", summary="Antwortvorlage")
async def get_reply_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketReplyTemplate, template_id)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _reply_template_out(tpl) | {
            "attachments": await _attachments_out(session, tpl.attachment_document_ids)
        }


@router.patch("/tickets/reply-templates/{template_id}", summary="Antwortvorlage bearbeiten")
async def patch_reply_template(
    template_id: uuid.UUID,
    body: ReplyTemplatePatch,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _require_reply_template_manage(principal)
    _assert_known_placeholders(body.subject, body.body)
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketReplyTemplate, template_id, with_for_update=True)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if "topic" in data:
            await _assert_known_topic(session, principal.tenant_id, data["topic"])
        if data.get("attachment_document_ids") is not None:
            await _assert_documents_exist(session, data["attachment_document_ids"])
        if data.get("name") and data["name"] != tpl.name:
            exists = await session.scalar(
                select(TicketReplyTemplate.id).where(TicketReplyTemplate.name == data["name"])
            )
            if exists is not None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Eine Antwortvorlage mit diesem Namen besteht bereits.",
                )
        for key, value in data.items():
            if value is None and key != "topic":
                continue
            setattr(tpl, key, value)
        tpl.updated_by = principal.user_id
        await session.flush()
        await session.refresh(tpl)
        return _reply_template_out(tpl)


@router.delete(
    "/tickets/reply-templates/{template_id}", status_code=204, summary="Antwortvorlage löschen"
)
async def delete_reply_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> None:
    _require_reply_template_manage(principal)
    async with tenant_tx(request, principal) as session:
        tpl = await session.get(TicketReplyTemplate, template_id, with_for_update=True)
        if tpl is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(tpl)
        await session.flush()


async def _reply_context(
    session: AsyncSession, ticket: Ticket, reply_to_message_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Empfänger, Postfach und Platzhalterwerte der Antwort auf ein Ticket: geantwortet wird
    auf die gewählte oder die letzte eingehende Nachricht des Tickets (Absender, Kopie,
    Postfach, Thread); ohne Mail gilt die Haupt-E-Mail des Kontakts und das Standardpostfach
    des Mandanten."""
    from mhvp.communication.models import Mailbox, Message
    from mhvp.communication.services import ticket_participants
    from mhvp.communication.transport import is_sendable
    from mhvp.contacts.models import Contact, ContactEmail
    from mhvp.properties.models import Property, Unit
    from mhvp.workspace.services import local_today

    inbound = None
    if reply_to_message_id is not None:
        inbound = await session.scalar(
            select(Message).where(Message.id == reply_to_message_id, Message.ticket_id == ticket.id)
        )
        if inbound is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Nachricht gehört nicht zu diesem Ticket."
            )
    if inbound is None:
        inbound = await session.scalar(
            select(Message)
            .where(Message.ticket_id == ticket.id, Message.direction == "in")
            .order_by(Message.received_at.desc().nulls_last(), Message.created_at.desc())
            .limit(1)
        )
    participants = await ticket_participants(session, ticket, include_thread_senders=False)
    sender_verified = bool(
        inbound is not None
        and inbound.from_address
        and inbound.from_address.lower() in participants
    )
    contact_id = (
        ticket.contact_id
        or ticket.initiator_contact_id
        or (inbound.contact_id if inbound is not None and sender_verified else None)
    )
    contact = await session.get(Contact, contact_id) if contact_id else None
    prop = await session.get(Property, ticket.property_id) if ticket.property_id else None
    unit = await session.get(Unit, ticket.unit_id) if ticket.unit_id else None
    to_addresses: list[str] = []
    cc_addresses: list[str] = []
    unverified_sender: str | None = None
    mailbox_address = None
    if inbound is not None and inbound.mailbox_id:
        box = await session.get(Mailbox, inbound.mailbox_id)
        mailbox_address = box.address.lower() if box else None
    if inbound is not None and inbound.direction == "out":
        # Antwort auf eine eigene ausgehende Mail: dieselben Empfänger erneut anschreiben.
        to_addresses = list(inbound.to_addresses)
        cc_addresses = list(inbound.cc_addresses or [])
    elif inbound is not None and inbound.from_address:
        sender = inbound.from_address
        # Vorbelegung nur mit einem am Ticket beteiligten Absender (Review 26.09.2026, H5):
        # ein fremder Absender wird nie automatisch Empfänger, sondern nur nach Auswahl.
        if sender_verified:
            to_addresses = [sender]
            own = {a.lower() for a in (inbound.to_addresses or [])} - {
                a.lower() for a in (inbound.cc_addresses or [])
            }
            cc_addresses = [
                a
                for a in (inbound.cc_addresses or [])
                if a.lower() != mailbox_address and a.lower() not in own
            ]
        else:
            unverified_sender = sender
    if not to_addresses and contact is not None:
        primary = await session.scalar(
            select(ContactEmail.email)
            .where(ContactEmail.contact_id == contact.id)
            .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
            .limit(1)
        )
        if primary:
            to_addresses = [primary]
    if not to_addresses:
        first_inbound = await session.scalar(
            select(Message)
            .where(Message.ticket_id == ticket.id, Message.direction == "in")
            .order_by(Message.received_at.asc().nulls_last(), Message.created_at.asc())
            .limit(1)
        )
        if first_inbound is not None and first_inbound.from_address:
            to_addresses = [first_inbound.from_address]
    mailbox = None
    if inbound is not None and inbound.mailbox_id:
        mailbox = await session.get(Mailbox, inbound.mailbox_id)
    if mailbox is None:
        mailbox = await session.scalar(select(Mailbox).where(Mailbox.is_default.is_(True)))
    today = local_today()
    return {
        "inbound": inbound,
        "contact": contact,
        "mailbox": mailbox,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "unverified_sender": unverified_sender,
        "values": reply_templates.values_for(
            ticket=ticket,
            contact=contact,
            prop=prop,
            unit=unit,
            today=f"{today.day:02d}.{today.month:02d}.{today.year}",
        ),
        "can_send": is_sendable(mailbox),
    }


@router.get(
    "/tickets/{ticket_id}/reply-context",
    summary="Vorbelegung der Antwort (An, Kopie, Betreff, Postfach)",
)
async def reply_context(
    ticket_id: uuid.UUID,
    request: Request,
    reply_to_message_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Vorbelegung des Antwortformulars im Ticket ohne Vorlage: Empfänger und Kopie aus der
    gewählten oder letzten eingehenden Mail, Betreff ``AW: <Betreff> TNR#<nummer>``, Postfach
    des Tickets und ob es sendefähig ist. Legt nichts an."""
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ctx = await _reply_context(session, ticket, reply_to_message_id)
        mailbox, inbound = ctx["mailbox"], ctx["inbound"]
        return {
            "reply_to_message_id": inbound.id if inbound else None,
            "subject": tnr.reply_subject(
                inbound.subject if inbound else ticket.title, ticket.number
            ),
            "to_addresses": ctx["to_addresses"],
            "cc_addresses": ctx["cc_addresses"],
            "unverified_sender": ctx["unverified_sender"],
            "mailbox_id": mailbox.id if mailbox else None,
            "mailbox_address": mailbox.address if mailbox else None,
            "can_send": ctx["can_send"],
            "tnr": tnr.format_tnr(ticket.number),
        }


@router.get(
    "/tickets/{ticket_id}/reply-templates/{template_id}/preview",
    summary="Antwortvorlage mit ausgefüllten Platzhaltern (Vorschau)",
)
async def preview_reply_template(
    ticket_id: uuid.UUID,
    template_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        tpl = await session.get(TicketReplyTemplate, template_id)
        if tpl is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Antwortvorlage nicht gefunden."
            )
        ctx = await _reply_context(session, ticket)
        mailbox = ctx["mailbox"]
        return {
            "template_id": tpl.id,
            "template_name": tpl.name,
            "subject": tnr.subject_with_tnr(
                reply_templates.render(tpl.subject, ctx["values"]), ticket.number
            ),
            "body": reply_templates.render(tpl.body, ctx["values"]),
            "values": ctx["values"],
            "to_addresses": ctx["to_addresses"],
            "cc_addresses": ctx["cc_addresses"],
            "unverified_sender": ctx["unverified_sender"],
            "mailbox_id": mailbox.id if mailbox else None,
            "mailbox_address": mailbox.address if mailbox else None,
            "can_send": ctx["can_send"],
            "attachments": await _attachments_out(session, tpl.attachment_document_ids),
        }


@router.post(
    "/tickets/{ticket_id}/reply",
    status_code=201,
    summary="Antwort aus dem Ticket senden (Entwurf einreichen, Freigabe, Postfach des Tickets)",
)
async def reply_to_ticket(
    ticket_id: uuid.UUID,
    body: TicketReplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Legt die ausgehende Nachricht am Ticket an und reicht sie sofort zur Freigabe ein
    (Status ``pending``). Der Versand selbst erfolgt wie bei jeder Antwort über
    ``POST /mail/messages/{id}/approve`` (Vier-Augen-Prinzip, Postfach des Tickets). Ohne
    ``confirm`` wird nichts angelegt; ein Versand ohne ausdrücklichen Klick ist ausgeschlossen."""
    from mhvp.communication.models import Message
    from mhvp.communication.routers import _out as message_out
    from mhvp.communication.routers import mailbox_accessible, tnr_references

    if not principal.has("communication:update"):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing communication:update.")
    if not body.confirm:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Versand nur nach ausdrücklicher Bestätigung (Antwort senden).",
        )
    _assert_known_placeholders(body.subject, body.body)
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id, with_for_update=True)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _assert_not_merged(ticket)
        tpl = None
        if body.template_id is not None:
            tpl = await session.get(TicketReplyTemplate, body.template_id)
            if tpl is None:
                raise ProblemError(
                    ErrorCodes.RESOURCE_NOT_FOUND, detail="Antwortvorlage nicht gefunden."
                )
        await _assert_documents_exist(session, body.attachment_document_ids)
        ctx = await _reply_context(session, ticket, body.reply_to_message_id)
        mailbox = ctx["mailbox"]
        if mailbox is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Kein eingerichtetes Postfach für den Versand (M20-01)."
            )
        if not await mailbox_accessible(session, principal, mailbox):
            raise ProblemError(
                ErrorCodes.FORBIDDEN,
                detail=f"Kein Zugriff auf das Postfach {mailbox.address}; die Freigabe für "
                "dieses Postfach erteilt ein Administrator.",
            )
        to_addresses = [a.strip() for a in (body.to_addresses or ctx["to_addresses"]) if a.strip()]
        if not to_addresses:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kein Empfänger für die Antwort.")
        cc_addresses = [a.strip() for a in body.cc_addresses if a.strip()]
        inbound = ctx["inbound"]
        now = datetime.now(UTC)
        draft = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="pending",
            mailbox_id=mailbox.id,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            # Kennung TNR#<nummer> genau einmal im Betreff (docs/rules/M19-02-tnr.md).
            subject=tnr.subject_with_tnr(body.subject, ticket.number),
            body=body.body,
            in_reply_to=inbound.header_message_id if inbound else None,
            references_header=tnr_references(inbound) if inbound else None,
            thread_id=(inbound.thread_id or inbound.id) if inbound else None,
            contact_id=ctx["contact"].id if ctx["contact"] else None,
            property_id=ticket.property_id,
            ticket_id=ticket.id,
            attachment_document_ids=list(body.attachment_document_ids),
            submitted_by=principal.user_id,
            submitted_at=now,
        )
        session.add(draft)
        await session.flush()
        await _event(
            session,
            ticket,
            "reply_submitted",
            principal.user_id,
            {
                "message_id": str(draft.id),
                "template_id": str(tpl.id) if tpl else None,
                "template_name": tpl.name if tpl else None,
                "to": to_addresses,
                "cc": cc_addresses,
                "attachments": len(body.attachment_document_ids),
            },
        )
        await session.flush()
        return message_out(draft)


async def _ticket_messages(
    session: AsyncSession, principal: TenantPrincipal, ticket: Ticket
) -> Any:
    """Nachrichten des Tickets, auf die der Benutzer über sein Postfach zugreifen darf
    (dieselbe Regel wie ``GET /mail/messages``), chronologisch."""
    from sqlalchemy import func, or_

    from mhvp.communication.models import Message
    from mhvp.communication.routers import _accessible_mailboxes

    query = select(Message).where(Message.ticket_id == ticket.id)
    if not principal.has("tenant_settings:update"):
        allowed = await _accessible_mailboxes(session, principal.user_id)
        query = query.where(or_(Message.mailbox_id.is_(None), Message.mailbox_id.in_(allowed)))
    return (
        await session.scalars(
            query.order_by(
                func.coalesce(Message.received_at, Message.sent_at, Message.created_at),
                Message.created_at,
            )
        )
    ).all()


async def _attachment_rows(session: AsyncSession, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    from mhvp.documents.models import Document

    if not ids:
        return []
    docs = {
        d.id: d for d in (await session.scalars(select(Document).where(Document.id.in_(ids)))).all()
    }
    out: list[dict[str, Any]] = []
    for document_id in ids:
        doc = docs.get(document_id)
        if doc is None:
            out.append(
                {
                    "document_id": document_id,
                    "filename": None,
                    "mime_type": None,
                    "size": None,
                    "missing": True,
                }
            )
        else:
            out.append(
                {
                    "document_id": doc.id,
                    "filename": doc.filename or doc.title,
                    "mime_type": doc.mime_type,
                    "size": doc.size,
                    "missing": False,
                }
            )
    return out


@router.get("/tickets/{ticket_id}/messages", summary="Mailverlauf des Tickets mit Anhängen")
async def ticket_messages(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """Ein- und ausgehende Mails des Tickets chronologisch, je Mail Empfänger, Kopie, Status,
    Klartext, bereinigtes HTML und die Anhangsliste (Name, Größe, Typ). Postfachrechte gelten
    wie in der Postfachansicht."""
    from mhvp.communication.models import Mailbox
    from mhvp.communication.routers import _out as message_out

    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await _ticket_messages(session, principal, ticket)
        mailbox_ids = {m.mailbox_id for m in rows if m.mailbox_id}
        boxes = (
            {
                b.id: b.address
                for b in (
                    await session.scalars(select(Mailbox).where(Mailbox.id.in_(mailbox_ids)))
                ).all()
            }
            if mailbox_ids
            else {}
        )
        out = []
        for m in rows:
            data = message_out(m)
            data["mailbox_address"] = boxes.get(m.mailbox_id) if m.mailbox_id else None
            data["attachments"] = await _attachment_rows(session, list(m.attachment_document_ids))
            out.append(data)
        return out


_PREVIEW_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
_ATTACHMENT_CSP = "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'"


@router.get(
    "/tickets/{ticket_id}/mail-attachments/{document_id}/content",
    summary="Anhang einer Ticket-Mail anzeigen oder herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def ticket_mail_attachment_content(
    ticket_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    download: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    """Liefert nur Dokumente, die Anhang einer für den Benutzer sichtbaren Mail dieses
    Tickets sind (Ticket-Bezug statt allgemeiner Dokumentenzugriff). Bilder und PDF werden
    inline zur Vorschau ausgeliefert, alles andere und ``download=true`` als Download."""
    from urllib.parse import quote

    from mhvp.documents import services as document_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, StorageKind

    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await _ticket_messages(session, principal, ticket)
        if not any(document_id in (m.attachment_document_ids or []) for m in rows):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if document.storage is StorageKind.GOOGLE_DRIVE:
            data = await document_services.download_from_drive(session, request, document)
        else:
            data = BlobStore(request.app.state.settings).get(document.storage_ref)
        filename, mime = document.filename, document.mime_type
    inline = not download and mime in _PREVIEW_MIME
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=mime if inline else "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": _ATTACHMENT_CSP,
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/tickets/{ticket_id}/reply-documents", summary="Dokumente als Anhang der Antwort suchen"
)
async def ticket_reply_documents(
    ticket_id: uuid.UUID,
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    """Kleine Suche des Dokumentenmoduls für das Antwortformular (Titel oder Dateiname),
    höchstens 20 Treffer, nur Metadaten. Der Ticketbezug prüft das Ticket, nicht die
    Dokumente; der Rechtsträgerbereich der Mitgliedschaft (A37) gilt unverändert."""
    from sqlalchemy import or_

    from mhvp.documents.models import Document
    from mhvp.documents.routers import _scope_filter

    async with tenant_tx(request, principal) as session:
        if await session.get(Ticket, ticket_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        like = f"%{_escape_like(q.strip())}%"
        query = select(Document).where(
            or_(
                Document.title.ilike(like, escape="\\"),
                Document.filename.ilike(like, escape="\\"),
            )
        )
        scoped = _scope_filter(session)
        if scoped is not None:
            query = query.where(Document.id.in_(scoped))
        docs = (await session.scalars(query.order_by(Document.created_at.desc()).limit(20))).all()
        return [
            {
                "document_id": d.id,
                "title": d.title,
                "filename": d.filename,
                "mime_type": d.mime_type,
                "size": d.size,
            }
            for d in docs
        ]


@router.post("/tickets", status_code=201, summary="Ticket anlegen (Vorlage, Routing, SLA)")
async def create_ticket(
    body: TicketIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tpl = (
            await session.get(TicketTemplate, body.template_id)
            if body.template_id
            else (
                await session.scalar(
                    select(TicketTemplate).where(TicketTemplate.category == body.category)
                )
                if body.category
                else None
            )
        )
        if body.template_id and tpl is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Ticketvorlage nicht gefunden."
            )
        title = body.title or (tpl.title if tpl else None)
        if not title:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Titel fehlt.")
        await _assert_known_topic(session, principal.tenant_id, body.topic)
        priority = body.priority or (tpl.default_priority if tpl else Priority.NORMAL)
        hours = tpl.sla_hours if tpl and tpl.sla_hours else SLA_HOURS[priority]
        checklist = (
            [
                {
                    "key": c["key"],
                    "label": c["label"],
                    "required": c.get("required", False),
                    "done": False,
                    "done_by": None,
                    "done_at": None,
                }
                for c in tpl.checklist
            ]
            if tpl
            else []
        )
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            template_id=tpl.id if tpl else None,
            title=title,
            priority=priority,
            team_id=tpl.default_team_id if tpl else None,
            assignee_user_id=tpl.default_assignee_user_id if tpl else None,
            checklist=checklist,
            sla_due_at=datetime.now(UTC) + timedelta(hours=hours),
            **body.model_dump(exclude={"title", "priority", "template_id", "topic"}),
            topic=body.topic or (tpl.topic if tpl else None),
        )
        session.add(ticket)
        await session.flush()
        from mhvp.sla.service import start_clock

        await start_clock(session, principal.tenant_id, ticket.id, ticket.priority)
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
    """Without ``target_ticket_id`` the sources merge into a new ticket with a new number (M6).
    With it (M36) the sources merge into that existing ticket, which keeps its number, status,
    priority and assignment. Either way comments, messages and history entries move to the
    target, every source gets a ``merged_into`` entry and is closed, its SLA clock is resolved,
    and the target records the origin of every source in a ``merged_from`` entry."""
    from sqlalchemy import func

    from mhvp.communication.models import Message
    from mhvp.sla.models import SlaClock
    from mhvp.sla.service import mark_resolved, start_clock

    ids = list(dict.fromkeys(body.ticket_ids))
    lock_ids = ids + ([body.target_ticket_id] if body.target_ticket_id else [])
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(Ticket).where(Ticket.id.in_(lock_ids)).with_for_update())
        ).all()
        by_id = {t.id: t for t in rows}
        if any(i not in by_id for i in lock_ids):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Ticket nicht gefunden.")
        sources = [by_id[i] for i in ids]
        target = by_id[body.target_ticket_id] if body.target_ticket_id else None
        assert_mergeable(sources, target)

        if target is None:
            everything = sources
            oldest = min(everything, key=lambda t: t.created_at)
            priority = max((t.priority for t in everything), key=list(Priority).index)
            due_candidates = [t.sla_due_at for t in everything if t.sla_due_at is not None]

            def _first(field: str) -> Any:
                value = getattr(oldest, field)
                if value is not None:
                    return value
                for t in everything:
                    value = getattr(t, field)
                    if value is not None:
                        return value
                return None

            target = Ticket(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                number=await next_number(session, principal.tenant_id, "ticket"),
                property_id=_first("property_id"),
                unit_id=_first("unit_id"),
                contact_id=_first("contact_id"),
                template_id=_first("template_id"),
                category=_first("category"),
                topic=_first("topic"),
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
                visible_for=sorted({v for t in everything for v in t.visible_for}),
                sla_due_at=min(due_candidates) if due_candidates else None,
            )
            session.add(target)
            await session.flush()
            await start_clock(session, principal.tenant_id, target.id, target.priority)
        else:
            target.visible_for = sorted(
                {*target.visible_for, *(v for t in sources for v in t.visible_for)}
            )

        existing = (
            await session.scalars(
                select(TicketAssignee.user_id).where(TicketAssignee.ticket_id == target.id)
            )
        ).all()
        source_assignee_ids: list[uuid.UUID | None] = []
        for t in sources:
            source_assignee_ids.append(t.assignee_user_id)
            source_assignee_ids.extend(
                (
                    await session.scalars(
                        select(TicketAssignee.user_id)
                        .where(TicketAssignee.ticket_id == t.id)
                        .order_by(TicketAssignee.created_at)
                    )
                ).all()
            )
        skip = [*existing, *([target.assignee_user_id] if target.assignee_user_id else [])]
        for carry in assignees_to_carry(skip, source_assignee_ids):
            session.add(
                TicketAssignee(
                    tenant_id=target.tenant_id,
                    ticket_id=target.id,
                    user_id=carry.user_id,
                    reason=carry.reason,
                )
            )

        for t in sources:
            counts = {}
            for model in (TicketComment, Message, TicketEvent):
                counts[model] = int(
                    await session.scalar(
                        select(func.count()).select_from(model).where(model.ticket_id == t.id)
                    )
                    or 0
                )
                await session.execute(
                    update(model).where(model.ticket_id == t.id).values(ticket_id=target.id)
                )
            await _event(
                session,
                target,
                "merged_from",
                principal.user_id,
                origin_data(
                    t,
                    comments=counts[TicketComment],
                    messages=counts[Message],
                    events=counts[TicketEvent],
                ),
            )
            await _event(
                session,
                t,
                "merged_into",
                principal.user_id,
                {"ticket_id": str(target.id), "number": target.number},
            )
            t.status = TicketStatus.CLOSED
            t.resolved_at = datetime.now(UTC)
            t.merged_into_ticket_id = target.id
            clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == t.id))
            if clock is not None:
                await mark_resolved(session, clock)

        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.merged",
            entity_type="ticket",
            entity_id=target.id,
            actor_user_id=principal.user_id,
            payload={"number": target.number, "source_ticket_ids": [str(t.id) for t in sources]},
        )
        await session.flush()
        return _ticket_out(target) | {"merged_ticket_ids": [t.id for t in sources]}


def _parse_status_filter(raw: str | None) -> list[TicketStatus]:
    """``status`` accepts one value (unchanged) or several, comma-separated, e.g.
    ``status=new,in_progress`` (M19 list filters, operator 25.09.2026: repeated query params
    are not forwarded reliably by all clients, so comma-separated is the documented form)."""
    if not raw:
        return []
    values = [part.strip() for part in raw.split(",") if part.strip()]
    try:
        return [TicketStatus(v) for v in values]
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Status: {exc}") from exc


@router.get(
    "/tickets",
    summary="Tickets",
    responses={
        200: {
            "headers": {
                "X-Total-Count": {
                    "description": "Gesamtzahl der Tickets der Filterung",
                    "schema": {"type": "integer"},
                },
                "X-Page": {"description": "Aktuelle Seite", "schema": {"type": "integer"}},
                "X-Page-Size": {"description": "Einträge je Seite", "schema": {"type": "integer"}},
            }
        }
    },
)
async def list_tickets(
    request: Request,
    response: Response,
    status: str | None = Query(
        default=None, description="Ein Status oder mehrere, kommagetrennt (z. B. new,in_progress)"
    ),
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = Query(
        default=None, description="Kontakt oder Initiator (contact_id ODER initiator_contact_id)"
    ),
    initiator_contact_id: uuid.UUID | None = Query(default=None, description="Nur Initiator"),
    any_contact_id: uuid.UUID | None = Query(
        default=None, description="Personenbezug: contact_id ODER initiator_contact_id"
    ),
    contact_role: str | None = Query(
        default=None, description="Rolle des verknüpften Kontakts zur Einheit: owner oder tenant"
    ),
    assignee_user_id: uuid.UUID | None = Query(
        default=None, description="Bearbeiter, primär oder zusätzlich zugewiesen"
    ),
    team_id: uuid.UUID | None = None,
    category: str | None = Query(default=None, max_length=100),
    priority: Priority | None = None,
    created_from: datetime | None = Query(default=None, description="Erstellt ab (inklusive)"),
    created_to: datetime | None = Query(default=None, description="Erstellt bis (inklusive)"),
    mine: bool = False,
    q: str | None = Query(
        default=None,
        max_length=300,
        description=(
            "Nummer, Titel, Beschreibung, Kontaktname oder E-Mail, Objektadresse,"
            " Betreff oder Absender verknüpfter Mails (beinhaltet)"
        ),
    ),
    include_merged: bool = Query(default=True, description="Zusammengeführte Tickets zeigen"),
    include_closed: bool = Query(
        default=False,
        description=(
            "Erledigte Tickets (done, closed, rejected) zeigen; gilt nur ohne status-Filter"
        ),
    ),
    merged_into: uuid.UUID | None = Query(default=None, description="Quelltickets eines Ziels"),
    limit: int = Query(default=100, ge=1, le=500),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=500,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    """Liste der Tickets, neueste Nummer zuerst. Paginierung (review 26.09.2026, H7): die
    Antwort bleibt eine Liste (bestehende Aufrufer); Gesamtzahl und Seite stehen in den
    Kopfzeilen ``X-Total-Count``, ``X-Page`` und ``X-Page-Size``."""
    from mhvp.communication.models import Message
    from mhvp.contacts.models import Contact, ContactEmail, PartyMember
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Property, PropertyOwner, Unit

    async with tenant_tx(request, principal) as session:
        query = select(Ticket).order_by(Ticket.number.desc())
        term = (q or "").strip().lstrip("#")
        if term:
            escaped = f"%{_escape_like(term)}%"
            title_match = Ticket.title.ilike(escaped, escape="\\")
            description_match = Ticket.public_description.ilike(escaped, escape="\\")
            contact_name_match = Ticket.contact_id.in_(
                select(Contact.id).where(Contact.display_name.ilike(escaped, escape="\\"))
            )
            property_match = Ticket.property_id.in_(
                select(Property.id).where(
                    (Property.street.ilike(escaped, escape="\\"))
                    | (Property.city.ilike(escaped, escape="\\"))
                    | (Property.house_number.ilike(escaped, escape="\\"))
                )
            )
            # Betreiber 26.09.2026: "beinhaltet"-Suche auch ueber Betreff und Absender der
            # verknuepften Mails sowie die E-Mail-Adressen des Kontakts.
            message_match = Ticket.id.in_(
                select(Message.ticket_id).where(
                    Message.ticket_id.is_not(None),
                    (Message.subject.ilike(escaped, escape="\\"))
                    | (Message.from_address.ilike(escaped, escape="\\")),
                )
            )
            contact_email_match = Ticket.contact_id.in_(
                select(ContactEmail.contact_id).where(
                    ContactEmail.email.ilike(escaped, escape="\\")
                )
            )
            text_match = (
                title_match
                | description_match
                | contact_name_match
                | contact_email_match
                | property_match
                | message_match
            )
            query = query.where(
                (Ticket.number == int(term)) | text_match
                if term.isdigit() and len(term) <= 9
                else text_match
            )
        if not include_merged:
            query = query.where(Ticket.merged_into_ticket_id.is_(None))
        if merged_into:
            query = query.where(Ticket.merged_into_ticket_id == merged_into)
        statuses = _parse_status_filter(status)
        if statuses:
            query = query.where(Ticket.status.in_(statuses))
        elif not include_closed and merged_into is None:
            query = query.where(Ticket.status.not_in(CLOSING_STATUSES))
        if property_id:
            query = query.where(Ticket.property_id == property_id)
        if unit_id:
            query = query.where(Ticket.unit_id == unit_id)
        for person in (contact_id, any_contact_id):
            if person:
                query = query.where(
                    (Ticket.contact_id == person) | (Ticket.initiator_contact_id == person)
                )
        if initiator_contact_id:
            query = query.where(Ticket.initiator_contact_id == initiator_contact_id)
        if contact_role:
            if contact_role not in ("owner", "tenant"):
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="contact_role muss owner oder tenant sein."
                )
            # Role of the ticket's linked contact (or, if also filtering by contact_id, that
            # contact) as owner or tenant of the ticket's unit (operator 25.09.2026):
            # Contract.unit_id == Ticket.unit_id, Contract.party_id via PartyMember.contact_id.
            # Ownership can also be recorded at property level via PropertyOwner (Mietverwaltung,
            # see properties.routers.add_owner), so the owner role additionally matches through
            # Unit.property_id == PropertyOwner.property_id.
            role_contact = contact_id if contact_id is not None else Ticket.contact_id

            def _parties() -> Any:
                return (
                    select(PartyMember.party_id)
                    .where(PartyMember.contact_id == role_contact)
                    .correlate(Ticket)
                )

            role_conditions: list[Any] = [Ticket.unit_id.is_not(None)]
            if contact_id is None:
                role_conditions.append(Ticket.contact_id.is_not(None))
            role_match: Any
            if contact_role == "tenant":
                role_match = (
                    select(Contract.id)
                    .where(
                        Contract.unit_id == Ticket.unit_id,
                        Contract.kind == ContractKind.TENANCY,
                        Contract.party_id.in_(_parties()),
                    )
                    .correlate(Ticket)
                    .exists()
                )
            else:
                ownership_contract = (
                    select(Contract.id)
                    .where(
                        Contract.unit_id == Ticket.unit_id,
                        Contract.kind == ContractKind.OWNERSHIP,
                        Contract.party_id.in_(_parties()),
                    )
                    .correlate(Ticket)
                    .exists()
                )
                property_owner = (
                    select(PropertyOwner.id)
                    .join(Unit, Unit.property_id == PropertyOwner.property_id)
                    .where(
                        Unit.id == Ticket.unit_id,
                        PropertyOwner.party_id.in_(_parties()),
                    )
                    .correlate(Ticket)
                    .exists()
                )
                role_match = ownership_contract | property_owner
            role_conditions.append(role_match)
            query = query.where(*role_conditions)
        if assignee_user_id:
            query = query.where(
                (Ticket.assignee_user_id == assignee_user_id)
                | Ticket.id.in_(
                    select(TicketAssignee.ticket_id).where(
                        TicketAssignee.user_id == assignee_user_id
                    )
                )
            )
        if team_id:
            query = query.where(Ticket.team_id == team_id)
        if category:
            query = query.where(Ticket.category == category)
        if priority:
            query = query.where(Ticket.priority == priority)
        if created_from:
            query = query.where(Ticket.created_at >= created_from)
        if created_to:
            query = query.where(Ticket.created_at <= created_to)
        if mine:
            query = query.where(Ticket.assignee_user_id == principal.user_id)
        size = page_size or limit
        total = (
            await session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
            or 0
        )
        rows = (await session.scalars(query.offset((page - 1) * size).limit(size))).all()
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(size)
        return [_ticket_out(t) for t in rows]


@router.get("/tickets/{ticket_id}/assignees", summary="Zuweiser eines Tickets mit Grund")
async def list_assignees(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(TicketAssignee)
            .where(TicketAssignee.ticket_id == ticket_id)
            .order_by(TicketAssignee.created_at)
        )
        return [_assignee_out(r) for r in rows.all()]


@router.post(
    "/tickets/{ticket_id}/assignees", status_code=201, summary="Zuweiser hinzufügen (manuell)"
)
async def add_assignee_endpoint(
    ticket_id: uuid.UUID,
    body: AssigneeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.communication.assignment import add_assignee

    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id, with_for_update=True)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _assert_not_merged(ticket)
        await add_assignee(session, ticket, body.user_id, body.reason, primary=body.primary)
        if body.primary:
            ticket.assignee_user_id = body.user_id
        await session.flush()
        row = await session.scalar(
            select(TicketAssignee).where(
                TicketAssignee.ticket_id == ticket_id, TicketAssignee.user_id == body.user_id
            )
        )
        assert row is not None  # noqa: S101 - just inserted or already existed
        return _assignee_out(row)


@router.delete(
    "/tickets/{ticket_id}/assignees/{user_id}", status_code=204, summary="Zuweiser entfernen"
)
async def remove_assignee(
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(TicketAssignee).where(
                TicketAssignee.ticket_id == ticket_id, TicketAssignee.user_id == user_id
            )
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)


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
        _assert_not_merged(ticket)
        if body.checklist_done is not None:
            ticket.checklist = [
                {**c, "done": i in body.checklist_done} for i, c in enumerate(ticket.checklist)
            ]
        template = (
            await session.get(TicketTemplate, ticket.template_id) if ticket.template_id else None
        )
        if body.extra_fields is not None:
            field_defs = {f["key"]: f for f in (template.extra_fields if template else [])}
            values = dict(ticket.extra_fields)
            for key, raw in body.extra_fields.items():
                field = field_defs.get(key, {"type": "text"})
                values[key] = _validate_extra_field_value(field, raw)
            ticket.extra_fields = values
        if body.status and body.status is not ticket.status:
            await transition_status(
                session,
                request.app.state.settings,
                ticket,
                body.status,
                principal.user_id,
                skip_flow=_may_skip_flow(principal),
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
        if body.topic is not None:
            await _assert_known_topic(session, principal.tenant_id, body.topic)
            ticket.topic = body.topic
        if body.contact_id is not None:
            ticket.contact_id = body.contact_id
        if body.property_id is not None:
            ticket.property_id = body.property_id
        if body.unit_id is not None:
            ticket.unit_id = body.unit_id
        await session.flush()
        return _ticket_out(ticket)


@router.patch("/tickets/{ticket_id}/checklist/{key}", summary="Checklistenpunkt abhaken")
async def toggle_checklist_item(
    ticket_id: uuid.UUID,
    key: str,
    body: ChecklistTogglePatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id, with_for_update=True)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _assert_not_merged(ticket)
        found = False
        now = datetime.now(UTC)
        checklist = []
        for item in ticket.checklist:
            if item.get("key") == key:
                found = True
                item = {
                    **item,
                    "done": body.done,
                    "done_by": str(principal.user_id) if body.done else None,
                    "done_at": now.isoformat() if body.done else None,
                }
            checklist.append(item)
        if not found:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Checklistenpunkt unbekannt.")
        ticket.checklist = checklist
        await _event(
            session, ticket, "checklist", principal.user_id, {"key": key, "done": body.done}
        )
        await session.flush()
        return _ticket_out(ticket)


class AttachInvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: uuid.UUID


@router.post(
    "/tickets/{ticket_id}/attach-invoice",
    summary="Rechnung zuordnen (Kategorie Rechnung, Jahresablage im Objektordner)",
)
async def attach_invoice(
    ticket_id: uuid.UUID,
    body: AttachInvoiceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """M11-finapi Stage 3: marks this ticket as an invoice ticket (`category = "invoice"`) and
    files the invoice's original document into the property's Google Drive year folder
    (`mhvp.documents.property_filing`, "<Objektordner>/<Jahr>"). Requires the ticket's own
    property and the invoice's original document; nothing is invented when either is
    missing. Idempotent: a repeated call with the same invoice does not re-upload the
    document, only re-confirms the link."""
    from mhvp.accounting.models import Invoice
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.dms import DmsError
    from mhvp.documents.models import Document
    from mhvp.documents.property_filing import file_document_in_property_year_folder
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id, with_for_update=True)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _assert_not_merged(ticket)
        invoice = await session.get(Invoice, body.invoice_id)
        if invoice is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechnung nicht gefunden.")
        if ticket.property_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Das Ticket hat kein zugeordnetes Objekt."
            )
        if invoice.document_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Rechnung hat keinen Originalbeleg."
            )
        property_ = await session.get(Property, ticket.property_id)
        document = await session.get(Document, invoice.document_id)
        if property_ is None or document is None:  # pragma: no cover - FK integrity
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)

        already_filed = ticket.extra_fields.get("invoice_drive_file_ref")
        if str(ticket.extra_fields.get("invoice_id")) != str(invoice.id) or not already_filed:
            import httpx

            tenant_slug = await _tenant_slug(session, principal.tenant_id)
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    result = await file_document_in_property_year_folder(
                        session,
                        tenant_slug=tenant_slug,
                        document=document,
                        property_=property_,
                        year=invoice.invoice_date.year,
                        blobs=BlobStore(request.app.state.settings),
                        client=client,
                    )
                except DmsError as exc:
                    raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
            already_filed = result.drive_file_ref

        ticket.category = "invoice"
        ticket.extra_fields = {
            **ticket.extra_fields,
            "invoice_id": str(invoice.id),
            "invoice_drive_file_ref": already_filed,
            "invoice_drive_year": invoice.invoice_date.year,
        }
        await _event(
            session,
            ticket,
            "invoice_attached",
            principal.user_id,
            {"invoice_id": str(invoice.id), "drive_file_ref": already_filed},
        )
        await session.flush()
        return _ticket_out(ticket)


async def _tenant_slug(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    from mhvp.platform.models import Tenant

    tenant = await session.get(Tenant, tenant_id)
    return tenant.slug if tenant is not None else str(tenant_id)


@router.post("/tickets/bulk-status", summary="Status mehrerer Tickets ändern")
async def bulk_status(
    body: BulkStatusIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    ids = list(dict.fromkeys(body.ticket_ids))
    if len(ids) > BULK_LIMIT_STANDARD and not _is_bulk_unlimited(principal):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Höchstens {BULK_LIMIT_STANDARD} Tickets gleichzeitig"
        )
    changed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    async with tenant_tx(request, principal) as session:
        tickets = (
            await session.scalars(select(Ticket).where(Ticket.id.in_(ids)).with_for_update())
        ).all()
        by_id = {t.id: t for t in tickets}
        for ticket_id in ids:
            ticket = by_id.get(ticket_id)
            if ticket is None:
                failed.append({"id": str(ticket_id), "reason": "Ticket nicht gefunden."})
                continue
            if ticket.merged_into_ticket_id is not None:
                failed.append({"id": str(ticket.id), "reason": "Ticket ist zusammengeführt."})
                continue
            if body.status is ticket.status:
                changed.append({"id": str(ticket.id), "status": ticket.status.value})
                continue
            try:
                await transition_status(
                    session,
                    request.app.state.settings,
                    ticket,
                    body.status,
                    principal.user_id,
                    bulk=True,
                    skip_flow=_may_skip_flow(principal),
                )
            except ProblemError as exc:
                failed.append({"id": str(ticket.id), "reason": exc.detail})
                continue
            changed.append({"id": str(ticket.id), "status": ticket.status.value})
        await session.flush()
    return {"changed": changed, "failed": failed}


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
        _assert_not_merged(ticket)
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
        assignees = (
            await session.scalars(
                select(TicketAssignee)
                .where(TicketAssignee.ticket_id == ticket.id)
                .order_by(TicketAssignee.created_at)
            )
        ).all()
        from sqlalchemy import func

        from mhvp.communication.models import Message
        from mhvp.portal.routers import ticket_attachments

        message_count = int(
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.ticket_id == ticket.id)
            )
            or 0
        )
        return _ticket_out(ticket) | {
            "comments": [
                {"body": c.body, "internal": c.internal, "created_at": c.created_at}
                for c in comments
            ],
            "events": [{"kind": e.kind, "data": e.data, "at": e.created_at} for e in events],
            "work_orders": [_order_out(o) for o in orders],
            "assignees": [_assignee_out(a) for a in assignees],
            "message_count": message_count,
            # A55: documents linked to the ticket as attachments (portal photos, PDFs).
            "attachments": await ticket_attachments(session, ticket.id),
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


from mhvp.tickets.proposals import router as proposals_router  # noqa: E402

router.include_router(proposals_router)
