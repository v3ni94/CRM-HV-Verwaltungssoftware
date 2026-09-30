"""Portal chat with the management as a message channel at the ticket (M21-01, Entscheidung
6 a, 14 Phase 3).

The chat is no separate system: a message is an external (non internal) ``TicketComment`` of
the portal user's own ticket, so history, CRM view, retention and search stay in the ticket.
The portal user reads only the external comments; internal notes never appear. A message of
the portal user notifies the ticket's assignee, a reply of the management (CRM) notifies the
portal user. The channel is off per tenant until ``PortalFeatureSetting.chat_enabled`` is on.

The pre-qualification is a proposal only (rule 0.1.6): it never changes a ticket. The rule
based part needs no provider. The AI part stays locked behind its own switch and the approved
AI provider with data processing agreement (gateway gate); this module makes no provider call
(open point, see docs/rules/P13-portal-w2.md)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import features
from mhvp.portal.models import PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.tickets.models import Ticket, TicketComment
from mhvp.workspace.services import notify

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin", tags=["Portal Verwaltung"])
REPLY = require_permission("tickets:update")
LOCKED = "Der Chat ist für diesen Mandanten nicht freigeschaltet."
PREQUALIFICATION_NOTE = (
    "Vorschlag zur Einordnung, keine Entscheidung. Die Verwaltung prüft jede Meldung selbst."
)
EMERGENCY_NOTE = (
    "Bei Gefahr für Leib und Leben rufen Sie bitte sofort den Notruf 112 an. "
    "Dieser Chat ist kein Notdienst."
)

# Deterministic keyword rules (Produktschutz, no legal meaning): topic, urgency.
_TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Heizung", ("heizung", "heizkörper", "warmwasser", "therme")),
    ("Wasser und Sanitär", ("wasser", "rohr", "toilette", "abfluss", "tropft", "leck")),
    ("Elektro", ("strom", "sicherung", "steckdose", "licht", "elektr")),
    ("Aufzug", ("aufzug", "fahrstuhl", "lift")),
    ("Schlüssel und Schloss", ("schlüssel", "schloss", "tür", "ausgesperrt")),
    ("Feuchtigkeit und Schimmel", ("schimmel", "feucht", "nässe")),
)
_URGENT = ("rohrbruch", "überschwemm", "gasgeruch", "gas ", "brand", "rauch", "stromausfall")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalChatMessageIn(_In):
    body: str = Field(min_length=1, max_length=5000)


class PortalChatReplyIn(_In):
    body: str = Field(min_length=1, max_length=5000)


class PortalChatPrequalifyIn(_In):
    text: str = Field(min_length=3, max_length=5000)


def prequalify_text(text: str) -> dict[str, Any]:
    """Rule based proposal: topics and whether the wording suggests an urgent case."""
    lower = f"{text.lower()} "
    topics = [name for name, words in _TOPICS if any(w in lower for w in words)]
    urgent = any(w in lower for w in _URGENT)
    return {
        "topics": topics,
        "urgent_hint": urgent,
        "note": PREQUALIFICATION_NOTE,
        "emergency_note": EMERGENCY_NOTE if urgent else None,
    }


async def _enabled(session: Any) -> Any:
    row = await features.get_or_default(session)
    if not row.chat_enabled:
        raise ProblemError(ErrorCodes.FORBIDDEN, detail=LOCKED)
    return row


async def _own_ticket(session: Any, account: PortalAccount, ticket_id: uuid.UUID) -> Ticket:
    ticket: Ticket | None = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.initiator_contact_id != account.contact_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return ticket


def _message_out(row: TicketComment, account: PortalAccount) -> dict[str, Any]:
    own = row.author_contact_id == account.contact_id
    return {
        "id": row.id,
        "direction": "own" if own else "management",
        "body": row.body,
        "created_at": row.created_at,
    }


@router.get("/tickets/{ticket_id}/messages", summary="Chatverlauf zur eigenen Meldung")
async def list_messages(
    ticket_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _enabled(session)
        ticket = await _own_ticket(session, account, ticket_id)
        rows = (
            await session.scalars(
                select(TicketComment)
                .where(TicketComment.ticket_id == ticket.id, TicketComment.internal.is_(False))
                .order_by(TicketComment.created_at, TicketComment.id)
            )
        ).all()
        return [_message_out(r, account) for r in rows]


@router.post("/tickets/{ticket_id}/messages", status_code=201, summary="Chatnachricht senden")
async def post_message(
    ticket_id: uuid.UUID,
    body: PortalChatMessageIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _enabled(session)
        ticket = await _own_ticket(session, account, ticket_id)
        row = TicketComment(
            tenant_id=principal.tenant_id,
            ticket_id=ticket.id,
            internal=False,
            author_contact_id=account.contact_id,
            body=body.body.strip(),
        )
        session.add(row)
        await session.flush()
        if ticket.assignee_user_id is not None:
            await notify(
                session,
                tenant_id=principal.tenant_id,
                user_id=ticket.assignee_user_id,
                kind="portal_chat_message",
                title=f"Neue Nachricht im Portal zu Meldung {ticket.number}",
                body=None,
                target_type="ticket",
                target_id=ticket.id,
            )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_chat.message",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=principal.user_id,
            payload={"comment_id": str(row.id)},
        )
        return _message_out(row, account)


@router.post(
    "/tickets/{ticket_id}/prequalify", summary="Vorqualifizierung einer Nachricht (nur Vorschlag)"
)
async def prequalify(
    ticket_id: uuid.UUID,
    body: PortalChatPrequalifyIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    """Rule based proposal always (chat on); the AI stage is reported as available only when
    its tenant switch is on and the gateway gate (released provider with data processing
    agreement and training opt out) is open. No provider is called here."""
    from mhvp.ai import gateway
    from mhvp.ai.models import AiTask

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        settings_row = await _enabled(session)
        await _own_ticket(session, account, ticket_id)
        result = prequalify_text(body.text)
        result["source"] = "regelbasiert"
        result["ai_available"] = False
        result["ai_blocked_reason"] = None
        if not settings_row.chat_ai_prequalification_enabled:
            result["ai_blocked_reason"] = "KI-Vorqualifizierung ist nicht eingeschaltet."
        else:
            try:
                await gateway.route(session, AiTask.CLASSIFY_EMAIL)
                result["ai_available"] = True
            except gateway.GatewayBlockedError as exc:
                result["ai_blocked_reason"] = str(exc)
        return result


@admin.post(
    "/tickets/{ticket_id}/messages", status_code=201, summary="Antwort der Verwaltung im Chat"
)
async def reply_message(
    ticket_id: uuid.UUID,
    body: PortalChatReplyIn,
    request: Request,
    principal: TenantPrincipal = Depends(REPLY),
) -> dict[str, Any]:
    """CRM reply visible in the portal (external comment) and announced by a notification to
    the portal user of the initiator. Needs the chat switch; never changes the ticket status."""
    async with tenant_tx(request, principal) as session:
        await _enabled(session)
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = TicketComment(
            tenant_id=principal.tenant_id,
            ticket_id=ticket.id,
            internal=False,
            author_user_id=principal.user_id,
            body=body.body.strip(),
        )
        session.add(row)
        await session.flush()
        recipient = (
            await session.scalar(
                select(PortalAccount.user_id).where(
                    PortalAccount.contact_id == ticket.initiator_contact_id,
                    PortalAccount.status == "active",
                )
            )
            if ticket.initiator_contact_id is not None
            else None
        )
        if recipient is not None:
            await notify(
                session,
                tenant_id=principal.tenant_id,
                user_id=recipient,
                kind="portal_chat_reply",
                title=f"Antwort der Verwaltung zu Meldung {ticket.number}",
                target_type="ticket",
                target_id=ticket.id,
            )
        return {"id": row.id, "notified": recipient is not None}
