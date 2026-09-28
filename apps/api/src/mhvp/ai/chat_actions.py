"""Changes asked for in the assistant chat become proposals (rule AI-LOOKUP-01, 0.1.6).

The model may name one action with its answer (``AnswerResult.action``). The platform checks it
deterministically before a proposal exists, and nothing is written before a human confirms the
proposal through ``POST /ai/proposals/{id}/apply``:

- the target record must be one of the platform's own hits of this run (never an id the model
  made up),
- contact changes reuse the checks and the write path of the ticket contact change proposals
  (``mhvp.tickets.proposals``: allowed fields, ``PUT /contacts`` path, history, event); bank
  details are refused, also when the question only mentions them, and stay with the four eyes
  release in the contact file,
- phone numbers and e-mail addresses reach the model masked; the value always comes from the
  user's own message (deterministic), never from the model,
- a new ticket and a contact note carry the text the model drafted; the human sees and confirms
  it.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from mhvp.ai import lookup
from mhvp.ai.models import AiProposal, AiTaskRun
from mhvp.core.problems import ProblemError
from mhvp.objektakte.masking import _EMAIL, _PHONE

ENTITY_TYPE = "chat_action"
BANK_WORDS = re.compile(r"\b(iban|bic|bankverbindung|konto(nummer|verbindung)?|bank)\b", re.I)
BANK_REFUSAL = (
    "Bankverbindungen ändere ich nicht über den Chat. Bitte in der Kontaktakte erfassen; die "
    "Änderung läuft dort über die Vier-Augen-Freigabe."
)
PERMISSIONS = {
    "contact_change": "contacts:update",
    "contact_note": "contacts:update",
    "ticket_create": "tickets:create",
}


def _hit(found: dict[str, Any] | None, ref: str | None, type_: str) -> dict[str, Any] | None:
    if not ref:
        return None
    return next(
        (x for x in lookup.links_of(found) if x["type"] == type_ and x["id"] == str(ref)), None
    )


def _hits(found: dict[str, Any] | None, refs: list[str], type_: str) -> dict[str, Any] | None:
    return next((h for r in refs if (h := _hit(found, r, type_)) is not None), None)


def build(run: AiTaskRun) -> tuple[dict[str, Any] | None, str | None]:
    """(proposal payload, note for the user). Payload None: no proposal is created."""
    from mhvp.tickets import proposals as contact_changes

    action = (run.output or {}).get("action")
    if not action:
        return None, None
    instruction = str(run.input_ref.get("instruction", ""))
    found = run.input_ref.get("lookup")
    kind = action.get("kind")
    refs = [str(r) for r in action.get("refs") or []]
    contact = _hits(found, refs, "contact")
    if kind == "contact_change":
        changes = [c for c in action.get("changes") or [] if c.get("field")]
        if BANK_WORDS.search(instruction) or any(
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
            "reason": action.get("reason") or "",
        }, None
    if kind == "contact_note":
        note = str(action.get("note") or "").strip()
        if contact is None or not note:
            return None, "Für die Notiz fehlen ein eindeutig gefundener Kontakt oder der Text."
        return {
            "kind": kind,
            "contact_id": contact["id"],
            "contact_label": contact["label"],
            "note": note[:20_000],
            "reason": action.get("reason") or "",
        }, None
    if kind == "ticket_create":
        title = str(action.get("title") or "").strip()
        if not title:
            return None, "Für das Ticket fehlt ein Titel."
        prop = _hits(found, refs, "property")
        unit = _hits(found, refs, "unit")
        return {
            "kind": kind,
            "title": title[:300],
            "description": str(action.get("description") or "")[:20_000] or None,
            "contact_id": contact["id"] if contact else None,
            "contact_label": contact["label"] if contact else None,
            "property_id": prop["id"] if prop else None,
            "property_label": prop["label"] if prop else None,
            "unit_id": unit["id"] if unit else None,
            "unit_label": unit["label"] if unit else None,
            "reason": action.get("reason") or "",
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
