"""Mail intake shared by the .eml upload endpoint and the Gmail sync job (M20).

Rules decided on 25.09.2026 (docs/integrations/mail-optimierung.md): every inbound mail creates a
ticket, unless it is a reply within a known thread; then it is attached to that thread's ticket.
A re-imported message (same Message-ID) never creates a second message or ticket.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import mail
from mhvp.communication.models import Message
from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.workspace.services import local_today

log = logging.getLogger(__name__)


async def ingest_parsed(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    parsed: dict[str, Any],
    document_id: uuid.UUID,
    mailbox_id: uuid.UUID | None,
    auto_ticket: bool,
) -> tuple[Message, bool]:
    """Store a parsed inbound mail. Returns (message, created)."""
    from mhvp.contacts.models import ContactEmail
    from mhvp.documents.models import DocumentSource
    from mhvp.documents.services import check_upload, store_document
    from mhvp.properties.models import Property
    from mhvp.tickets.models import TicketTemplate

    if parsed["message_id"]:
        known = await session.scalar(
            select(Message).where(
                Message.header_message_id == parsed["message_id"], Message.direction == "in"
            )
        )
        if known is not None:
            return known, False
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
    parent = None
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
            check_upload(att["mime"], att["data"], settings.document_max_bytes)
            doc = await store_document(
                session,
                blobs,
                tenant_id=tenant_id,
                data=att["data"],
                title=att["filename"],
                filename=att["filename"],
                mime_type=att["mime"],
                source=DocumentSource.EMAIL,
                category_id=None,
                links=[],
                created_by=actor_user_id,
            )
            attachments.append(doc.id)
        except ProblemError:
            continue  # unsupported attachment types stay in the original mail document
    row = Message(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        direction="in",
        mailbox_id=mailbox_id,
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
        document_id=document_id,
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
        tenant_id=tenant_id,
        type="message.received",
        entity_type="message",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        payload={"urgency": row.classification["urgency"]},
    )
    if parent is not None and parent.ticket_id:
        await attach_to_ticket(session, row, parent.ticket_id, actor_user_id)
    elif auto_ticket:
        await create_ticket(session, row, actor_user_id)
    if row.ticket_id is not None:
        await _queue_suggestion(session, settings, tenant_id, row)
    return row, True


async def _queue_suggestion(
    session: AsyncSession, settings: Settings, tenant_id: uuid.UUID, row: Message
) -> None:
    """Vorschlag je Mail (M20 Übernahme aus dem Immoware Hub): synchron in Tests und
    Entwicklung (``ai_inline``, wie der Assistent in ``mhvp.ai.routers``), sonst über die Queue
    ``ai``. Ein Fehler beim Vorschlag darf die Mailaufnahme nie stören."""
    if settings.ai_inline:
        from mhvp.communication import suggest

        try:
            result = await suggest.suggest_for_message(session, settings, row)
        except Exception as exc:
            row.suggestion, row.suggestion_status = {"reason": str(exc)[:500]}, "failed"
            return
        status = result.pop("status")
        row.suggestion, row.suggestion_status = result, status
    else:
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.communication.suggest_message",
                args=[str(tenant_id), str(row.id)],
                queue="ai",
            )
        except Exception:
            log.warning("could not queue mail suggestion", extra={"message_id": str(row.id)})


async def ingest_raw(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    raw: bytes,
    mailbox_id: uuid.UUID | None,
    auto_ticket: bool,
) -> tuple[Message, bool]:
    """Store the raw RFC 822 message as a document, then ingest it."""
    from mhvp.documents.models import DocumentSource
    from mhvp.documents.services import store_document

    parsed = mail.parse(raw)
    if parsed["message_id"]:
        known = await session.scalar(
            select(Message).where(
                Message.header_message_id == parsed["message_id"], Message.direction == "in"
            )
        )
        if known is not None:
            return known, False
    document = await store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=raw,
        title=(parsed["subject"] or "E-Mail")[:200],
        filename="mail.eml",
        mime_type="message/rfc822",
        source=DocumentSource.EMAIL,
        category_id=None,
        links=[],
        created_by=actor_user_id,
    )
    return await ingest_parsed(
        session,
        blobs,
        settings,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        parsed=parsed,
        document_id=document.id,
        mailbox_id=mailbox_id,
        auto_ticket=auto_ticket,
    )


async def attach_to_ticket(
    session: AsyncSession, row: Message, ticket_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> None:
    from mhvp.tickets.models import TicketEvent

    row.ticket_id = ticket_id
    if row.status == "new":
        row.status = "assigned"
    session.add(
        TicketEvent(
            tenant_id=row.tenant_id,
            ticket_id=ticket_id,
            kind="mail_received",
            data={"message_id": str(row.id), "from": row.from_address},
            user_id=actor_user_id,
        )
    )
    await session.flush()


async def create_ticket(
    session: AsyncSession, row: Message, actor_user_id: uuid.UUID | None
) -> Any:
    """Ticket from an inbound mail; idempotent when the message already has one."""
    from mhvp.core.numbering import next_number
    from mhvp.tickets.models import Priority, Ticket, TicketSource, TicketTemplate
    from mhvp.tickets.routers import SLA_HOURS

    if row.ticket_id:
        return await session.get(Ticket, row.ticket_id)
    tpl = None
    if row.classification.get("category"):
        tpl = await session.scalar(
            select(TicketTemplate).where(TicketTemplate.category == row.classification["category"])
        )
    priority = (
        Priority.URGENT
        if row.classification.get("urgency") == "urgent"
        else (tpl.default_priority if tpl else Priority.NORMAL)
    )
    ticket = Ticket(
        tenant_id=row.tenant_id,
        created_by=actor_user_id,
        number=await next_number(session, row.tenant_id, "ticket"),
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
    return ticket
