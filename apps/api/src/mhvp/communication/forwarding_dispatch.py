"""Versand und Protokollierung der Rechnungs-Weiterleitung (operator 25.09.2026): nutzt den
bestehenden Gmail-Sendeweg (Scope ``gmail.send``, bereits vorhanden) und archiviert die
weitergeleitete Mail anschließend im Ursprungspostfach. Jede Weiterleitung wird als
``TicketEvent``-ähnliches Ereignis protokolliert (``message.forwarded``, ``mhvp.core.events``).

Anhänge (Review 26.09.2026, H3): alle gespeicherten Anhänge der Originalmail (die eigentliche
Rechnung als PDF) werden als MIME-Anhänge beigefügt. Fehlt ein Anhang im Objektspeicher oder
hat die Mail keine Anhänge, wird zwar weitergeleitet, das Original bleibt aber im Posteingang.
"""

from __future__ import annotations

import logging
import uuid
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
from mhvp.communication.models import Mailbox, Message
from mhvp.core.config import Settings
from mhvp.core.events import emit

log = logging.getLogger(__name__)


def _build_forward(
    original: Message,
    forward_address: str,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> bytes:
    """Neue Mail an das Buchhaltungspostfach: Betreff, Klartext und die übergebenen
    Anhänge ``(filename, mime_type, data)``."""
    msg = EmailMessage()
    msg["Subject"] = f"Weiterleitung: {original.subject or 'E-Mail ohne Betreff'}"
    msg["To"] = forward_address
    if original.from_address:
        msg["Reply-To"] = original.from_address
    body = (
        f"Automatisch weitergeleitete Rechnung, ursprünglicher Absender: "
        f"{original.from_address or 'unbekannt'}.\n\n---\n\n{original.body or ''}"
    )
    msg.set_content(body)
    for filename, mime_type, data in attachments or []:
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=filename,
        )
    return msg.as_bytes()


async def load_attachments(
    session: AsyncSession, settings: Settings, message: Message
) -> tuple[list[tuple[str, str, bytes]], int]:
    """Liest die Anhänge der Nachricht aus dem Objektspeicher. Liefert die Anhänge und die
    Anzahl der erwarteten Anhänge; ein Unterschied bedeutet, dass ein Anhang fehlt."""
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document

    expected = len(message.attachment_document_ids)
    if not expected:
        return [], 0
    docs = {
        d.id: d
        for d in await session.scalars(
            select(Document).where(Document.id.in_(message.attachment_document_ids))
        )
    }
    blobs = BlobStore(settings)
    out: list[tuple[str, str, bytes]] = []
    for doc_id in message.attachment_document_ids:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        try:
            data = blobs.get(doc.storage_ref)
        except Exception:
            log.warning("forward attachment unreadable", extra={"document_id": str(doc_id)})
            continue
        out.append((doc.filename, doc.mime_type, data))
    return out, expected


async def forward_and_archive(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    message: Message,
    forward_address: str,
) -> None:
    if message.mailbox_id is None:
        return
    mailbox = await session.get(Mailbox, message.mailbox_id)
    if mailbox is None or mailbox.kind != "gmail":
        return  # nur Gmail-Postfächer haben den Sendeweg dieser Weiterleitung
    attachments, expected = await load_attachments(session, settings, message)
    complete = expected > 0 and len(attachments) == expected
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    try:
        await client.send_raw(_build_forward(message, forward_address, attachments))
        # Archivieren nur, wenn die Weiterleitung alle Anhänge enthält (H3); sonst bleibt das
        # Original mit der Rechnung im Posteingang sichtbar.
        if complete and message.gmail_message_id and mailbox.archive_on_ticket_done:
            try:
                await client.archive(message.gmail_message_id)
            except GmailScopeMissingError:
                mailbox.archive_scope_missing = True
    finally:
        await client.aclose()
    await emit(
        session,
        tenant_id=tenant_id,
        type="message.forwarded",
        entity_type="message",
        entity_id=message.id,
        actor_user_id=actor_user_id,
        payload={
            "forward_address": forward_address,
            "sender": message.from_address,
            "attachments": len(attachments),
            "attachments_expected": expected,
            "archived": bool(complete and message.gmail_message_id),
        },
    )
