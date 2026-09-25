"""Automatische Ticket-Zuweisung aus eingehenden Mails (operator 25.09.2026,
docs/integrations/mail-optimierung.md). Reine, deterministische Regeln, kein KI-Aufruf:

(a) Anschrift: das Postfach ist genau einem Mitglied per ``MailboxUser`` zugeordnet.
(b) Anrede/Signatur: Nachname-Treffer gegen aktive Mitglieder in Anrede- und Signaturzeile.
(c) Kompetenz: jedes Mitglied, dessen Kompetenzen das erkannte Thema enthalten, wird als
    zusätzlicher Zuweiser mit Grund "Kompetenz <Thema>" ergänzt.
(d) Verlauf: bei einer Mail, die zu einem bereits bestehenden Vorgang gehört (Thread oder
    derselbe Kontakt), werden die bisherigen Zuweiser übernommen.

Der primäre Zuweiser bleibt ``Ticket.assignee_user_id``; weitere Zuweiser stehen in
``TicketAssignee``. Niemals wird der Betreiber pauschal zugewiesen, wenn keine Regel greift.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox, MailboxUser, Message
from mhvp.platform.models import Membership, MembershipStatus, User
from mhvp.tickets.competences import classify_topic, label_for
from mhvp.tickets.models import Ticket, TicketAssignee

# Anrede: "Sehr geehrte Frau Brink", "Hallo Ina", "Liebe Frau Dr. Brink" ...
_SALUTATION_RE = re.compile(
    r"(?:sehr geehrte[r]?|hallo|liebe[r]?|guten tag)\s+"
    r"(?:herr|frau)?\s*(?:dr\.?|prof\.?)?\s*([A-ZÄÖÜ][\wäöüß\-]+)",
    re.IGNORECASE,
)
_SIGNATURE_WINDOW = 6  # letzte Zeilen des Mailtexts gelten als Signaturblock


@dataclass(frozen=True)
class ActiveMember:
    user_id: uuid.UUID
    display_name: str
    competences: list[str]


async def active_members(session: AsyncSession, tenant_id: uuid.UUID) -> list[ActiveMember]:
    rows = await session.execute(
        select(User.id, User.display_name, Membership.competences)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.tenant_id == tenant_id, Membership.status == MembershipStatus.ACTIVE)
    )
    return [
        ActiveMember(
            user_id=r.id, display_name=r.display_name, competences=list(r.competences or [])
        )
        for r in rows.all()
    ]


def _surnames(display_name: str) -> list[str]:
    """Nachname-Kandidaten eines Mitglieds: das letzte Wort des Anzeigenamens, mit und ohne
    Umlaut-Normalisierung, für die tolerante Prüfung gegen "Frau/Herr <Nachname>"."""
    parts = display_name.strip().split()
    return [parts[-1]] if parts else []


def _norm(word: str) -> str:
    return word.strip().strip(",.:;").lower()


def match_by_name(text: str, members: list[ActiveMember]) -> ActiveMember | None:
    """Erste Übereinstimmung eines Mitglieds-Nachnamens in Anrede oder Signatur (letzte
    Zeilen). Erfordert Wortgleichheit (keine Teilstring-Treffer), toleriert "Frau"/"Herr"."""
    if not text:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    signature = "\n".join(lines[-_SIGNATURE_WINDOW:])
    salutation_match = _SALUTATION_RE.search(text)
    candidates = set()
    if salutation_match:
        candidates.add(_norm(salutation_match.group(1)))
    for word in re.findall(r"[A-ZÄÖÜ][\wäöüß\-]+", signature):
        candidates.add(_norm(word))
    for member in members:
        for surname in _surnames(member.display_name):
            if _norm(surname) in candidates:
                return member
    return None


async def _mailbox_owner(session: AsyncSession, mailbox_id: uuid.UUID | None) -> uuid.UUID | None:
    """Genau ein Mitglied per ``MailboxUser`` zugeordnet -> dieses Mitglied; Standardpostfächer
    (für alle lesbar) oder mehrere Zuordnungen ergeben keine Anschrift-Zuweisung."""
    if mailbox_id is None:
        return None
    mailbox = await session.get(Mailbox, mailbox_id)
    if mailbox is None or mailbox.is_default:
        return None
    user_ids = list(
        await session.scalars(
            select(MailboxUser.user_id).where(MailboxUser.mailbox_id == mailbox_id)
        )
    )
    return user_ids[0] if len(user_ids) == 1 else None


async def _previous_assignees(
    session: AsyncSession, tenant_id: uuid.UUID, contact_id: uuid.UUID | None
) -> list[TicketAssignee]:
    if contact_id is None:
        return []
    last_ticket_id = await session.scalar(
        select(Ticket.id)
        .where(Ticket.tenant_id == tenant_id, Ticket.initiator_contact_id == contact_id)
        .order_by(Ticket.created_at.desc())
        .limit(1)
    )
    if last_ticket_id is None:
        return []
    return list(
        await session.scalars(
            select(TicketAssignee).where(TicketAssignee.ticket_id == last_ticket_id)
        )
    )


async def add_assignee(
    session: AsyncSession,
    ticket: Ticket,
    user_id: uuid.UUID,
    reason: str,
    *,
    primary: bool = False,
) -> None:
    existing = await session.scalar(
        select(TicketAssignee).where(
            TicketAssignee.ticket_id == ticket.id, TicketAssignee.user_id == user_id
        )
    )
    if existing is not None:
        return
    session.add(
        TicketAssignee(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            user_id=user_id,
            primary=primary,
            reason=reason,
        )
    )
    if primary and ticket.assignee_user_id is None:
        ticket.assignee_user_id = user_id


async def auto_assign_new_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, message: Message, ticket: Ticket
) -> None:
    """Regeln (a) bis (c) bei Ticketanlage aus einer Mail; (d) nur wenn keine der anderen
    Regeln bereits einen primären Zuweiser ergeben hat."""
    members = await active_members(session, tenant_id)
    matched_any = False

    mailbox_user_id = await _mailbox_owner(session, message.mailbox_id)
    if mailbox_user_id is not None:
        await add_assignee(session, ticket, mailbox_user_id, "Anschrift", primary=True)
        matched_any = True

    text = f"{message.subject or ''}\n{message.body or ''}"
    name_match = match_by_name(text, members)
    if name_match is not None:
        await add_assignee(session, ticket, name_match.user_id, "Signatur", primary=not matched_any)
        matched_any = True

    tenant_extra = await _tenant_extra_catalogue(session, tenant_id)
    topic = ticket.topic or classify_topic(text, tenant_extra)
    if topic:
        ticket.topic = topic
        label = label_for(topic, tenant_extra)
        for member in members:
            if topic in member.competences:
                await add_assignee(session, ticket, member.user_id, f"Kompetenz {label}")

    if not matched_any:
        previous = await _previous_assignees(session, tenant_id, message.contact_id)
        for row in previous:
            await add_assignee(session, ticket, row.user_id, "Verlauf", primary=row.primary)


async def _tenant_extra_catalogue(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[dict[str, Any]]:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(
        select(TenantSettings.competence_catalogue_extra).where(
            TenantSettings.tenant_id == tenant_id
        )
    )
    return list(row or [])
