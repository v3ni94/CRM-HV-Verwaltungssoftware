"""Letters on the tenant letterhead filed as documents with a dispatch record (M12 gaps,
29.09.2026): one place for the Nachforderungsschreiben (Verwalterwechsel) and the rent
increase letter.

The PDF is rendered by ``mhvp.documents.letters`` from the tenant's stored letterhead only
(company and branding of ``tenant_settings``; nothing is invented, a missing mandatory field
refuses with ``LETTERHEAD_INCOMPLETE``). The document is stored as ``generated`` and linked
to the entities of the case; an optional ticket is linked as well and receives an internal
comment with the document.

The dispatch record (``mhvp.communication.models.Dispatch``) documents channel, date, user
and an optional tracking reference. It is a record, never a transmission:

* ``post``: the letter is recorded as sent on ``sent_on`` with the evidence given (for
  example the registered mail number); the actual posting happens outside the platform.
* ``email``: a mail draft is prepared for the mailbox; it leaves only through the mail
  approval (M20-04). The record stays ``prepared`` until the approved mail is sent.
* ``portal``: the document becomes visible in the recipient's portal inbox at once. Callers
  whose delivery is gated (rent increase, G3) refuse this channel themselves.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Dispatch
from mhvp.core.auth.principal import TenantPrincipal
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole

CHANNELS = ("post", "email", "portal")
EVIDENCE = ("registered_mail", "courier", "hand_delivery", "email_log", "portal_read", "other")


class DispatchRecordIn(BaseModel):
    """Dispatch record given with the letter: channel, date and tracking reference."""

    model_config = ConfigDict(extra="forbid")

    channel: str = Field(pattern="^(post|email|portal)$")
    # Day of the posting (post) or of the hand over; without it the record stays prepared.
    sent_on: date | None = None
    evidence_kind: str | None = Field(default=None, pattern="^(" + "|".join(EVIDENCE) + ")$")
    # Tracking reference, for example the registered mail number.
    evidence_ref: str | None = Field(default=None, max_length=200)


class LetterRecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    letter_date: date | None = None
    ticket_id: uuid.UUID | None = None
    dispatch: DispatchRecordIn | None = None


def dispatch_out(row: Dispatch | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "document_id": row.document_id,
        "contact_id": row.contact_id,
        "channel": row.channel,
        "status": row.status,
        "message_id": row.message_id,
        "evidence_kind": row.evidence_kind,
        "evidence_ref": row.evidence_ref,
        "sent_at": row.sent_at,
        "created_by": row.created_by,
    }


async def store_letter(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    principal: TenantPrincipal,
    head: letters.Letterhead,
    letter: letters.Letter,
    title: str,
    filename: str,
    links: list[tuple[str, uuid.UUID]],
    category_id: uuid.UUID | None = None,
) -> Document:
    """Render the letter on the letterhead and file it as a generated document."""
    pdf = letters.render_pdf(head, letter)
    return await docs.store_document(
        session,
        blobs,
        tenant_id=principal.tenant_id,
        data=pdf,
        title=title,
        filename=filename,
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=category_id,
        links=[(t, i, LinkRole.GENERATED) for t, i in links],
        created_by=principal.user_id,
    )


async def link_ticket(
    session: AsyncSession,
    *,
    principal: TenantPrincipal,
    document: Document,
    ticket_id: uuid.UUID,
    note: str,
) -> None:
    """Link the document to the ticket and leave an internal comment naming it."""
    from mhvp.tickets.models import Ticket, TicketComment

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Ticket nicht gefunden.")
    session.add(
        DocumentLink(
            tenant_id=principal.tenant_id,
            document_id=document.id,
            entity_type="ticket",
            entity_id=ticket.id,
            role=LinkRole.GENERATED,
        )
    )
    session.add(
        TicketComment(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ticket_id=ticket.id,
            internal=True,
            author_user_id=principal.user_id,
            body=note,
            document_ids=[document.id],
        )
    )
    await session.flush()


async def record_dispatch(
    session: AsyncSession,
    *,
    principal: TenantPrincipal,
    document: Document,
    contact_id: uuid.UUID,
    record: DispatchRecordIn,
    entity_type: str,
    entity_id: uuid.UUID,
) -> Dispatch:
    """Create the dispatch row for the letter (see module docstring) and the domain event
    ``<entity_type>.letter_dispatch_recorded`` with channel, date and reference."""
    from mhvp.communication.dispatch import DispatchIn, create_dispatch

    row = await create_dispatch(
        session,
        principal,
        DispatchIn(document_id=document.id, contact_id=contact_id, channel=record.channel),
        None,
    )
    row.evidence_kind = record.evidence_kind
    row.evidence_ref = record.evidence_ref
    if record.channel == "post" and record.sent_on is not None:
        row.status = "sent"
        row.sent_at = datetime.combine(record.sent_on, datetime.min.time(), tzinfo=UTC)
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"{entity_type}.letter_dispatch_recorded",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={
            "document_id": str(document.id),
            "dispatch_id": str(row.id),
            "channel": record.channel,
            "status": row.status,
            "sent_on": record.sent_on.isoformat() if record.sent_on else None,
            "evidence_kind": record.evidence_kind,
            "evidence_ref": record.evidence_ref,
        },
    )
    await session.flush()
    return row
