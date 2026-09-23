"""Mailbox (/api/v1/mail, M20): intake, assignment, list of cases, ticket from mail, reply
draft. Sending needs a configured and enabled mailbox (M20-01)."""

import smtplib
import ssl
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import mail
from mhvp.communication.models import Mailbox, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/mail", tags=["Postfach"])
READ = require_permission("communication:read")
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
ADMIN = require_permission("tenant_settings:update")
SMTP_TIMEOUT = 30


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MailboxIn(_In):
    address: str = Field(min_length=3, max_length=320)
    kind: str = Field(default="imap", pattern="^(imap|gmail)$")
    imap_host: str | None = Field(default=None, max_length=255)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    secret: str | None = Field(default=None, max_length=4000)
    enabled: bool = False


class MailIngestIn(_In):
    document_id: uuid.UUID
    mailbox_id: uuid.UUID | None = None


class MailAssignIn(_In):
    contact_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    status: str | None = Field(default=None, pattern="^(new|assigned|done)$")


class MailAppointmentIn(_In):
    index: int = Field(ge=0, le=4)
    title: str = Field(min_length=1, max_length=300)


def _mailbox_out(m: Mailbox) -> dict[str, Any]:
    return {
        "id": m.id,
        "address": m.address,
        "kind": m.kind,
        "imap_host": m.imap_host,
        "smtp_host": m.smtp_host,
        "enabled": m.enabled,
        "has_secret": bool(m.secret),
    }


def _out(m: Message) -> dict[str, Any]:
    return {
        k: getattr(m, k)
        for k in (
            "id",
            "channel",
            "direction",
            "status",
            "from_address",
            "to_addresses",
            "subject",
            "body",
            "received_at",
            "sent_at",
            "contact_id",
            "property_id",
            "ticket_id",
            "thread_id",
            "document_id",
            "attachment_document_ids",
            "classification",
            "appointment_suggestions",
        )
    }


async def _message(session: AsyncSession, message_id: uuid.UUID) -> Message:
    row = await session.get(Message, message_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.post(
    "/mailboxes", status_code=201, summary="Postfach einrichten (Zugangsdaten verschlüsselt)"
)
async def create_mailbox(
    body: MailboxIn, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = Mailbox(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _mailbox_out(row)


@router.post("/ingest", status_code=201, summary="E-Mail (.eml) aufnehmen und zuordnen")
async def ingest(
    body: MailIngestIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.contacts.models import ContactEmail
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, DocumentSource
    from mhvp.documents.services import check_upload, store_document
    from mhvp.properties.models import Property
    from mhvp.tickets.models import TicketTemplate

    async with tenant_tx(request, principal) as session:
        document = await session.get(Document, body.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        blobs = BlobStore(request.app.state.settings)
        try:
            parsed = mail.parse(blobs.get(document.storage_ref))
        except (ValueError, UnicodeError):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Datei ist keine lesbare E-Mail."
            ) from None
        if parsed["message_id"]:
            known = await session.scalar(
                select(Message).where(
                    Message.header_message_id == parsed["message_id"], Message.direction == "in"
                )
            )
            if known is not None:
                return _out(known)  # re-import: no second case (B08 analog)
        contact_id = None
        if parsed["from"]:
            contact_id = await session.scalar(
                select(ContactEmail.contact_id)
                .where(func.lower(ContactEmail.email) == parsed["from"])
                .limit(1)
            )
        number = mail.property_number(parsed["subject"], parsed["body"])
        property_id = (
            await session.scalar(select(Property.id).where(Property.number == number))
            if number
            else None
        )
        categories = list(await session.scalars(select(TicketTemplate.category)))
        thread_id = None
        if parsed["in_reply_to"]:
            parent = await session.scalar(
                select(Message).where(Message.header_message_id == parsed["in_reply_to"])
            )
            if parent is not None:
                thread_id = parent.thread_id or parent.id
                contact_id = contact_id or parent.contact_id
                property_id = property_id or parent.property_id
        attachments = []
        for att in parsed["attachments"]:
            try:
                check_upload(
                    att["mime"], att["data"], request.app.state.settings.document_max_bytes
                )
                doc = await store_document(
                    session,
                    blobs,
                    tenant_id=principal.tenant_id,
                    data=att["data"],
                    title=att["filename"],
                    filename=att["filename"],
                    mime_type=att["mime"],
                    source=DocumentSource.EMAIL,
                    category_id=None,
                    links=[],
                    created_by=principal.user_id,
                )
                attachments.append(doc.id)
            except ProblemError:
                continue  # unsupported attachment types stay in the original mail document
        row = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="in",
            mailbox_id=body.mailbox_id,
            from_address=parsed["from"],
            to_addresses=parsed["to"],
            subject=parsed["subject"],
            body=parsed["body"],
            header_message_id=parsed["message_id"],
            in_reply_to=parsed["in_reply_to"],
            thread_id=thread_id,
            received_at=parsed["received_at"] or datetime.now(UTC),
            contact_id=contact_id,
            property_id=property_id,
            document_id=document.id,
            attachment_document_ids=attachments,
            status="assigned" if contact_id else "new",
            classification={
                "method": "rules",
                "urgency": mail.urgency(parsed["subject"], parsed["body"]),
                "category": mail.category(parsed["subject"], parsed["body"], categories),
                "property_number": number,
                "contact_matched": contact_id is not None,
            },
            appointment_suggestions=mail.appointments(parsed["body"], local_today()),
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="message.received",
            entity_type="message",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"urgency": row.classification["urgency"]},
        )
        return _out(row)


@router.get("/messages", summary="Vorgangsliste")
async def messages(
    request: Request,
    status: str | None = None,
    contact_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Message).order_by(Message.created_at.desc())
        if status:
            query = query.where(Message.status == status)
        if contact_id:
            query = query.where(Message.contact_id == contact_id)
        return [_out(m) for m in (await session.scalars(query.limit(limit))).all()]


@router.patch("/messages/{message_id}", summary="Zuordnen oder erledigen")
async def assign(
    message_id: uuid.UUID,
    body: MailAssignIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        if body.status is None and (body.contact_id or body.property_id) and row.status == "new":
            row.status = "assigned"
        await session.flush()
        return _out(row)


@router.post("/messages/{message_id}/ticket", status_code=201, summary="Ticket aus E-Mail")
async def to_ticket(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    from mhvp.core.numbering import next_number
    from mhvp.tickets.models import Priority, Ticket, TicketSource, TicketTemplate
    from mhvp.tickets.routers import SLA_HOURS

    if not principal.has("tickets:create"):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing tickets:create.")
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.ticket_id:
            return {"ticket_id": row.ticket_id}
        tpl = None
        if row.classification.get("category"):
            tpl = await session.scalar(
                select(TicketTemplate).where(
                    TicketTemplate.category == row.classification["category"]
                )
            )
        priority = (
            Priority.URGENT
            if row.classification.get("urgency") == "urgent"
            else (tpl.default_priority if tpl else Priority.NORMAL)
        )
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            template_id=tpl.id if tpl else None,
            category=tpl.category if tpl else None,
            title=(row.subject or "E-Mail ohne Betreff")[:300],
            public_description=row.body,
            priority=priority,
            team_id=tpl.default_team_id if tpl else None,
            assignee_user_id=tpl.default_assignee_user_id if tpl else None,
            initiator_contact_id=row.contact_id,
            property_id=row.property_id,
            source=TicketSource.EMAIL,
            sla_due_at=datetime.now(UTC)
            + timedelta(hours=(tpl.sla_hours if tpl and tpl.sla_hours else SLA_HOURS[priority])),
        )
        session.add(ticket)
        await session.flush()
        row.ticket_id, row.status = ticket.id, "assigned"
        await session.flush()
        return {"ticket_id": ticket.id, "number": ticket.number, "priority": ticket.priority.value}


@router.post(
    "/messages/{message_id}/reply-draft",
    status_code=201,
    summary="Antwortentwurf (Vorlage, keine KI)",
)
async def reply_draft(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    from mhvp.contacts.models import Contact
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        contact = await session.get(Contact, row.contact_id) if row.contact_id else None
        salutation = "Sehr geehrte Damen und Herren"
        if contact is not None and contact.salutation and contact.last_name:
            greeting = "Sehr geehrter Herr" if contact.salutation == "Herr" else "Sehr geehrte Frau"
            salutation = f"{greeting} {contact.last_name}"
        ticket = await session.get(Ticket, row.ticket_id) if row.ticket_id else None
        draft = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="draft",
            mailbox_id=row.mailbox_id,
            to_addresses=[row.from_address] if row.from_address else [],
            subject=f"AW: {row.subject or ''}"[:998],
            body=mail.draft_reply(salutation, row.subject, ticket.number if ticket else None),
            in_reply_to=row.header_message_id,
            thread_id=row.thread_id or row.id,
            contact_id=row.contact_id,
            property_id=row.property_id,
            ticket_id=row.ticket_id,
        )
        session.add(draft)
        await session.flush()
        return _out(draft)


@router.post(
    "/messages/{message_id}/send", summary="Entwurf senden (nur mit eingerichtetem Postfach)"
)
async def send(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.direction != "out" or row.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur Entwürfe können gesendet werden.")
        box = await session.get(Mailbox, row.mailbox_id) if row.mailbox_id else None
        if box is None or not box.enabled or not box.smtp_host or not box.secret:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Kein eingerichtetes Postfach für den Versand (M20-01)."
            )
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = (
            box.address,
            ", ".join(row.to_addresses),
            row.subject or "",
        )
        if row.in_reply_to:
            msg["In-Reply-To"] = row.in_reply_to
        msg.set_content(row.body or "")
        with smtplib.SMTP(box.smtp_host, box.smtp_port or 587, timeout=SMTP_TIMEOUT) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(box.username or box.address, box.secret)
            smtp.send_message(msg)
        row.status, row.sent_at = "sent", datetime.now(UTC)
        await session.flush()
        return _out(row)


@router.post(
    "/messages/{message_id}/appointment",
    status_code=201,
    summary="Erkannten Termin in den Kalender übernehmen",
)
async def take_appointment(
    message_id: uuid.UUID,
    body: MailAppointmentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.workspace.models import CalendarEntry

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if body.index >= len(row.appointment_suggestions):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        suggestion = row.appointment_suggestions[body.index]
        entry = CalendarEntry(
            tenant_id=principal.tenant_id,
            owner_user_id=principal.user_id,
            created_by=principal.user_id,
            title=body.title,
            starts_on=date.fromisoformat(suggestion["date"]),
            all_day=suggestion["time"] is None,
            notes=f"Aus E-Mail: {row.subject or ''}"[:4000],
            property_id=row.property_id,
        )
        session.add(entry)
        await session.flush()
        return {"calendar_entry_id": entry.id, "date": entry.starts_on}
