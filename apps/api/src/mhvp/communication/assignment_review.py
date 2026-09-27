"""Zuordnungsprüfung mit Rückfrage (Betreiber 27.09.2026): jede eingehende Mail und jedes
Ticket wird auf Kontakt, Verwaltungsobjekt und Einheit geprüft (``assignment.py``). Sichere
Treffer werden automatisch übernommen und begründet; unsichere Treffer bleiben als offene
Rückfrage ("Handelt es sich um den Kontakt ...?") stehen, bis ein Mitglied mit Ja oder Nein
entscheidet. Jede Entscheidung wird mit Vorschlag, Person und Zeitpunkt protokolliert
(``assignment_review`` plus Domänenereignis) und nur bei eingeschaltetem Mandantenschalter
``ai_learning_examples_enabled`` als Lernbeispiel gespeichert (ADR 0010).

Reihenfolge: Kontakt zuerst, dann Objekt (aus Text und aus den Verträgen des Kontakts), dann
Einheit (aus Text und Vertrag). Ein Ja beim Kontakt löst die Prüfung der beiden nachgelagerten
Dimensionen erneut aus. Ein KI-Vorschlag (``Message.suggestion``) wird nur als zusätzlicher
Hinweis eingespeist, nie als sichere Zuordnung (Regel 0.1.6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, inspect, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.communication import assignment
from mhvp.communication.models import Mailbox, MailboxUser, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import emit
from mhvp.core.ids import uuid7
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import Ticket, TicketEvent

DIMENSIONS = ("contact", "property", "unit")
Dimension = Literal["contact", "property", "unit"]
# apply: store rows and take sure hits into empty fields (ingest, ticket creation and change,
# after a decision); ask: store rows, sure hits stay questions (first decision on a record
# never reviewed); preview: write nothing (GET endpoints, review 1.36.0).
Mode = Literal["apply", "ask", "preview"]
PRESET_REASON = "Bereits zugeordnet"
SUPERSEDED_REASON = "Inzwischen anders zugeordnet"
SUPERSEDED_DETAIL = (
    "Die Zuordnung wurde inzwischen anders gesetzt. Die Rückfrage ist überholt, bitte neu laden."
)
CANDIDATE_CHANGED_DETAIL = (
    "Der bestätigte Kandidat gehört nicht zu den aktuellen Vorschlägen. Die Rückfrage ist "
    "überholt, bitte neu laden."
)
CANDIDATE_REQUIRED_DETAIL = "Bei Ja ist der bestätigte Kandidat (candidate_id) anzugeben."
ENTITY_FIELDS: dict[str, dict[str, str]] = {
    "message": {"contact": "contact_id", "property": "property_id"},
    "ticket": {"contact": "contact_id", "property": "property_id", "unit": "unit_id"},
}


class AssignmentReview(IdMixin, TimestampMixin, TenantMixin, Base):
    """Eine Zeile je Vorgang (Mail oder Ticket) und Dimension. ``status``: ``auto`` (sicher,
    automatisch übernommen), ``open`` (Rückfrage), ``accepted``/``rejected`` (entschieden),
    ``none`` (kein Treffer), ``preset`` (war bereits zugeordnet), ``superseded`` (offene
    Rückfrage, deren Feld inzwischen auf anderem Weg gesetzt wurde). Review 1.36.0: ``basis_id``
    is the field value the row was computed against (the value a viewer of the question saw;
    None for a question on an empty field), set by the check only and never by a decision.
    ``chosen_id`` is the value the row stands for: the decision (Ja: the candidate, Nein: the
    value kept), or the value already set for ``auto`` and ``preset``. A decision needs the field
    to still hold ``basis_id``; a Ja is final, see ``decide``."""

    __tablename__ = "assignment_review"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id", "dimension", name="uq_assignment_review_entity_dimension"
        ),
        Index("ix_assignment_review_tenant_status", "tenant_id", "status"),
    )

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # message, ticket
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    chosen_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    basis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(16))  # accept, reject, manual
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Auswertung ----------------------------------------------------------------------------------


def _preview_id(entity_type: str, entity_id: uuid.UUID, dimension: str) -> uuid.UUID:
    """Stable id of a row computed by a read only GET and not stored (review 1.36.0)."""
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"mhvp:assignment-review:{entity_type}:{entity_id}:{dimension}"
    )


async def _get_review(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID, dimension: str
) -> AssignmentReview | None:
    row: AssignmentReview | None = await session.scalar(
        select(AssignmentReview).where(
            AssignmentReview.entity_type == entity_type,
            AssignmentReview.entity_id == entity_id,
            AssignmentReview.dimension == dimension,
        )
    )
    return row


def _text_of(entity: Message | Ticket) -> str:
    if isinstance(entity, Message):
        return f"{entity.subject or ''}\n{entity.body or ''}"
    return "\n".join(
        p for p in (entity.title, entity.public_description, entity.internal_description) if p
    )


def _name_text_of(entity: Message | Ticket) -> str | None:
    """Sender names of a message come from its text without quoted earlier mails, so a quoted
    own signature names no contact; the ticket description is already without them
    (``mail.strip_quoted``). Review 1.36.0."""
    if not isinstance(entity, Message):
        return None
    return f"{entity.subject or ''}\n{assignment.without_quoted(entity.body or '')}"


def _ai_hints(entity: Message | Ticket) -> tuple[str | None, str | None]:
    if not isinstance(entity, Message):
        return None, None
    suggestion = entity.suggestion or {}
    name = suggestion.get("contact_name")
    number = suggestion.get("property_number")
    return (str(name) if name else None, str(number) if number else None)


async def evaluate(
    session: AsyncSession,
    entity_type: str,
    entity: Message | Ticket,
    *,
    actor_user_id: uuid.UUID | None,
    from_address: str | None = None,
    mode: Mode = "apply",
) -> list[AssignmentReview]:
    """Checks every dimension, takes sure hits into empty fields and writes or updates the
    review rows. Decided dimensions are not checked again; a field already set counts as
    ``preset``, as ``auto`` only when the rules are sure about exactly that value, and a stored
    open question whose field was set in another way since as ``superseded``; rows without a
    question (``none``, ``auto``, ``preset``) follow the current value. ``mode`` see ``Mode``;
    every stored ``auto``, also a confirmed pre-filled value, writes the domain event
    ``assignment_review.auto`` once (review 1.36.0). In preview mode a pre-filled value is
    only a ``preset``, nothing is stored and no event exists."""
    text = _text_of(entity)
    ai_name, ai_number = _ai_hints(entity)
    fields = ENTITY_FIELDS[entity_type]
    out: list[AssignmentReview] = []

    contact_id = getattr(entity, "contact_id", None)
    property_id = getattr(entity, "property_id", None)
    unit_id = getattr(entity, "unit_id", None) if "unit" in fields else None
    results: dict[str, assignment.DimensionResult] = {}

    # Sure chain (operator 27.09.2026, A-068 Nachtrag 1.37.0): the existing, previously stored
    # decision on the contact dimension is looked up before the loop below rewrites it, so a
    # contact confirmed by an earlier Ja (or a stored auto match) also feeds the chain, not only
    # a contact just found sure in this call.
    existing_contact_review = await _get_review(session, entity_type, entity.id, "contact")

    results["contact"] = await assignment.evaluate_contact(
        session,
        entity.tenant_id,
        from_address=from_address or getattr(entity, "from_address", None),
        text=text,
        ai_contact_name=ai_name,
        name_text=_name_text_of(entity),
    )
    if contact_id is None and results["contact"].status == "sure":
        contact_id = results["contact"].best.id if results["contact"].best else None
    contact_confirmed = contact_id is not None and (
        results["contact"].status == "sure"
        or (
            existing_contact_review is not None
            and existing_contact_review.status in ("accepted", "auto")
            and existing_contact_review.chosen_id == contact_id
        )
    )
    chain: tuple[assignment.Candidate, assignment.Candidate] | None = None
    if contact_confirmed:
        chain = await assignment.contact_sure_chain(session, entity.tenant_id, contact_id)  # type: ignore[arg-type]

    results["property"] = await assignment.evaluate_property(
        session,
        entity.tenant_id,
        text=text,
        contact_id=contact_id,
        ai_property_number=ai_number,
    )
    if chain is not None and (property_id is None or property_id == chain[0].id):
        # Rule 1: exactly one active tenancy contract or exactly one active ownership unit of a
        # sure contact assigns its unit and property automatically, only into an empty field; a
        # field already holding exactly that value (e.g. inherited by a ticket from the mail it
        # was created from) is reconfirmed as sure so it reads "auto", not a weaker "preset".
        results["property"] = assignment.DimensionResult("sure", [chain[0]])
        property_id = chain[0].id
    elif property_id is None and results["property"].status == "sure":
        property_id = results["property"].best.id if results["property"].best else None
    if "unit" in fields:
        results["unit"] = await assignment.evaluate_unit(
            session,
            entity.tenant_id,
            text=text,
            contact_id=contact_id,
            property_id=property_id,
        )
        unit_matches_chain = chain is not None and unit_id in (None, chain[1].id)
        if chain is not None and chain[0].id == property_id and unit_matches_chain:
            results["unit"] = assignment.DimensionResult("sure", [chain[1]])

    applied: list[tuple[AssignmentReview, bool]] = []  # (row, value was pre-filled)
    for dimension, result in results.items():
        field = fields.get(dimension)
        if field is None:
            continue
        review = await _get_review(session, entity_type, entity.id, dimension)
        if review is not None and (review.decision is not None or mode == "preview"):
            out.append(review)  # stored rows stay untouched in preview mode
            continue
        stored = review is not None
        if review is None:
            review = AssignmentReview(
                id=(
                    _preview_id(entity_type, entity.id, dimension) if mode == "preview" else uuid7()
                ),
                tenant_id=entity.tenant_id,
                created_by=actor_user_id,
                entity_type=entity_type,
                entity_id=entity.id,
                dimension=dimension,
            )
            if mode != "preview":
                session.add(review)
        current = getattr(entity, field)
        best = result.best
        review.candidates = [c.as_dict() for c in result.candidates]
        if stored and review.status in ("open", "superseded") and current != review.basis_id:
            # An open question whose field was set in another way since (thread, TNR, call
            # assistant, manual change) is overtaken; ``basis_id`` keeps the value it was
            # computed against, so a decision from an older view ends in a conflict. Rows
            # without a question follow the current value below (review 1.36.0).
            review.status = "superseded"
            review.reason = SUPERSEDED_REASON
        elif current is not None:
            # Already set (sender address at ingest, thread, manual choice): "auto" only when
            # the rules are sure about exactly this value, otherwise a preset (review 1.36.0).
            confirmed = (
                mode != "preview"
                and result.status == "sure"
                and best is not None
                and best.id == current
            )
            logged = stored and review.status == "auto" and review.chosen_id == current
            review.status = "auto" if confirmed else "preset"
            review.chosen_id = review.basis_id = current
            review.reason = "; ".join(best.reasons) if confirmed and best else PRESET_REASON
            if confirmed and not logged:
                applied.append((review, True))
        elif result.status == "sure" and best is not None and mode == "apply":
            setattr(entity, field, best.id)
            review.status = "auto"
            review.chosen_id = review.basis_id = best.id
            review.reason = "; ".join(best.reasons)
            applied.append((review, False))
        elif result.status in ("sure", "unsure"):
            review.status = "open"
            review.chosen_id = review.basis_id = None
            review.reason = None
        else:
            review.status = "none"
            review.chosen_id = review.basis_id = None
            review.reason = None
        out.append(review)
    if mode == "preview":
        return out
    await session.flush()
    for review, prefilled in applied:
        await _record_auto(session, entity, review, actor_user_id, prefilled=prefilled)
    for review in out:
        # An UPDATE expires the server side ``updated_at``; load it here, a lazy load in
        # ``review_out`` fails under asyncio (MissingGreenlet).
        if "updated_at" in inspect(review).expired_attributes:
            await session.refresh(review, ["updated_at"])
    return out


async def _record_auto(
    session: AsyncSession,
    entity: Message | Ticket,
    review: AssignmentReview,
    actor_user_id: uuid.UUID | None,
    *,
    prefilled: bool,
) -> None:
    """Domain event (and ticket history entry) for an automatic assignment; ``prefilled``: the
    value was set before the check (sender address at ingest, copied from the mail) and the
    rules confirm it (review 1.36.0)."""
    data = {
        "dimension": review.dimension,
        "decision": "auto",
        "chosen_id": str(review.chosen_id) if review.chosen_id else None,
        "reason": review.reason,
        "prefilled": prefilled,
    }
    await emit(
        session,
        tenant_id=entity.tenant_id,
        type="assignment_review.auto",
        entity_type=review.entity_type,
        entity_id=entity.id,
        actor_user_id=actor_user_id,
        payload=data | {"candidates": review.candidates},
    )
    if isinstance(entity, Ticket):
        session.add(
            TicketEvent(
                tenant_id=entity.tenant_id,
                ticket_id=entity.id,
                kind="assignment_review",
                user_id=actor_user_id,
                data=data,
            )
        )


async def review_message(
    session: AsyncSession,
    message: Message,
    actor_user_id: uuid.UUID | None,
    *,
    mode: Mode = "apply",
) -> list[AssignmentReview]:
    reviews = await evaluate(session, "message", message, actor_user_id=actor_user_id, mode=mode)
    if mode == "apply" and message.contact_id is not None and message.status == "new":
        message.status = "assigned"
    return reviews


async def review_ticket(
    session: AsyncSession,
    ticket: Ticket,
    actor_user_id: uuid.UUID | None,
    *,
    from_address: str | None = None,
    mode: Mode = "apply",
) -> list[AssignmentReview]:
    """``from_address``: sender of the mail the ticket comes from; the ticket check at mail
    intake passes it because the message is linked to the ticket only afterwards (review
    1.36.0). Without it the first inbound message of an email ticket is used."""
    if from_address is None and ticket.source is not None and ticket.source.value == "email":
        from_address = await session.scalar(
            select(Message.from_address)
            .where(Message.ticket_id == ticket.id, Message.direction == "in")
            .order_by(Message.created_at)
            .limit(1)
        )
    return await evaluate(
        session,
        "ticket",
        ticket,
        actor_user_id=actor_user_id,
        from_address=from_address,
        mode=mode,
    )


# Entscheidung --------------------------------------------------------------------------------


async def _load_entity(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> Message | Ticket:
    # populate_existing: the locked read must see a value another request set meanwhile.
    row: Message | Ticket | None
    if entity_type == "message":
        row = await session.get(Message, entity_id, with_for_update=True, populate_existing=True)
    else:
        row = await session.get(Ticket, entity_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _assert_candidate_exists(
    session: AsyncSession, dimension: str, candidate_id: uuid.UUID
) -> str:
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import Property, Unit

    model: Any = {"contact": Contact, "property": Property, "unit": Unit}[dimension]
    row = await session.get(model, candidate_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kandidat nicht gefunden.")
    if dimension == "contact":
        return str(row.display_name)
    if dimension == "property":
        return f"{row.number} {row.name}"
    return f"Einheit {row.number}"


async def _record_example(
    session: AsyncSession,
    review: AssignmentReview,
    *,
    entity: Message | Ticket,
    decision: str,
    candidate_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Lernbeispiel nur bei eingeschaltetem Mandantenschalter (ADR 0010). Aufgabe
    ``classify_email`` mit Kennzeichen ``kind = assignment_review``; die Merkmale enthalten
    die Absenderadresse und den Betreff, nicht den Volltext."""
    from mhvp.ai.examples import learning_examples_enabled
    from mhvp.ai.models import AiExample, AiTask

    if not await learning_examples_enabled(session, review.tenant_id):
        return
    features: dict[str, Any] = {
        "kind": "assignment_review",
        "entity_type": review.entity_type,
        "entity_id": str(review.entity_id),
        "dimension": review.dimension,
        "from_address": getattr(entity, "from_address", None),
        "subject": getattr(entity, "subject", None) or getattr(entity, "title", None),
        "candidates": review.candidates,
    }
    session.add(
        AiExample(
            tenant_id=review.tenant_id,
            created_by=actor_user_id,
            task=AiTask.CLASSIFY_EMAIL,
            features=features,
            result={
                "decision": decision,
                "chosen_id": str(candidate_id) if candidate_id else None,
            },
        )
    )


async def decide(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    dimension: str,
    decision: str,
    candidate_id: uuid.UUID | None,
    seen_value: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> list[AssignmentReview]:
    """Ja übernimmt den Kandidaten (aus der Liste oder nach Nein manuell gewählt), Nein
    verwirft die Vorschläge; danach werden die nachgelagerten, noch unentschiedenen Dimensionen
    erneut geprüft. Die Entscheidung bleibt am Datensatz und als Ereignis nachvollziehbar.

    Review 1.36.0, optimistic about what the member saw: ``seen_value`` is the field value shown
    with the question (None for an empty field) and a Ja names the confirmed candidate, there is
    no fallback to the first proposal. The API answers 409 (``ASSIGNMENT_CHANGED``) and writes
    nothing when the field no longer holds ``seen_value`` or ``basis_id`` (the value the row was
    computed against), when the row is already accepted (a Ja is final), or when the candidate
    of a Ja is not among the current candidates; only after a Nein (row ``rejected``) a Ja may
    name any record (manual choice). The same Ja again on an accepted row whose field still
    holds that candidate changes nothing and answers 200. A Ja on a preset or an automatic value
    corrects it; later changes are made on the record itself (PATCH)."""
    if dimension not in ENTITY_FIELDS[entity_type]:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Dimension {dimension} für {entity_type} unbekannt."
        )
    if decision == "accept" and candidate_id is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail=CANDIDATE_REQUIRED_DETAIL)
    entity = await _load_entity(session, entity_type, entity_id)
    review = await _get_review(session, entity_type, entity_id, dimension)
    if review is None and (isinstance(entity, Ticket) or entity.direction == "in"):
        # Never stored (record from before the review, GET only previews): store the review
        # now, sure hits as questions only, so the decision refers to the proposal shown.
        if isinstance(entity, Message):
            await review_message(session, entity, actor_user_id, mode="ask")
        else:
            await review_ticket(session, entity, actor_user_id, mode="ask")
        review = await _get_review(session, entity_type, entity_id, dimension)
    field = ENTITY_FIELDS[entity_type][dimension]
    current = getattr(entity, field)
    if review is None:
        review = AssignmentReview(
            tenant_id=entity.tenant_id,
            created_by=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            dimension=dimension,
            status="none",
            candidates=[],
            basis_id=current,
        )
        session.add(review)
    proposed = review.candidates[0]["id"] if review.candidates else None
    chosen = candidate_id if decision == "accept" else None  # the candidate of a Ja
    label = ""
    if chosen is not None:
        label = await _assert_candidate_exists(session, dimension, chosen)
    if review.status == "accepted" and chosen is not None and chosen == review.chosen_id == current:
        # The same Ja again (a repeated request, or another member with the same answer) changes
        # nothing and overwrites nothing, whatever the older view showed (review 1.36.0).
        return await reviews_for(session, entity_type, entity_id)
    if current != seen_value or current != review.basis_id or review.status == "accepted":
        # The member decided on an outdated view (review 1.36.0): the field was set in another
        # way since the question was shown (another member, thread, TNR, call assistant, manual
        # change), or since the row was computed; a Ja is final, a later decision never
        # overwrites it. Nothing is written. A row stored only now (read only preview until
        # here) was computed against the current value, so a wrong preset can be corrected.
        raise ProblemError(ErrorCodes.ASSIGNMENT_CHANGED, detail=SUPERSEDED_DETAIL)
    in_list = chosen is not None and any(c["id"] == str(chosen) for c in review.candidates)
    if chosen is not None and not in_list and review.status != "rejected":
        # The question the member confirmed is no longer the current one (candidates computed
        # again since, for instance after a change of the text); a record outside the list is
        # a manual choice, offered only after Nein (review 1.36.0).
        raise ProblemError(ErrorCodes.ASSIGNMENT_CHANGED, detail=CANDIDATE_CHANGED_DETAIL)
    if chosen is not None:
        setattr(entity, field, chosen)
        review.status = "accepted"
        review.chosen_id = chosen
        review.decision = "accept" if in_list else "manual"
        review.reason = f"Bestätigt: {label}" if in_list else f"Manuell gewählt: {label}"
        if isinstance(entity, Message) and entity.status == "new":
            entity.status = "assigned"
    else:
        review.status = "rejected"
        review.chosen_id = review.basis_id  # the field keeps its value
        review.decision = "reject"
        review.reason = "Vorschlag verworfen"
    review.decided_by = actor_user_id
    review.decided_at = datetime.now(UTC)
    await session.flush()
    payload = {
        "dimension": dimension,
        "decision": review.decision,
        "proposed_id": proposed,
        "chosen_id": str(chosen) if chosen else None,
        "candidates": review.candidates,
    }
    await emit(
        session,
        tenant_id=entity.tenant_id,
        type="assignment_review.decided",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    if isinstance(entity, Ticket):
        session.add(
            TicketEvent(
                tenant_id=entity.tenant_id,
                ticket_id=entity.id,
                kind="assignment_review",
                user_id=actor_user_id,
                data=payload,
            )
        )
    await _record_example(
        session,
        review,
        entity=entity,
        decision=review.decision or decision,
        candidate_id=chosen,
        actor_user_id=actor_user_id,
    )
    # Nachgelagerte Dimensionen erneut prüfen (Objekt und Einheit folgen dem Kontakt).
    if entity_type == "message":
        return await review_message(session, entity, actor_user_id)  # type: ignore[arg-type]
    return await review_ticket(session, entity, actor_user_id)  # type: ignore[arg-type]


def review_out(row: AssignmentReview, entity: Message | Ticket | None = None) -> dict[str, Any]:
    """With ``entity``, a question or decision whose field was set meanwhile in another way
    (thread, TNR, call assistant, manual change) is shown as ``superseded`` with the value set
    now; a row without a question (``none``, ``auto``, ``preset``) follows that value as
    ``preset``, as the next check would store it (review 1.36.0)."""
    status, chosen_id, reason = row.status, row.chosen_id, row.reason
    if entity is not None:
        current = getattr(entity, ENTITY_FIELDS[row.entity_type][row.dimension], None)
        if current is not None and current != chosen_id:
            if row.decision is None and row.status in ("none", "auto", "preset"):
                status, chosen_id, reason = "preset", current, PRESET_REASON
            else:
                status, chosen_id, reason = "superseded", current, SUPERSEDED_REASON
    return {
        "id": str(row.id),
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "dimension": row.dimension,
        "status": status,
        "candidates": row.candidates,
        "chosen_id": str(chosen_id) if chosen_id else None,
        "reason": reason,
        "decision": row.decision,
        "decided_by": str(row.decided_by) if row.decided_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def reviews_for(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[AssignmentReview]:
    rows = await session.scalars(
        select(AssignmentReview).where(
            AssignmentReview.entity_type == entity_type, AssignmentReview.entity_id == entity_id
        )
    )
    order = {d: i for i, d in enumerate(DIMENSIONS)}
    return sorted(rows.all(), key=lambda r: order.get(r.dimension, 9))


async def open_reviews(
    session: AsyncSession, entity_type: str, *, limit: int, principal: TenantPrincipal
) -> list[AssignmentReview]:
    """Open questions whose field is still empty (or unchanged). Mail rows follow the mailbox
    visibility of the mail list (review 1.36.0): members see messages without mailbox, of
    the default mailboxes and of mailboxes shared with them, administrators every message."""
    model: Any = Message if entity_type == "message" else Ticket
    unchanged = or_(
        *(
            (AssignmentReview.dimension == dimension)
            & getattr(model, field).is_not_distinct_from(AssignmentReview.basis_id)
            for dimension, field in ENTITY_FIELDS[entity_type].items()
        )
    )
    query = (
        select(AssignmentReview)
        .join(model, model.id == AssignmentReview.entity_id)
        .where(
            AssignmentReview.entity_type == entity_type,
            AssignmentReview.status == "open",
            unchanged,
        )
    )
    if entity_type == "message" and not principal.has("tenant_settings:update"):
        granted = select(MailboxUser.mailbox_id).where(MailboxUser.user_id == principal.user_id)
        allowed = select(Mailbox.id).where(
            or_(Mailbox.is_default.is_(True), Mailbox.id.in_(granted))
        )
        query = query.where(or_(Message.mailbox_id.is_(None), Message.mailbox_id.in_(allowed)))
    rows = await session.scalars(query.order_by(AssignmentReview.created_at.desc()).limit(limit))
    return list(rows.all())


async def current_reviews(
    session: AsyncSession, entity_type: str, entity: Message | Ticket
) -> list[dict[str, Any]]:
    """Read only view for the GET endpoints (review 1.36.0): stored rows, and for a record
    never reviewed (from before the review, or a duplicate copy) the rules computed on the
    fly without storing anything; sure hits appear as questions, nothing is assigned."""
    reviews = await reviews_for(session, entity_type, entity.id)
    missing = set(ENTITY_FIELDS[entity_type]) - {r.dimension for r in reviews}
    if missing and isinstance(entity, Message) and entity.direction == "in":
        reviews = await review_message(session, entity, None, mode="preview")
    elif missing and isinstance(entity, Ticket):
        reviews = await review_ticket(session, entity, None, mode="preview")
    order = {d: i for i, d in enumerate(DIMENSIONS)}
    return [review_out(r, entity) for r in sorted(reviews, key=lambda r: order.get(r.dimension, 9))]


# API -----------------------------------------------------------------------------------------

router = APIRouter(tags=["Zuordnungsprüfung"])
MAIL_READ = require_permission("communication:read")
MAIL_UPDATE = require_permission("communication:update")
TICKET_READ = require_permission("tickets:read")
TICKET_UPDATE = require_permission("tickets:update")


class AssignmentDecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: Dimension
    decision: Literal["accept", "reject"]
    candidate_id: uuid.UUID | None = Field(
        default=None,
        description="Bei accept Pflicht: der bestätigte Kandidat aus der aktuellen Liste, nach "
        "Nein auch ein manuell gewählter Datensatz. Kein Rückgriff auf den ersten Vorschlag; "
        "steht der Kandidat nicht mehr in der Liste, antwortet die API mit 409.",
    )
    seen_value: uuid.UUID | None = Field(
        description="Feldwert, den das Mitglied mit der Rückfrage gesehen hat (null bei leerem "
        "Feld). Weicht der aktuelle Wert ab, antwortet die API mit 409 und speichert nichts.",
    )


async def _decide(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    body: AssignmentDecideIn,
    principal: TenantPrincipal,
) -> list[AssignmentReview]:
    return await decide(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        dimension=body.dimension,
        decision=body.decision,
        candidate_id=body.candidate_id,
        seen_value=body.seen_value,
        actor_user_id=principal.user_id,
    )


async def _message_checked(
    session: AsyncSession, message_id: uuid.UUID, principal: TenantPrincipal
) -> Message:
    from mhvp.communication.routers import assert_message_accessible

    row = await session.get(Message, message_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await assert_message_accessible(session, principal, row)
    return row


@router.get("/mail/assignment-reviews/open", summary="Offene Rückfragen zur Zuordnung (Mail)")
async def open_mail_reviews(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(MAIL_READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await open_reviews(session, "message", limit=limit, principal=principal)
        return [review_out(r) for r in rows]


@router.get(
    "/mail/messages/{message_id}/assignment-review",
    summary="Zuordnungsprüfung einer Mail (Kontakt, Objekt)",
)
async def get_message_review(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MAIL_READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        row = await _message_checked(session, message_id, principal)
        return await current_reviews(session, "message", row)


@router.post(
    "/mail/messages/{message_id}/assignment-review/decide",
    summary="Rückfrage zur Zuordnung beantworten (Mail)",
)
async def decide_message_review(
    message_id: uuid.UUID,
    body: AssignmentDecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(MAIL_UPDATE),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        message = await _message_checked(session, message_id, principal)
        reviews = await _decide(session, "message", message_id, body, principal)
        return [review_out(r, message) for r in reviews]


@router.get("/tickets/assignment-reviews/open", summary="Offene Rückfragen zur Zuordnung (Tickets)")
async def open_ticket_reviews(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(TICKET_READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await open_reviews(session, "ticket", limit=limit, principal=principal)
        return [review_out(r) for r in rows]


@router.get(
    "/tickets/{ticket_id}/assignment-review",
    summary="Zuordnungsprüfung eines Tickets (Kontakt, Objekt, Einheit)",
)
async def get_ticket_review(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(TICKET_READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await current_reviews(session, "ticket", ticket)


@router.post(
    "/tickets/{ticket_id}/assignment-review/decide",
    summary="Rückfrage zur Zuordnung beantworten (Ticket)",
)
async def decide_ticket_review(
    ticket_id: uuid.UUID,
    body: AssignmentDecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKET_UPDATE),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        reviews = await _decide(session, "ticket", ticket_id, body, principal)
        ticket = await session.get(Ticket, ticket_id)  # locked in ``decide``, no new query
        return [review_out(r, ticket) for r in reviews]
