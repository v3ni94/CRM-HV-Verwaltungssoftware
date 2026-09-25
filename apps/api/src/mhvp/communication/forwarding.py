"""Forwarding of company invoices to the invoicing mailbox (M32).

Invoices addressed to the company itself (for example telecom, health insurance, tax adviser)
go to the invoicing program's inbox address and the mail is archived afterwards. Invoices for
managed properties must never be forwarded, so nothing is forwarded automatically unless the
sender is on the tenant's approved list AND the mode is set to "auto"; the default mode
"suggest" only marks candidates and a person clicks per mail. Approvals teach the list."""

import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.gmail import GmailClient
from mhvp.communication.models import Mailbox, Message
from mhvp.core.events import emit
from mhvp.documents.blobs import BlobStore
from mhvp.platform.models import TenantSettings

MODES = ("suggest", "auto")


def parse_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    mode = str(raw.get("mode") or "suggest")
    return {
        "enabled": bool(raw.get("enabled")) and bool(raw.get("address")),
        "address": str(raw.get("address") or "")[:320],
        "mode": mode if mode in MODES else "suggest",
        "senders": [str(s).strip().lower() for s in raw.get("senders") or [] if str(s).strip()],
    }


async def load_config(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    row = await session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
    return parse_config(row.mail_forwarding if row else None)


def sender_matches(from_address: str | None, senders: list[str]) -> bool:
    """Full address or domain match ("telekom.de" covers rechnung@telekom.de)."""
    if not from_address:
        return False
    address = from_address.strip().lower()
    if "<" in address and ">" in address:
        address = address.split("<", 1)[1].split(">", 1)[0].strip()
    domain = address.rsplit("@", 1)[-1]
    return any(entry in (address, domain) for entry in senders)


def build_forward(raw: bytes, from_address: str, to_address: str, subject: str) -> bytes:
    """Original mail attached unchanged as message/rfc822 (invoice programs parse attachments)."""
    outer = EmailMessage()
    outer["From"] = from_address
    outer["To"] = to_address
    outer["Subject"] = f"WG: {subject}"[:250]
    outer.set_content(
        "Automatische Weiterleitung einer Gesellschaftsrechnung aus der MH-Verwaltungsplattform."
        "\nDie Originalnachricht liegt als Anhang bei."
    )
    outer.add_attachment(raw, maintype="message", subtype="rfc822", filename="original.eml")
    return outer.as_bytes()


async def forward_message(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    mailbox: Mailbox,
    message: Message,
    target: str,
    client: GmailClient,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Sends the forward, archives the original in Gmail and stamps the message. The caller
    verified configuration and permissions; errors bubble up and change nothing locally."""
    if message.document_id is None:
        raise ValueError("Originalnachricht ist nicht als Dokument gespeichert.")
    raw = blobs.get(BlobStore.key(message.tenant_id, message.document_id))
    await client.send_raw(
        build_forward(raw, mailbox.address, target, message.subject or "Rechnung")
    )
    if message.header_message_id:
        gmail_id = await client.find_by_rfc822_message_id(message.header_message_id)
        if gmail_id:
            await client.archive(gmail_id)
    message.forwarded_to = target
    message.forwarded_at = datetime.now(UTC)
    if message.status in ("new", "assigned"):
        message.status = "done"
    await emit(
        session,
        tenant_id=message.tenant_id,
        type="mail.invoice_forwarded",
        entity_type="message",
        entity_id=message.id,
        actor_user_id=actor_user_id,
        payload={"to": target, "from": message.from_address},
    )
    await session.flush()


async def archive_message(session: AsyncSession, settings: Any, row: Message) -> None:
    """Archives the mail in Gmail after it is done, best effort: a missing Google grant
    (reconnect needed) or a network error never fails the status change."""
    import httpx

    from mhvp.communication.gmail import GmailError, make_client, oauth_client

    if row.direction != "in" or not row.header_message_id or row.mailbox_id is None:
        return
    mailbox = await session.get(Mailbox, row.mailbox_id)
    if mailbox is None or mailbox.kind != "gmail" or not mailbox.secret:
        return
    try:
        client_id, client_secret = await oauth_client(session, settings)
        client = make_client(client_id, client_secret, mailbox)
        try:
            gmail_id = await client.find_by_rfc822_message_id(row.header_message_id)
            if gmail_id:
                await client.archive(gmail_id)
        finally:
            await client.aclose()
    except (GmailError, httpx.HTTPError):
        return


async def archive_ticket_messages(session: AsyncSession, settings: Any, ticket_id: Any) -> None:
    """A done ticket tidies the inbox: every linked inbound mail is archived best effort."""
    rows = (
        await session.scalars(
            select(Message).where(Message.ticket_id == ticket_id, Message.direction == "in")
        )
    ).all()
    for row in rows:
        await archive_message(session, settings, row)


async def auto_forward_mailbox(
    session: AsyncSession, settings: Any, blobs: BlobStore, mailbox: Mailbox
) -> dict[str, int]:
    """Auto mode of the sync job: forwards only approved senders; one failure never blocks
    the rest and never fails the sync."""
    from mhvp.communication.gmail import GmailError, make_client, oauth_client

    config = await load_config(session, mailbox.tenant_id)
    counts = {"forwarded": 0, "failed": 0}
    if not config["enabled"] or config["mode"] != "auto" or not config["senders"]:
        return counts
    rows = [
        m
        for m in await auto_candidates(session, mailbox)
        if sender_matches(m.from_address, config["senders"])
    ]
    if not rows:
        return counts
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    try:
        for message in rows:
            try:
                await forward_message(
                    session,
                    blobs,
                    mailbox=mailbox,
                    message=message,
                    target=config["address"],
                    client=client,
                    actor_user_id=None,
                )
                counts["forwarded"] += 1
            except (GmailError, ValueError):
                counts["failed"] += 1
    finally:
        await client.aclose()
    return counts


async def auto_candidates(session: AsyncSession, mailbox: Mailbox) -> list[Message]:
    """Inbound, unforwarded mails of this mailbox with attachments (an invoice arrives as a
    file). The sender filter runs in Python because the list matches domains too."""
    rows = (
        await session.scalars(
            select(Message).where(
                Message.mailbox_id == mailbox.id,
                Message.direction == "in",
                Message.forwarded_at.is_(None),
                Message.status.in_(("new", "assigned")),
            )
        )
    ).all()
    return [m for m in rows if m.attachment_document_ids]
