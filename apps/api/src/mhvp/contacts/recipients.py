"""Recipient resolution with authorised representatives (operator decision 26.09.2026).

A contact may name an authorised representative (``ContactRelation`` of kind
``representative``, ``contact_id`` = represented contact, ``related_contact_id`` =
representative). The relation carries a delivery rule (``delivery_mode``):

* ``both`` (default): represented contact and representative receive everything,
* ``representative_only``: only the representative receives,
* ``owner_only``: only the represented contact receives, the representative is informed by
  nothing automatic.

Mail dispatch (``mhvp.communication.dispatch``, single and serial), letters
(``mhvp.documents.routers``, single and serial), the WEG invitation recipients
(``mhvp.hoa.meetings``), dunning letters (``mhvp.accounting.dunning_letters``) and rental
statement letters (``mhvp.billing.letters``) call :func:`resolve_recipients` and never read
the relation table themselves (operator decision 27.09.2026, M23-07). A letter that goes to
the representative only carries the line "für <Vollmachtgeber>"; a dunning letter that goes
to the representative only carries :data:`REPRESENTATIVE_ONLY_WARNING` until legal advice
confirms the effect of Zugang. A relation counts only while valid (``valid_from`` /
``valid_to``) and while the representative is not deleted. Without an active representative
the contact itself is the only recipient. Repeated contacts are returned once, in first
occurrence order.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactRelation, DeliveryMode, RelationKind

REPRESENTATIVE_ONLY_WARNING = (
    "Zustellung nur an den Bevollmächtigten: ob die Mahnung damit dem Vollmachtgeber zugeht, "
    "ist anwaltlich zu klären (M23-07)"
)


@dataclass(frozen=True)
class Recipient:
    """One delivery target. ``represents`` is the represented contact when the recipient is an
    authorised representative, ``None`` when the contact receives for itself."""

    contact_id: uuid.UUID
    represents: uuid.UUID | None = None


def _active(row: ContactRelation, on: date) -> bool:
    if row.valid_from is not None and row.valid_from > on:
        return False
    return not (row.valid_to is not None and row.valid_to < on)


async def active_representatives(
    session: AsyncSession, contact_ids: Sequence[uuid.UUID], *, on: date | None = None
) -> dict[uuid.UUID, list[ContactRelation]]:
    """Valid ``representative`` relations per represented contact, oldest first, without
    deleted representatives."""
    if not contact_ids:
        return {}
    day = on or datetime.now(UTC).date()
    rows = (
        await session.execute(
            select(ContactRelation)
            .join(Contact, Contact.id == ContactRelation.related_contact_id)
            .where(
                ContactRelation.contact_id.in_(list(contact_ids)),
                ContactRelation.kind == RelationKind.REPRESENTATIVE,
                Contact.deleted_at.is_(None),
                or_(ContactRelation.valid_from.is_(None), ContactRelation.valid_from <= day),
                or_(ContactRelation.valid_to.is_(None), ContactRelation.valid_to >= day),
            )
            .order_by(ContactRelation.created_at, ContactRelation.id)
        )
    ).scalars()
    out: dict[uuid.UUID, list[ContactRelation]] = {}
    for row in rows:
        if _active(row, day):
            out.setdefault(row.contact_id, []).append(row)
    return out


async def resolve_recipients(
    session: AsyncSession, contact_ids: Sequence[uuid.UUID], *, on: date | None = None
) -> list[Recipient]:
    """Delivery targets for the given contacts under their delivery rules (module docstring).

    Order: per input contact first the contact itself (if it receives), then its
    representatives in creation order. A contact reached twice (as itself and as somebody's
    representative, or named twice) is returned once with its first reason."""
    representatives = await active_representatives(session, contact_ids, on=on)
    out: list[Recipient] = []
    seen: set[uuid.UUID] = set()

    def add(recipient: Recipient) -> None:
        if recipient.contact_id not in seen:
            seen.add(recipient.contact_id)
            out.append(recipient)

    for contact_id in contact_ids:
        relations = representatives.get(contact_id, [])
        modes = {DeliveryMode(r.delivery_mode) for r in relations}
        # The represented contact receives unless every rule says representative only.
        if not relations or modes != {DeliveryMode.REPRESENTATIVE_ONLY}:
            add(Recipient(contact_id))
        for relation in relations:
            if DeliveryMode(relation.delivery_mode) is not DeliveryMode.OWNER_ONLY:
                add(Recipient(relation.related_contact_id, represents=contact_id))
    return out


def representative_only(recipients: Sequence[Recipient], contact_id: uuid.UUID) -> bool:
    """True when ``contact_id`` does not receive for itself, only its representatives do."""
    return not any(r.contact_id == contact_id and r.represents is None for r in recipients)


async def debtor_contact_id(session: AsyncSession, party_id: uuid.UUID) -> uuid.UUID | None:
    """Contact of the first party member (address holder of statements and dunning letters).
    ``None`` when the party has no member."""
    from mhvp.contacts.models import PartyMember

    contact_id: uuid.UUID | None = await session.scalar(
        select(PartyMember.contact_id)
        .where(PartyMember.party_id == party_id)
        .order_by(PartyMember.created_at, PartyMember.id)
        .limit(1)
    )
    return contact_id
