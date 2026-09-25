"""Versand und Protokollierung der Rechnungs-Weiterleitung (operator 25.09.2026): nutzt den
bestehenden Gmail-Sendeweg (Scope ``gmail.send``, bereits vorhanden) und archiviert die
weitergeleitete Mail anschließend im Ursprungspostfach. Jede Weiterleitung wird als
``TicketEvent``-ähnliches Ereignis protokolliert (``message.forwarded``, ``mhvp.core.events``).
"""

from __future__ import annotations

import uuid
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
from mhvp.communication.models import Mailbox, Message
from mhvp.core.config import Settings
from mhvp.core.events import emit


def _build_forward(original: Message, forward_address: str) -> bytes:
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
    return msg.as_bytes()


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
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    try:
        await client.send_raw(_build_forward(message, forward_address))
        if message.gmail_message_id and mailbox.archive_on_ticket_done:
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
        payload={"forward_address": forward_address, "sender": message.from_address},
    )
