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
from mhvp.communication.html import sanitize_html
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
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
) -> tuple[Message, bool]:
    """Store a parsed inbound mail. Returns (message, created).

    ``gmail_message_id`` and ``gmail_thread_id`` come from the Gmail sync (Review 26.09.2026,
    M15): the archive job and the forwarding need the Gmail id, the thread id is the last
    resort for threading (M7)."""
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
    parent = await find_parent(
        session,
        in_reply_to=parsed["in_reply_to"],
        references=parsed.get("references"),
        gmail_thread_id=gmail_thread_id,
    )
    if parent is not None:
        thread_id = parent.thread_id or parent.id
        contact_id = contact_id or parent.contact_id
        property_id = property_id or parent.property_id
    attachments = []
    rejected: list[dict[str, Any]] = []
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
        except ProblemError as exc:
            # Abgewiesene Anhänge (Typ oder Größe, Review 26.09.2026, M8) bleiben im Roh-.eml;
            # Name, Typ, Größe und Grund werden an der Nachricht vermerkt und angezeigt.
            rejected.append(
                {
                    "filename": att["filename"],
                    "mime": att["mime"],
                    "size": len(att["data"]),
                    "reason": (exc.detail or exc.error.title)[:300],
                }
            )
    row = Message(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        direction="in",
        mailbox_id=mailbox_id,
        from_address=parsed["from"],
        to_addresses=parsed["to"],
        cc_addresses=list(parsed.get("cc") or []),
        subject=parsed["subject"],
        body=parsed["body"],
        body_html=sanitize_html(parsed.get("body_html")),
        header_message_id=parsed["message_id"],
        in_reply_to=parsed["in_reply_to"],
        references_header=parsed.get("references"),
        thread_id=thread_id,
        received_at=parsed["received_at"] or datetime.now(UTC),
        contact_id=contact_id,
        property_id=property_id,
        document_id=document_id,
        attachment_document_ids=attachments,
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        status="assigned" if contact_id else "new",
        classification={
            "method": "rules",
            "urgency": mail.urgency(parsed["subject"], parsed["body"]),
            "category": mail.category(parsed["subject"], parsed["body"], categories),
            "property_number": number,
            "contact_matched": contact_id is not None,
            "attachments_total": len(parsed["attachments"]),
            "attachments_rejected": rejected,
            "inline_skipped": int(parsed.get("inline_skipped") or 0),
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
    tnr_ticket = await ticket_by_tnr(session, tenant_id, parsed["subject"])
    if parent is not None and parent.ticket_id:
        await attach_to_ticket(session, row, parent.ticket_id, actor_user_id)
    elif tnr_ticket is not None and await sender_belongs_to_ticket(session, row, tnr_ticket):
        # Kennung TNR#<nummer> im Betreff (docs/rules/M19-02-tnr.md): Zuordnung zum Ticket des
        # Mandanten auch ohne Thread-Kopfzeilen, aber nur bei bekanntem Absender (Ticketkontakt
        # oder Beteiligter des bisherigen Mailverlaufs); der Vorgang übernimmt den Thread.
        await attach_to_ticket(session, row, tnr_ticket.id, actor_user_id)
        row.thread_id = row.thread_id or await _ticket_thread_id(session, tnr_ticket.id)
        row.contact_id = row.contact_id or tnr_ticket.contact_id or tnr_ticket.initiator_contact_id
        row.property_id = row.property_id or tnr_ticket.property_id
        await session.flush()
    else:
        if tnr_ticket is not None:
            # Fremder Absender mit geratener oder weitergeleiteter Kennung: nur Vorschlag,
            # keine Zuordnung (Datenschutz, Fehlzustellung der nächsten Antwort).
            row.classification = dict(row.classification) | {
                "tnr_suggestion": {
                    "ticket_id": str(tnr_ticket.id),
                    "number": tnr_ticket.number,
                    "reason": "Absender nicht am Ticket beteiligt",
                }
            }
            await session.flush()
        if auto_ticket:
            await create_ticket(session, row, actor_user_id)
    if row.ticket_id is not None:
        await _queue_suggestion(session, settings, tenant_id, row)
        from mhvp.tickets.proposals import queue_for_message

        await queue_for_message(session, settings, tenant_id, row)
    if property_id is None:  # Objektrechnungen laufen nie über die Weiterleitung.
        await _classify_and_queue_forward(session, tenant_id, row, attachments)
    return row, True


async def find_parent(
    session: AsyncSession,
    *,
    in_reply_to: str | None,
    references: str | None,
    gmail_thread_id: str | None,
) -> Message | None:
    """Known message the inbound mail replies to (Review 26.09.2026, M7): ``In-Reply-To``
    first, then every id of ``References`` (closest first, so a reply to a forwarded or
    externally sent mail still finds the case), finally the Gmail thread id."""
    candidates = mail.reference_ids(in_reply_to) + mail.reference_ids(references)
    seen: set[str] = set()
    for header_id in candidates:
        if header_id in seen:
            continue
        seen.add(header_id)
        parent = await session.scalar(
            select(Message)
            .where(Message.header_message_id == header_id)
            .order_by(Message.created_at)
            .limit(1)
        )
        if parent is not None:
            return parent
    if gmail_thread_id:
        by_thread: Message | None = await session.scalar(
            select(Message)
            .where(Message.gmail_thread_id == gmail_thread_id)
            .order_by(Message.created_at)
            .limit(1)
        )
        return by_thread
    return None


async def _classify_and_queue_forward(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    row: Message,
    attachment_ids: list[uuid.UUID],
) -> None:
    """Rechnungs-Weiterleitung (M20, operator 25.09.2026): siehe ``mhvp.communication.forwarding``.
    Die Klassifikation läuft im Ingest; der Versand selbst wird nur vorgemerkt
    (``classification.invoice_forward.status = "queued"``) und nach dem Commit durch
    ``forward_queued`` ausgeführt (Review 26.09.2026, M13). Rollt der Ingest zurück, ist nichts
    versendet; der Marker je Nachricht mit Zeilensperre verhindert einen zweiten Versand."""
    from mhvp.communication.forwarding import classify_invoice
    from mhvp.documents.models import Document
    from mhvp.platform.models import TenantSettings

    tenant_settings = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    cfg = tenant_settings.invoice_forwarding if tenant_settings else {}
    if not cfg.get("enabled") or not cfg.get("forward_address"):
        return
    attachment_names = []
    for doc_id in attachment_ids:
        doc = await session.get(Document, doc_id)
        if doc is not None:
            attachment_names.append(doc.filename or doc.title or "")
    result = classify_invoice(
        sender=row.from_address,
        subject=row.subject,
        body=row.body,
        attachment_names=attachment_names,
        sender_allowlist=list(cfg.get("sender_allowlist", [])) + list(cfg.get("learning_list", [])),
    )
    classification = dict(row.classification)
    forward: dict[str, Any] = {"decision": result.decision, "reason": result.reason}
    if result.decision == "forward":
        forward["status"] = "queued"
    classification["invoice_forward"] = forward
    row.classification = classification
    await session.flush()


FORWARD_QUEUE_LIMIT = 50


async def forward_queued(
    session: AsyncSession, settings: Settings, tenant_id: uuid.UUID
) -> dict[str, int]:
    """Nachlaufjob der automatischen Weiterleitung (Review 26.09.2026, M13): sendet jede
    vorgemerkte Nachricht des Mandanten genau einmal. Die Zeilensperre (``FOR UPDATE SKIP
    LOCKED``) serialisiert parallele Läufe; nach dem Versand wird der Marker auf ``sent``
    gesetzt, ein Fehler auf ``failed`` mit Grund (kein automatischer zweiter Versuch, der
    Vorschlag bleibt im Postfach manuell auslösbar)."""
    from mhvp.communication.forwarding_dispatch import forward_and_archive
    from mhvp.platform.models import TenantSettings

    counts = {"forwarded": 0, "failed": 0}
    tenant_settings = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    cfg = tenant_settings.invoice_forwarding if tenant_settings else {}
    address = cfg.get("forward_address")
    rows = list(
        await session.scalars(
            select(Message)
            .where(
                Message.direction == "in",
                Message.classification["invoice_forward"]["status"].astext == "queued",
            )
            .order_by(Message.created_at)
            .limit(FORWARD_QUEUE_LIMIT)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        classification = dict(row.classification)
        forward = dict(classification.get("invoice_forward") or {})
        if not cfg.get("enabled") or not address:
            forward["status"] = "skipped"
            forward["error"] = "Weiterleitung nicht mehr eingerichtet."
        else:
            try:
                await forward_and_archive(
                    session, settings, tenant_id, row.created_by, row, address
                )
                forward["status"] = "sent"
                forward["forwarded_to"] = address
                counts["forwarded"] += 1
            except Exception as exc:
                log.warning("invoice forward failed", extra={"message_id": str(row.id)})
                forward["status"] = "failed"
                forward["error"] = f"{type(exc).__name__}: {exc}"[:500]
                counts["failed"] += 1
        classification["invoice_forward"] = forward
        row.classification = classification
    await session.flush()
    return counts


async def dispatch_forward_queue(settings: Settings, tenant_id: uuid.UUID) -> None:
    """Startet ``forward_queued`` nach dem Commit des Ingests: synchron ohne Worker
    (``ai_inline``, Tests), sonst über die Queue ``mail``. Ein Fehler beim Anstoßen darf den
    Ingest nie stören; vorgemerkte Nachrichten bleiben ``queued`` und werden vom nächsten
    Lauf nachgeholt."""
    if settings.ai_inline:
        from mhvp.communication.tasks import forward_queued_once

        try:
            await forward_queued_once(settings, tenant_id)
        except Exception:
            log.warning("forward queue failed inline", extra={"tenant_id": str(tenant_id)})
    else:
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.communication.forward_queued", args=[str(tenant_id)], queue="mail"
            )
        except Exception:
            log.warning("could not queue forward job", extra={"tenant_id": str(tenant_id)})


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
    gmail_message_id: str | None = None,
    gmail_thread_id: str | None = None,
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
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
    )


async def enqueue_archive_for_ticket(
    session: AsyncSession, settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> None:
    """ "Erledigt archiviert Mail" (M20-03, operator 25.09.2026): beim Setzen eines Tickets auf
    erledigt, geschlossen oder abgelehnt werden dessen Gmail-Nachrichten archiviert. Läuft
    synchron (Tests, ``ai_inline`` wird hier als "ohne Worker" gelesen) oder über die Queue
    ``mail``; ein Fehler beim Anstoßen darf den Statuswechsel nie stören."""
    if settings.ai_inline:
        from mhvp.communication.tasks import archive_ticket_messages_once

        try:
            await archive_ticket_messages_once(settings, tenant_id, ticket_id)
        except Exception:
            log.warning("archive job failed inline", extra={"ticket_id": str(ticket_id)})
    else:
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.communication.archive_ticket_messages",
                args=[str(tenant_id), str(ticket_id)],
                queue="mail",
            )
        except Exception:
            log.warning("could not queue archive job", extra={"ticket_id": str(ticket_id)})


async def ticket_by_tnr(session: AsyncSession, tenant_id: uuid.UUID, subject: str | None) -> Any:
    """Ticket des Mandanten zur Kennung ``TNR#<nummer>`` im Betreff; ``None`` ohne Kennung,
    ohne Treffer oder bei einem zusammengeführten Ticket (dann gilt das Zielticket). Der
    Mandantenfilter steht zusätzlich zur RLS, damit nie ein fremdes Ticket getroffen wird."""
    from mhvp.tickets.models import Ticket
    from mhvp.tickets.tnr import extract_tnr

    number = extract_tnr(subject)
    if number is None:
        return None
    ticket = await session.scalar(
        select(Ticket).where(Ticket.tenant_id == tenant_id, Ticket.number == number)
    )
    if ticket is not None and ticket.merged_into_ticket_id is not None:
        ticket = await session.get(Ticket, ticket.merged_into_ticket_id)
    return ticket


async def ticket_participants(
    session: AsyncSession, ticket: Any, *, include_thread_senders: bool = True
) -> set[str]:
    """E-Mail-Adressen, die zum Ticket gehören: Ticketkontakt und Ersteller (alle
    hinterlegten Adressen), der ursprüngliche Absender des Tickets, Empfänger und Kopie
    bereits gesendeter Antworten sowie (für die TNR-Zuordnung) Absender bereits zugeordneter
    eingehender Mails. Für die Vorbelegung des Antwortempfängers gilt die engere Menge ohne
    spätere Absender (Review 26.09.2026, H5)."""
    from mhvp.contacts.models import ContactEmail

    addresses: set[str] = set()
    contact_ids = [c for c in (ticket.contact_id, ticket.initiator_contact_id) if c]
    if contact_ids:
        for email_address in await session.scalars(
            select(ContactEmail.email).where(ContactEmail.contact_id.in_(contact_ids))
        ):
            addresses.add(email_address.lower())
    rows = (
        await session.scalars(
            select(Message)
            .where(Message.ticket_id == ticket.id)
            .order_by(Message.received_at.asc().nulls_last(), Message.created_at.asc())
        )
    ).all()
    first_sender = next(
        (m.from_address for m in rows if m.direction == "in" and m.from_address), None
    )
    if first_sender:
        addresses.add(first_sender.lower())
    for m in rows:
        if m.direction == "in" and m.from_address and include_thread_senders:
            addresses.add(m.from_address.lower())
        elif m.direction == "out" and m.status == "sent":
            addresses.update(a.lower() for a in (m.to_addresses or []))
            addresses.update(a.lower() for a in (m.cc_addresses or []))
    return addresses


async def sender_belongs_to_ticket(session: AsyncSession, row: Message, ticket: Any) -> bool:
    if not row.from_address:
        return False
    return row.from_address.lower() in await ticket_participants(session, ticket)


async def _ticket_thread_id(session: AsyncSession, ticket_id: uuid.UUID) -> uuid.UUID | None:
    first = await session.scalar(
        select(Message).where(Message.ticket_id == ticket_id).order_by(Message.created_at).limit(1)
    )
    return (first.thread_id or first.id) if first is not None else None


_CLOSED_STATES = ("done", "closed", "rejected")


async def attach_to_ticket(
    session: AsyncSession, row: Message, ticket_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> None:
    """Hängt die eingehende Mail an das Ticket. Ein erledigtes, geschlossenes oder abgelehntes
    Ticket wird dabei wieder geöffnet (Status ``in_progress``, Ereignis ``reopened``, SLA-Uhr
    läuft weiter); Bearbeiter und Zuweiser erhalten eine interne Benachrichtigung
    (Review 26.09.2026, H4)."""
    from mhvp.sla.models import SlaClock
    from mhvp.sla.service import reopen_clock
    from mhvp.tickets.models import Ticket, TicketAssignee, TicketEvent, TicketStatus
    from mhvp.workspace.services import notify

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
    ticket = await session.get(Ticket, ticket_id)
    reopened = False
    if ticket is not None and ticket.status.value in _CLOSED_STATES:
        previous = ticket.status.value
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.resolved_at = None
        reopened = True
        session.add(
            TicketEvent(
                tenant_id=row.tenant_id,
                ticket_id=ticket_id,
                kind="reopened",
                data={"from": previous, "to": "in_progress", "message_id": str(row.id)},
                user_id=actor_user_id,
            )
        )
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        if clock is not None:
            await reopen_clock(session, clock)
    await session.flush()
    if ticket is not None:
        recipients = {ticket.assignee_user_id} if ticket.assignee_user_id else set()
        recipients.update(
            await session.scalars(
                select(TicketAssignee.user_id).where(TicketAssignee.ticket_id == ticket_id)
            )
        )
        title = (
            f"Ticket {ticket.number} durch neue E-Mail wieder geöffnet"
            if reopened
            else f"Neue E-Mail zu Ticket {ticket.number}"
        )
        for user_id in recipients:
            await notify(
                session,
                tenant_id=row.tenant_id,
                user_id=user_id,
                kind="ticket.mail_received",
                title=title,
                body=(row.subject or "")[:300],
                entity_type="ticket",
                entity_id=ticket_id,
            )
        await emit(
            session,
            tenant_id=row.tenant_id,
            type="ticket.mail_received",
            entity_type="ticket",
            entity_id=ticket_id,
            actor_user_id=actor_user_id,
            payload={"message_id": str(row.id), "reopened": reopened},
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
        # Nur der eigene Textblock ohne zitierte Mails und Signatur (Review 26.09.2026,
        # M17); der Volltext bleibt an der Nachricht.
        public_description=mail.strip_quoted(row.body),
        priority=priority,
        team_id=tpl.default_team_id if tpl else None,
        assignee_user_id=tpl.default_assignee_user_id if tpl else None,
        contact_id=row.contact_id,
        initiator_contact_id=row.contact_id,
        property_id=row.property_id,
        source=TicketSource.EMAIL,
        sla_due_at=datetime.now(UTC)
        + timedelta(hours=(tpl.sla_hours if tpl and tpl.sla_hours else SLA_HOURS[priority])),
    )
    session.add(ticket)
    await session.flush()
    from mhvp.communication.assignment import auto_assign_new_ticket

    await auto_assign_new_ticket(session, row.tenant_id, row, ticket)
    row.ticket_id, row.status = ticket.id, "assigned"
    await session.flush()
    return ticket


# M20-03 Freigabepflicht je Mitglied und Direktversand ------------------------------------


async def author_reply_approval(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> tuple[bool, str | None]:
    """Kennzeichen des Verfassers (Betreiberentscheidung 26.09.2026): ``(pflichtig, grund)``.
    Ein befristetes Kennzeichen (``reply_approval_until``) gilt bis einschließlich dieses
    Tages (Betreiberzeitzone), danach nicht mehr."""
    from mhvp.platform.models import Membership

    if user_id is None:
        return False, None
    row = (
        await session.execute(
            select(
                Membership.reply_approval_required,
                Membership.reply_approval_reason,
                Membership.reply_approval_until,
            ).where(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None or not row.reply_approval_required:
        return False, None
    if row.reply_approval_until is not None and row.reply_approval_until < local_today():
        return False, None
    return True, row.reply_approval_reason


async def reply_approval_all(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """Notbremse des Mandanten: alle Ticketantworten mit Freigabe (Standard aus)."""
    from mhvp.platform.models import TenantSettings

    return bool(
        await session.scalar(
            select(TenantSettings.ticket_reply_approval_all).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


async def notify_reply_approvers(
    session: AsyncSession, row: Message, *, ticket_number: int | None, exclude: uuid.UUID | None
) -> int:
    """Offene Vorlage an alle Freigabeberechtigten (``communication:approve``) des Mandanten
    außer dem Verfasser; idempotent je Nachricht (``workspace.services.notify``)."""
    from mhvp.banking.tasks import users_with_permission
    from mhvp.workspace.services import notify

    count = 0
    tnr = f"TNR#{ticket_number} " if ticket_number is not None else ""
    for user_id in await users_with_permission(session, row.tenant_id, "communication:approve"):
        if user_id == exclude:
            continue
        created = await notify(
            session,
            tenant_id=row.tenant_id,
            user_id=user_id,
            kind="mail.approval_requested",
            title=f"Antwort {tnr}zur Freigabe: {row.subject or '(ohne Betreff)'}",
            body="Eine vorformulierte Ticketantwort wartet auf die Freigabe durch eine "
            "zweite Person.",
            entity_type="message",
            entity_id=row.id,
        )
        count += 1 if created is not None else 0
    return count
