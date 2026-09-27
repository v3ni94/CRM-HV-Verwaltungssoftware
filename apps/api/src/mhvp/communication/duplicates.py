"""Duplicates across own mailboxes (operator 27.09.2026, mail workspace).

A sender who writes the same mail to a collective address (info@) and to a personal address
(brink@) produces two copies during the Gmail sync or the .eml intake. The copy in the
personal mailbox leads; the copy in the collective mailbox is stored as well (archiving,
evidence) but linked to the leading copy through ``Message.duplicate_of_id`` and hidden from
the overview. Every copy of a group shares ticket and thread, so replies, comments and the
"in progress" marker (``mhvp.communication.progress``) apply to the whole group.

Matching: the RFC 5322 ``Message-ID`` first; without one, or when a relay rewrote it, the
same sender, subject, timestamp and text hash (``md5`` of the plain text in SQL).

Which mailbox is collective is a stored flag (``Mailbox.is_collective``) with a default
derived from the local part (``is_collective_address``); the rule is an assumption
(docs/ASSUMPTIONS.md) and editable per mailbox.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox, Message

# Keep in sync with the regex of migration 0213.
COLLECTIVE_LOCAL_PARTS = frozenset(
    {
        "info",
        "post",
        "buchhaltung",
        "office",
        "kontakt",
        "verwaltung",
        "rechnung",
        "rechnungen",
        "mail",
        "service",
        "zentrale",
        "hausverwaltung",
        "support",
        "kundenservice",
        "bewerbung",
        "team",
    }
)
_SEPARATORS = ".+-"


def is_collective_address(address: str | None) -> bool:
    """Default of ``Mailbox.is_collective``: local part (before ``@``, up to the first ``.``,
    ``+`` or ``-``) in ``COLLECTIVE_LOCAL_PARTS``; everything else counts as personal."""
    if not address or "@" not in address:
        return False
    local = address.split("@", 1)[0].strip().lower()
    for sep in _SEPARATORS:
        local = local.split(sep, 1)[0]
    return local in COLLECTIVE_LOCAL_PARTS


def group_root(row: Message) -> uuid.UUID:
    return row.duplicate_of_id or row.id


async def group_members(session: AsyncSession, row: Message) -> list[Message]:
    """Every copy of the mail ``row`` belongs to, the leading copy first."""
    root = group_root(row)
    rows = (
        await session.scalars(
            select(Message)
            .where(or_(Message.id == root, Message.duplicate_of_id == root))
            .order_by(Message.duplicate_of_id.is_not(None), Message.created_at)
        )
    ).all()
    return list(rows)


async def find_known(session: AsyncSession, parsed: dict[str, Any]) -> list[Message]:
    """Stored copies of the parsed inbound mail in any mailbox (leading copy first, empty when
    the mail is new). Message-ID first, then sender, subject, timestamp and text hash."""
    found: Message | None = None
    if parsed.get("message_id"):
        found = await session.scalar(
            select(Message)
            .where(Message.header_message_id == parsed["message_id"], Message.direction == "in")
            .order_by(Message.created_at)
            .limit(1)
        )
    # The fallback applies only to mails without a Message-ID: a known, different Message-ID
    # is a different mail even when sender, subject, timestamp and text coincide (call notes).
    if (
        found is None
        and not parsed.get("message_id")
        and parsed.get("from")
        and parsed.get("received_at")
    ):
        found = await session.scalar(
            select(Message)
            .where(
                Message.direction == "in",
                Message.from_address == parsed["from"],
                Message.subject == parsed.get("subject"),
                Message.received_at == parsed["received_at"],
                func.md5(func.coalesce(Message.body, "")) == func.md5(parsed.get("body") or ""),
            )
            .order_by(Message.created_at)
            .limit(1)
        )
    if found is None:
        return []
    return await group_members(session, found)


async def mailbox_collective(session: AsyncSession, mailbox_id: uuid.UUID | None) -> bool:
    if mailbox_id is None:
        return True  # without a mailbox binding a copy never outranks a personal mailbox
    flag = await session.scalar(select(Mailbox.is_collective).where(Mailbox.id == mailbox_id))
    return bool(flag) if flag is not None else True


def copy_of(
    primary: Message,
    *,
    mailbox_id: uuid.UUID | None,
    document_id: uuid.UUID,
    received_at: Any,
    gmail_message_id: str | None,
    gmail_thread_id: str | None,
    actor_user_id: uuid.UUID | None,
) -> Message:
    """New row for the same mail in another mailbox; carries the case data of the leading
    copy (ticket, thread, contact, property, attachments) so both copies read alike."""
    return Message(
        tenant_id=primary.tenant_id,
        created_by=actor_user_id,
        direction="in",
        mailbox_id=mailbox_id,
        from_address=primary.from_address,
        to_addresses=list(primary.to_addresses),
        cc_addresses=list(primary.cc_addresses),
        subject=primary.subject,
        body=primary.body,
        body_html=primary.body_html,
        header_message_id=primary.header_message_id,
        in_reply_to=primary.in_reply_to,
        references_header=primary.references_header,
        thread_id=primary.thread_id or primary.id,
        received_at=received_at or primary.received_at,
        contact_id=primary.contact_id,
        property_id=primary.property_id,
        ticket_id=primary.ticket_id,
        document_id=document_id,
        attachment_document_ids=list(primary.attachment_document_ids),
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        status=primary.status,
        classification=dict(primary.classification) | {"duplicate_copy": True},
        appointment_suggestions=list(primary.appointment_suggestions),
        duplicate_of_id=primary.id,
    )


async def link(session: AsyncSession, leading: Message, other: Message) -> Message:
    """Links ``other`` to the group of ``leading`` and returns the copy that leads afterwards:
    a personal mailbox beats a collective one, otherwise the earlier copy stays in front.
    Ticket, thread, contact and property are shared across the group."""
    lead_collective = await mailbox_collective(session, leading.mailbox_id)
    other_collective = await mailbox_collective(session, other.mailbox_id)
    root = group_root(leading)
    if root != leading.id:
        fetched = await session.get(Message, root)
        if fetched is not None:
            leading = fetched
    new_lead, new_dup = (other, leading) if other_collective < lead_collective else (leading, other)
    if new_lead.id != leading.id:
        # The former leading copy and its duplicates now point to the new leading copy.
        await session.execute(
            update(Message)
            .where(Message.duplicate_of_id == leading.id)
            .values(duplicate_of_id=new_lead.id)
        )
        new_lead.duplicate_of_id = None
    new_dup.duplicate_of_id = new_lead.id
    await share_case(session, new_lead)
    await session.flush()
    return new_lead


async def share_case(session: AsyncSession, row: Message) -> None:
    """Spreads ticket, thread, contact and property over every copy of the group (the first
    value wins; a copy that already has a different ticket keeps it, see the maintenance
    counters)."""
    members = await group_members(session, row)
    if not members:
        return
    ticket_id = next((m.ticket_id for m in members if m.ticket_id), None)
    thread_id = next((m.thread_id for m in members if m.thread_id), None) or members[0].id
    contact_id = next((m.contact_id for m in members if m.contact_id), None)
    property_id = next((m.property_id for m in members if m.property_id), None)
    for m in members:
        if ticket_id and m.ticket_id is None:
            m.ticket_id = ticket_id
            if m.status == "new":
                m.status = "assigned"
        if m.thread_id is None and m.id != thread_id:
            m.thread_id = thread_id
        m.contact_id = m.contact_id or contact_id
        m.property_id = m.property_id or property_id


async def link_existing(session: AsyncSession) -> dict[str, int]:
    """Maintenance for mails stored before this rule: groups inbound copies of the same
    mail across different mailboxes and links them. Counts ``groups``, ``linked`` and
    ``ticket_conflicts`` (copies that already carry different tickets; left as they are)."""
    counts = {"groups": 0, "linked": 0, "ticket_conflicts": 0}
    key_id = func.coalesce(Message.header_message_id, "")
    key_fallback = func.concat(
        func.coalesce(Message.from_address, ""),
        "|",
        func.coalesce(Message.subject, ""),
        "|",
        func.coalesce(func.to_char(Message.received_at, "YYYY-MM-DD HH24:MI:SS"), ""),
        "|",
        func.md5(func.coalesce(Message.body, "")),
    )
    key = func.coalesce(func.nullif(key_id, ""), key_fallback)
    grouped = (
        select(key.label("key"))
        .where(Message.direction == "in")
        .group_by(key)
        .having(func.count(func.distinct(Message.mailbox_id)) > 1)
    )
    keys = list((await session.scalars(grouped)).all())
    for value in keys:
        rows = list(
            (
                await session.scalars(
                    select(Message)
                    .where(Message.direction == "in", key == value)
                    .order_by(Message.created_at)
                )
            ).all()
        )
        if len(rows) < 2:
            continue
        counts["groups"] += 1
        tickets = {m.ticket_id for m in rows if m.ticket_id}
        if len(tickets) > 1:
            counts["ticket_conflicts"] += 1
        lead = rows[0]
        for other in rows[1:]:
            if other.duplicate_of_id is not None or other.id == lead.id:
                continue
            if lead.duplicate_of_id == other.id:
                continue
            lead = await link(session, lead, other)
            counts["linked"] += 1
    return counts
