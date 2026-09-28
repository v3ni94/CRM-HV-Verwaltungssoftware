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
  it together with the model's reason.
"""

from __future__ import annotations

import re
import uuid
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
INTENT = {
    "contact_change": CHANGE_INTENT,
    "contact_note": NOTE_INTENT,
    "ticket_create": TICKET_INTENT,
}
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
    return None, None


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
