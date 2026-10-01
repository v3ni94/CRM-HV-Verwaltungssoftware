"""Contact data of the resident on a work order (AC06, GA02-06, rule AC06-einwilligungen).

A work order sent to a service provider may carry the contact data of the affected tenant or
owner (the ticket's contact, else its initiator) so that the provider can arrange the
appointment. Passing them on is a transfer to a third party: it needs a valid ``data_sharing``
consent of that contact, or the tenant policy ``consent_or_contract`` (the order serves the
contract). Without permission the order goes out without the personal fields and the reason
is returned and logged. The check runs on every read, so a revocation applies at once."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts import consent_rules
from mhvp.contacts.models import Contact, ContactEmail, ContactPhone
from mhvp.tickets.models import Ticket, WorkOrder


async def order_resident_contact_id(session: AsyncSession, order: WorkOrder) -> uuid.UUID | None:
    if order.ticket_id is None:
        return None
    ticket = await session.get(Ticket, order.ticket_id)
    if ticket is None:
        return None
    return ticket.contact_id or ticket.initiator_contact_id


async def order_contact_share(session: AsyncSession, order: WorkOrder) -> dict[str, Any]:
    """``{"shared", "reason", "contact"}``; ``contact`` holds name, phone and e-mail only when
    shared. Without a resident contact nothing is shared (reason ``no_resident_contact``)."""
    contact_id = await order_resident_contact_id(session, order)
    if contact_id is None:
        return {"shared": False, "reason": "no_resident_contact", "contact": None}
    decision = await consent_rules.data_sharing_decision(
        session, contact_id, contractual_necessity=True
    )
    if not decision.allowed:
        return {"shared": False, "reason": decision.reason, "contact": None}
    contact = await session.get(Contact, contact_id)
    if contact is None:
        return {"shared": False, "reason": "no_resident_contact", "contact": None}
    phone = await session.scalar(
        select(ContactPhone.number)
        .where(ContactPhone.contact_id == contact_id)
        .order_by(ContactPhone.is_primary.desc(), ContactPhone.created_at)
        .limit(1)
    )
    email = await session.scalar(
        select(ContactEmail.email)
        .where(ContactEmail.contact_id == contact_id)
        .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
        .limit(1)
    )
    return {
        "shared": True,
        "reason": decision.reason,
        "contact": {"name": contact.display_name, "phone": phone, "email": email},
    }
