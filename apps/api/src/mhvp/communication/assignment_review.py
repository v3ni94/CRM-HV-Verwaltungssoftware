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
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.communication import assignment
from mhvp.communication.models import Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import Ticket, TicketEvent

DIMENSIONS = ("contact", "property", "unit")
Dimension = Literal["contact", "property", "unit"]
ENTITY_FIELDS: dict[str, dict[str, str]] = {
    "message": {"contact": "contact_id", "property": "property_id"},
    "ticket": {"contact": "contact_id", "property": "property_id", "unit": "unit_id"},
}


class AssignmentReview(IdMixin, TimestampMixin, TenantMixin, Base):
    """Eine Zeile je Vorgang (Mail oder Ticket) und Dimension. ``status``: ``auto`` (sicher,
    automatisch übernommen), ``open`` (Rückfrage), ``accepted``/``rejected`` (entschieden),
    ``none`` (kein Treffer), ``preset`` (war bereits zugeordnet)."""

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
    reason: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(16))  # accept, reject, manual
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Auswertung ----------------------------------------------------------------------------------


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
) -> list[AssignmentReview]:
    """Prüft alle Dimensionen, übernimmt sichere Treffer in leere Felder und schreibt oder
    aktualisiert die Prüfzeilen. Entschiedene Dimensionen werden nicht erneut geprüft;
    bereits gesetzte Felder gelten als ``preset``."""
    text = _text_of(entity)
    ai_name, ai_number = _ai_hints(entity)
    fields = ENTITY_FIELDS[entity_type]
    out: list[AssignmentReview] = []

    contact_id = getattr(entity, "contact_id", None)
    property_id = getattr(entity, "property_id", None)
    results: dict[str, assignment.DimensionResult] = {}

    results["contact"] = await assignment.evaluate_contact(
        session,
        entity.tenant_id,
        from_address=from_address or getattr(entity, "from_address", None),
        text=text,
        ai_contact_name=ai_name,
    )
    if contact_id is None and results["contact"].status == "sure":
        contact_id = results["contact"].best.id if results["contact"].best else None
    results["property"] = await assignment.evaluate_property(
        session,
        entity.tenant_id,
        text=text,
        contact_id=contact_id,
        ai_property_number=ai_number,
    )
    if property_id is None and results["property"].status == "sure":
        property_id = results["property"].best.id if results["property"].best else None
    if "unit" in fields:
        results["unit"] = await assignment.evaluate_unit(
            session,
            entity.tenant_id,
            text=text,
            contact_id=contact_id,
            property_id=property_id,
        )

    for dimension, result in results.items():
        field = fields.get(dimension)
        if field is None:
            continue
        review = await _get_review(session, entity_type, entity.id, dimension)
        if review is not None and review.decision is not None:
            out.append(review)
            continue
        if review is None:
            review = AssignmentReview(
                tenant_id=entity.tenant_id,
                created_by=actor_user_id,
                entity_type=entity_type,
                entity_id=entity.id,
                dimension=dimension,
            )
            session.add(review)
        current = getattr(entity, field)
        review.candidates = [c.as_dict() for c in result.candidates]
        if current is not None:
            # Bereits gesetzt (z. B. Absenderadresse beim Eingang): bestätigt eine Regel den
            # Wert, gilt er als automatisch zugeordnet mit Begründung, sonst als Vorgabe.
            match = next((c for c in result.candidates if c.id == current), None)
            review.status = "auto" if match is not None else "preset"
            review.chosen_id = current
            review.reason = "; ".join(match.reasons) if match else "Bereits zugeordnet"
        elif result.status == "sure" and result.best is not None:
            setattr(entity, field, result.best.id)
            review.status = "auto"
            review.chosen_id = result.best.id
            review.reason = "; ".join(result.best.reasons)
        elif result.status == "unsure":
            review.status = "open"
            review.chosen_id = None
            review.reason = None
        else:
            review.status = "none"
            review.chosen_id = None
            review.reason = None
        out.append(review)
    await session.flush()
    return out


async def review_message(
    session: AsyncSession, message: Message, actor_user_id: uuid.UUID | None
) -> list[AssignmentReview]:
    reviews = await evaluate(session, "message", message, actor_user_id=actor_user_id)
    if message.contact_id is not None and message.status == "new":
        message.status = "assigned"
    return reviews


async def review_ticket(
    session: AsyncSession, ticket: Ticket, actor_user_id: uuid.UUID | None
) -> list[AssignmentReview]:
    from_address = None
    if ticket.source is not None and ticket.source.value == "email":
        from_address = await session.scalar(
            select(Message.from_address)
            .where(Message.ticket_id == ticket.id, Message.direction == "in")
            .order_by(Message.created_at)
            .limit(1)
        )
    return await evaluate(
        session, "ticket", ticket, actor_user_id=actor_user_id, from_address=from_address
    )


# Entscheidung --------------------------------------------------------------------------------


async def _load_entity(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> Message | Ticket:
    row: Message | Ticket | None
    if entity_type == "message":
        row = await session.get(Message, entity_id, with_for_update=True)
    else:
        row = await session.get(Ticket, entity_id, with_for_update=True)
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
    actor_user_id: uuid.UUID | None,
) -> list[AssignmentReview]:
    """Ja übernimmt den Kandidaten (aus der Liste oder manuell gewählt), Nein verwirft die
    Vorschläge; danach werden die nachgelagerten, noch unentschiedenen Dimensionen erneut
    geprüft. Die Entscheidung bleibt am Datensatz und als Ereignis nachvollziehbar."""
    if dimension not in ENTITY_FIELDS[entity_type]:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Dimension {dimension} für {entity_type} unbekannt."
        )
    entity = await _load_entity(session, entity_type, entity_id)
    review = await _get_review(session, entity_type, entity_id, dimension)
    if review is None:
        review = AssignmentReview(
            tenant_id=entity.tenant_id,
            created_by=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            dimension=dimension,
            status="none",
            candidates=[],
        )
        session.add(review)
    proposed = review.candidates[0]["id"] if review.candidates else None
    field = ENTITY_FIELDS[entity_type][dimension]
    if decision == "accept":
        if candidate_id is None:
            if proposed is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Kein Kandidat vorhanden.")
            candidate_id = uuid.UUID(proposed)
        label = await _assert_candidate_exists(session, dimension, candidate_id)
        in_list = any(c["id"] == str(candidate_id) for c in review.candidates)
        setattr(entity, field, candidate_id)
        review.status = "accepted"
        review.chosen_id = candidate_id
        review.decision = "accept" if in_list else "manual"
        review.reason = f"Bestätigt: {label}" if in_list else f"Manuell gewählt: {label}"
        if isinstance(entity, Message) and entity.status == "new":
            entity.status = "assigned"
    else:
        review.status = "rejected"
        review.chosen_id = None
        review.decision = "reject"
        review.reason = "Vorschlag verworfen"
    review.decided_by = actor_user_id
    review.decided_at = datetime.now(UTC)
    await session.flush()
    payload = {
        "dimension": dimension,
        "decision": review.decision,
        "proposed_id": proposed,
        "chosen_id": str(review.chosen_id) if review.chosen_id else None,
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
        candidate_id=review.chosen_id,
        actor_user_id=actor_user_id,
    )
    # Nachgelagerte Dimensionen erneut prüfen (Objekt und Einheit folgen dem Kontakt).
    if entity_type == "message":
        return await review_message(session, entity, actor_user_id)  # type: ignore[arg-type]
    return await review_ticket(session, entity, actor_user_id)  # type: ignore[arg-type]


def review_out(row: AssignmentReview) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "dimension": row.dimension,
        "status": row.status,
        "candidates": row.candidates,
        "chosen_id": str(row.chosen_id) if row.chosen_id else None,
        "reason": row.reason,
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
    session: AsyncSession, entity_type: str, *, limit: int
) -> list[AssignmentReview]:
    rows = await session.scalars(
        select(AssignmentReview)
        .where(AssignmentReview.entity_type == entity_type, AssignmentReview.status == "open")
        .order_by(AssignmentReview.created_at.desc())
        .limit(limit)
    )
    return list(rows.all())


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
        description="Kandidat (aus der Liste oder manuell gewählt); ohne Angabe bei accept "
        "der erste Vorschlag.",
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
        return [review_out(r) for r in await open_reviews(session, "message", limit=limit)]


@router.get(
    "/mail/messages/{message_id}/assignment-review",
    summary="Zuordnungsprüfung einer Mail (Kontakt, Objekt)",
)
async def get_message_review(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MAIL_READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        row = await _message_checked(session, message_id, principal)
        reviews = await reviews_for(session, "message", row.id)
        if not reviews and row.direction == "in":
            reviews = await review_message(session, row, principal.user_id)
        return [review_out(r) for r in reviews]


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
        await _message_checked(session, message_id, principal)
        reviews = await decide(
            session,
            entity_type="message",
            entity_id=message_id,
            dimension=body.dimension,
            decision=body.decision,
            candidate_id=body.candidate_id,
            actor_user_id=principal.user_id,
        )
        return [review_out(r) for r in reviews]


@router.get("/tickets/assignment-reviews/open", summary="Offene Rückfragen zur Zuordnung (Tickets)")
async def open_ticket_reviews(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(TICKET_READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return [review_out(r) for r in await open_reviews(session, "ticket", limit=limit)]


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
        reviews = await reviews_for(session, "ticket", ticket.id)
        if not reviews:
            reviews = await review_ticket(session, ticket, principal.user_id)
        return [review_out(r) for r in reviews]


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
        reviews = await decide(
            session,
            entity_type="ticket",
            entity_id=ticket_id,
            dimension=body.dimension,
            decision=body.decision,
            candidate_id=body.candidate_id,
            actor_user_id=principal.user_id,
        )
        return [review_out(r) for r in reviews]
