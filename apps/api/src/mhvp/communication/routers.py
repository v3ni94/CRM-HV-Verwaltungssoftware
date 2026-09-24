"""Mailbox (/api/v1/mail, M20): intake, assignment, list of cases, ticket from mail, reply
draft. Sending needs a configured and enabled mailbox (M20-01)."""

import smtplib
import ssl
import uuid
from datetime import UTC, date, datetime
from email.message import EmailMessage
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import mail
from mhvp.communication.models import Mailbox, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError

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
    auto_ticket: bool = False


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
        "last_synced_at": m.last_synced_at,
        "last_error": m.last_error,
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


class MailboxPatchIn(_In):
    secret: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None
    kind: str | None = Field(default=None, pattern="^(imap|gmail)$")


@router.get("/mailboxes", summary="Postfächer (ohne Zugangsdaten)")
async def list_mailboxes(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(select(Mailbox).order_by(Mailbox.address))
        return [_mailbox_out(m) for m in rows]


@router.patch("/mailboxes/{mailbox_id}", summary="Postfach ändern (Token, aktiv)")
async def patch_mailbox(
    mailbox_id: uuid.UUID,
    body: MailboxPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(ADMIN),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Mailbox, mailbox_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await session.flush()
        return _mailbox_out(row)


@router.post("/mailboxes/{mailbox_id}/sync", summary="Gmail-Posteingang jetzt abrufen")
async def sync_mailbox_now(
    mailbox_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    from mhvp.communication.gmail import GmailError, sync_one

    try:
        async with tenant_tx(request, principal) as session:
            box = await session.get(Mailbox, mailbox_id)
            if box is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            if box.kind != "gmail":
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Nur Gmail-Postfächer werden abgerufen."
                )
            return await sync_one(session, request.app.state.settings, mailbox_id)
    except GmailError as exc:
        # The failed sync rolled back; keep the reason visible on the mailbox.
        async with tenant_tx(request, principal) as session:
            box = await session.get(Mailbox, mailbox_id, with_for_update=True)
            if box is not None:
                box.last_error = str(exc)[:1000]
        raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc


@router.post("/ingest", status_code=201, summary="E-Mail (.eml) aufnehmen und zuordnen")
async def ingest(
    body: MailIngestIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.communication.services import ingest_parsed
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document

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
        row, _ = await ingest_parsed(
            session,
            blobs,
            request.app.state.settings,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            parsed=parsed,
            document_id=document.id,
            mailbox_id=body.mailbox_id,
            auto_ticket=body.auto_ticket,
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
    from mhvp.communication.services import create_ticket

    if not principal.has("tickets:create"):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing tickets:create.")
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        ticket = await create_ticket(session, row, principal.user_id)
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
