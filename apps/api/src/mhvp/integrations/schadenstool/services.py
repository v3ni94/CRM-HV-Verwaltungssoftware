"""Exchange with the claims adjuster (rule INT-SDT-01).

Everything here runs in one tenant transaction (RLS) and never touches money, bookings or
release gates. Three flows:

* Outbound: :func:`queue_handover`, :func:`queue_comment`, :func:`queue_attachment` and
  :func:`queue_status_if_linked` only write ``SchadenstoolOutbox`` rows; :func:`process_outbox`
  (Celery, every minute) sends them with a stable ``Idempotency-Key`` and retries with the
  webhook retry plan (``mhvp.core.webhooks.RETRY_SCHEDULE_SECONDS``), honouring Retry-After.
* Inbound: the webhook stores events (dedup by ``eventId``); :func:`process_events` fetches
  the changed ticket and applies it via :func:`apply_remote_ticket`.
* Reconciliation: :func:`pull` walks ``GET /tickets`` with ``updatedSince`` and cursor.

Unmapped remote tickets land in the takeover queue (``sync_status=pending_takeover``) with
match proposals; only a member creates or links a local ticket (:func:`take_over`).
Every exchange emits a domain event ``schadenstool.*`` (audit); logs carry ids only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import RETRY_SCHEDULE_SECONDS
from mhvp.integrations.schadenstool.client import (
    Credentials,
    ErrorKind,
    SchadenstoolClient,
    SchadenstoolError,
)
from mhvp.integrations.schadenstool.models import (
    Direction,
    EventStatus,
    ItemKind,
    LinkStatus,
    OutboxKind,
    OutboxStatus,
    SchadenstoolEvent,
    SchadenstoolItemLink,
    SchadenstoolOutbox,
    SchadenstoolTenantConfig,
    SchadenstoolTicketLink,
)
from mhvp.integrations.schadenstool.status_map import remote_status_for
from mhvp.tickets.models import Ticket, TicketComment, TicketEvent, TicketStatus

log = logging.getLogger(__name__)

TICKET_EVENTS = frozenset(
    {
        "ticket.created",
        "ticket.updated",
        "ticket.status_changed",
        "ticket.comment_added",
        "ticket.attachment_added",
    }
)
OUTBOX_BATCH = 50
PULL_PAGE_LIMIT = 100
PULL_MAX_PAGES = 50
PULL_OVERLAP = timedelta(minutes=5)
WAIT_FOR_CREATE_SECONDS = 60


# Configuration ---------------------------------------------------------------------------


async def get_config(
    session: AsyncSession, tenant_id: uuid.UUID
) -> SchadenstoolTenantConfig | None:
    row: SchadenstoolTenantConfig | None = await session.scalar(
        select(SchadenstoolTenantConfig).where(SchadenstoolTenantConfig.tenant_id == tenant_id)
    )
    return row


def credentials(config: SchadenstoolTenantConfig) -> Credentials | None:
    if not config.base_url or not config.token:
        return None
    return Credentials(base_url=config.base_url, token=config.token, hmac_secret=config.hmac_secret)


def active_client(config: SchadenstoolTenantConfig | None) -> SchadenstoolClient:
    """Client for an enabled connection; the feature flag blocks every call (incl. jobs)."""
    creds = credentials(config) if config is not None else None
    if config is None or not config.enabled or creds is None:
        raise ProblemError(ErrorCodes.SCHADENSTOOL_NOT_ENABLED)
    return SchadenstoolClient(creds)


async def require_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> SchadenstoolTenantConfig:
    config = await get_config(session, tenant_id)
    active_client(config)
    if config is None:  # pragma: no cover - active_client raised already
        raise ProblemError(ErrorCodes.SCHADENSTOOL_NOT_ENABLED)
    return config


def problem_for(exc: SchadenstoolError) -> ProblemError:
    code = {
        ErrorKind.AUTH: ErrorCodes.SCHADENSTOOL_AUTH,
        ErrorKind.RATE_LIMITED: ErrorCodes.SCHADENSTOOL_RATE_LIMITED,
        ErrorKind.UNAVAILABLE: ErrorCodes.SCHADENSTOOL_UNAVAILABLE,
    }.get(exc.kind, ErrorCodes.SCHADENSTOOL_REJECTED)
    return ProblemError(code, detail=exc.message)


async def _audit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    type_: str,
    *,
    entity_id: uuid.UUID | None,
    actor: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await emit(
        session,
        tenant_id=tenant_id,
        type=f"schadenstool.{type_}",
        entity_type="schadenstool_ticket_link",
        entity_id=entity_id,
        actor_user_id=actor,
        payload=payload or {},
    )


# Remote field helpers (the draft names fields, not full schemas: accept both spellings) --


def _str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)[:64]


def remote_ticket_id(body: dict[str, Any]) -> str | None:
    return _str(body.get("id") or body.get("mdvId") or body.get("ticketId"))


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _author_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("displayName")
    if isinstance(value, str) and value.strip():
        return value.strip()[:200]
    return None


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# Outbound queue ----------------------------------------------------------------------------


async def link_for_ticket(
    session: AsyncSession, ticket_id: uuid.UUID
) -> SchadenstoolTicketLink | None:
    row: SchadenstoolTicketLink | None = await session.scalar(
        select(SchadenstoolTicketLink).where(SchadenstoolTicketLink.ticket_id == ticket_id)
    )
    return row


def _outbox(
    link: SchadenstoolTicketLink,
    kind: OutboxKind,
    key: str,
    payload: dict[str, Any],
    actor: uuid.UUID | None,
    item: SchadenstoolItemLink | None = None,
) -> SchadenstoolOutbox:
    return SchadenstoolOutbox(
        tenant_id=link.tenant_id,
        link_id=link.id,
        item_link_id=item.id if item is not None else None,
        kind=kind.value,
        idempotency_key=key,
        payload=payload,
        status=OutboxStatus.PENDING.value,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
        requested_by=actor,
    )


async def build_ticket_payload(
    session: AsyncSession, ticket: Ticket, form: dict[str, Any]
) -> dict[str, Any]:
    """Body of ``POST /tickets`` (contract 6.3). Only the public description is sent, never
    the internal one; reporter and damage come from the form (no invented insurance data)."""
    from mhvp.properties.models import Property, Unit

    payload: dict[str, Any] = {
        "externalTicketId": str(ticket.id),
        "title": (form.get("title") or ticket.title)[:300],
        "description": form.get("description") or ticket.public_description or "",
    }
    if ticket.property_id:
        prop = await session.get(Property, ticket.property_id)
        if prop is not None:
            payload["objectExternalId"] = prop.number
    if ticket.unit_id:
        unit = await session.get(Unit, ticket.unit_id)
        if unit is not None:
            payload["unitExternalId"] = unit.number
    if "objectExternalId" not in payload:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Das Ticket braucht ein Objekt, damit der Schadenbearbeiter es zuordnen kann.",
        )
    if form.get("reporter"):
        payload["reporter"] = {"name": str(form["reporter"])[:200]}
    damage = {
        key: form[key] for key in ("date", "type", "location") if form.get(key) not in (None, "")
    }
    if isinstance(damage.get("date"), date):
        damage["date"] = damage["date"].isoformat()
    if damage:
        payload["damage"] = damage
    return payload


async def queue_handover(
    session: AsyncSession, ticket: Ticket, form: dict[str, Any], actor: uuid.UUID | None
) -> SchadenstoolTicketLink:
    await require_enabled(session, ticket.tenant_id)
    link = await link_for_ticket(session, ticket.id)
    if link is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Das Ticket ist bereits an den Schadenbearbeiter übergeben.",
        )
    payload = await build_ticket_payload(session, ticket, form)
    link = SchadenstoolTicketLink(
        tenant_id=ticket.tenant_id,
        ticket_id=ticket.id,
        remote_external_id=str(ticket.id),
        object_external_id=payload.get("objectExternalId"),
        remote_title=payload["title"],
        sync_status=LinkStatus.PENDING_CREATE.value,
    )
    session.add(link)
    await session.flush()
    # Stable per local ticket: a retry or a second worker sends the same key.
    session.add(_outbox(link, OutboxKind.CREATE_TICKET, f"mhvp-ticket-{ticket.id}", payload, actor))
    await _audit(
        session,
        ticket.tenant_id,
        "handover_queued",
        entity_id=link.id,
        actor=actor,
        payload={"ticket_id": str(ticket.id)},
    )
    await session.flush()
    return link


async def _linked_or_pending(session: AsyncSession, ticket: Ticket) -> SchadenstoolTicketLink:
    await require_enabled(session, ticket.tenant_id)
    link = await link_for_ticket(session, ticket.id)
    if link is None or link.sync_status not in (
        LinkStatus.LINKED.value,
        LinkStatus.PENDING_CREATE.value,
    ):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Das Ticket ist nicht mit dem Schadenbearbeiter verknüpft.",
        )
    return link


async def _author_display(session: AsyncSession, user_id: uuid.UUID | None) -> str:
    from mhvp.platform.models import User

    if user_id is None:
        return "Hausverwaltung"
    name = await session.scalar(select(User.display_name).where(User.id == user_id))
    return str(name) if name else "Hausverwaltung"


async def queue_comment(
    session: AsyncSession, ticket: Ticket, comment: TicketComment, actor: uuid.UUID | None
) -> SchadenstoolItemLink:
    link = await _linked_or_pending(session, ticket)
    existing = await session.scalar(
        select(SchadenstoolItemLink).where(
            SchadenstoolItemLink.kind == ItemKind.COMMENT.value,
            SchadenstoolItemLink.local_id == comment.id,
        )
    )
    if existing is not None:
        return existing
    item = SchadenstoolItemLink(
        tenant_id=ticket.tenant_id,
        link_id=link.id,
        kind=ItemKind.COMMENT.value,
        direction=Direction.OUTBOUND.value,
        local_id=comment.id,
    )
    session.add(item)
    await session.flush()
    payload = {
        "externalCommentId": str(comment.id),
        "author": await _author_display(session, comment.author_user_id),
        "message": comment.body,
        "createdAt": (comment.created_at or datetime.now(UTC)).isoformat(),
    }
    session.add(
        _outbox(link, OutboxKind.COMMENT, f"mhvp-comment-{comment.id}", payload, actor, item)
    )
    await _audit(
        session,
        ticket.tenant_id,
        "comment_queued",
        entity_id=link.id,
        actor=actor,
        payload={"comment_id": str(comment.id)},
    )
    await session.flush()
    return item


async def queue_attachment(
    session: AsyncSession, ticket: Ticket, document_id: uuid.UUID, actor: uuid.UUID | None
) -> SchadenstoolItemLink:
    from mhvp.documents.models import Document, DocumentLink

    link = await _linked_or_pending(session, ticket)
    linked = await session.scalar(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document_id,
            DocumentLink.entity_type == "ticket",
            DocumentLink.entity_id == ticket.id,
        )
    )
    document = await session.get(Document, document_id)
    if document is None or linked is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Dokument gehört nicht zu diesem Ticket."
        )
    existing = await session.scalar(
        select(SchadenstoolItemLink).where(
            SchadenstoolItemLink.kind == ItemKind.ATTACHMENT.value,
            SchadenstoolItemLink.local_id == document_id,
        )
    )
    if existing is not None:
        return existing
    item = SchadenstoolItemLink(
        tenant_id=ticket.tenant_id,
        link_id=link.id,
        kind=ItemKind.ATTACHMENT.value,
        direction=Direction.OUTBOUND.value,
        local_id=document_id,
    )
    session.add(item)
    await session.flush()
    session.add(
        _outbox(
            link,
            OutboxKind.ATTACHMENT,
            f"mhvp-attachment-{document_id}",
            {"document_id": str(document_id)},
            actor,
            item,
        )
    )
    await _audit(
        session,
        ticket.tenant_id,
        "attachment_queued",
        entity_id=link.id,
        actor=actor,
        payload={"document_id": str(document_id)},
    )
    await session.flush()
    return item


async def queue_status_if_linked(
    session: AsyncSession, ticket: Ticket, new_status: TicketStatus, actor: uuid.UUID | None
) -> bool:
    """Hook of ``transition_status``: a mapped status of a linked ticket is queued for
    ``PATCH``; an unmapped status, a disabled connection or no link queues nothing."""
    link = await link_for_ticket(session, ticket.id)
    if link is None or link.sync_status not in (
        LinkStatus.LINKED.value,
        LinkStatus.PENDING_CREATE.value,
    ):
        return False
    config = await get_config(session, ticket.tenant_id)
    if config is None or not config.enabled:
        return False
    remote = remote_status_for(new_status)
    if remote is None:
        return False
    row = _outbox(link, OutboxKind.STATUS, "", {"status": remote}, actor)
    row.id = uuid.uuid4()
    row.idempotency_key = f"mhvp-status-{row.id}"
    session.add(row)
    await session.flush()
    return True


# Outbound processing ---------------------------------------------------------------------


def _schedule_retry(row: SchadenstoolOutbox, exc: SchadenstoolError, now: datetime) -> None:
    row.attempts += 1
    row.last_status_code = exc.status_code
    row.last_error = exc.message
    if exc.retryable and row.attempts <= len(RETRY_SCHEDULE_SECONDS):
        delay = RETRY_SCHEDULE_SECONDS[row.attempts - 1]
        if exc.retry_after is not None:
            delay = max(delay, exc.retry_after)
        row.next_attempt_at = now + timedelta(seconds=delay)
    else:
        row.status = OutboxStatus.FAILED.value


async def _send(
    session: AsyncSession,
    client: SchadenstoolClient,
    row: SchadenstoolOutbox,
    link: SchadenstoolTicketLink,
    blobs: Any,
    now: datetime,
) -> bool:
    """Sends one row. ``False`` when it must wait for the ticket create (no attempt used)."""
    if row.kind == OutboxKind.CREATE_TICKET.value:
        body = await client.create_ticket(row.payload, row.idempotency_key)
        link.remote_id = remote_ticket_id(body) or link.remote_id
        link.remote_external_id = _str(body.get("externalId")) or link.remote_external_id
        link.remote_status = _str(body.get("status")) or link.remote_status
        link.sync_status = LinkStatus.LINKED.value
        link.last_error = None
        link.last_synced_at = now
        return True
    if not link.remote_id:
        row.next_attempt_at = now + timedelta(seconds=WAIT_FOR_CREATE_SECONDS)
        return False
    item = await session.get(SchadenstoolItemLink, row.item_link_id) if row.item_link_id else None
    if row.kind == OutboxKind.COMMENT.value:
        body = await client.add_comment(link.remote_id, row.payload, row.idempotency_key)
        if item is not None:
            item.remote_id = _str(body.get("commentId") or body.get("id")) or item.remote_id
    elif row.kind == OutboxKind.ATTACHMENT.value:
        from mhvp.documents.models import Document

        document = await session.get(Document, uuid.UUID(row.payload["document_id"]))
        if document is None:
            raise SchadenstoolError(ErrorKind.REJECTED, "Dokument nicht mehr vorhanden.")
        content = blobs.get(document.storage_ref)
        body = await client.add_attachment(
            link.remote_id,
            filename=document.filename,
            content=content,
            mime_type=document.mime_type,
            external_attachment_id=str(document.id),
            idempotency_key=row.idempotency_key,
        )
        if item is not None:
            item.remote_id = (
                _str(body.get("attachmentId") or body.get("id") or body.get("documentId"))
                or item.remote_id
            )
    elif row.kind == OutboxKind.STATUS.value:
        await client.patch_status(link.remote_id, row.payload["status"], row.idempotency_key)
        link.remote_status = row.payload["status"]
    link.last_synced_at = now
    return True


async def process_outbox(
    session: AsyncSession, tenant_id: uuid.UUID, *, blobs: Any = None, now: datetime | None = None
) -> dict[str, int]:
    """Sends due rows of one tenant. Disabled connection or an invalid token: nothing is sent."""
    now = now or datetime.now(UTC)
    counts = {"sent": 0, "retry": 0, "failed": 0, "waiting": 0}
    config = await get_config(session, tenant_id)
    if config is None or not config.enabled or credentials(config) is None or config.token_invalid:
        return counts
    client = active_client(config)
    rows = (
        await session.scalars(
            select(SchadenstoolOutbox)
            .where(
                SchadenstoolOutbox.status == OutboxStatus.PENDING.value,
                SchadenstoolOutbox.next_attempt_at <= now,
            )
            .order_by(SchadenstoolOutbox.created_at, SchadenstoolOutbox.id)
            .limit(OUTBOX_BATCH)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for row in rows:
        link = await session.get(SchadenstoolTicketLink, row.link_id)
        if link is None:
            continue
        try:
            done = await _send(session, client, row, link, blobs, now)
        except SchadenstoolError as exc:
            if exc.kind == ErrorKind.AUTH:
                config.token_invalid = True
                row.last_error = exc.message
                row.last_status_code = exc.status_code
                counts["retry"] += 1
                await _audit(session, tenant_id, "token_invalid", entity_id=link.id)
                break
            _schedule_retry(row, exc, now)
            if row.status == OutboxStatus.FAILED.value:
                counts["failed"] += 1
                if row.kind == OutboxKind.CREATE_TICKET.value:
                    link.sync_status = LinkStatus.ERROR.value
                link.last_error = exc.message
                await _audit(
                    session,
                    tenant_id,
                    "send_failed",
                    entity_id=link.id,
                    payload={"kind": row.kind, "status": exc.status_code},
                )
            else:
                counts["retry"] += 1
            continue
        if not done:
            counts["waiting"] += 1
            continue
        row.status = OutboxStatus.SENT.value
        row.sent_at = now
        row.attempts += 1
        row.last_error = None
        counts["sent"] += 1
        await _audit(
            session,
            tenant_id,
            "sent",
            entity_id=link.id,
            payload={"kind": row.kind, "remote_id": link.remote_id},
        )
    await session.flush()
    return counts


# Inbound ---------------------------------------------------------------------------------


async def _property_for_object(
    session: AsyncSession, object_external_id: str | None
) -> uuid.UUID | None:
    """Proposal only: our property number equals the remote ``objectExternalId``."""
    from mhvp.properties.models import Property

    if not object_external_id:
        return None
    found: uuid.UUID | None = await session.scalar(
        select(Property.id).where(Property.number == object_external_id).limit(1)
    )
    return found


async def _proposed_ticket(session: AsyncSession, external_id: str | None) -> uuid.UUID | None:
    wanted = _uuid_or_none(external_id)
    if wanted is None:
        return None
    found = await session.scalar(select(Ticket.id).where(Ticket.id == wanted))
    return found


async def apply_remote_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    client: SchadenstoolClient,
    body: dict[str, Any],
    *,
    blobs: Any = None,
    settings: Any = None,
    now: datetime | None = None,
) -> SchadenstoolTicketLink | None:
    """Upserts the link of a remote ticket. Mapped: store status and ``updatedAt``, pull
    comments and attachments. Unmapped: takeover queue with proposals, nothing local."""
    now = now or datetime.now(UTC)
    remote_id = remote_ticket_id(body)
    if remote_id is None:
        return None
    link = await session.scalar(
        select(SchadenstoolTicketLink).where(SchadenstoolTicketLink.remote_id == remote_id)
    )
    external_id = _str(body.get("externalId") or body.get("externalTicketId"))
    if link is None and external_id:
        # Answer of our own POST may still be in flight: match the pending create.
        local = _uuid_or_none(external_id)
        if local is not None:
            link = await session.scalar(
                select(SchadenstoolTicketLink).where(SchadenstoolTicketLink.ticket_id == local)
            )
            if link is not None and link.remote_id not in (None, remote_id):
                link = None
            if link is not None:
                link.remote_id = remote_id
                link.sync_status = LinkStatus.LINKED.value
    if link is None:
        object_external_id = _str(body.get("objectExternalId"))
        link = SchadenstoolTicketLink(
            tenant_id=tenant_id,
            remote_id=remote_id,
            sync_status=LinkStatus.PENDING_TAKEOVER.value,
            object_external_id=object_external_id,
            proposed_property_id=await _property_for_object(session, object_external_id),
            proposed_ticket_id=await _proposed_ticket(session, external_id),
        )
        session.add(link)
        await _audit(
            session, tenant_id, "takeover_queued", entity_id=None, payload={"remote_id": remote_id}
        )
    link.remote_external_id = external_id or link.remote_external_id
    link.remote_title = str(body.get("title"))[:300] if body.get("title") else link.remote_title
    link.remote_status = _str(body.get("status")) or link.remote_status
    link.remote_updated_at = _parse_dt(body.get("updatedAt")) or link.remote_updated_at
    link.object_external_id = _str(body.get("objectExternalId")) or link.object_external_id
    link.last_synced_at = now
    await session.flush()
    if link.sync_status == LinkStatus.LINKED.value and link.ticket_id is not None:
        await sync_comments(session, client, link)
        await sync_attachments(session, client, link, blobs=blobs, settings=settings)
    return link


async def sync_comments(
    session: AsyncSession, client: SchadenstoolClient, link: SchadenstoolTicketLink
) -> int:
    """Remote comments become internal ticket comments (author name kept on the item link).
    Our own comments coming back (``externalCommentId`` known, or remote id known) are
    skipped: no echo, no duplicate."""
    if link.remote_id is None or link.ticket_id is None:
        return 0
    created = 0
    for remote in await client.list_comments(link.remote_id):
        remote_id = _str(remote.get("id") or remote.get("commentId"))
        if remote_id is None:
            continue
        known = await session.scalar(
            select(SchadenstoolItemLink.id).where(
                SchadenstoolItemLink.kind == ItemKind.COMMENT.value,
                SchadenstoolItemLink.remote_id == remote_id,
            )
        )
        if known is not None:
            continue
        own = _uuid_or_none(remote.get("externalCommentId"))
        if own is not None:
            mine = await session.scalar(
                select(SchadenstoolItemLink).where(
                    SchadenstoolItemLink.kind == ItemKind.COMMENT.value,
                    SchadenstoolItemLink.local_id == own,
                )
            )
            if mine is not None:
                mine.remote_id = mine.remote_id or remote_id
                continue
        message = str(remote.get("message") or "").strip()
        if not message:
            continue
        author = _author_name(remote.get("author"))
        comment = TicketComment(
            tenant_id=link.tenant_id,
            ticket_id=link.ticket_id,
            internal=True,
            body=message,
        )
        session.add(comment)
        await session.flush()
        session.add(
            SchadenstoolItemLink(
                tenant_id=link.tenant_id,
                link_id=link.id,
                kind=ItemKind.COMMENT.value,
                direction=Direction.INBOUND.value,
                local_id=comment.id,
                remote_id=remote_id,
                author_name=author,
            )
        )
        await session.flush()
        created += 1
        await _audit(
            session,
            link.tenant_id,
            "comment_received",
            entity_id=link.id,
            payload={"comment_id": str(comment.id), "remote_id": remote_id},
        )
    return created


async def sync_attachments(
    session: AsyncSession,
    client: SchadenstoolClient,
    link: SchadenstoolTicketLink,
    *,
    blobs: Any,
    settings: Any = None,
) -> int:
    """Remote attachments are downloaded into the DMS (``store_document`` scans for malware)
    and linked to the ticket. Our own uploads coming back are skipped."""
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import store_document

    if link.remote_id is None or link.ticket_id is None:
        return 0
    created = 0
    for remote in await client.list_attachments(link.remote_id):
        remote_id = _str(remote.get("id") or remote.get("attachmentId") or remote.get("documentId"))
        if remote_id is None:
            continue
        known = await session.scalar(
            select(SchadenstoolItemLink.id).where(
                SchadenstoolItemLink.kind == ItemKind.ATTACHMENT.value,
                SchadenstoolItemLink.remote_id == remote_id,
            )
        )
        if known is not None:
            continue
        own = _uuid_or_none(remote.get("externalAttachmentId"))
        if own is not None:
            mine = await session.scalar(
                select(SchadenstoolItemLink).where(
                    SchadenstoolItemLink.kind == ItemKind.ATTACHMENT.value,
                    SchadenstoolItemLink.local_id == own,
                )
            )
            if mine is not None:
                mine.remote_id = mine.remote_id or remote_id
                continue
        url = remote.get("downloadUrl") or remote.get("url")
        if not isinstance(url, str) or blobs is None:
            continue
        content, mime = await client.download(url)
        filename = str(
            remote.get("fileName")
            or remote.get("filename")
            or remote.get("name")
            or f"schaden-{remote_id}"
        )[:255]
        mime_type = str(remote.get("mimeType") or mime or "application/octet-stream")
        mime_type = mime_type.split(";")[0].strip()[:127]
        document = await store_document(
            session,
            blobs,
            tenant_id=link.tenant_id,
            data=content,
            title=filename[:300],
            filename=filename,
            mime_type=mime_type,
            source=DocumentSource.IMPORT,
            category_id=None,
            links=[("ticket", link.ticket_id, LinkRole.ATTACHMENT)],
            created_by=None,
            settings=settings,
        )
        session.add(
            SchadenstoolItemLink(
                tenant_id=link.tenant_id,
                link_id=link.id,
                kind=ItemKind.ATTACHMENT.value,
                direction=Direction.INBOUND.value,
                local_id=document.id,
                remote_id=remote_id,
            )
        )
        await session.flush()
        created += 1
        await _audit(
            session,
            link.tenant_id,
            "attachment_received",
            entity_id=link.id,
            payload={"document_id": str(document.id), "remote_id": remote_id},
        )
    return created


async def record_event(session: AsyncSession, tenant_id: uuid.UUID, event: dict[str, Any]) -> bool:
    """Stores a verified webhook event. ``False`` for a duplicate ``eventId`` (at least once)."""
    from sqlalchemy.dialects.postgresql import insert

    event_id = _str(event.get("eventId"))
    event_type = str(event.get("eventType") or "")[:64]
    if event_id is None or not event_type:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ereignis ohne eventId oder eventType.")
    stmt = (
        insert(SchadenstoolEvent)
        .values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            event_id=event_id,
            event_type=event_type,
            entity_type=_str(event.get("entityType")),
            entity_id=_str(event.get("entityId")),
            occurred_at=_parse_dt(event.get("occurredAt")),
            payload=event.get("payload") if isinstance(event.get("payload"), dict) else {},
            status=EventStatus.RECEIVED.value,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "event_id"])
        .returning(SchadenstoolEvent.id)
    )
    inserted = await session.scalar(stmt)
    return inserted is not None


def _event_ticket_id(row: SchadenstoolEvent) -> str | None:
    if row.entity_type in (None, "ticket") and row.entity_id:
        return row.entity_id
    payload = row.payload or {}
    return _str(payload.get("ticketId") or payload.get("ticket_id"))


async def process_events(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    blobs: Any = None,
    settings: Any = None,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    counts = {"processed": 0, "ignored": 0, "failed": 0, "retry": 0}
    config = await get_config(session, tenant_id)
    if config is None or not config.enabled or credentials(config) is None or config.token_invalid:
        return counts
    client = active_client(config)
    rows = (
        await session.scalars(
            select(SchadenstoolEvent)
            .where(SchadenstoolEvent.status == EventStatus.RECEIVED.value)
            .order_by(SchadenstoolEvent.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for row in rows:
        ticket_id = _event_ticket_id(row)
        if row.event_type not in TICKET_EVENTS or ticket_id is None:
            row.status, row.processed_at = EventStatus.IGNORED.value, now
            counts["ignored"] += 1
            continue
        try:
            async with session.begin_nested():
                body = await client.get_ticket(ticket_id)
                if not remote_ticket_id(body):
                    body = {**body, "id": ticket_id}
                await apply_remote_ticket(
                    session, tenant_id, client, body, blobs=blobs, settings=settings, now=now
                )
        except SchadenstoolError as exc:
            row.error = exc.message
            if exc.kind == ErrorKind.AUTH:
                config.token_invalid = True
                counts["retry"] += 1
                break
            if exc.retryable:
                counts["retry"] += 1
                continue
            row.status, row.processed_at = EventStatus.FAILED.value, now
            counts["failed"] += 1
            continue
        row.status, row.processed_at, row.error = EventStatus.PROCESSED.value, now, None
        counts["processed"] += 1
    await session.flush()
    return counts


async def pull(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    blobs: Any = None,
    settings: Any = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Reconciliation: every remote ticket changed since the watermark (``updatedSince``),
    page by page via ``nextCursor``. The watermark moves to the newest ``updatedAt`` seen
    minus an overlap; applying a ticket twice is harmless (idempotent)."""
    now = now or datetime.now(UTC)
    counts = {"tickets": 0, "pages": 0}
    config = await get_config(session, tenant_id)
    if config is None or not config.enabled or credentials(config) is None or config.token_invalid:
        return counts
    client = active_client(config)
    since = config.pull_watermark.isoformat() if config.pull_watermark else None
    cursor: str | None = None
    newest = config.pull_watermark
    try:
        for _ in range(PULL_MAX_PAGES):
            page = await client.list_tickets(
                limit=PULL_PAGE_LIMIT, cursor=cursor, updated_since=since
            )
            counts["pages"] += 1
            for body in page["items"]:
                await apply_remote_ticket(
                    session, tenant_id, client, body, blobs=blobs, settings=settings, now=now
                )
                counts["tickets"] += 1
                updated = _parse_dt(body.get("updatedAt"))
                if updated is not None and (newest is None or updated > newest):
                    newest = updated
            cursor = page["nextCursor"]
            if not cursor:
                break
    except SchadenstoolError as exc:
        if exc.kind == ErrorKind.AUTH:
            config.token_invalid = True
        config.last_pull_at = now
        config.last_pull_message = exc.message
        await session.flush()
        return counts
    if newest is not None:
        config.pull_watermark = newest - PULL_OVERLAP
    config.last_pull_at = now
    config.last_pull_message = f"{counts['tickets']} Tickets abgeglichen."
    await session.flush()
    return counts


# Takeover --------------------------------------------------------------------------------


async def take_over(
    session: AsyncSession,
    link: SchadenstoolTicketLink,
    *,
    action: str,
    actor: uuid.UUID | None,
    ticket_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    blobs: Any = None,
    settings: Any = None,
) -> SchadenstoolTicketLink:
    """Member decision for one remote ticket: ``create`` a local ticket, ``link`` an existing
    one or ``dismiss``. Nothing happens without this call (proposal semantics)."""
    from mhvp.core.numbering import next_number
    from mhvp.properties.models import Property
    from mhvp.tickets.models import Priority, TicketSource
    from mhvp.tickets.routers import SLA_HOURS

    config = await require_enabled(session, link.tenant_id)
    if link.sync_status != LinkStatus.PENDING_TAKEOVER.value:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Dieses Schadenticket ist schon entschieden."
        )
    now = datetime.now(UTC)
    if action == "dismiss":
        link.sync_status = LinkStatus.DISMISSED.value
    elif action == "link":
        if ticket_id is None or await session.get(Ticket, ticket_id) is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ticket nicht gefunden.")
        if await link_for_ticket(session, ticket_id) is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Das Ticket ist bereits mit einem Schadenticket verknüpft.",
            )
        link.ticket_id = ticket_id
        link.sync_status = LinkStatus.LINKED.value
    elif action == "create":
        if property_id is not None and await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Objekt nicht gefunden.")
        client = active_client(config)
        if link.remote_id is None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Schadenticket ohne Kennung.")
        try:
            body = await client.get_ticket(link.remote_id)
        except SchadenstoolError as exc:
            raise problem_for(exc) from exc
        ticket = Ticket(
            tenant_id=link.tenant_id,
            created_by=actor,
            number=await next_number(session, link.tenant_id, "ticket"),
            property_id=property_id,
            title=str(body.get("title") or link.remote_title or "Schadenticket")[:300],
            public_description=str(body.get("description") or "") or None,
            priority=Priority.NORMAL,
            source=TicketSource.MANUAL,
            sla_due_at=now + timedelta(hours=SLA_HOURS[Priority.NORMAL]),
        )
        session.add(ticket)
        await session.flush()
        session.add(
            TicketEvent(
                tenant_id=link.tenant_id,
                ticket_id=ticket.id,
                kind="schadenstool_takeover",
                user_id=actor,
                data={"remote_id": link.remote_id},
            )
        )
        link.ticket_id = ticket.id
        link.sync_status = LinkStatus.LINKED.value
    else:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Entscheidung.")
    link.decided_by, link.decided_at = actor, now
    await session.flush()
    await _audit(
        session,
        link.tenant_id,
        f"takeover_{action}",
        entity_id=link.id,
        actor=actor,
        payload={"remote_id": link.remote_id, "ticket_id": str(link.ticket_id or "")},
    )
    if link.sync_status == LinkStatus.LINKED.value:
        client = active_client(config)
        try:
            await sync_comments(session, client, link)
            await sync_attachments(session, client, link, blobs=blobs, settings=settings)
        except SchadenstoolError as exc:
            # The decision stands; the next pull or webhook fetches comments and files.
            link.last_error = exc.message
    await session.flush()
    return link


async def check_connection(config: SchadenstoolTenantConfig) -> tuple[bool, str]:
    creds = credentials(config)
    if creds is None:
        return False, "Basisadresse und Token fehlen."
    try:
        await SchadenstoolClient(creds).list_tickets(limit=1)
    except SchadenstoolError as exc:
        return False, exc.message
    return True, "Verbindung erfolgreich."
