"""Anrufe über die KI-Telefonassistenz Hallo Heidi am Ticket (Betreiberauftrag 26.09.2026).

Hallo Heidi schickt je Anruf ein Gesprächsprotokoll per Mail; der Mail-Eingang legt daraus ein
Ticket an. Für solche Mails ersetzt dieser Ablauf die allgemeine Stammdatenerkennung aus
``mhvp.tickets.proposals``:

1. Erkennung (``is_call_mail``): Absendermuster oder Kennwort im Betreff, im Text nur zusammen
   mit einer beschrifteten Rufnummer. Muster je Mandant in ``tenant_settings.call_assistant``
   (``GET/PUT /mail/call-assistant``), sonst die eingebauten ``DEFAULT_*``.
2. Extraktion (``extract``): deterministisch per Regex Anrufernummer, Anrufername, Objekt
   (Objektnummer oder Anschrift), Einheit (Whg., WE, Etage) und Anliegen; zusätzlich der
   KI-Task ``call_summary`` (maskierte Kennungen, nur Vorschlag), der fehlende Angaben ergänzt.
   Das Ergebnis steht als Ticketereignis ``call_summary`` am Ticket.
3. Zuordnung (``resolve``): Objekt über Nummer oder Anschrift, dann Personen mit laufendem
   Vertrag (Miete oder Eigentum) an diesem Objekt mit Namensabgleich; sonst Name allein, nur bei
   genau einem Treffer (Dublettenprüfung, mehrere Treffer werden Kandidaten); sonst eindeutige
   Rufnummer. Ticket bekommt ``contact_id``, ``property_id``, ``unit_id``, soweit noch leer.
4. Nummernabgleich: Ist die Anrufernummer (E.164) nicht unter den Rufnummern des Kontakts,
   entsteht ein ``AiProposal`` (``entity_type="contact_change"``) "Telefonnummer ergänzen" mit
   Antwortentwurf auf das Anliegen (Playbook, sonst generischer Text). Entscheidung über die
   bestehenden Endpunkte; ``accept-and-reply`` übernimmt die Nummer und legt den Entwurf am
   Ticket an. Versendet wird nichts (Freigabepfad des Mailmoduls).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.communication.models import Message
from mhvp.contacts.models import Contact, ContactEmail, ContactKind, ContactPhone, PartyMember
from mhvp.contacts.validation import InvalidValueError, normalise_phone
from mhvp.contracts.models import Contract
from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.objektakte.masking import mask_identifiers
from mhvp.properties.models import Property, Unit
from mhvp.tickets.models import Ticket, TicketEvent

log = logging.getLogger(__name__)

DEFAULT_SENDER_PATTERNS: tuple[str, ...] = ("hallo-heidi", "halloheidi", "hallo.heidi")
DEFAULT_KEYWORDS: tuple[str, ...] = ("hallo heidi",)
MAX_EXCERPT = 4000
MIN_AI_CONFIDENCE = 0.5
GENERIC_REPLY = (
    "Wir haben Ihr Anliegen aus Ihrem Anruf aufgenommen und kümmern uns darum. "
    "Sobald wir Neues haben, melden wir uns bei Ihnen."
)


# Configuration ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CallAssistantConfig:
    enabled: bool = True
    sender_patterns: tuple[str, ...] = DEFAULT_SENDER_PATTERNS
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS


def config_from(raw: dict[str, Any] | None) -> CallAssistantConfig:
    raw = raw or {}
    senders = [str(s).strip().lower() for s in raw.get("sender_patterns") or [] if str(s).strip()]
    keywords = [str(k).strip().lower() for k in raw.get("keywords") or [] if str(k).strip()]
    return CallAssistantConfig(
        enabled=bool(raw.get("enabled", True)),
        sender_patterns=tuple(senders) or DEFAULT_SENDER_PATTERNS,
        keywords=tuple(keywords) or DEFAULT_KEYWORDS,
    )


async def load_config(session: AsyncSession) -> CallAssistantConfig:
    from mhvp.platform.models import TenantSettings

    raw = await session.scalar(select(TenantSettings.call_assistant))
    return config_from(raw)


# Extraction ---------------------------------------------------------------------------------

_PHONE_VALUE = r"(?:\+|00)?\d[\d \t/()\-]{4,20}\d"
_PHONE_LABEL = (
    r"(?:Rückrufnummer|Rueckrufnummer|Rufnummer|Telefonnummer|Handynummer|Mobilnummer"
    r"|Anrufernummer|Telefon|Tel\.?|Handy|Mobil|Nummer)"
)
_LABELLED_PHONE = re.compile(
    rf"{_PHONE_LABEL}(?:[ \t]+(?:des|der)[ \t]+Anrufer(?:s|in)?)?"
    rf"[ \t]*[:=\-]?[ \t]*({_PHONE_VALUE})",
    re.IGNORECASE,
)
_ANY_PHONE = re.compile(rf"(?<![\w+])({_PHONE_VALUE})(?![\w])")
_NAME_WORD = r"[A-ZÄÖÜ][\wäöüß'\-]+"
_NAME_LABEL = re.compile(
    r"^[ \t]*(?:Name(?:[ \t]+des[ \t]+Anrufers)?|Anrufer(?:in)?(?:name)?|Kontakt|Kunde|Kundin)"
    r"[ \t]*:[ \t]*(?:(Frau|Herr|Herrn)[ \t]+)?(?:(?:Dr\.|Prof\.)[ \t]+)?"
    rf"({_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,3}})",
    re.IGNORECASE | re.MULTILINE,
)
_NAME_PROSE = re.compile(
    rf"\b(Frau|Herr|Herrn)[ \t]+((?:{_NAME_WORD}[ \t]+)?{_NAME_WORD})[ \t]+"
    r"(?:hat[ \t]+angerufen|ruft[ \t]+an|rief[ \t]+an|meldet[ \t]+sich|bittet|möchte|moechte)"
)
_PROPERTY_LABEL = re.compile(
    r"^[ \t]*(?:Objekt(?:adresse|nummer)?|Adresse|Anschrift|Liegenschaft|Immobilie)"
    r"(?:[ \t]*Nr\.?)?[ \t]*:[ \t]*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_PROPERTY_NUMBER = re.compile(r"\bObjekt(?:nummer)?[ \t]*(?:Nr\.?)?[ \t]*:?[ \t]*(\d{3})\b", re.I)
_BARE_NUMBER = re.compile(r"^\s*(\d{3})\b")
_UNIT = re.compile(
    r"\b(?:Whg\.?|Wohnung|WE|Wohneinheit|Einheit|Gewerbeeinheit|GE)[ \t]*(?:Nr\.?)?[ \t]*[:#]?"
    r"[ \t]*(\d{1,4}[a-zA-Z]?)\b"
)
_FLOOR = re.compile(
    r"\b(\d{1,2}\.[ \t]*(?:OG|Obergeschoss|Etage|Stock)|EG|Erdgeschoss|DG|Dachgeschoss|UG"
    r"|Souterrain)(?:[ \t]+(links|rechts|mitte|Mitte|Links|Rechts))?\b"
)
_CONCERN = re.compile(
    r"^[ \t]*(?:Anliegen|Grund(?:[ \t]+des[ \t]+Anrufs)?|Nachricht|Zusammenfassung|Notiz"
    r"|Gesprächsnotiz|Gespraechsnotiz|Thema)[ \t]*:[ \t]*(.+?)"
    r"(?=\n[ \t]*\n|\n[ \t]*[A-ZÄÖÜ][\wäöüß \t]{1,30}:|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_CALLBACK = re.compile(r"\bRückruf|\bRueckruf|zurückrufen|zurueckrufen", re.IGNORECASE)
_STREET_NORMAL = re.compile(r"(straße|strasse|str\.?)\b")


@dataclass
class CallData:
    caller_phone: str | None = None
    caller_phone_raw: str | None = None
    caller_phone_label: str | None = None
    caller_name: str | None = None
    salutation: str | None = None
    property_hint: str | None = None
    property_number: str | None = None
    street: str | None = None
    house_number: str | None = None
    unit_hint: str | None = None
    unit_number: str | None = None
    floor: str | None = None
    concern: str | None = None
    callback_requested: bool = False
    sources: dict[str, str] = field(default_factory=dict)


def normalise_e164(value: str | None) -> str | None:
    """E.164 or ``None``; the German default region handles ``0171 ...``."""
    if not value:
        return None
    try:
        return normalise_phone(value.strip())
    except InvalidValueError:
        return None


def phone_label(e164: str | None) -> str:
    """``mobile`` for German mobile ranges 015, 016, 017, otherwise ``other``."""
    if e164 and e164.startswith(("+4915", "+4916", "+4917")):
        return "mobile"
    return "other"


def is_call_mail(
    config: CallAssistantConfig, sender: str | None, subject: str | None, body: str | None
) -> bool:
    if not config.enabled:
        return False
    sender_l = (sender or "").lower()
    if any(p in sender_l for p in config.sender_patterns):
        return True
    subject_l = (subject or "").lower()
    if any(k in subject_l for k in config.keywords):
        return True
    body_l = (body or "").lower()
    # Nur Kennwort im Text reicht nicht ("Hallo Heidi," als Anrede an eine Mitarbeiterin).
    return any(k in body_l for k in config.keywords) and bool(_LABELLED_PHONE.search(body or ""))


def _parse_property(hint: str, data: CallData) -> None:
    from mhvp.tickets.proposals import _HOUSE_ADDITION, _STREET

    number = _PROPERTY_NUMBER.search(hint) or _BARE_NUMBER.match(hint)
    if number and not data.property_number:
        data.property_number = number.group(1)
    street = _STREET.search(hint)
    if street and not data.street:
        data.street = street.group(1).strip()
        data.house_number = _HOUSE_ADDITION.sub(r"\1\2", street.group(2).strip())


def _parse_unit(text: str, data: CallData) -> None:
    unit = _UNIT.search(text)
    if unit and not data.unit_number:
        data.unit_number = unit.group(1)
    floor = _FLOOR.search(text)
    if floor and not data.floor:
        data.floor = " ".join(p for p in (floor.group(1), floor.group(2)) if p)
    if not data.unit_hint:
        parts = [f"Whg. {data.unit_number}" if data.unit_number else None, data.floor]
        data.unit_hint = ", ".join(p for p in parts if p) or None


def extract(subject: str | None, body: str | None) -> CallData:
    """Deterministic extraction from a call protocol mail."""
    text = f"{subject or ''}\n{body or ''}"
    data = CallData()
    labelled = _LABELLED_PHONE.search(text)
    candidates = [labelled.group(1)] if labelled else []
    candidates += [m.group(1) for m in _ANY_PHONE.finditer(text)]
    for raw in candidates:
        e164 = normalise_e164(raw)
        if e164:
            data.caller_phone_raw, data.caller_phone = raw.strip(), e164
            data.caller_phone_label = phone_label(e164)
            data.sources["caller_phone"] = "regex"
            break
    name = _NAME_LABEL.search(text) or _NAME_PROSE.search(text)
    if name:
        salutation = (name.group(1) or "").capitalize() or None
        data.salutation = "Herr" if salutation == "Herrn" else salutation
        data.caller_name = name.group(2).strip()
        data.sources["caller_name"] = "regex"
    prop = _PROPERTY_LABEL.search(text)
    if prop:
        data.property_hint = prop.group(1).strip()[:200]
        _parse_property(data.property_hint, data)
    else:
        number = _PROPERTY_NUMBER.search(text)
        if number:
            data.property_number = number.group(1)
            data.property_hint = f"Objekt {number.group(1)}"
    if data.property_hint:
        data.sources["property_hint"] = "regex"
    _parse_unit(text, data)
    concern = _CONCERN.search(body or "")
    if concern:
        data.concern = " ".join(concern.group(1).split())[:1000]
        data.sources["concern"] = "regex"
    data.callback_requested = bool(_CALLBACK.search(text))
    return data


def merge_ai(data: CallData, ai: dict[str, Any] | None) -> CallData:
    """AI fills gaps only; the phone number always comes from the deterministic stage (the
    provider saw a placeholder)."""
    if not ai or float(ai.get("confidence") or 0) < MIN_AI_CONFIDENCE:
        return data
    if not data.caller_name and ai.get("caller_name"):
        data.caller_name = str(ai["caller_name"]).strip()[:200]
        data.sources["caller_name"] = "ai"
    if ai.get("property_hint") and not (data.property_number or data.street):
        data.property_hint = str(ai["property_hint"]).strip()[:200]
        _parse_property(data.property_hint, data)
        data.sources["property_hint"] = "ai"
    if ai.get("unit_hint") and not data.unit_number:
        _parse_unit(str(ai["unit_hint"]), data)
        data.unit_hint = data.unit_hint or str(ai["unit_hint"]).strip()[:100]
    if ai.get("concern") and not data.concern:
        data.concern = str(ai["concern"]).strip()[:1000]
        data.sources["concern"] = "ai"
    data.callback_requested = data.callback_requested or bool(ai.get("callback_requested"))
    return data


# Resolution ---------------------------------------------------------------------------------


@dataclass
class Resolution:
    property_id: uuid.UUID | None = None
    property_label: str | None = None
    unit_id: uuid.UUID | None = None
    unit_label: str | None = None
    contact_id: uuid.UUID | None = None
    matched_by: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)


def street_key(value: str | None) -> str:
    """``Hauptstr. 5`` and ``Hauptstraße`` compare equal."""
    lowered = _STREET_NORMAL.sub("str", (value or "").lower())
    return re.sub(r"[\s.\-]", "", lowered)


def split_name(full: str) -> tuple[str | None, str]:
    parts = full.split()
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def name_matches(contact: Contact, full: str) -> bool:
    first, last = split_name(full)
    if (contact.last_name or "").lower() != last.lower():
        return False
    return first is None or (contact.first_name or "").lower() == first.lower()


async def _property(session: AsyncSession, data: CallData) -> Property | None:
    base = select(Property)
    if data.property_number:
        row = await session.scalar(base.where(Property.number == data.property_number))
        if row is not None:
            return row
    if data.street:
        query = base
        if data.house_number:
            query = query.where(func.lower(Property.house_number) == data.house_number.lower())
        key = street_key(data.street)
        rows = [p for p in await session.scalars(query.limit(200)) if street_key(p.street) == key]
        if len(rows) == 1:
            return rows[0]
    return None


async def _unit(session: AsyncSession, prop: Property, data: CallData) -> Unit | None:
    if not data.unit_number:
        return None
    unit: Unit | None = await session.scalar(
        select(Unit)
        .where(
            Unit.property_id == prop.id,
            or_(
                func.lower(Unit.number) == data.unit_number.lower(),
                func.lower(Unit.label) == data.unit_number.lower(),
            ),
        )
        .limit(1)
    )
    return unit


async def _people_at(
    session: AsyncSession, property_id: uuid.UUID, today: date
) -> list[tuple[Contact, uuid.UUID]]:
    """Persons with a running tenancy or ownership contract at the property, with the unit."""
    rows = await session.execute(
        select(Contact, Contract.unit_id)
        .join(PartyMember, PartyMember.contact_id == Contact.id)
        .join(Contract, Contract.party_id == PartyMember.party_id)
        .where(
            Contract.property_id == property_id,
            Contract.start_date <= today,
            or_(Contract.end_date.is_(None), Contract.end_date >= today),
            Contact.deleted_at.is_(None),
        )
    )
    return [(contact, unit_id) for contact, unit_id in rows.all()]


async def resolve(session: AsyncSession, data: CallData, today: date | None = None) -> Resolution:
    today = today or datetime.now(UTC).date()
    result = Resolution()
    prop = await _property(session, data)
    unit: Unit | None = None
    if prop is not None:
        result.property_id, result.property_label = prop.id, f"{prop.number} {prop.name}"
        unit = await _unit(session, prop, data)
    if prop is not None and data.caller_name:
        people = [(c, u) for c, u in await _people_at(session, prop.id, today)]
        hits = {c.id: (c, u) for c, u in people if name_matches(c, data.caller_name)}
        if unit is not None and len(hits) > 1:
            hits = {k: v for k, v in hits.items() if v[1] == unit.id} or hits
        if len(hits) == 1:
            contact, unit_id = next(iter(hits.values()))
            result.contact_id, result.matched_by = contact.id, "property_name"
            if unit is None:
                unit = await session.get(Unit, unit_id)
        elif hits:
            result.candidates = [
                {"id": str(c.id), "display_name": c.display_name} for c, _ in hits.values()
            ]
    if result.contact_id is None and not result.candidates and data.caller_name:
        first, last = split_name(data.caller_name)
        query = select(Contact).where(
            Contact.deleted_at.is_(None),
            Contact.kind == ContactKind.PERSON,
            func.lower(Contact.last_name) == last.lower(),
        )
        if first:
            query = query.where(func.lower(Contact.first_name) == first.lower())
        rows = list(await session.scalars(query.order_by(Contact.display_name).limit(6)))
        if len(rows) == 1:
            result.contact_id, result.matched_by = rows[0].id, "name"
        elif rows:
            result.candidates = [{"id": str(r.id), "display_name": r.display_name} for r in rows]
    if result.contact_id is None and not result.candidates and data.caller_phone:
        ids = list(
            await session.scalars(
                select(ContactPhone.contact_id)
                .join(Contact, Contact.id == ContactPhone.contact_id)
                .where(ContactPhone.number == data.caller_phone, Contact.deleted_at.is_(None))
                .distinct()
                .limit(3)
            )
        )
        if len(ids) == 1:
            result.contact_id, result.matched_by = ids[0], "phone"
    if unit is not None:
        result.unit_id = unit.id
        result.unit_label = unit.label or unit.number
    return result


async def known_numbers(session: AsyncSession, contact_id: uuid.UUID) -> set[str]:
    numbers = await session.scalars(
        select(ContactPhone.number).where(ContactPhone.contact_id == contact_id)
    )
    return {normalise_e164(n) or n for n in numbers}


# Reply --------------------------------------------------------------------------------------


async def reply_for_call(
    session: AsyncSession,
    contact: Contact | None,
    data: CallData,
    subject: str | None,
    phone_added: bool,
) -> dict[str, Any]:
    from mhvp.communication.suggest import best_playbook
    from mhvp.tickets.proposals import greeting_for

    full = None
    if contact is not None and contact.first_name and contact.last_name:
        full = f"{contact.first_name} {contact.last_name}"
    greeting = greeting_for(
        (contact.salutation if contact else None) or data.salutation,
        (contact.last_name if contact else None)
        or (split_name(data.caller_name)[1] if data.caller_name else None),
        full or data.caller_name,
    )
    playbook = (await best_playbook(session, data.concern))[0] if data.concern else None
    text = (playbook.reply_template or "").strip() if playbook is not None else ""
    lines = [f"{greeting},", "", f"vielen Dank für Ihren Anruf. {text or GENERIC_REPLY}"]
    if data.concern:
        lines += ["", f"Ihr Anliegen: {data.concern}"]
    if phone_added:
        lines += ["", "Ihre neue Rufnummer haben wir in unseren Stammdaten ergänzt."]
    lines += ["", "Mit freundlichen Grüßen", "[Name]", "[Firma]"]
    topic = (data.concern or "").split(".")[0][:80] if data.concern else None
    return {
        "subject": f"Ihr Anruf bei uns: {topic}"[:998] if topic else "Ihr Anruf bei uns",
        "body": "\n".join(lines),
        "playbook_id": str(playbook.id) if playbook is not None else None,
    }


async def primary_email(session: AsyncSession, contact_id: uuid.UUID | None) -> str | None:
    if contact_id is None:
        return None
    email: str | None = await session.scalar(
        select(ContactEmail.email)
        .where(ContactEmail.contact_id == contact_id)
        .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
        .limit(1)
    )
    return email


# Proposal -----------------------------------------------------------------------------------


async def _ai(
    settings: Settings, message: Message
) -> tuple[AiTaskRun | None, dict[str, Any] | None, str | None]:
    from mhvp.communication.suggest import _run_gateway_task

    context = {"context_type": "message", "context_id": str(message.id)}
    prompt = (
        f"Betreff: {mask_identifiers(message.subject or '')}\n"
        f"Gesprächsprotokoll (Auszug, Kennungen maskiert):\n"
        f"{mask_identifiers((message.body or '')[:MAX_EXCERPT])}"
    )
    try:
        run = await _run_gateway_task(
            settings, message.tenant_id, AiTask.CALL_SUMMARY, prompt, context
        )
    except Exception as exc:  # the deterministic stage never depends on the provider
        log.warning("call summary run failed", extra={"message_id": str(message.id)})
        return None, None, str(exc)[:500]
    if run.status is RunStatus.SUCCEEDED and run.output:
        return run, run.output, None
    return run, None, run.error or "KI-Lauf ohne Ergebnis."


async def propose_call(
    session: AsyncSession,
    settings: Settings,
    ticket: Ticket,
    message: Message,
    actor_user_id: uuid.UUID | None,
) -> AiProposal | None:
    """Evaluates one call protocol mail: stores the summary at the ticket, assigns contact,
    property and unit, and proposes the caller number when it is new for the contact."""
    from mhvp.tickets.proposals import ENTITY_TYPE, _existing

    existing = await _existing(session, ticket.id, message.id)
    if existing is not None:
        return existing
    data = extract(message.subject, message.body)
    run, ai, skip_reason = await _ai(settings, message)
    data = merge_ai(data, ai)
    match = await resolve(session, data)
    if ticket.contact_id is None and match.contact_id is not None:
        ticket.contact_id = match.contact_id
    if ticket.property_id is None and match.property_id is not None:
        ticket.property_id = match.property_id
    if ticket.unit_id is None and match.unit_id is not None:
        ticket.unit_id = match.unit_id
    if message.property_id is None and match.property_id is not None:
        message.property_id = match.property_id
    call = {
        **{k: v for k, v in asdict(data).items() if k != "sources"},
        "sources": data.sources,
        "property_id": str(match.property_id) if match.property_id else None,
        "property_label": match.property_label,
        "unit_id": str(match.unit_id) if match.unit_id else None,
        "unit_label": match.unit_label,
    }
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="call_summary",
            data={
                "message_id": str(message.id),
                "call": call,
                "contact_id": str(match.contact_id) if match.contact_id else None,
                "matched_by": match.matched_by,
                "ai": "used" if ai is not None else "skipped",
            },
            user_id=actor_user_id,
        )
    )
    contact = await session.get(Contact, match.contact_id) if match.contact_id else None
    if data.caller_phone is None:
        return None
    if contact is not None and data.caller_phone in await known_numbers(session, contact.id):
        return None
    if run is None:
        run = AiTaskRun(
            tenant_id=ticket.tenant_id,
            task=AiTask.CALL_SUMMARY,
            prompt_version="v1",
            input_hash="",
            input_ref={"context": {"context_type": "message", "context_id": str(message.id)}},
            status=RunStatus.BLOCKED,
            error=skip_reason,
        )
        session.add(run)
        await session.flush()
    who = contact.display_name if contact else (data.caller_name or "unbekannter Anrufer")
    changes = [
        {
            "field": "phone",
            "old": None,
            "new": data.caller_phone,
            "label": data.caller_phone_label,
            "confidence": 0.9,
        }
    ]
    reply = await reply_for_call(session, contact, data, message.subject, phone_added=True)
    proposed: dict[str, Any] = {
        "kind": "call",
        "message_id": str(message.id),
        "title": f"Stammdaten ergänzen: Telefonnummer für {who} (Anruf über Hallo Heidi)",
        "contact_id": str(contact.id) if contact else None,
        "contact_display_name": contact.display_name if contact else None,
        "matched_by": match.matched_by,
        "candidates": match.candidates,
        "changes": changes,
        "bank_change_mentioned": False,
        "bank_hint": None,
        "reason": "Anruf mit neuer Rufnummer",
        "address_valid_from": None,
        "mail_salutation": data.salutation,
        "call": call,
        "source": {
            "deterministic": {"categories": ["phone"], "call": data.sources},
            "ai": "used" if ai is not None else "skipped",
            "ai_reason": skip_reason,
            "model": run.model,
        },
        "reply_draft": reply,
    }
    proposal = AiProposal(
        tenant_id=ticket.tenant_id,
        created_by=actor_user_id,
        task_run_id=run.id,
        entity_type=ENTITY_TYPE,
        context_id=ticket.id,
        proposed=proposed,
    )
    session.add(proposal)
    await session.flush()
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="proposal_created",
            data={"proposal_id": str(proposal.id), "title": proposed["title"]},
            user_id=actor_user_id,
        )
    )
    await emit(
        session,
        tenant_id=ticket.tenant_id,
        type="ai_proposal.created",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        actor_user_id=actor_user_id,
        payload={"entity_type": ENTITY_TYPE, "ticket_id": str(ticket.id), "kind": "call"},
    )
    return proposal
