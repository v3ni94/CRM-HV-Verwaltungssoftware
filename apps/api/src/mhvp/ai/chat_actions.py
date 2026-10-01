"""Changes asked for in the assistant chat become proposals (rule AI-LOOKUP-01, 0.1.6).

The model may name one action with its answer (``AnswerResult.action``). The platform checks it
deterministically before a proposal exists, and nothing is written before a human confirms the
proposal through ``POST /ai/proposals/{id}/apply``:

- an action needs a chat run with a platform lookup (``input_ref["lookup"]``); runs of the
  automation or other callers of ``answer_question`` never produce one,
- the user's own message (the page hint of the chat bubble removed) must ask for that kind of
  change (``CHANGE_INTENT``, ``NOTE_INTENT``, ``TICKET_INTENT``); an action the model adds on
  its own, or that a record, a mail or a ticket description asked for, is dropped and logged,
- the target record must be one of the platform's own hits of this run (never an id the model
  made up),
- contact changes reuse the checks and the write path of the ticket contact change proposals
  (``mhvp.tickets.proposals``: allowed fields, ``PUT /contacts`` path, history, event),
- phone numbers and e-mail addresses reach the model masked; the value always comes from the
  user's own message (deterministic), never from the model; a new name or address value must
  appear in the user's message as well, otherwise the user is asked to state it,
- bank details are refused for every kind, also when the message, the note or the ticket text
  only mentions them or contains an IBAN; they stay with the four eyes release in the contact
  file,
- a new ticket and a contact note carry the text the model drafted; the human sees and confirms
  it together with the model's reason,
- a calendar entry or a deadline entry (``calendar_create``, ``deadline_create``) becomes an
  internal entry of the confirmer's own CRM calendar (``workspace.CalendarEntry``, target
  internal): date and time must be valid and in a plausible window, participants are contact
  hits of this run and are only noted, never invited (no Google event, no mail, rule M23-05);
  a deadline entry carries reminders and appears in the deadline list as an appointment. It is
  orientation only, never a legal deadline calculation (M1-09).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any

from mhvp.ai import lookup
from mhvp.ai.models import AiProposal, AiTaskRun
from mhvp.core.logging import get_logger
from mhvp.core.problems import ProblemError
from mhvp.objektakte.masking import _EMAIL, _PHONE, contains_iban

log = get_logger("mhvp.ai.chat_actions")

ENTITY_TYPE = "chat_action"
# Import runs of confirmed chat actions carry this source (``ai:<task>:<kind>``).
SOURCE_PREFIX = "ai:answer_question:"
BANK_WORDS = re.compile(r"\b(iban|bic|bankverbindung|konto(nummer|verbindung)?|bank)\b", re.I)
BANK_REFUSAL = (
    "Bankverbindungen ändere ich nicht über den Chat. Bitte in der Kontaktakte erfassen; die "
    "Änderung läuft dort über die Vier-Augen-Freigabe."
)
# Deterministic intent of the user's own message per kind (0.1.6: the model's confidence or
# an instruction found in a record is no request of the user).
CHANGE_INTENT = re.compile(
    r"änder|aender|\bneue[rsn]?\b|\bneu\b|\btrag(e|en|t)?\b.*\bein\b|eintrag|korrigier"
    r"|aktualisier|berichtig|umgezogen|umzug|heißt jetzt|lautet (jetzt|neu)|ersetz",
    re.I,
)
NOTE_INTENT = re.compile(r"notiz|notier|vermerk|festhalten|halte .*fest|hinterleg", re.I)
TICKET_INTENT = re.compile(r"ticket|vorgang|aufgabe|anleg|erstell|\bleg(e|en|t)?\b.*\ban\b", re.I)
# The user asks for a calendar or deadline entry: a time word plus a creating verb, or the
# words "Termin" / "Frist" with "eintragen", "anlegen", "vormerken", "einplanen", "notieren".
CALENDAR_INTENT = re.compile(
    r"(termin|besichtigung|übergabe|telefonat|ortstermin).{0,160}?"
    r"(eintrag|anleg|erstell|vormerk|einplan|notier|block|reservier|vereinbar)"
    r"|\b(trag|leg|plan|merk).{0,160}?(termin|besichtigung|übergabe).{0,160}?\b(ein|an|vor)\b",
    re.I | re.S,
)
DEADLINE_INTENT = re.compile(
    r"(frist|wiedervorlage|erinnerung).{0,160}?(eintrag|anleg|erstell|vormerk|notier|setz)"
    r"|\b(trag|leg|merk|setz).{0,160}?(frist|wiedervorlage|erinnerung).{0,160}?\b(ein|an|vor)\b",
    re.I | re.S,
)
# M7-03 (10.3 Werkzeuge des Chats): property proposal, filing a document, preparing a portal
# invitation, a letter from a template.
PROPERTY_INTENT = re.compile(
    r"(objekt|liegenschaft|weg|haus).{0,120}?(anleg|erstell|aufnehm|neu)"
    r"|\b(leg|nimm|erstell).{0,120}?(objekt|liegenschaft)",
    re.I | re.S,
)
DOCUMENT_INTENT = re.compile(
    r"(dokument|datei|unterlage|anhang|pdf|beleg).{0,160}?(ableg|zuordn|verknüpf|hinterleg)"
    r"|\b(leg|ordne|verknüpfe?).{0,160}?\b(ab|zu)\b",
    re.I | re.S,
)
PORTAL_INTENT = re.compile(r"portal.{0,80}?(einlad|zugang)|einladung.{0,80}?portal", re.I | re.S)
LETTER_INTENT = re.compile(
    r"(brief|schreiben|anschreiben).{0,160}?(erstell|erzeug|entw|vorlage|schreib)"
    r"|vorlage.{0,160}?(brief|schreiben)"
    r"|(erstell|erzeug|entw|schreib).{0,80}?(brief|anschreiben)",
    re.I | re.S,
)
PROPERTY_FIELDS = ("number", "name", "street", "house_number", "postal_code", "city")
MANAGEMENT_TYPES = ("rental", "hoa", "hoa_with_sev")

INTENT = {
    "contact_change": CHANGE_INTENT,
    "contact_note": NOTE_INTENT,
    "ticket_create": TICKET_INTENT,
    "calendar_create": CALENDAR_INTENT,
    "deadline_create": DEADLINE_INTENT,
    "property_create": PROPERTY_INTENT,
    "document_file": DOCUMENT_INTENT,
    "portal_invite_prepare": PORTAL_INTENT,
    "letter_create": LETTER_INTENT,
}
APPOINTMENT_KINDS = ("uebergabe", "besichtigung", "telefonat", "vor_ort", "sonstiges")
DEADLINE_REMINDERS = ["1d", "7d"]  # reminder codes of ``workspace.jobs.REMINDER_OFFSET_DAYS``
PAST_DAYS = 30  # a date further back than this is refused (typo in the model output)
FUTURE_DAYS = 5 * 365
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FIELD_LABELS = {
    "salutation": "die Anrede",
    "title": "den Titel",
    "first_name": "den Vornamen",
    "last_name": "den Nachnamen",
    "company_name": "den Firmennamen",
    "street": "die Straße",
    "house_number": "die Hausnummer",
    "postal_code": "die Postleitzahl",
    "city": "den Ort",
}
PERMISSIONS = {
    "contact_change": "contacts:update",
    "contact_note": "contacts:update",
    "ticket_create": "tickets:create",
    # Own calendar entries need membership only (``POST /workspace/calendar``); ``ai:create``
    # is what every chat caller holds.
    "calendar_create": "ai:create",
    "deadline_create": "ai:create",
    "property_create": "properties:create",
    "document_file": "documents:update",
    "portal_invite_prepare": "contacts:update",
    "letter_create": "documents:create",
}


def is_chat_action_run(source: str | None) -> bool:
    return bool(source) and str(source).startswith(SOURCE_PREFIX)


def _hit(found: dict[str, Any] | None, ref: str | None, type_: str) -> dict[str, Any] | None:
    if not ref:
        return None
    return next(
        (x for x in lookup.links_of(found) if x["type"] == type_ and x["id"] == str(ref)), None
    )


def _hits(found: dict[str, Any] | None, refs: list[str], type_: str) -> dict[str, Any] | None:
    return next((h for r in refs if (h := _hit(found, r, type_)) is not None), None)


def mentions_bank(*texts: str | None) -> bool:
    """Bank words or an IBAN in any of the texts (the user's message, a drafted note, a ticket
    title or description)."""
    return any(bool(BANK_WORDS.search(t)) or contains_iban(t) for t in texts if t)


def _stated(value: str, instruction: str) -> bool:
    """The new value appears in the user's message (case and whitespace insensitive)."""
    return lookup.flat(value).lower() in lookup.flat(instruction).lower()


def plausible_date(value: object, today: date) -> date | None:
    """ISO date of the model output inside the window the platform accepts; the human sees and
    may correct it before confirming."""
    try:
        parsed = date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
    if parsed < today - timedelta(days=PAST_DAYS) or parsed > today + timedelta(days=FUTURE_DAYS):
        return None
    return parsed


def _entry(
    run: AiTaskRun, action: dict[str, Any], found: dict[str, Any] | None, deadline: bool
) -> tuple[dict[str, Any] | None, str | None]:
    """Payload of a calendar or deadline entry: title, date, optional time, participants
    (contact hits, noted only), property hit; nothing is written here."""
    from mhvp.workspace.services import local_today

    title = str(action.get("title") or "").strip()
    if not title:
        return None, (
            "Für die Frist fehlt eine Bezeichnung."
            if deadline
            else "Für den Termin fehlt eine Bezeichnung."
        )
    when = plausible_date(action.get("date"), local_today())
    if when is None:
        return None, (
            "Bitte nennen Sie das Datum der Frist (TT.MM.JJJJ) in Ihrer Nachricht."
            if deadline
            else "Bitte nennen Sie das Datum des Termins (TT.MM.JJJJ) in Ihrer Nachricht."
        )
    time_ = str(action.get("time") or "").strip() or None
    if time_ is not None and not _TIME.match(time_):
        time_ = None
    refs = [str(r) for r in action.get("refs") or []]
    participants = [
        {"contact_id": h["id"], "label": h["label"]}
        for r in refs
        if (h := _hit(found, r, "contact")) is not None
    ][:10]
    prop = _hits(found, refs, "property")
    kind = str(action.get("appointment_kind") or "sonstiges")
    if kind not in APPOINTMENT_KINDS:
        kind = "sonstiges"
    return {
        "kind": "deadline_create" if deadline else "calendar_create",
        "title": title[:300],
        "date": when.isoformat(),
        "time": None if deadline else time_,
        "appointment_kind": None if deadline else kind,
        "participants": participants,
        "property_id": prop["id"] if prop else None,
        "property_label": prop["label"] if prop else None,
        "description": str(action.get("description") or "").strip()[:4000] or None,
        "reminders": DEADLINE_REMINDERS if deadline else [],
        "reason": str(action.get("reason") or "")[:500],
    }, None


def _dropped(run: AiTaskRun, kind: str | None, why: str) -> tuple[None, None]:
    log.info(
        "chat action dropped",
        extra={"run_id": str(run.id), "kind": kind, "reason": why},
    )
    return None, None


def build(run: AiTaskRun) -> tuple[dict[str, Any] | None, str | None]:
    """(proposal payload, note for the user). Payload None: no proposal is created."""
    from mhvp.tickets import proposals as contact_changes

    action = (run.output or {}).get("action")
    if not action:
        return None, None
    kind = action.get("kind")
    found = run.input_ref.get("lookup")
    if found is None:
        # Not a chat run with a platform lookup (automation, intake): never a chat action.
        return _dropped(run, kind, "no lookup")
    # The page hint of the chat bubble ("Kontext: ... Seite Bank.") is not part of the request.
    instruction = lookup.strip_context(str(run.input_ref.get("instruction", "")))
    intent = INTENT.get(str(kind))
    if intent is None:
        return None, None
    if not intent.search(instruction):
        return _dropped(run, kind, "no change intent in the user's message")
    refs = [str(r) for r in action.get("refs") or []]
    contact = _hits(found, refs, "contact")
    if kind in ("calendar_create", "deadline_create"):
        if mentions_bank(instruction, str(action.get("title") or "")):
            return None, BANK_REFUSAL
        return _entry(run, action, found, deadline=kind == "deadline_create")
    if kind == "contact_change":
        changes = [c for c in action.get("changes") or [] if c.get("field")]
        if mentions_bank(instruction) or any(
            str(c["field"]).startswith("bank") or c["field"] in contact_changes.BLOCKED_FIELDS
            for c in changes
        ):
            return None, BANK_REFUSAL
        if contact is None:
            return None, "Für die Änderung fehlt ein eindeutig gefundener Kontakt."
        cleaned = []
        for change in changes:
            name = str(change["field"])
            new = str(change.get("new") or "").strip()
            if name in ("phone", "email"):
                pattern = _PHONE if name == "phone" else _EMAIL
                values = list(
                    dict.fromkeys(m.group(0).strip() for m in pattern.finditer(instruction))
                )
                if len(values) != 1:
                    return None, (
                        "Bitte nennen Sie die neue Telefonnummer eindeutig in Ihrer Nachricht."
                        if name == "phone"
                        else "Bitte nennen Sie die neue E-Mail-Adresse eindeutig."
                    )
                new = values[0]
            elif not new or not _stated(new, instruction):
                # Name and address values come from the user's message as well (never a
                # value the model took from a record, a mail or its own guess).
                label = FIELD_LABELS.get(name, f"das Feld {name}")
                return None, f"Bitte nennen Sie {label} wörtlich in Ihrer Nachricht."
            cleaned.append({"field": name, "new": new})
        try:
            valid = contact_changes._validate_changes(cleaned)
        except ProblemError as exc:
            return None, str(exc.detail or exc)
        return {
            "kind": kind,
            "contact_id": contact["id"],
            "contact_label": contact["label"],
            "changes": valid,
            "reason": str(action.get("reason") or "")[:500],
        }, None
    if kind == "contact_note":
        note = str(action.get("note") or "").strip()
        if mentions_bank(instruction, note):
            return None, BANK_REFUSAL
        if contact is None or not note:
            return None, "Für die Notiz fehlen ein eindeutig gefundener Kontakt oder der Text."
        return {
            "kind": kind,
            "contact_id": contact["id"],
            "contact_label": contact["label"],
            "note": note[:20_000],
            "reason": str(action.get("reason") or "")[:500],
        }, None
    if kind == "ticket_create":
        title = str(action.get("title") or "").strip()
        description = str(action.get("description") or "").strip()
        if mentions_bank(instruction, title, description):
            return None, BANK_REFUSAL
        if not title:
            return None, "Für das Ticket fehlt ein Titel."
        prop = _hits(found, refs, "property")
        unit = _hits(found, refs, "unit")
        return {
            "kind": kind,
            "title": title[:300],
            "description": description[:20_000] or None,
            "contact_id": contact["id"] if contact else None,
            "contact_label": contact["label"] if contact else None,
            "property_id": prop["id"] if prop else None,
            "property_label": prop["label"] if prop else None,
            "unit_id": unit["id"] if unit else None,
            "unit_label": unit["label"] if unit else None,
            "reason": str(action.get("reason") or "")[:500],
        }, None
    if kind == "property_create":
        return _property(action, instruction)
    if kind == "document_file":
        return _document_file(run, action, found)
    if kind in ("portal_invite_prepare", "letter_create"):
        if mentions_bank(instruction):
            return None, BANK_REFUSAL
        if contact is None:
            return None, "Für diese Aktion fehlt ein eindeutig gefundener Kontakt."
        prop = _hits(found, refs, "property")
        unit = _hits(found, refs, "unit")
        payload: dict[str, Any] = {
            "kind": kind,
            "contact_id": contact["id"],
            "contact_label": contact["label"],
            "reason": str(action.get("reason") or "")[:500],
        }
        if kind == "letter_create":
            payload |= {
                "template_query": str(action.get("template") or "").strip()[:200],
                "property_id": prop["id"] if prop else None,
                "property_label": prop["label"] if prop else None,
                "unit_id": unit["id"] if unit else None,
                "unit_label": unit["label"] if unit else None,
            }
        return payload, None
    return None, None


def _property(action: dict[str, Any], instruction: str) -> tuple[dict[str, Any] | None, str | None]:
    """Property proposal (status onboarding at creation): every value must appear in the
    user's message; the management type is one of the platform values."""
    if mentions_bank(instruction):
        return None, BANK_REFUSAL
    data = action.get("property") or {}
    values: dict[str, str | None] = {}
    for name in PROPERTY_FIELDS:
        value = str(data.get(name) or "").strip()
        if value and not _stated(value, instruction):
            return None, f"Bitte nennen Sie {PROPERTY_LABELS[name]} wörtlich in Ihrer Nachricht."
        values[name] = value or None
    if not values["number"] or not re.fullmatch(r"[0-9]{3}", values["number"] or ""):
        return None, "Bitte nennen Sie die dreistellige Objektnummer in Ihrer Nachricht."
    if not values["name"] or len(values["name"] or "") < 2:
        return None, "Bitte nennen Sie den Namen des Objekts in Ihrer Nachricht."
    management = str(data.get("management_type") or "")
    if management not in MANAGEMENT_TYPES:
        return None, "Bitte nennen Sie die Verwaltungsart (Miete, WEG oder WEG mit SEV)."
    return {
        "kind": "property_create",
        **values,
        "management_type": management,
        "reason": str(action.get("reason") or "")[:500],
    }, None


PROPERTY_LABELS = {
    "number": "die Objektnummer",
    "name": "den Namen des Objekts",
    "street": "die Straße",
    "house_number": "die Hausnummer",
    "postal_code": "die Postleitzahl",
    "city": "den Ort",
}
FILE_TARGETS = ("property", "unit", "contact")


def _document_file(
    run: AiTaskRun, action: dict[str, Any], found: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Files the documents attached to this chat message at one hit of the run (property, unit
    or contact); never a document the model names on its own."""
    documents = [str(d) for d in run.input_ref.get("document_ids") or []]
    if not documents:
        return None, "Bitte hängen Sie das Dokument an Ihre Nachricht an."
    refs = [str(r) for r in action.get("refs") or []]
    target = next(((t, h) for t in FILE_TARGETS if (h := _hits(found, refs, t)) is not None), None)
    if target is None:
        return None, "Für die Ablage fehlt ein eindeutig gefundenes Objekt, Einheit oder Kontakt."
    type_, hit = target
    return {
        "kind": "document_file",
        "document_ids": documents[:20],
        "entity_type": type_,
        "entity_id": hit["id"],
        "entity_label": hit["label"],
        "reason": str(action.get("reason") or "")[:500],
    }, None


async def enrich(session: Any, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Checks that need the database (M7-03), in the job's session under RLS: the letter
    template must be an active template named in the request; the portal invitation needs an
    e-mail address in the contact file and no existing portal account."""
    from sqlalchemy import func, or_, select

    kind = payload.get("kind")
    if kind == "letter_create":
        from mhvp.documents.models import DocumentTemplate

        query = str(payload.get("template_query") or "").strip()
        if not query:
            return None, "Bitte nennen Sie die Briefvorlage (Name oder Code)."
        rows = (
            await session.scalars(
                select(DocumentTemplate)
                .where(
                    DocumentTemplate.active.is_(True),
                    or_(
                        func.lower(DocumentTemplate.code) == query.lower(),
                        DocumentTemplate.name.ilike(f"%{query}%"),
                    ),
                )
                .order_by(DocumentTemplate.code, DocumentTemplate.version.desc())
            )
        ).all()
        latest = {r.code: r for r in reversed(rows)}
        if len(latest) != 1:
            return None, (
                "Keine aktive Briefvorlage gefunden. Bitte nennen Sie den Namen der Vorlage."
                if not latest
                else "Mehrere Briefvorlagen passen. Bitte nennen Sie die Vorlage genauer."
            )
        template = next(iter(latest.values()))
        return {
            **payload,
            "template_id": str(template.id),
            "template_label": template.name,
        }, None
    if kind == "portal_invite_prepare":
        from mhvp.contacts.models import ContactEmail
        from mhvp.portal.models import PortalAccount

        contact_id = uuid.UUID(str(payload["contact_id"]))
        if await session.scalar(
            select(PortalAccount.id).where(PortalAccount.contact_id == contact_id)
        ):
            return None, "Für den Kontakt besteht bereits ein Portalzugang."
        email = await session.scalar(
            select(ContactEmail.email)
            .where(ContactEmail.contact_id == contact_id)
            .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
            .limit(1)
        )
        if not email:
            return (
                None,
                "Der Kontakt hat keine E-Mail-Adresse; bitte zuerst in der Kontaktakte erfassen.",
            )
        return {**payload, "email_masked": _mask_email(str(email))}, None
    return payload, None


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def proposal(run: AiTaskRun, payload: dict[str, Any], provider_used: str | None) -> AiProposal:
    return AiProposal(
        tenant_id=run.tenant_id,
        task_run_id=run.id,
        entity_type=ENTITY_TYPE,
        context_id=run.conversation_id,
        proposed={**payload, "provider_used": provider_used},
    )


def uuid_or_none(value: object) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None
