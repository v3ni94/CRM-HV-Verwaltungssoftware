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
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
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


# Zuordnungsprüfung Kontakt, Objekt, Einheit (Betreiber 27.09.2026) ---------------------------
#
# Regeln sind deterministisch und begründet; jede Dimension endet als "sure" (automatisch
# zuordenbar), "unsure" (Rückfrage nötig, Vorschläge mit Konfidenz) oder "none" (kein
# Treffer). Der KI-Vorschlagspfad (``suggest.py``) liefert nur Namen und Objektnummern als
# zusätzliche Vorschläge, nie eine sichere Zuordnung (Regel 0.1.6). Konfidenzen sind keine
# Geldwerte; sie werden als Gleitkommazahl zwischen 0 und 1 geführt.

SURE_THRESHOLD = 0.9
UNSURE_THRESHOLD = 0.4
UNSURE_CAP = 0.85  # Obergrenze ohne Absendertreffer bei Mails
_SENDER_REASON = "Absenderadresse stimmt überein"
MAX_CANDIDATES = 5
_CUSTOMER_NUMBER_RE = re.compile(
    r"(?:kunden|kd\.?|debitoren)\s*-?\s*(?:nummer|nr\.?)\s*[:#]?\s*([A-Za-z0-9\-/]{3,20})",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?:\+49|0049|0)[\d\s/().\-]{6,20}\d")
# A bare "Nr." is no unit keyword (house, invoice or order numbers); it only counts after an
# explicit unit word such as "Wohnung Nr. 3" or "WE Nr. 3" (review 1.36.0).
_UNIT_RE = re.compile(
    r"\b(?:einheit|we|whg\.?|wohnung|wohneinheit|stellplatz|tg)\s*(?:nr\.?\s*)?"
    r"([A-Za-z]?\d{1,4}[A-Za-z]?)\b",
    re.IGNORECASE,
)
# A line starting with a greeting names the recipient; own staff named there is never the
# sender (review 1.36.0). "Liebe Grüße" is a closing formula, not a salutation.
_SALUTATION_LINE_RE = re.compile(
    r"^\s*(?:sehr\s+geehrte[rs]?|hallo|hi|moin|liebe[rs]?(?!\s+gr)|guten\s+(?:tag|morgen|abend))\b",
    re.IGNORECASE,
)
_NAME_WORD_RE = re.compile(r"[A-ZÄÖÜ][\wäöüß\-]{2,}")
_NAME_STOP = {
    "sehr",
    "geehrte",
    "geehrter",
    "geehrtes",
    "werte",
    "werter",
    "hallo",
    "hey",
    "moin",
    "servus",
    "liebe",
    "lieber",
    "liebes",
    "guten",
    "tag",
    "morgen",
    "abend",
    "damen",
    "herren",
    "herr",
    "herrn",
    "frau",
    "familie",
    "zusammen",
    "allerseits",
    "team",
    "dear",
    "hello",
    "prof",
    "mit",
    "freundlichen",
    "grüßen",
    "gruß",
    "viele",
    "beste",
    "grüße",
    "gruss",
    "grüsse",
    "grüssen",
    "freundliche",
    "herzliche",
    "herzlichen",
    "schöne",
    "schönen",
    "besten",
    "lieben",
    "mfg",
    "regards",
    "danke",
    "vielen",
    "dank",
    "objekt",
    "einheit",
    "wohnung",
    "mieter",
    "eigentümer",
    "hausverwaltung",
    "gmbh",
    "telefon",
    "mobil",
    "mail",
    "betreff",
    "gesendet",
    "von",
    "an",
    "the",
}


@dataclass
class Candidate:
    id: uuid.UUID
    label: str
    detail: str | None
    confidence: float
    reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "label": self.label,
            "detail": self.detail,
            "confidence": round(min(self.confidence, 1.0), 2),
            "reasons": list(self.reasons),
        }


@dataclass
class DimensionResult:
    status: str  # sure, unsure, none
    candidates: list[Candidate]

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def _finish(scores: dict[uuid.UUID, Candidate]) -> DimensionResult:
    ranked = sorted(scores.values(), key=lambda c: c.confidence, reverse=True)
    ranked = [c for c in ranked if c.confidence >= UNSURE_THRESHOLD][:MAX_CANDIDATES]
    if not ranked:
        return DimensionResult("none", [])
    top = ranked[0]
    second = ranked[1].confidence if len(ranked) > 1 else 0.0
    # Sicher nur bei eindeutigem Spitzenkandidaten: ein zweiter Kandidat mit ähnlicher
    # Konfidenz macht die Zuordnung zur Rückfrage.
    if top.confidence >= SURE_THRESHOLD and second < SURE_THRESHOLD:
        return DimensionResult("sure", ranked)
    return DimensionResult("unsure", ranked)


def _bump(
    scores: dict[uuid.UUID, Candidate],
    key: uuid.UUID,
    label: str,
    detail: str | None,
    score: float,
    reason: str,
) -> None:
    row = scores.get(key)
    if row is None:
        scores[key] = Candidate(key, label, detail, score, [reason])
        return
    row.confidence = min(1.0, row.confidence + score)
    if reason not in row.reasons:
        row.reasons.append(reason)


def has_salutation_line(text: str) -> bool:
    return any(_SALUTATION_LINE_RE.match(line) for line in (text or "").splitlines())


_REPLY_MARKER_RE = re.compile(
    r"^(Am .{3,120} schrieb .{0,200}:\s*$|On .{3,120} wrote:\s*$"
    r"|-{2,}\s*Urspr.ngliche Nachricht\s*-{2,}|-{2,}\s*Original Message\s*-{2,})",
    re.IGNORECASE,
)
_HEADER_FROM_RE = re.compile(r"^(Von|From):\s*\S", re.IGNORECASE)
_HEADER_NEXT_RE = re.compile(r"^(Gesendet|Sent|An|To|Betreff|Subject):", re.IGNORECASE)
_HEADER_WINDOW = 3


def without_quoted(text: str) -> str:
    """Text without quoted earlier mails, for the sender name of a message (review 1.36.0):
    lines starting with ``>`` are left out, and only a real reply or forward header ends the
    text: "Am ... schrieb ...:", "Ursprüngliche Nachricht", or a "Von:"/"From:" line followed
    within the next three lines by "Gesendet:", "Sent:", "An:", "To:", "Betreff:" or
    "Subject:". A line of underscores or an own line "Von: Hausverwaltung" does not end it.
    Without any text left (a bottom-posted reply below the quote) the text with the ``>``
    lines removed is used. Unlike the ticket description the sender's own signature stays, it
    names the sender; a quoted own signature does not."""
    lines = (text or "").splitlines()
    unquoted = [line for line in lines if not line.strip().startswith(">")]
    kept: list[str] = []
    for index, line in enumerate(unquoted):
        stripped = line.strip()
        if _REPLY_MARKER_RE.match(stripped):
            break
        if _HEADER_FROM_RE.match(stripped) and any(
            _HEADER_NEXT_RE.match(following.strip())
            for following in unquoted[index + 1 : index + 1 + _HEADER_WINDOW]
        ):
            break
        kept.append(line)
    if not "\n".join(kept).strip():
        return "\n".join(unquoted)
    return "\n".join(kept)


def name_tokens(text: str, staff_names: Collection[str] = ()) -> set[str]:
    """Capitalised words of the first two lines (call notes start with the name) and of the
    signature block (last lines), without stock phrases. ``staff_names`` (names of own active
    members) are dropped only from salutation lines, which name the recipient; every other word
    and line counts, also a contact sharing a staff surname (review 1.36.0)."""
    if not text:
        return set()
    lines = [line for line in text.splitlines() if line.strip()]
    staff = {_norm(name) for name in staff_names}
    tokens: set[str] = set()
    for line in lines[:2] + lines[-_SIGNATURE_WINDOW:]:
        words = {_norm(w) for w in _NAME_WORD_RE.findall(line)}
        if staff and _SALUTATION_LINE_RE.match(line):
            words -= staff
        tokens |= words
    return {t for t in tokens if t not in _NAME_STOP and len(t) >= 3}


def customer_numbers(text: str) -> set[str]:
    return {m.group(1).strip().lower() for m in _CUSTOMER_NUMBER_RE.finditer(text or "")}


def phone_numbers(text: str) -> set[str]:
    """Telefonnummern aus dem Text in E.164; unparsbare Kandidaten werden übergangen."""
    from mhvp.contacts.validation import InvalidValueError, normalise_phone

    out: set[str] = set()
    for match in _PHONE_RE.finditer(text or ""):
        raw = match.group(0)
        if sum(ch.isdigit() for ch in raw) < 7:
            continue
        try:
            out.add(normalise_phone(raw))
        except InvalidValueError:
            continue
    return out


def unit_tokens(text: str) -> set[str]:
    return {m.group(1).lower() for m in _UNIT_RE.finditer(text or "")}


def _contact_label(contact: Any) -> tuple[str, str | None]:
    roles = [r for r in (contact.roles or []) if isinstance(r, str)]
    return contact.display_name, ", ".join(roles) or None


async def evaluate_contact(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    from_address: str | None,
    text: str,
    ai_contact_name: str | None = None,
    name_text: str | None = None,
) -> DimensionResult:
    """``name_text``: the text sender names are taken from, if it differs from ``text`` (a
    message without its quoted earlier mails, review 1.36.0)."""
    from sqlalchemy import func

    from mhvp.contacts.models import (
        Contact,
        ContactEmail,
        ContactIdentifier,
        ContactPhone,
        IdentifierKind,
    )

    scores: dict[uuid.UUID, Candidate] = {}
    contacts: dict[uuid.UUID, Any] = {}
    sender_ids: set[uuid.UUID] = set()

    async def _load(ids: set[uuid.UUID]) -> None:
        missing = [i for i in ids if i not in contacts]
        if missing:
            rows = await session.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.id.in_(missing),
                    Contact.deleted_at.is_(None),
                )
            )
            for row in rows:
                contacts[row.id] = row

    if from_address:
        email_ids = set(
            await session.scalars(
                select(ContactEmail.contact_id).where(
                    func.lower(ContactEmail.email) == from_address.strip().lower()
                )
            )
        )
        await _load(email_ids)
        hit = [i for i in email_ids if i in contacts]
        score = 1.0 if len(hit) == 1 else 0.6
        sender_ids = set(hit)
        for cid in hit:
            label, detail = _contact_label(contacts[cid])
            _bump(scores, cid, label, detail, score, _SENDER_REASON)

    numbers = customer_numbers(text)
    if numbers:
        rows = await session.execute(
            select(ContactIdentifier.contact_id, ContactIdentifier.value).where(
                ContactIdentifier.kind == IdentifierKind.CUSTOMER_NUMBER,
                func.lower(ContactIdentifier.value).in_(numbers),
            )
        )
        pairs = rows.all()
        await _load({p.contact_id for p in pairs})
        for pair in pairs:
            if pair.contact_id in contacts:
                label, detail = _contact_label(contacts[pair.contact_id])
                _bump(
                    scores,
                    pair.contact_id,
                    label,
                    detail,
                    0.95,
                    f"Kundennummer {pair.value} im Text",
                )

    phones = phone_numbers(text)
    if phones:
        phone_ids = set(
            await session.scalars(
                select(ContactPhone.contact_id).where(ContactPhone.number.in_(phones))
            )
        )
        await _load(phone_ids)
        for cid in phone_ids:
            if cid in contacts:
                label, detail = _contact_label(contacts[cid])
                _bump(scores, cid, label, detail, 0.7, "Telefonnummer aus der Signatur")

    names_from = text if name_text is None else name_text
    staff_names: set[str] = set()
    if has_salutation_line(names_from):
        staff_names = {
            word
            for member in await active_members(session, tenant_id)
            for word in member.display_name.split()
        }
    tokens = name_tokens(names_from, staff_names)
    if ai_contact_name:
        tokens |= {_norm(w) for w in ai_contact_name.split() if len(w) >= 3}
    if tokens:
        name_rows = await session.scalars(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
                func.lower(Contact.last_name).in_(tokens),
            )
        )
        for row in name_rows:
            contacts[row.id] = row
            label, detail = _contact_label(row)
            first = _norm(row.first_name or "")
            if first and first in tokens:
                _bump(scores, row.id, label, detail, 0.7, "Vor- und Nachname im Text")
            else:
                _bump(scores, row.id, label, detail, 0.5, "Nachname im Text")
    if ai_contact_name:
        for cid, cand in scores.items():
            if _norm(ai_contact_name) == _norm(contacts[cid].display_name):
                cand.reasons.append("KI-Vorschlag (nur Hinweis)")
    # Operator rule (review 1.36.0): only an exact sender address of exactly one active contact
    # is sure. Customer number, phone, name or a shared sender address are proposals at most
    # (forwardings, call notes, third parties writing about a contact), also for tickets
    # without a sender address.
    for cid, cand in scores.items():
        if cand.confidence <= UNSURE_CAP or (len(sender_ids) == 1 and cid in sender_ids):
            continue
        cand.confidence = UNSURE_CAP
        if not from_address:
            cand.reasons.append("Keine Absenderadresse")
        elif cid in sender_ids:
            cand.reasons.append("Absenderadresse mehrfach vergeben")
        elif sender_ids:
            cand.reasons.append("Absenderadresse gehört zu einem anderen Kontakt")
        else:
            cand.reasons.append("Absenderadresse unbekannt")
    return _finish(scores)


async def contact_property_units(
    session: AsyncSession, tenant_id: uuid.UUID, contact_id: uuid.UUID
) -> list[tuple[uuid.UUID, uuid.UUID | None, str]]:
    """Objekte (und Einheiten) aus Verträgen und Objektbeziehungen des Kontakts:
    ``(property_id, unit_id | None, Grund)``. Beendete Verträge und abgelaufene Beziehungen
    zählen nicht."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import PropertyContact
    from mhvp.workspace.services import local_today

    today = local_today()
    out: list[tuple[uuid.UUID, uuid.UUID | None, str]] = []
    contracts = await session.execute(
        select(Contract.property_id, Contract.unit_id, Contract.kind)
        .join(PartyMember, PartyMember.party_id == Contract.party_id)
        .where(
            Contract.tenant_id == tenant_id,
            PartyMember.contact_id == contact_id,
            or_(Contract.end_date.is_(None), Contract.end_date >= today),
        )
    )
    for row in contracts.all():
        out.append((row.property_id, row.unit_id, f"Vertrag ({row.kind.value}) des Kontakts"))
    relations = await session.execute(
        select(PropertyContact.property_id, PropertyContact.category_code).where(
            PropertyContact.tenant_id == tenant_id,
            PropertyContact.contact_id == contact_id,
            or_(PropertyContact.valid_to.is_(None), PropertyContact.valid_to >= today),
        )
    )
    for rel in relations.all():
        out.append((rel.property_id, None, f"Objektbeziehung ({rel.category_code}) des Kontakts"))
    return out


def _property_label(prop: Any) -> tuple[str, str | None]:
    address = " ".join(p for p in (prop.street, prop.house_number) if p)
    city = " ".join(p for p in (prop.postal_code, prop.city) if p)
    return f"{prop.number} {prop.name}", ", ".join(p for p in (address, city) if p) or None


async def evaluate_property(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    text: str,
    contact_id: uuid.UUID | None,
    ai_property_number: str | None = None,
) -> DimensionResult:
    from mhvp.communication import mail
    from mhvp.properties.models import Property

    scores: dict[uuid.UUID, Candidate] = {}
    props = {
        p.id: p
        for p in await session.scalars(select(Property).where(Property.tenant_id == tenant_id))
    }
    number = mail.property_number(text, None)
    if number:
        for prop in props.values():
            if prop.number == number:
                label, detail = _property_label(prop)
                _bump(scores, prop.id, label, detail, 1.0, f"Objektnummer {number} im Text")
    if ai_property_number and ai_property_number != number:
        for prop in props.values():
            if prop.number == ai_property_number:
                label, detail = _property_label(prop)
                _bump(scores, prop.id, label, detail, 0.5, "KI-Vorschlag Objektnummer")
    haystack = " ".join((text or "").lower().split())
    for prop in props.values():
        street = (prop.street or "").strip().lower()
        if len(street) < 4 or street not in haystack:
            continue
        label, detail = _property_label(prop)
        house = (prop.house_number or "").strip().lower()
        if house and re.search(rf"{re.escape(street)}\s*{re.escape(house)}\b", haystack):
            _bump(scores, prop.id, label, detail, 0.85, f"Adresse {prop.street} {house} im Text")
        else:
            _bump(scores, prop.id, label, detail, 0.6, f"Straße {prop.street} im Text")
    if contact_id is not None:
        links = await contact_property_units(session, tenant_id, contact_id)
        by_property: dict[uuid.UUID, str] = {}
        for pid, _unit, reason in links:
            by_property.setdefault(pid, reason)
        score = 0.8 if len(by_property) == 1 else 0.5
        for pid, reason in by_property.items():
            if pid not in props:
                continue
            label, detail = _property_label(props[pid])
            _bump(scores, pid, label, detail, score, reason)
    return _finish(scores)


def _unit_label(unit: Any) -> tuple[str, str | None]:
    parts = [p for p in (unit.label, unit.location, unit.floor) if p]
    return f"Einheit {unit.number}", ", ".join(parts) or None


async def evaluate_unit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    text: str,
    contact_id: uuid.UUID | None,
    property_id: uuid.UUID | None,
) -> DimensionResult:
    from mhvp.properties.models import Unit

    scores: dict[uuid.UUID, Candidate] = {}
    units: dict[uuid.UUID, Any] = {}
    backed: set[uuid.UUID] = set()  # units found through a contract of the contact
    if property_id is not None:
        for unit in await session.scalars(
            select(Unit).where(Unit.tenant_id == tenant_id, Unit.property_id == property_id)
        ):
            units[unit.id] = unit
        tokens = unit_tokens(text)
        haystack = " ".join((text or "").lower().split())
        for unit in units.values():
            label, detail = _unit_label(unit)
            if unit.number.lower() in tokens:
                _bump(scores, unit.id, label, detail, 0.6, f"Einheitennummer {unit.number} im Text")
            location = (unit.location or "").strip().lower()
            if len(location) >= 4 and location in haystack:
                _bump(scores, unit.id, label, detail, 0.6, f"Wohnungslage {unit.location} im Text")
    if contact_id is not None:
        links = [
            (pid, uid, reason)
            for pid, uid, reason in await contact_property_units(session, tenant_id, contact_id)
            if uid is not None and (property_id is None or pid == property_id)
        ]
        unit_ids = {uid for _p, uid, _r in links if uid is not None}
        missing = [u for u in unit_ids if u not in units]
        if missing:
            for unit in await session.scalars(select(Unit).where(Unit.id.in_(missing))):
                units[unit.id] = unit
        score = 0.85 if len(unit_ids) == 1 else 0.5
        for _pid, uid, reason in links:
            if uid is None or uid in backed or uid not in units:
                continue
            backed.add(uid)
            label, detail = _unit_label(units[uid])
            _bump(scores, uid, label, detail, score, reason)
    # Operator rule (review 1.36.0): a unit number or location in the text alone is a proposal,
    # never an automatic assignment; only together with a contract of the contact it is sure.
    for uid, cand in scores.items():
        if uid not in backed and cand.confidence > UNSURE_CAP:
            cand.confidence = UNSURE_CAP
    return _finish(scores)
