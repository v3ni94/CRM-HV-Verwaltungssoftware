"""Mailbox (/api/v1/mail, M20): intake, assignment, list of cases, ticket from mail, reply
draft. Sending an outbound draft needs a configured and enabled mailbox (M20-01) and runs
through a Vier-Augen-Freigabe: submit -> approve (by someone else) -> sent, or reject -> draft."""

import smtplib
import ssl
import uuid
from datetime import UTC, date, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import mail
from mhvp.communication.models import Mailbox, MailboxUser, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/mail", tags=["Postfach"])
READ = require_permission("communication:read")
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
APPROVE = require_permission("communication:approve")
ADMIN = require_permission("tenant_settings:update")
SMTP_TIMEOUT = 30
OAUTH_STATE_TTL = 600


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


class MailDraftPatchIn(_In):
    subject: str | None = Field(default=None, max_length=998)
    body: str | None = None
    to_addresses: list[str] | None = None


class MailRejectIn(_In):
    note: str = Field(min_length=1, max_length=4000)


class MailReplyDraftIn(_In):
    body: str | None = None


def _mailbox_out(m: Mailbox, user_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
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
        "is_default": m.is_default,
        "user_ids": user_ids or [],
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
            "created_by",
            "mailbox_id",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "rejection_note",
            "gmail_message_id",
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
    is_default: bool | None = None


class MailboxUsersIn(_In):
    user_ids: list[uuid.UUID] = Field(max_length=500)


class OAuthClientIn(_In):
    client_id: str = Field(min_length=10, max_length=200)
    client_secret: str | None = Field(default=None, max_length=200)


async def _mailbox_users(session: AsyncSession) -> dict[uuid.UUID, list[uuid.UUID]]:
    grants: dict[uuid.UUID, list[uuid.UUID]] = {}
    for mailbox_id, user_id in await session.execute(
        select(MailboxUser.mailbox_id, MailboxUser.user_id)
    ):
        grants.setdefault(mailbox_id, []).append(user_id)
    return grants


async def _accessible_mailboxes(session: AsyncSession, user_id: uuid.UUID | None) -> Any:
    """Mailboxes visible to a member: default ones plus explicitly granted ones."""
    granted = select(MailboxUser.mailbox_id).where(MailboxUser.user_id == user_id)
    return select(Mailbox.id).where(or_(Mailbox.is_default.is_(True), Mailbox.id.in_(granted)))


@router.get("/mailboxes", summary="Postfächer (ohne Zugangsdaten)")
async def list_mailboxes(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(select(Mailbox).order_by(Mailbox.address))
        grants = await _mailbox_users(session)
        return [_mailbox_out(m, grants.get(m.id)) for m in rows]


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
        return _mailbox_out(row, (await _mailbox_users(session)).get(row.id))


@router.put("/mailboxes/{mailbox_id}/users", summary="Postfach für Benutzer freigeben")
async def put_mailbox_users(
    mailbox_id: uuid.UUID,
    body: MailboxUsersIn,
    request: Request,
    principal: TenantPrincipal = Depends(ADMIN),
) -> dict[str, Any]:
    """Replaces the explicit grants. A default mailbox is visible to every member anyway."""
    async with tenant_tx(request, principal) as session:
        row = await session.get(Mailbox, mailbox_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.execute(delete(MailboxUser).where(MailboxUser.mailbox_id == mailbox_id))
        wanted = sorted(set(body.user_ids), key=str)
        session.add_all(
            [
                MailboxUser(tenant_id=principal.tenant_id, mailbox_id=mailbox_id, user_id=uid)
                for uid in wanted
            ]
        )
        await session.flush()
        return _mailbox_out(row, wanted)


@router.delete("/mailboxes/{mailbox_id}", status_code=204, summary="Postfach entfernen")
async def delete_mailbox(
    mailbox_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Mailbox, mailbox_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        # Messages stay (audit trail); they just lose the mailbox link.
        await session.execute(
            update(Message).where(Message.mailbox_id == mailbox_id).values(mailbox_id=None)
        )
        await session.delete(row)


# Google OAuth (M20-01): client per tenant, consent flow creates the mailbox --------------


@router.get("/oauth/google", summary="Google OAuth-Client (Status)")
async def get_oauth_client(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    from mhvp.communication import gmail
    from mhvp.platform.models import TenantSettings

    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings))
        own = bool(row and row.google_client_id and row.google_client_secret)
        own_id = row.google_client_id if row and own else None
    env = bool(settings.google_client_id and settings.google_client_secret)
    return {
        "client_id": own_id or settings.google_client_id,
        "configured": own or env,
        "source": "tenant" if own else ("environment" if env else None),
        "redirect_uri": gmail.redirect_uri(settings),
    }


@router.put("/oauth/google", summary="Google OAuth-Client speichern")
async def put_oauth_client(
    body: OAuthClientIn, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    from mhvp.communication import gmail
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.google_client_id = body.client_id.strip()
        if body.client_secret:
            row.google_client_secret = body.client_secret.strip()
        if not row.google_client_secret:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Client-Secret fehlt.")
    return {
        "client_id": body.client_id.strip(),
        "configured": True,
        "source": "tenant",
        "redirect_uri": gmail.redirect_uri(request.app.state.settings),
    }


@router.post("/oauth/google/start", summary="Google-Postfach verbinden (Consent-URL)")
async def start_oauth(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, str]:
    import secrets

    from mhvp.communication import gmail

    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        try:
            client_id, _ = await gmail.oauth_client(session, settings)
        except gmail.GmailError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
    state = secrets.token_urlsafe(32)
    await request.app.state.resources.redis.set(
        f"mail:oauth:{state}", f"{principal.tenant_id}:{principal.user_id}", ex=OAUTH_STATE_TTL
    )
    return {"url": gmail.authorization_url(client_id, settings, state)}


@router.get("/oauth/google/callback", summary="Google OAuth-Rückruf", include_in_schema=False)
async def oauth_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> Any:
    from mhvp.communication import gmail

    settings = request.app.state.settings
    if not state:
        # Direct call of the redirect URI (browser, monitoring): explain instead of a 422.
        return _oauth_result(
            settings,
            error="Diese Adresse ist nur der Rücksprung von Google. Bitte im CRM unter "
            "Einstellungen, Postfächer auf 'Mit Google verbinden' klicken.",
        )
    redis = request.app.state.resources.redis
    stored = await redis.getdel(f"mail:oauth:{state}")
    if not stored:
        return _oauth_result(settings, error="Der Verbindungsversuch ist abgelaufen.")
    tenant_id, user_id = (uuid.UUID(x) for x in stored.decode().split(":"))
    if error or not code:
        return _oauth_result(settings, error="Google hat den Zugriff nicht erteilt.")
    try:
        async with tenant_transaction(sessions(request), tenant_id) as session:
            client_id, client_secret = await gmail.oauth_client(session, settings)
            refresh, address = await gmail.exchange_code(client_id, client_secret, code, settings)
            box = await session.scalar(
                select(Mailbox).where(Mailbox.address == address).with_for_update()
            )
            if box is None:
                box = Mailbox(tenant_id=tenant_id, created_by=user_id, address=address)
                session.add(box)
            box.kind, box.secret, box.enabled, box.last_error = "gmail", refresh, True, None
            box.gmail_history_id = None
            await session.flush()
    except gmail.GmailError as exc:
        return _oauth_result(settings, error=str(exc))
    return _oauth_result(settings, address=address)


def _oauth_result(settings: Any, address: str | None = None, error: str | None = None) -> Any:
    from urllib.parse import urlencode

    if settings.web_crm_url:
        query = {"connected": address} if address else {"oauth_error": error or ""}
        base = settings.web_crm_url.rstrip("/")
        return RedirectResponse(f"{base}/einstellungen/postfaecher?{urlencode(query)}", 302)
    text = f"Postfach {address} verbunden." if address else f"Fehler: {error}"
    return HTMLResponse(f"<p>{text}</p>", status_code=200 if address else 400)


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
    direction: str | None = Query(default=None, pattern="^(in|out)$"),
    ticket_id: uuid.UUID | None = None,
    mailbox_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Message).order_by(Message.created_at.desc())
        if not principal.has("tenant_settings:update"):  # admins see every mailbox
            allowed = await _accessible_mailboxes(session, principal.user_id)
            query = query.where(or_(Message.mailbox_id.is_(None), Message.mailbox_id.in_(allowed)))
        if status:
            query = query.where(Message.status == status)
        if contact_id:
            query = query.where(Message.contact_id == contact_id)
        if direction:
            query = query.where(Message.direction == direction)
        if ticket_id:
            query = query.where(Message.ticket_id == ticket_id)
        if mailbox_id:
            query = query.where(Message.mailbox_id == mailbox_id)
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    Message.subject.ilike(like),
                    Message.from_address.ilike(like),
                    Message.body.ilike(like),
                )
            )
        return [_out(m) for m in (await session.scalars(query.limit(limit))).all()]


@router.get("/messages/{message_id}", summary="Einzelne Nachricht")
async def get_message(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Message, message_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _out(row)


@router.get("/messages/{message_id}/thread", summary="Alle Nachrichten des Vorgangs")
async def message_thread(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    from sqlalchemy import func

    async with tenant_tx(request, principal) as session:
        row = await session.get(Message, message_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        thread_id = row.thread_id or row.id
        query = (
            select(Message)
            .where(or_(Message.thread_id == thread_id, Message.id == thread_id))
            .order_by(func.coalesce(Message.received_at, Message.sent_at, Message.created_at))
        )
        return [_out(m) for m in (await session.scalars(query)).all()]


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
    message_id: uuid.UUID,
    request: Request,
    body: MailReplyDraftIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
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
            body=body.body
            if body is not None and body.body is not None
            else mail.draft_reply(salutation, row.subject, ticket.number if ticket else None),
            in_reply_to=row.header_message_id,
            thread_id=row.thread_id or row.id,
            contact_id=row.contact_id,
            property_id=row.property_id,
            ticket_id=row.ticket_id,
        )
        session.add(draft)
        await session.flush()
        return _out(draft)


@router.patch("/messages/{message_id}/draft", summary="Entwurf bearbeiten")
async def patch_draft(
    message_id: uuid.UUID,
    body: MailDraftPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.direction != "out" or row.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur Entwürfe können bearbeitet werden.")
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await session.flush()
        return _out(row)


@router.post("/messages/{message_id}/submit", summary="Entwurf zur Freigabe einreichen")
async def submit(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.direction != "out" or row.status != "draft":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur Entwürfe können eingereicht werden."
            )
        row.status = "pending"
        row.submitted_by, row.submitted_at = principal.user_id, datetime.now(UTC)
        row.rejection_note = None
        await session.flush()
        return _out(row)


@router.post("/messages/{message_id}/approve", summary="Entwurf freigeben und senden")
async def approve(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    from mhvp.communication import gmail
    from mhvp.tickets.models import TicketEvent

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.direction != "out" or row.status != "pending":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur eingereichte Entwürfe können freigegeben werden."
            )
        if principal.user_id in (row.submitted_by, row.created_by):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vier-Augen-Prinzip: eigene Entwürfe können nicht freigegeben werden.",
            )
        box = await session.get(Mailbox, row.mailbox_id) if row.mailbox_id else None
        if box is None or not box.enabled or not box.secret:
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
            msg["References"] = row.in_reply_to
        msg.set_content(row.body or "")
        domain = box.address.rsplit("@", 1)[-1] or None
        msg["Message-ID"] = make_msgid(domain=domain)

        if box.kind == "gmail":
            try:
                client_id, client_secret = await gmail.oauth_client(
                    session, request.app.state.settings
                )
                client = gmail.make_client(client_id, client_secret, box)
                try:
                    gmail_message_id = await client.send_raw(bytes(msg))
                finally:
                    await client.aclose()
            except gmail.GmailError as exc:
                raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
            row.gmail_message_id = gmail_message_id
        else:
            if not box.smtp_host:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Kein eingerichtetes Postfach für den Versand (M20-01).",
                )
            try:
                with smtplib.SMTP(
                    box.smtp_host, box.smtp_port or 587, timeout=SMTP_TIMEOUT
                ) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.login(box.username or box.address, box.secret)
                    smtp.send_message(msg)
            except (smtplib.SMTPException, OSError) as exc:
                raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc

        row.status, row.sent_at = "sent", datetime.now(UTC)
        row.approved_by, row.approved_at = principal.user_id, datetime.now(UTC)
        row.header_message_id = msg["Message-ID"]
        await session.flush()
        if row.ticket_id:
            session.add(
                TicketEvent(
                    tenant_id=row.tenant_id,
                    ticket_id=row.ticket_id,
                    kind="mail_sent",
                    data={"message_id": str(row.id), "to": row.to_addresses},
                    user_id=principal.user_id,
                )
            )
            await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="mail.sent",
            entity_type="message",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"ticket_id": str(row.ticket_id) if row.ticket_id else None},
        )
        return _out(row)


@router.post("/messages/{message_id}/reject", summary="Entwurf zurückweisen")
async def reject(
    message_id: uuid.UUID,
    body: MailRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)
        if row.direction != "out" or row.status != "pending":
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Nur eingereichte Entwürfe können zurückgewiesen werden.",
            )
        row.status = "draft"
        row.rejection_note = body.note
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
