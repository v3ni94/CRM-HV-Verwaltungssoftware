"""Mailbox (/api/v1/mail, M20): intake, assignment, list of cases, ticket from mail, reply
draft. Sending an outbound draft needs a configured and enabled mailbox (M20-01) and runs
through a Vier-Augen-Freigabe: submit -> approve (by someone else) -> sent, or reject -> draft."""

import logging
import uuid
from datetime import UTC, date, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import schemas as ai_s
from mhvp.communication import attachments, mail, services, transport
from mhvp.communication.models import Mailbox, MailboxUser, Message, Playbook
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.escaping import LIKE_ESCAPE, escape_like
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets import tnr

log = logging.getLogger(__name__)
router = APIRouter(prefix="/mail", tags=["Postfach"])
READ = require_permission("communication:read")
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
APPROVE = require_permission("communication:approve")
ADMIN = require_permission("tenant_settings:update")
PLAYBOOK_ADMIN = require_permission("tenant_settings:update")
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
    to_addresses: list[EmailStr] | None = Field(default=None, max_length=20)


class MailRejectIn(_In):
    note: str = Field(min_length=1, max_length=4000)


class MailReplyDraftIn(_In):
    body: str | None = None


class PlaybookIn(_In):
    title: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    keywords: list[str] = Field(default_factory=list, max_length=64)
    summary: str = ""
    steps: list[str] = Field(default_factory=list)
    reply_template: str | None = None
    status: str = Field(default="draft", pattern="^(draft|active|archived)$")


class PlaybookPatchIn(_In):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    keywords: list[str] | None = Field(default=None, max_length=64)
    summary: str | None = None
    steps: list[str] | None = None
    reply_template: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|archived)$")


class ApplyPlaybookIn(_In):
    playbook_id: uuid.UUID


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
        "calendar_enabled": m.calendar_enabled,
        "calendar_id": m.calendar_id,
        "archive_on_ticket_done": m.archive_on_ticket_done,
        "archive_scope_missing": m.archive_scope_missing,
        "user_ids": user_ids or [],
    }


PREVIEW_CHARS = 200
_LIST_FIELDS = (
    "id",
    "channel",
    "direction",
    "status",
    "from_address",
    "to_addresses",
    "cc_addresses",
    "subject",
    "header_message_id",
    "in_reply_to",
    "references_header",
    "send_error",
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
    "updated_by",
    "mailbox_id",
    "submitted_by",
    "submitted_at",
    "approved_by",
    "approved_at",
    "author_approval_required",
    "author_approval_reason",
    "rejection_note",
    "gmail_message_id",
    "suggestion",
    "suggestion_status",
)


def _preview(body: str | None) -> str | None:
    if not body:
        return None
    text = " ".join(body.split())
    return text[:PREVIEW_CHARS] + ("…" if len(text) > PREVIEW_CHARS else "")


def _list_out(m: Message) -> dict[str, Any]:
    """List row (Review 26.09.2026, M3): every field of the detail except ``body`` and
    ``body_html``; ``body_preview`` holds the first 200 characters. The detail endpoint
    (``GET /mail/messages/{id}``) and the thread deliver the full text."""
    out = {k: getattr(m, k) for k in _LIST_FIELDS}
    out["body_preview"] = _preview(m.body)
    return out


def _out(m: Message) -> dict[str, Any]:
    out = _list_out(m)
    out["body"], out["body_html"] = m.body, m.body_html
    return out


def _playbook_out(p: Playbook) -> dict[str, Any]:
    return {
        k: getattr(p, k)
        for k in (
            "id",
            "title",
            "category",
            "keywords",
            "summary",
            "steps",
            "reply_template",
            "source_ticket_id",
            "status",
            "usage_count",
            "last_used_at",
            "created_by",
            "created_at",
            "updated_at",
        )
    }


async def _message(
    session: AsyncSession, message_id: uuid.UUID, principal: TenantPrincipal | None = None
) -> Message:
    row = await session.get(Message, message_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if principal is not None:
        await assert_message_accessible(session, principal, row)
    return row


async def assert_message_accessible(
    session: AsyncSession, principal: TenantPrincipal, row: Message
) -> None:
    """Postfachzugriff je Einzelnachricht wie in der Liste (Review 26.09.2026, H2): ohne
    Postfach frei, sonst Standardpostfach, Freigabe per ``MailboxUser`` oder Administrator.
    Nicht zugängliche Nachrichten gelten als nicht vorhanden (404, kein Rückschluss)."""
    if row.mailbox_id is None or principal.has("tenant_settings:update"):
        return
    box = await session.get(Mailbox, row.mailbox_id)
    if box is None or not await mailbox_accessible(session, principal, box):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


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
    calendar_enabled: bool | None = None
    calendar_id: str | None = Field(default=None, min_length=1, max_length=320)
    archive_on_ticket_done: bool | None = None


class MailboxUsersIn(_In):
    user_ids: list[uuid.UUID] = Field(max_length=500)


class OAuthClientIn(_In):
    client_id: str = Field(min_length=10, max_length=200)
    client_secret: str | None = Field(default=None, max_length=200)


class OAuthStartIn(_In):
    purpose: str = Field(default="mail", pattern="^(mail|drive)$")


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


async def mailbox_accessible(
    session: AsyncSession, principal: TenantPrincipal, mailbox: Mailbox
) -> bool:
    """Whether the acting user may write through ``mailbox``: administrators
    (``tenant_settings:update``, the permission that manages mailboxes) always, members only
    for the default mailbox or one granted via ``MailboxUser`` (same rule as the mail list)."""
    if principal.has("tenant_settings:update"):
        return True
    if mailbox.is_default:
        return True
    if principal.user_id is None:
        return False
    grant = await session.scalar(
        select(MailboxUser.mailbox_id).where(
            MailboxUser.mailbox_id == mailbox.id, MailboxUser.user_id == principal.user_id
        )
    )
    return grant is not None


async def _live_mailbox(
    session: AsyncSession, mailbox_id: uuid.UUID, *, lock: bool = False
) -> Mailbox:
    """Mailbox that is not soft deleted (Review 26.09.2026, M12); 404 otherwise."""
    row = await session.get(Mailbox, mailbox_id, with_for_update=lock)
    if row is None or row.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/mailboxes", summary="Postfächer (ohne Zugangsdaten)")
async def list_mailboxes(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(Mailbox).where(Mailbox.deleted_at.is_(None)).order_by(Mailbox.address)
        )
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
        row = await _live_mailbox(session, mailbox_id, lock=True)
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
        row = await _live_mailbox(session, mailbox_id, lock=True)
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
    """Soft delete (Review 26.09.2026, M12): the mailbox is deactivated (no sync, no send,
    credentials removed, no longer a default mailbox) and disappears from the settings; its
    messages keep the mailbox binding, so they stay visible only to administrators and the
    users the mailbox was shared with, never to every member."""
    async with tenant_tx(request, principal) as session:
        row = await _live_mailbox(session, mailbox_id, lock=True)
        row.deleted_at = datetime.now(UTC)
        row.enabled = False
        row.is_default = False
        row.secret = None
        row.calendar_enabled = False
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="mailbox.deleted",
            entity_type="mailbox",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"address": row.address},
        )


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


@router.post("/oauth/google/start", summary="Google-Konto verbinden (Consent-URL)")
async def start_oauth(
    request: Request,
    body: OAuthStartIn | None = None,
    principal: TenantPrincipal = Depends(ADMIN),
) -> dict[str, str]:
    import secrets

    from mhvp.communication import gmail

    purpose = (body or OAuthStartIn()).purpose
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        try:
            client_id, _ = await gmail.oauth_client(session, settings)
        except gmail.GmailError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
    state = secrets.token_urlsafe(32)
    await request.app.state.resources.redis.set(
        f"mail:oauth:{state}",
        f"{principal.tenant_id}:{principal.user_id}:{purpose}",
        ex=OAUTH_STATE_TTL,
    )
    return {"url": gmail.authorization_url(client_id, settings, state, purpose=purpose)}


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
    parts = stored.decode().split(":")
    tenant_id, user_id = uuid.UUID(parts[0]), uuid.UUID(parts[1])
    # Alte Redis-Werte ohne dritten Teil stammen aus dem Postfach-Ablauf (mail).
    purpose = parts[2] if len(parts) > 2 else "mail"
    if error or not code:
        return _oauth_result(
            settings, error="Google hat den Zugriff nicht erteilt.", purpose=purpose
        )
    try:
        async with tenant_transaction(sessions(request), tenant_id) as session:
            client_id, client_secret = await gmail.oauth_client(session, settings)
            refresh, address = await gmail.exchange_code(client_id, client_secret, code, settings)
            if purpose == "drive":
                await _store_drive_connection(
                    session, tenant_id, user_id, client_id, client_secret, refresh
                )
            else:
                box = await session.scalar(
                    select(Mailbox).where(Mailbox.address == address).with_for_update()
                )
                if box is None:
                    box = Mailbox(tenant_id=tenant_id, created_by=user_id, address=address)
                    session.add(box)
                box.kind, box.secret, box.enabled, box.last_error = "gmail", refresh, True, None
                box.gmail_history_id = None
                box.deleted_at = None  # reconnecting a removed address revives it (M12)
            await session.flush()
    except gmail.GmailError as exc:
        return _oauth_result(settings, error=str(exc), purpose=purpose)
    return _oauth_result(settings, address=address, purpose=purpose)


async def _store_drive_connection(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> None:
    """Speichert das Drive-Refresh-Token als DMS-Anbindung (Google Drive ist Ziel des
    Dokumentenmoduls; Zugriff hier ausschließlich über dessen Model, nicht dessen Router)."""
    import json

    from mhvp.documents.models import DmsConnection, StorageKind

    row = await session.scalar(
        select(DmsConnection).where(DmsConnection.kind == StorageKind.GOOGLE_DRIVE)
    )
    if row is None:
        row = DmsConnection(tenant_id=tenant_id, kind=StorageKind.GOOGLE_DRIVE)
        session.add(row)
    row.secret = json.dumps({"client_secret": client_secret, "refresh_token": refresh_token})
    options = dict(row.options or {})
    options["client_id"] = client_id
    row.options = options
    if options.get("root_folder_id"):
        row.enabled = True
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="dms_connection.updated",
        entity_type="dms_connection",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"kind": "google_drive", "enabled": row.enabled},
    )


def _oauth_result(
    settings: Any, address: str | None = None, error: str | None = None, purpose: str = "mail"
) -> Any:
    from urllib.parse import urlencode

    target = "postfaecher" if purpose == "mail" else "dms"
    if settings.web_crm_url:
        if address and purpose == "mail":
            query = {"connected": address}
        elif address:
            query = {"connected": "drive", "account": address}
        else:
            query = {"oauth_error": error or ""}
        base = settings.web_crm_url.rstrip("/")
        # Land on the same-site return page first: session cookies are SameSite=Strict and
        # would not accompany a redirect chain that started at Google (login page otherwise).
        inner = f"/einstellungen/{target}?{urlencode(query)}"
        return RedirectResponse(f"{base}/api/session/return?{urlencode({'next': inner})}", 302)
    text = f"Konto {address} verbunden." if address else f"Fehler: {error}"
    return HTMLResponse(f"<p>{text}</p>", status_code=200 if address else 400)


@router.post("/mailboxes/{mailbox_id}/sync", summary="Gmail-Posteingang jetzt abrufen")
async def sync_mailbox_now(
    mailbox_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    from mhvp.communication.gmail import GmailError, sync_one
    from mhvp.communication.services import dispatch_forward_queue

    try:
        async with tenant_tx(request, principal) as session:
            box = await _live_mailbox(session, mailbox_id)
            if box.kind != "gmail":
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Nur Gmail-Postfächer werden abgerufen."
                )
            result = await sync_one(session, request.app.state.settings, mailbox_id)
    except GmailError as exc:
        # The failed sync rolled back; keep the reason visible on the mailbox.
        async with tenant_tx(request, principal) as session:
            failed = await session.get(Mailbox, mailbox_id, with_for_update=True)
            if failed is not None:
                failed.last_error = str(exc)[:1000]
        raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc
    if result["created"]:
        # Rechnungs-Weiterleitung erst nach dem Commit des Abrufs (M13).
        await dispatch_forward_queue(request.app.state.settings, principal.tenant_id)
    return result


@router.post("/ingest", status_code=201, summary="E-Mail (.eml) aufnehmen und zuordnen")
async def ingest(
    body: MailIngestIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.communication.services import dispatch_forward_queue, ingest_parsed
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
        result = _out(row)
        queued = (row.classification.get("invoice_forward") or {}).get("status") == "queued"
    if queued:
        # Versand der Weiterleitung erst nach dem Commit (Review 26.09.2026, M13).
        await dispatch_forward_queue(request.app.state.settings, principal.tenant_id)
        async with tenant_tx(request, principal) as session:
            refreshed = await session.get(Message, row.id)
            if refreshed is not None:
                result = _out(refreshed)
    return result


def _messages_query(
    principal: TenantPrincipal,
    *,
    status: str | None,
    contact_id: uuid.UUID | None,
    direction: str | None,
    ticket_id: uuid.UUID | None,
    mailbox_id: uuid.UUID | None,
    q: str | None,
    include_closed: bool = True,
) -> Any:
    """Filter of the mail list and its count. Members see messages without mailbox, of the
    default mailboxes and of mailboxes shared with them; administrators every message."""
    query = select(Message)
    if not principal.has("tenant_settings:update"):  # admins see every mailbox
        granted = select(MailboxUser.mailbox_id).where(MailboxUser.user_id == principal.user_id)
        allowed = select(Mailbox.id).where(
            or_(Mailbox.is_default.is_(True), Mailbox.id.in_(granted))
        )
        query = query.where(or_(Message.mailbox_id.is_(None), Message.mailbox_id.in_(allowed)))
    if status:
        query = query.where(Message.status == status)
    elif not include_closed and ticket_id is None:
        # Erledigte Vorgänge standardmäßig ausgeblendet (1.23.0 der Parallel-Session)
        from mhvp.tickets.models import Ticket
        from mhvp.tickets.status import CLOSING_STATUSES

        closed_ticket = select(Ticket.id).where(Ticket.status.in_(CLOSING_STATUSES))
        query = query.where(
            Message.status != "done",
            or_(Message.ticket_id.is_(None), Message.ticket_id.not_in(closed_ticket)),
        )
    if contact_id:
        query = query.where(Message.contact_id == contact_id)
    if direction:
        query = query.where(Message.direction == direction)
    if ticket_id:
        query = query.where(Message.ticket_id == ticket_id)
    if mailbox_id:
        query = query.where(Message.mailbox_id == mailbox_id)
    if q:
        like = f"%{escape_like(q)}%"  # literal search term (M3)
        query = query.where(
            or_(
                Message.subject.ilike(like, escape=LIKE_ESCAPE),
                Message.from_address.ilike(like, escape=LIKE_ESCAPE),
                Message.body.ilike(like, escape=LIKE_ESCAPE),
            )
        )
    return query


@router.get("/messages", summary="Vorgangsliste (ohne Text, mit Vorschau)")
async def messages(
    request: Request,
    status: str | None = None,
    contact_id: uuid.UUID | None = None,
    direction: str | None = Query(default=None, pattern="^(in|out)$"),
    ticket_id: uuid.UUID | None = None,
    mailbox_id: uuid.UUID | None = None,
    q: str | None = None,
    include_closed: bool = Query(
        default=False,
        description=(
            "Erledigte Nachrichten zeigen (Status done oder verknüpftes Ticket done, closed,"
            " rejected); gilt nur ohne status-Filter"
        ),
    ),
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    """Rows carry ``body_preview`` (200 characters) instead of ``body`` and ``body_html``
    (Review 26.09.2026, M3); ``GET /mail/messages/{id}`` delivers the full text."""
    async with tenant_tx(request, principal) as session:
        query = _messages_query(
            principal,
            status=status,
            contact_id=contact_id,
            direction=direction,
            ticket_id=ticket_id,
            mailbox_id=mailbox_id,
            q=q,
            include_closed=include_closed,
        ).order_by(Message.created_at.desc())
        return [_list_out(m) for m in (await session.scalars(query.limit(limit))).all()]


@router.get("/messages/count", summary="Anzahl der Nachrichten je Filter")
async def messages_count(
    request: Request,
    status: str | None = None,
    contact_id: uuid.UUID | None = None,
    direction: str | None = Query(default=None, pattern="^(in|out)$"),
    ticket_id: uuid.UUID | None = None,
    mailbox_id: uuid.UUID | None = None,
    q: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, int]:
    """Count with the same filters and visibility as the list (badge "Freigaben", M3)."""
    async with tenant_tx(request, principal) as session:
        query = _messages_query(
            principal,
            status=status,
            contact_id=contact_id,
            direction=direction,
            ticket_id=ticket_id,
            mailbox_id=mailbox_id,
            q=q,
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        return {"count": int(total or 0)}


@router.get("/messages/{message_id}", summary="Einzelne Nachricht")
async def get_message(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Message, message_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await assert_message_accessible(session, principal, row)
        return _out(row)


@router.get("/messages/{message_id}/thread", summary="Alle Nachrichten des Vorgangs")
async def message_thread(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Message, message_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await assert_message_accessible(session, principal, row)
        thread_id = row.thread_id or row.id
        query = (
            select(Message)
            .where(or_(Message.thread_id == thread_id, Message.id == thread_id))
            .order_by(func.coalesce(Message.received_at, Message.sent_at, Message.created_at))
        )
        if not principal.has("tenant_settings:update"):
            allowed = await _accessible_mailboxes(session, principal.user_id)
            query = query.where(or_(Message.mailbox_id.is_(None), Message.mailbox_id.in_(allowed)))
        return [_out(m) for m in (await session.scalars(query)).all()]


@router.patch("/messages/{message_id}", summary="Zuordnen oder erledigen")
async def assign(
    message_id: uuid.UUID,
    body: MailAssignIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
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
        row = await _message(session, message_id, principal)
        ticket = await create_ticket(session, row, principal.user_id)
        return {"ticket_id": ticket.id, "number": ticket.number, "priority": ticket.priority.value}


INVOICE_INTAKE = require_permission("accounting:create")


@router.post(
    "/messages/{message_id}/attachments/{attachment_id}/invoice-extraction",
    status_code=202,
    summary="Anhang als Rechnung erfassen (KI-Vorschlag)",
)
async def invoice_extraction_from_attachment(
    message_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(INVOICE_INTAKE),
) -> dict[str, Any]:
    """Starts extract_invoice on an existing mail attachment document (rule 0.1.6: proposal
    only, the invoice itself is created only after a confirmed review, see mhvp.ai.imports)."""
    from mhvp.documents.models import Document

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        if attachment_id not in row.attachment_document_ids:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Anhang gehört nicht zu dieser Nachricht."
            )
        document = await session.get(Document, attachment_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if document.mime_type != "application/pdf":
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Nur PDF-Anhänge können als Rechnung erfasst werden."
            )
    from mhvp.ai.models import AiTask
    from mhvp.ai.routers import start_extraction_run

    run = await start_extraction_run(
        request,
        principal,
        AiTask.EXTRACT_INVOICE,
        [attachment_id],
        "Rechnung aus E-Mail-Anhang erfassen",
        "invoice",
        message_id,
    )
    return {"run_id": str(run.id), "proposal_id": run.proposal_id}


class InvoiceForwardSettingsIn(_In):
    enabled: bool = True
    forward_address: str | None = Field(default=None, max_length=320)
    sender_allowlist: list[str] = Field(default_factory=list, max_length=200)


@router.get("/invoice-forwarding", summary="Rechnungs-Weiterleitung: Einstellungen (Postfächer)")
async def get_invoice_forwarding(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == principal.tenant_id)
        )
        cfg = row.invoice_forwarding if row else {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "forward_address": cfg.get("forward_address"),
        "sender_allowlist": list(cfg.get("sender_allowlist", [])),
        "learning_list": list(cfg.get("learning_list", [])),
    }


@router.put(
    "/invoice-forwarding", summary="Rechnungs-Weiterleitung: Einstellungen speichern (Postfächer)"
)
async def put_invoice_forwarding(
    body: InvoiceForwardSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(ADMIN),
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == principal.tenant_id)
        )
        if row is None:
            row = TenantSettings(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
            await session.flush()
        cfg = dict(row.invoice_forwarding)
        cfg["enabled"] = body.enabled
        cfg["forward_address"] = body.forward_address
        cfg["sender_allowlist"] = sorted(
            {s.lower().strip() for s in body.sender_allowlist if s.strip()}
        )
        cfg.setdefault("learning_list", [])
        cfg.setdefault("confirmed_counts", {})
        row.invoice_forwarding = cfg
        row.updated_by = principal.user_id
        await session.flush()
    return await get_invoice_forwarding(request, principal)


class CallAssistantSettingsIn(_In):
    enabled: bool = True
    sender_patterns: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=50)


class CallAssistantSettingsOut(BaseModel):
    enabled: bool
    sender_patterns: list[str]
    keywords: list[str]


def _call_assistant_out(raw: dict[str, Any] | None) -> CallAssistantSettingsOut:
    from mhvp.tickets.call_assistant import config_from

    cfg = config_from(raw)
    return CallAssistantSettingsOut(
        enabled=cfg.enabled,
        sender_patterns=list(cfg.sender_patterns),
        keywords=list(cfg.keywords),
    )


@router.get(
    "/call-assistant",
    summary="Telefonassistenz (Hallo Heidi): Erkennungsmuster der Protokoll-Mails",
)
async def get_call_assistant(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> CallAssistantSettingsOut:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        raw = await session.scalar(
            select(TenantSettings.call_assistant).where(
                TenantSettings.tenant_id == principal.tenant_id
            )
        )
    return _call_assistant_out(raw)


@router.put(
    "/call-assistant",
    summary="Telefonassistenz (Hallo Heidi): Erkennungsmuster speichern",
)
async def put_call_assistant(
    body: CallAssistantSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(ADMIN),
) -> CallAssistantSettingsOut:
    """Absendermuster (Teil der Absenderadresse) und Kennwörter (Betreff, im Text nur mit
    beschrifteter Rufnummer). Leere Listen nutzen die eingebauten Muster."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == principal.tenant_id)
        )
        if row is None:
            row = TenantSettings(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
            await session.flush()
        row.call_assistant = {
            "enabled": body.enabled,
            "sender_patterns": sorted(
                {s.lower().strip()[:200] for s in body.sender_patterns if s.strip()}
            ),
            "keywords": sorted({k.lower().strip()[:200] for k in body.keywords if k.strip()}),
        }
        row.updated_by = principal.user_id
        await session.flush()
        return _call_assistant_out(row.call_assistant)


@router.post(
    "/messages/{message_id}/forward-invoice",
    summary='Rechnung weiterleiten ("Weiterleiten?"-Vorschlag bestätigen)',
)
async def forward_invoice(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Der Operator bestätigt einen Weiterleitungs-Vorschlag manuell; nach der zweiten
    Bestätigung eines Absenders landet dieser auf der Lernliste (operator 25.09.2026) und
    künftige Mails desselben Absenders werden automatisch weitergeleitet."""
    from mhvp.communication.forwarding import register_confirmation
    from mhvp.communication.forwarding_dispatch import forward_and_archive
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        settings_row = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == principal.tenant_id)
        )
        if settings_row is None or not settings_row.invoice_forwarding.get("forward_address"):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Keine Zieladresse für die Weiterleitung hinterlegt (Postfächer).",
            )
        forward_address = settings_row.invoice_forwarding["forward_address"]
        await forward_and_archive(
            session,
            request.app.state.settings,
            principal.tenant_id,
            principal.user_id,
            row,
            forward_address,
        )
        settings_row.invoice_forwarding = register_confirmation(
            settings_row.invoice_forwarding, row.from_address or ""
        )
        classification = dict(row.classification)
        forward = dict(classification.get("invoice_forward") or {})
        forward["status"], forward["forwarded_to"] = "sent", forward_address
        classification["invoice_forward"] = forward
        row.classification = classification
        await session.flush()
        return {"forwarded_to": forward_address}


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
        row = await _message(session, message_id, principal)
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
            subject=(
                tnr.reply_subject(row.subject, ticket.number)
                if ticket is not None
                else f"AW: {row.subject or ''}"[:998]
            ),
            body=body.body
            if body is not None and body.body is not None
            else mail.draft_reply(salutation, row.subject, ticket.number if ticket else None),
            in_reply_to=row.header_message_id,
            references_header=tnr_references(row),
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
        row = await _message(session, message_id, principal)
        if row.direction != "out" or row.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur Entwürfe können bearbeitet werden.")
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        # Wer den Text zuletzt geändert hat, zählt im Vier-Augen-Prinzip (M16).
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post("/messages/{message_id}/submit", summary="Entwurf zur Freigabe einreichen")
async def submit(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        if row.direction != "out" or row.status != "draft":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur Entwürfe können eingereicht werden."
            )
        row.status = "pending"
        row.submitted_by, row.submitted_at = principal.user_id, datetime.now(UTC)
        row.rejection_note = None
        await session.flush()
        return _out(row)


def tnr_references(parent: Message) -> str | None:
    """Kopfzeile ``References`` der Antwort: die Referenzen der Ursprungsmail plus deren
    Message-ID, damit der Thread beim Empfänger zusammenbleibt (RFC 5322)."""
    ids = [i for i in (parent.references_header or "").split() if i]
    if parent.header_message_id and parent.header_message_id not in ids:
        ids.append(parent.header_message_id)
    return " ".join(ids)[:20000] or None


async def _find_sent_gmail_id(
    session: AsyncSession, settings: Any, box: Mailbox, header_message_id: str | None
) -> str | None:
    """Versandnachweis aus Gmail für die gespeicherte Message-ID (M1)."""
    from mhvp.communication import gmail

    if not header_message_id:
        return None
    try:
        client_id, client_secret = await gmail.oauth_client(session, settings)
        client = gmail.make_client(client_id, client_secret, box)
        try:
            return await client.find_by_rfc822_msgid(header_message_id)
        finally:
            await client.aclose()
    except gmail.GmailError as exc:
        raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from exc


async def _record_sent(
    session: AsyncSession,
    row: Message,
    principal: TenantPrincipal,
    gmail_message_id: str | None,
) -> None:
    """Statuswechsel auf ``sent`` mit Ticket-Ereignis, SLA-Erstreaktion und Domänenereignis."""
    from mhvp.tickets.models import TicketEvent

    if gmail_message_id is not None:
        row.gmail_message_id = gmail_message_id
    row.send_error = None
    row.status, row.sent_at = "sent", datetime.now(UTC)
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
        # M20-03 Nachvollziehbarkeit: wer vorformuliert und wer freigegeben hat.
        session.add(
            TicketEvent(
                tenant_id=row.tenant_id,
                ticket_id=row.ticket_id,
                kind="reply_sent",
                data={
                    "message_id": str(row.id),
                    "to": row.to_addresses,
                    "drafted_by": str(row.created_by) if row.created_by else None,
                    "approved_by": str(row.approved_by) if row.approved_by else None,
                    "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                    "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                    "self_approved": row.approved_by == row.created_by,
                    "author_approval_required": row.author_approval_required,
                    "author_approval_reason": row.author_approval_reason,
                },
                user_id=principal.user_id,
            )
        )
        from mhvp.sla.models import SlaClock
        from mhvp.sla.service import mark_first_response

        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == row.ticket_id))
        if clock is not None:
            await mark_first_response(session, clock)
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


def _assert_sendable_box(box: Mailbox | None) -> Mailbox:
    if box is None or box.deleted_at is not None or not box.enabled or not box.secret:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Kein eingerichtetes Postfach für den Versand (M20-01)."
        )
    return box


@router.post("/messages/{message_id}/approve", summary="Entwurf freigeben und senden")
async def approve(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Freigabe und Versand über ``approve_and_send`` (Vier-Augen oder Direktversand nach
    Regel M20-03, siehe dort)."""
    return await approve_and_send(message_id, request, principal)


async def _self_approval_allowed(
    session: AsyncSession, row: Message, principal: TenantPrincipal
) -> bool:
    """M20-03 (Betreiberentscheidung 26.09.2026): eine dem Ticket zugeordnete Antwort darf der
    Verfasser selbst freigeben, wenn er ``communication:approve`` hat, zum Zeitpunkt der
    Vorformulierung kein Kennzeichen (Azubi, neuer Mitarbeiter) trug, aktuell keines trägt
    und die Notbremse des Mandanten (alle Antworten mit Freigabe) aus ist. Nachrichten ohne
    Ticket (Postfach frei, Playbook, Weiterleitung) bleiben immer beim Vier-Augen-Prinzip."""
    if row.ticket_id is None or row.author_approval_required:
        return False
    if not principal.has("communication:approve"):
        return False
    flagged, _ = await services.author_reply_approval(session, row.tenant_id, principal.user_id)
    if flagged:
        return False
    return not await services.reply_approval_all(session, row.tenant_id)


async def approve_and_send(
    message_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal,
    *,
    direct_send: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Zweiphasiger Versand (Review 26.09.2026, M1), damit ein Fehler nach ``send_raw`` nie
    zu einem zweiten Versand führt.

    M20-03: ist der Freigebende zugleich Verfasser, entscheidet ``_self_approval_allowed``
    (Ticketantwort, Recht ``communication:approve``, kein Kennzeichen, keine Notbremse), sonst
    Vier-Augen. ``direct_send`` liefert der Aufrufer ``POST /tickets/{id}/reply`` mit
    Kontext; jede Selbstfreigabe wird als ``message.direct_sent`` (Nutzer, Ticket, Kennzeichen)
    und am Ticket als ``reply_approved`` und ``reply_sent`` protokolliert.
    Der Versandweg selbst ist unverändert:

    1. Eigene Transaktion: Prüfungen (Vier-Augen, Postfachzugriff), Status ``sending`` und
       die Message-ID als Idempotenzschlüssel werden gespeichert.
    2. Zweite Transaktion mit Zeilensperre: Versand, dann ``sent`` mit Gmail-ID, Ereignisse.

    Scheitert Schritt 2 nach dem Versand (Verbindungsabbruch, Fehler beim Ereignis), bleibt
    die Nachricht ``sending`` mit ihrer Message-ID. Die nächste Freigabe sucht bei Gmail nach
    dieser Message-ID: gefunden heißt gesendet (kein zweiter Versand), sonst wird mit
    derselben Message-ID gesendet. Ohne Nachweismöglichkeit (SMTP) wird nicht erneut
    gesendet; eine Person löst den Fall über Zurückweisen (neuer Entwurf) auf."""
    settings = request.app.state.settings

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        resume = row.status == "sending"
        if row.direction != "out" or row.status not in ("pending", "sending"):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur eingereichte Entwürfe können freigegeben werden."
            )
        self_approval = principal.user_id in (row.submitted_by, row.created_by, row.updated_by)
        if self_approval and not await _self_approval_allowed(session, row, principal):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vier-Augen-Prinzip: eigene oder selbst bearbeitete Entwürfe können "
                "nicht freigegeben werden.",
            )
        box = _assert_sendable_box(
            await session.get(Mailbox, row.mailbox_id) if row.mailbox_id else None
        )
        if not await mailbox_accessible(session, principal, box):
            # Freigabe nur über ein Postfach, das der Freigebende selbst nutzen darf (M16).
            raise ProblemError(
                ErrorCodes.FORBIDDEN,
                detail="Keine Berechtigung für das Postfach dieses Entwurfs.",
                developer_message="Mailbox not granted to the approver.",
            )
        if not row.to_addresses:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Der Entwurf hat keinen Empfänger.")
        if not resume:
            domain = box.address.rsplit("@", 1)[-1] or None
            row.header_message_id = make_msgid(domain=domain)
            row.status = "sending"
            row.send_error = None
            row.approved_by, row.approved_at = principal.user_id, datetime.now(UTC)
            if row.ticket_id:
                from mhvp.tickets.models import TicketEvent

                session.add(
                    TicketEvent(
                        tenant_id=row.tenant_id,
                        ticket_id=row.ticket_id,
                        kind="reply_approved",
                        data={
                            "message_id": str(row.id),
                            "approved_by": str(principal.user_id),
                            "approved_at": row.approved_at.isoformat(),
                            "self_approved": self_approval,
                            "drafted_by": str(row.created_by) if row.created_by else None,
                            "author_approval_required": row.author_approval_required,
                            "author_approval_reason": row.author_approval_reason,
                        },
                        user_id=principal.user_id,
                    )
                )
        await session.flush()

    send_failure: str | None = None
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id)  # Zeilensperre für die Dauer des Versands
        if row.status == "sent":
            return _out(row)  # parallel bereits abgeschlossen
        if row.status != "sending":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Die Freigabe wurde zwischenzeitlich zurückgenommen."
            )
        box = _assert_sendable_box(await session.get(Mailbox, row.mailbox_id))
        gmail_message_id: str | None = None
        proven = False
        if resume:
            if box.kind != "gmail":
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Versandnachweis fehlt: der Entwurf wurde bereits zum Versand "
                    "freigegeben, das Ergebnis ist unbekannt (SMTP). Bitte im Postausgang "
                    "des Postfachs prüfen und den Entwurf zurückweisen, um neu zu senden.",
                )
            gmail_message_id = await _find_sent_gmail_id(
                session, settings, box, row.header_message_id
            )
            proven = gmail_message_id is not None
        if not proven:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = (
                box.address,
                ", ".join(row.to_addresses),
                row.subject or "",
            )
            if row.cc_addresses:
                msg["Cc"] = ", ".join(row.cc_addresses)
            if row.in_reply_to:
                msg["In-Reply-To"] = row.in_reply_to
                msg["References"] = row.references_header or row.in_reply_to
            msg.set_content(row.body or "")
            # Standardanhänge aus Antwortvorlagen (operator 26.09.2026): Dokumentverweise der
            # ausgehenden Nachricht werden beim Versand beigefügt.
            await attachments.attach_documents(session, request, msg, row.attachment_document_ids)
            msg["Message-ID"] = row.header_message_id  # Idempotenzschlüssel des Versands
            try:
                gmail_message_id = await transport.send_message(session, settings, box, msg)
            except transport.MailTransportUncertainError as exc:
                # Antwort des Transports fehlt: Versand offen lassen; die nächste Freigabe
                # prüft per Message-ID (Gmail) oder eine Person weist zurück (SMTP).
                row.send_error = str(exc)[:2000]
                if box.kind != "gmail":
                    row.status = "pending"
                await session.flush()
                send_failure = str(exc)
            except transport.MailTransportError as exc:
                # Der Transport hat den Versand abgelehnt: nichts ist raus, der Entwurf
                # bleibt eingereicht (Anzeige "fehlgeschlagen" im Ticket).
                row.send_error = str(exc)[:2000]
                row.status = "pending"
                await session.flush()
                send_failure = str(exc)
        if send_failure is None:
            await _record_sent(session, row, principal, gmail_message_id)
            if self_approval:
                await emit(
                    session,
                    tenant_id=principal.tenant_id,
                    type="message.direct_sent",
                    entity_type="message",
                    entity_id=row.id,
                    actor_user_id=principal.user_id,
                    payload={
                        "user_id": str(principal.user_id),
                        "ticket_id": str(row.ticket_id) if row.ticket_id else None,
                        "author_approval_required": row.author_approval_required,
                        "author_approval_reason": row.author_approval_reason,
                        "template_id": (direct_send or {}).get("template_id"),
                        "origin": (direct_send or {}).get("origin", "mailbox"),
                    },
                )
            result = _out(row)
    if send_failure is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail=send_failure)
    return result


@router.post("/messages/{message_id}/reject", summary="Entwurf zurückweisen")
async def reject(
    message_id: uuid.UUID,
    body: MailRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        # ``sending`` ohne Versandnachweis (SMTP, Review 26.09.2026, M1) wird hier von einer
        # Person aufgelöst: zurück zum Entwurf, neuer Versuch mit neuer Message-ID.
        if row.direction != "out" or row.status not in ("pending", "sending"):
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
        row = await _message(session, message_id, principal)
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


# KI-Vorschläge und Playbooks (M20 Übernahme aus dem Immoware Hub) ---------------------------


@router.post("/messages/{message_id}/suggest", summary="KI-Vorschlag neu berechnen")
async def recompute_suggestion(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    from mhvp.communication import suggest

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        result = await suggest.suggest_for_message(session, request.app.state.settings, row)
        status = result.pop("status")
        row.suggestion, row.suggestion_status = result, status
        await session.flush()
        return _out(row)


@router.post("/messages/{message_id}/preparation", summary="Mail-Vorbereitung berechnen")
async def compute_preparation(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Resolves contact/unit/property, searches this property's documents (local and scoped
    external DMS) and drafts a reply from the tenant's and property's knowledge base (Welle 3
    item 14). A proposal only; never sent (rule 0.1.6)."""
    from mhvp.communication import preparation

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        result = await preparation.prepare_for_message(session, request.app.state.settings, row)
        suggestion = dict(row.suggestion or {})
        suggestion["preparation"] = result
        row.suggestion = suggestion
        await session.flush()
        return result


@router.get("/messages/{message_id}/preparation", summary="Mail-Vorbereitung lesen")
async def get_preparation(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        preparation_result = (row.suggestion or {}).get("preparation")
        if preparation_result is None:
            return {"status": "none"}
        return dict(preparation_result)


@router.post("/messages/{message_id}/preparation/correct", summary="Mail-Vorbereitung korrigieren")
async def correct_preparation(
    message_id: uuid.UUID,
    body: ai_s.PreparationCorrectionIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Records a person's correction of the automatic resolution as a learned knowledge base
    entry (kind ``correction``); the AI never approves this alone (rule 0.1.6)."""
    from mhvp.communication import preparation

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        entry = await preparation.record_correction(
            session,
            row,
            contact_id=body.contact_id,
            unit_id=body.unit_id,
            property_id=body.property_id,
            note=body.note,
            user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="message.preparation_corrected",
            entity_type="message",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"knowledge_entry_id": str(entry.id)},
        )
        return {"knowledge_entry_id": entry.id}


@router.get("/playbooks", summary="Playbooks")
async def list_playbooks(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Playbook).order_by(Playbook.title)
        if status:
            query = query.where(Playbook.status == status)
        if q:
            query = query.where(Playbook.title.ilike(f"%{q}%"))
        return [_playbook_out(p) for p in (await session.scalars(query)).all()]


@router.post("/playbooks", status_code=201, summary="Playbook anlegen")
async def create_playbook(
    body: PlaybookIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = Playbook(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _playbook_out(row)


@router.patch("/playbooks/{playbook_id}", summary="Playbook ändern oder freigeben")
async def patch_playbook(
    playbook_id: uuid.UUID,
    body: PlaybookPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Playbook, playbook_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await session.flush()
        return _playbook_out(row)


@router.delete("/playbooks/{playbook_id}", status_code=204, summary="Playbook löschen")
async def delete_playbook(
    playbook_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(PLAYBOOK_ADMIN)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Playbook, playbook_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)


@router.post(
    "/messages/{message_id}/apply-playbook",
    status_code=201,
    summary="Antwortentwurf aus Playbook",
)
async def apply_playbook(
    message_id: uuid.UUID,
    body: ApplyPlaybookIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.contacts.models import Contact
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        playbook = await session.get(Playbook, body.playbook_id, with_for_update=True)
        if playbook is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        contact = await session.get(Contact, row.contact_id) if row.contact_id else None
        salutation = "Sehr geehrte Damen und Herren"
        if contact is not None and contact.salutation and contact.last_name:
            greeting = "Sehr geehrter Herr" if contact.salutation == "Herr" else "Sehr geehrte Frau"
            salutation = f"{greeting} {contact.last_name}"
        ticket = await session.get(Ticket, row.ticket_id) if row.ticket_id else None
        objekt = row.suggestion.get("property_number") or ""
        template = playbook.reply_template
        if template:
            body_text = (
                template.replace("{anrede}", salutation)
                .replace("{ticket}", str(ticket.number) if ticket else "")
                .replace("{objekt}", objekt)
            )
        elif row.suggestion.get("reply_draft"):
            body_text = str(row.suggestion["reply_draft"])
        else:
            body_text = mail.draft_reply(salutation, row.subject, ticket.number if ticket else None)
        playbook.usage_count += 1
        playbook.last_used_at = datetime.now(UTC)
        draft = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="draft",
            mailbox_id=row.mailbox_id,
            to_addresses=[row.from_address] if row.from_address else [],
            subject=(
                tnr.reply_subject(row.subject, ticket.number)
                if ticket is not None
                else f"AW: {row.subject or ''}"[:998]
            ),
            body=body_text,
            in_reply_to=row.header_message_id,
            references_header=tnr_references(row),
            thread_id=row.thread_id or row.id,
            contact_id=row.contact_id,
            property_id=row.property_id,
            ticket_id=row.ticket_id,
        )
        session.add(draft)
        await session.flush()
        return _out(draft)
