"""Duplicates across own mailboxes (operator 27.09.2026, mail workspace).

A sender who writes the same mail to a collective address (info@) and to a personal address
(brink@) produces two copies during the Gmail sync or the .eml intake. The copy in the
personal mailbox leads; the copy in the collective mailbox is stored as well (archiving,
evidence) but linked to the leading copy through ``Message.duplicate_of_id`` and hidden from
the overview. Every copy of a group shares ticket and thread, so replies, comments and the
"in progress" marker (``mhvp.communication.progress``) apply to the whole group.

Matching: the RFC 5322 ``Message-ID`` first; without one, or when a relay rewrote it, the
same sender, subject, timestamp and text hash (``md5`` of the plain text in SQL). The sender
chooses the Message-ID, so a match in another mailbox only counts as the same mail when the
content fingerprint (``same_content``) agrees too; otherwise the received mail is stored as a
mail of its own (review 1.36.0). The ingest of one mail is serialised per tenant and mail key
(``lock_mail``) so that parallel syncs of two own mailboxes cannot both store a leading copy.

Which mailbox is collective is a stored flag (``Mailbox.is_collective``) with a default
derived from the local part (``is_collective_address``); the rule is an assumption
(docs/ASSUMPTIONS.md) and editable per mailbox.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import exists, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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


def hide_copies(query: Any, allowed: Any = None) -> Any:
    """Restricts a ``select(Message)`` to one row per mail group (feedback 28.09.2026: the
    same mail was still shown several times in the thread view, the ticket history and the
    contact history, because every copy shares thread, ticket and contact).

    ``allowed`` is the subquery of the mailboxes the user may read, ``None`` for a user who
    reads every mailbox. A copy stays visible when its leading copy is not readable for the
    user (personal mailbox of a colleague), so nothing disappears; otherwise only the leading
    copy is listed (also when the user opened a copy: the thread then shows the leading copy
    with the same content). Stored copies are never deleted (evidence), only hidden."""
    if allowed is None:
        condition: Any = Message.duplicate_of_id.is_(None)
    else:
        leading = aliased(Message)
        visible_lead = select(leading.id).where(
            leading.id == Message.duplicate_of_id,
            or_(leading.mailbox_id.is_(None), leading.mailbox_id.in_(allowed)),
        )
        condition = or_(Message.duplicate_of_id.is_(None), ~exists(visible_lead))
    return query.where(condition)


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


def _mail_key(parsed: dict[str, Any]) -> str | None:
    if parsed.get("message_id"):
        return f"id:{parsed['message_id']}"
    if parsed.get("from") and parsed.get("received_at"):
        return f"fb:{parsed['from']}|{parsed.get('subject') or ''}|{parsed['received_at']}"
    return None


async def lock_mail(session: AsyncSession, tenant_id: uuid.UUID, parsed: dict[str, Any]) -> None:
    """Serialises the ingest of one mail per tenant and mail key until the transaction ends
    (review 1.36.0). Since migration 0213 the unique index allows one row per mailbox, so two
    parallel syncs of own mailboxes would both miss the uncommitted row of the other and store
    two leading copies (two tickets, two invoice forwards). The second sync now waits for the
    first commit and stores a linked copy instead. Taking the lock twice in one transaction
    (``ingest_raw`` and ``ingest_parsed``) is harmless."""
    key = _mail_key(parsed)
    if key is None:
        return
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"mhvp:mail-in:{tenant_id}:{key}"},
    )


async def _candidates(session: AsyncSession, parsed: dict[str, Any]) -> list[Message]:
    """Stored inbound rows matching the parsed mail by Message-ID, or without one by sender,
    subject, timestamp and text hash (oldest first)."""
    if parsed.get("message_id"):
        by_id = await session.scalars(
            select(Message)
            .where(Message.header_message_id == parsed["message_id"], Message.direction == "in")
            .order_by(Message.created_at)
        )
        return list(by_id.all())
    # The fallback applies only to mails without a Message-ID: a known, different Message-ID
    # is a different mail even when sender, subject, timestamp and text coincide (call notes).
    if parsed.get("from") and parsed.get("received_at"):
        by_content = await session.scalars(
            select(Message)
            .where(
                Message.direction == "in",
                Message.from_address == parsed["from"],
                Message.subject == parsed.get("subject"),
                Message.received_at == parsed["received_at"],
                func.md5(func.coalesce(Message.body, "")) == func.md5(parsed.get("body") or ""),
            )
            .order_by(Message.created_at)
        )
        return list(by_content.all())
    return []


async def same_content(session: AsyncSession, row: Message, parsed: dict[str, Any]) -> bool:
    """Content fingerprint of a stored row and a parsed mail: sender, subject, plain text and
    the attachments (SHA-256 of the data) agree. Rejected attachments are not stored as
    documents, so every stored attachment must occur in the mail and the total must match."""
    from mhvp.documents.models import Document

    if row.from_address != parsed.get("from") or row.subject != parsed.get("subject"):
        return False
    if (row.body or "") != (parsed.get("body") or ""):
        return False
    received = Counter(
        hashlib.sha256(att["data"]).hexdigest() for att in parsed.get("attachments") or []
    )
    total = (row.classification or {}).get("attachments_total")
    if isinstance(total, int) and total != sum(received.values()):
        return False
    ids = list(row.attachment_document_ids or [])
    if not ids:
        return True
    stored = Counter(
        (await session.scalars(select(Document.sha256).where(Document.id.in_(ids)))).all()
    )
    return all(received[digest] >= n for digest, n in stored.items())


async def _row_fingerprint(session: AsyncSession, row: Message) -> tuple[Any, ...]:
    """``same_content`` for two stored rows (maintenance): sender, subject, text and the
    SHA-256 of the stored attachments."""
    from mhvp.documents.models import Document

    ids = list(row.attachment_document_ids or [])
    digests = (
        sorted((await session.scalars(select(Document.sha256).where(Document.id.in_(ids)))).all())
        if ids
        else []
    )
    return (row.from_address, row.subject, row.body or "", digests)


async def known_gmail_row(
    session: AsyncSession, mailbox_id: uuid.UUID | None, gmail_message_id: str | None
) -> Message | None:
    """Row already stored for this Gmail message of this mailbox (feedback 28.09.2026). The
    Gmail id is stable per mailbox, so a second fetch (incremental sync, push, retry queue and
    backfill overlap) of a mail without ``Message-ID`` and without ``Date`` returns the stored
    row instead of a second mail; the content key alone needs a timestamp and missed it."""
    if mailbox_id is None or not gmail_message_id:
        return None
    row: Message | None = await session.scalar(
        select(Message)
        .where(
            Message.mailbox_id == mailbox_id,
            Message.gmail_message_id == gmail_message_id,
            Message.direction == "in",
        )
        .order_by(Message.created_at)
        .limit(1)
    )
    return row


async def own_sent(session: AsyncSession, parsed: dict[str, Any]) -> Message | None:
    """Outbound mail of this tenant that the inbound mail is the delivered copy of (feedback
    28.09.2026): a reply sent through the platform to or with a copy to an own mailbox (cc
    info@) is synced back from that mailbox with the same ``Message-ID``. Matches only a sent
    (or sending) row with the same ``Message-ID`` and subject whose sender is the stored
    sender or the address of its mailbox; the platform generates that ``Message-ID``."""
    message_id = parsed.get("message_id")
    if not message_id:
        return None
    rows = (
        await session.scalars(
            select(Message)
            .where(
                Message.header_message_id == message_id,
                Message.direction == "out",
                Message.status.in_(("sent", "sending")),
            )
            .order_by(Message.created_at)
        )
    ).all()
    sender = (parsed.get("from") or "").lower()
    for row in rows:
        if (row.subject or None) != (parsed.get("subject") or None):
            continue
        addresses = {(row.from_address or "").lower()}
        if row.mailbox_id is not None:
            box = await session.get(Mailbox, row.mailbox_id)
            if box is not None:
                addresses.add(box.address.lower())
        if sender and sender in addresses:
            return row
    return None


def echo_of(
    sent: Message,
    parsed: dict[str, Any],
    *,
    mailbox_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
    gmail_message_id: str | None,
    gmail_thread_id: str | None,
    actor_user_id: uuid.UUID | None,
) -> Message:
    """Inbound row for the delivered copy of an own sent mail, linked to the sent row and
    hidden like any other copy. It opens no ticket, no suggestion and no invoice forward;
    the status is ``done`` because the mail needs no handling (it is our own)."""
    return Message(
        tenant_id=sent.tenant_id,
        created_by=actor_user_id,
        direction="in",
        mailbox_id=mailbox_id,
        from_address=parsed.get("from"),
        reply_to=parsed.get("reply_to"),
        to_addresses=list(parsed.get("to") or []),
        cc_addresses=list(parsed.get("cc") or []),
        subject=parsed.get("subject"),
        body=parsed.get("body"),
        body_html=sent.body_html,
        header_message_id=parsed.get("message_id"),
        in_reply_to=parsed.get("in_reply_to"),
        references_header=parsed.get("references"),
        thread_id=sent.thread_id or sent.id,
        received_at=parsed.get("received_at") or sent.sent_at,
        contact_id=sent.contact_id,
        property_id=sent.property_id,
        ticket_id=sent.ticket_id,
        document_id=document_id,
        attachment_document_ids=list(sent.attachment_document_ids or []),
        gmail_message_id=gmail_message_id,
        gmail_thread_id=gmail_thread_id,
        status="done",
        classification={"method": "rules", "duplicate_copy": True, "own_sent_echo": True},
        appointment_suggestions=[],
        duplicate_of_id=sent.id,
    )


async def find_known(
    session: AsyncSession, parsed: dict[str, Any], mailbox_id: uuid.UUID | None
) -> tuple[Message | None, Message | None]:
    """Stored copies of the parsed inbound mail as ``(stored, primary)``.

    ``stored``: the row that already holds this mail for the same mailbox binding (a
    re-import, nothing new is stored); an upload without mailbox also returns the leading copy
    of a mail with the same content. ``primary``: the leading copy of the same mail in another
    own mailbox; the received mail becomes its linked copy. Both are None for a new mail,
    including a Message-ID collision with different content (review 1.36.0): that mail is
    stored as its own message and never shows the content of the stored one."""
    candidates = await _candidates(session, parsed)
    for row in candidates:
        if row.mailbox_id == mailbox_id:
            return row, None
    for row in candidates:
        if await same_content(session, row, parsed):
            members = await group_members(session, row)
            lead = members[0] if members else row
            return (lead, None) if mailbox_id is None else (None, lead)
    return None, None


async def mailbox_collective(session: AsyncSession, mailbox_id: uuid.UUID | None) -> bool:
    if mailbox_id is None:
        return True  # without a mailbox binding a copy never outranks a personal mailbox
    flag = await session.scalar(select(Mailbox.is_collective).where(Mailbox.id == mailbox_id))
    return bool(flag) if flag is not None else True


def copy_of(
    primary: Message,
    *,
    mailbox_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
    received_at: Any,
    gmail_message_id: str | None,
    gmail_thread_id: str | None,
    actor_user_id: uuid.UUID | None,
) -> Message:
    """New row for the same mail in another mailbox; carries the case data of the leading
    copy (ticket, thread, contact, property, attachments) so both copies read alike.

    A copy never forwards an invoice (review 1.36.0): it keeps the decision and reason of the
    invoice classification (the "Weiterleiten?" proposal stays visible) but never the dispatch
    state, so only the copy that went through the intake can be queued for ``forward_queued``."""
    classification = dict(primary.classification) | {"duplicate_copy": True}
    forward = primary.classification.get("invoice_forward")
    if isinstance(forward, dict):
        classification["invoice_forward"] = {
            k: v for k, v in forward.items() if k in ("decision", "reason")
        } | {"status": "duplicate", "of": str(primary.id)}
    return Message(
        tenant_id=primary.tenant_id,
        created_by=actor_user_id,
        direction="in",
        mailbox_id=mailbox_id,
        from_address=primary.from_address,
        # The copy answers to the same Reply-To as the leading copy (hotfix 27.09.2026).
        reply_to=primary.reply_to,
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
        done_source=primary.done_source,
        done_at=primary.done_at,
        classification=classification,
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


async def align_copies(session: AsyncSession, actor_user_id: uuid.UUID | None) -> dict[str, int]:
    """Maintenance (fix 1.42.2): a copy whose status differs from its leading copy takes the
    status of the leading copy (``done`` set before the fix only reached the copy the user
    clicked). One ``message.copy_aligned`` event per changed row with ``previous_status``;
    idempotent, nothing is deleted."""
    from mhvp.core.events import emit

    leading = aliased(Message)
    rows = (
        await session.execute(
            select(Message, leading.status)
            .join(leading, leading.id == Message.duplicate_of_id)
            .where(Message.direction == "in", Message.status != leading.status)
            .order_by(Message.created_at)
        )
    ).all()
    changed = 0
    for copy, lead_status in rows:
        if (copy.classification or {}).get("own_sent_echo"):
            continue  # an echo of an own sent mail is always done, its lead is the sent row
        previous = copy.status
        copy.status = lead_status
        changed += 1
        await emit(
            session,
            tenant_id=copy.tenant_id,
            type="message.copy_aligned",
            entity_type="message",
            entity_id=copy.id,
            actor_user_id=actor_user_id,
            payload={
                "previous_status": previous,
                "status": lead_status,
                "leading_message_id": str(copy.duplicate_of_id),
            },
        )
    await session.flush()
    return {"changed": changed}


async def link_existing(session: AsyncSession) -> dict[str, int]:
    """Maintenance for mails stored before this rule: groups inbound copies of the same
    mail across different mailboxes and links them. Counts ``groups``, ``linked`` and
    ``ticket_conflicts``: a copy whose group would then carry different tickets is skipped and
    stays visible on its own (linking would hide the mail of another case, review 1.36.0). A
    row with the same Message-ID but different content is a mail of its own and stays apart,
    as in the ingest (``same_content``)."""
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
        lead = rows[0]
        for other in rows[1:]:
            if other.duplicate_of_id is not None or other.id == lead.id:
                continue
            if lead.duplicate_of_id == other.id:
                continue
            if await _row_fingerprint(session, other) != await _row_fingerprint(session, lead):
                continue
            members = await group_members(session, lead) + await group_members(session, other)
            if len({m.ticket_id for m in members if m.ticket_id}) > 1:
                counts["ticket_conflicts"] += 1
                continue
            lead = await link(session, lead, other)
            counts["linked"] += 1
    return counts
