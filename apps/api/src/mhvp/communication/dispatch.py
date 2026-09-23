"""Dispatch per channel, delivery evidence, communication history, calendar feed (M23).

Postal dispatch is recorded with evidence (for example registered mail number); a print and
mail provider is not connected (M23-01). E-mail dispatch prepares a draft for the mailbox
(M20); portal dispatch makes the document visible in the recipient's portal inbox."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.communication.models import Dispatch, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(tags=["Kommunikation"])
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
READ_CONTACTS = require_permission("contacts:read")
CHANNELS = ("post", "email", "portal")
EVIDENCE = ("registered_mail", "courier", "hand_delivery", "email_log", "portal_read", "other")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DispatchIn(_In):
    document_id: uuid.UUID
    contact_id: uuid.UUID
    channel: str | None = Field(default=None, pattern="^(post|email|portal)$")


class SerialDispatchIn(_In):
    items: list[DispatchIn] = Field(min_length=1, max_length=2000)


class EvidenceIn(_In):
    status: str = Field(pattern="^(sent|delivered|failed)$")
    evidence_kind: str | None = Field(default=None, pattern="^(" + "|".join(EVIDENCE) + ")$")
    evidence_ref: str | None = Field(default=None, max_length=200)
    evidence_document_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


def _out(d: Dispatch) -> dict[str, Any]:
    return {
        k: getattr(d, k)
        for k in (
            "id",
            "document_id",
            "contact_id",
            "channel",
            "status",
            "message_id",
            "batch",
            "evidence_kind",
            "evidence_ref",
            "evidence_document_id",
            "sent_at",
            "delivered_at",
        )
    }


async def _create(
    session: Any, principal: TenantPrincipal, item: DispatchIn, batch: str | None
) -> Dispatch:
    from mhvp.contacts.models import Contact, ContactEmail
    from mhvp.documents.models import Document, DocumentLink, LinkRole

    contact = await session.get(Contact, item.contact_id)
    document = await session.get(Document, item.document_id)
    if contact is None or document is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    channel = item.channel or (
        contact.preferred_channel.value if contact.preferred_channel else "post"
    )
    row = Dispatch(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        document_id=document.id,
        contact_id=contact.id,
        channel=channel,
        batch=batch,
    )
    linked = await session.scalar(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document.id,
            DocumentLink.entity_type == "contact",
            DocumentLink.entity_id == contact.id,
        )
    )
    if linked is None:
        session.add(
            DocumentLink(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                entity_type="contact",
                entity_id=contact.id,
                role=LinkRole.GENERATED,
            )
        )
    if channel == "email":
        address = await session.scalar(
            select(ContactEmail.email)
            .where(ContactEmail.contact_id == contact.id)
            .order_by(ContactEmail.is_primary.desc())
            .limit(1)
        )
        if address is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"{contact.display_name}: keine E-Mail-Adresse für den Versand.",
            )
        message = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="draft",
            to_addresses=[address],
            subject=document.title[:998],
            body="Anbei erhalten Sie unser Schreiben.",
            contact_id=contact.id,
            attachment_document_ids=[document.id],
        )
        session.add(message)
        await session.flush()
        row.message_id = message.id
    if channel == "portal":
        row.status, row.sent_at = "sent", datetime.now(UTC)  # visible in the portal inbox now
    session.add(row)
    await session.flush()
    return row


@router.post("/dispatches", status_code=201, summary="Zustellung vorbereiten")
async def create(
    body: DispatchIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _create(session, principal, body, None))


@router.post("/dispatches/serial", status_code=201, summary="Serienversand je Zustellweg")
async def serial(
    body: SerialDispatchIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    batch = uuid.uuid4().hex[:16]
    async with tenant_tx(request, principal) as session:
        rows = [await _create(session, principal, item, batch) for item in body.items]
        groups: dict[str, list[dict[str, Any]]] = {c: [] for c in CHANNELS}
        for r in rows:
            groups[r.channel].append(_out(r))
        return {
            "batch": batch,
            "by_channel": groups,
            "counts": {c: len(v) for c, v in groups.items()},
        }


@router.post(
    "/dispatches/{dispatch_id}/evidence", summary="Versand oder Zugang mit Nachweis erfassen"
)
async def evidence(
    dispatch_id: uuid.UUID,
    body: EvidenceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Dispatch, dispatch_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status == "delivered":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Zugang ist bereits nachgewiesen.")
        if body.status == "delivered" and not (
            body.evidence_kind and (body.evidence_ref or body.evidence_document_id)
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zugang nur mit Nachweis (Art und Referenz oder Beleg).",
            )
        at = body.occurred_at or datetime.now(UTC)
        row.status = body.status
        row.evidence_kind, row.evidence_ref, row.evidence_document_id = (
            body.evidence_kind,
            body.evidence_ref,
            body.evidence_document_id,
        )
        if body.status in ("sent", "delivered") and row.sent_at is None:
            row.sent_at = at
        if body.status == "delivered":
            row.delivered_at = at
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"dispatch.{body.status}",
            entity_type="dispatch",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"evidence": body.evidence_kind},
        )
        await session.flush()
        return _out(row)


@router.get("/contacts/{contact_id}/history", summary="Kommunikationshistorie des Kontakts")
async def history(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ_CONTACTS)
) -> list[dict[str, Any]]:
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        events: list[dict[str, Any]] = []
        if principal.has("communication:read"):
            for m in (
                await session.scalars(select(Message).where(Message.contact_id == contact_id))
            ).all():
                events.append(
                    {
                        "kind": f"email_{m.direction}",
                        "at": m.received_at or m.sent_at or m.created_at,
                        "title": m.subject,
                        "id": m.id,
                        "status": m.status,
                    }
                )
            for d in (
                await session.scalars(select(Dispatch).where(Dispatch.contact_id == contact_id))
            ).all():
                events.append(
                    {
                        "kind": f"dispatch_{d.channel}",
                        "at": d.delivered_at or d.sent_at or d.created_at,
                        "title": str(d.document_id),
                        "id": d.id,
                        "status": d.status,
                    }
                )
        if principal.has("tickets:read"):
            for t in (
                await session.scalars(
                    select(Ticket).where(Ticket.initiator_contact_id == contact_id)
                )
            ).all():
                events.append(
                    {
                        "kind": "ticket",
                        "at": t.created_at,
                        "title": t.title,
                        "id": t.id,
                        "status": t.status.value,
                    }
                )
        return sorted(events, key=lambda e: e["at"], reverse=True)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\n", "\\n")


@router.get(
    "/workspace/calendar.ics", summary="Kalender als ICS (eigene, geteilte Termine, Fristen)"
)
async def calendar_ics(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> PlainTextResponse:
    from sqlalchemy import or_

    from mhvp.workspace import services
    from mhvp.workspace.models import CalendarEntry

    today = services.local_today()
    end = today + timedelta(days=366)
    async with tenant_tx(request, principal) as session:
        entries = (
            await session.scalars(
                select(CalendarEntry).where(
                    or_(CalendarEntry.owner_user_id == principal.user_id, CalendarEntry.shared),
                    CalendarEntry.starts_on.between(today - timedelta(days=30), end),
                )
            )
        ).all()
        derived = await services.derived_dates(
            session,
            today - timedelta(days=30),
            end,
            contracts=principal.has("contracts:read"),
            properties=principal.has("properties:read"),
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MHVP//Kalender//DE", "CALSCALE:GREGORIAN"]

    def event(uid: str, day: date, title: str) -> None:
        nxt = day + timedelta(days=1)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@mhvp",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{nxt:%Y%m%d}",
                f"SUMMARY:{_ics_escape(title)}",
                "END:VEVENT",
            ]
        )

    for e in entries:
        event(str(e.id), e.starts_on, e.title)
    for d in derived:
        event(f"{d['kind']}-{d['entity_id']}", d["date"], d["title"])
    lines.append("END:VCALENDAR")
    return PlainTextResponse("\r\n".join(lines) + "\r\n", media_type="text/calendar")
