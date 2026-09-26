"""Document inbox proposals (A42): list, accept, reject.

Accepting a proposal is the only place where the pipeline's result becomes a link or a category
(rule 0.1.6). Rejecting stores a structural learning example when a classification rule fired
(rule id, pattern type, source, mime type; no document content, M7-04) so the next run scores
that rule lower.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.ai.models import AiExample, AiProposal, AiTask, Decision
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import intake
from mhvp.documents import services as svc
from mhvp.documents.models import Document, DocumentCategory, DocumentLink, LinkRole

router = APIRouter(tags=["Dokumente"])
READ = require_permission("documents:read")
UPDATE = require_permission("documents:update")
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


class IntakeProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str | None
    source: str
    confidence: float
    proposed: dict[str, Any]
    decision: Decision
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    final: dict[str, Any] | None
    created_at: datetime


class IntakeProposalPage(BaseModel):
    data: list[IntakeProposalOut]
    meta: dict[str, int]


class IntakeAcceptIn(BaseModel):
    """Overrides for the proposed values; omitted fields take the proposal, ``null`` drops it."""

    model_config = ConfigDict(extra="forbid")

    property_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    use_proposed: bool = Field(
        default=True, description="false: nur die hier angegebenen Werte übernehmen"
    )


class IntakeRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


def _out(proposal: AiProposal, document: Document | None) -> IntakeProposalOut:
    proposed = proposal.proposed or {}
    return IntakeProposalOut(
        id=proposal.id,
        document_id=proposal.context_id or uuid.UUID(int=0),
        document_title=document.title if document is not None else None,
        source=str(proposed.get("source", "")),
        confidence=float(proposed.get("confidence", 0.0)),
        proposed=proposed,
        decision=proposal.decision,
        decided_by=proposal.decided_by,
        decided_at=proposal.decided_at,
        final=proposal.final,
        created_at=proposal.created_at,
    )


async def _pending(session: Any, proposal_id: uuid.UUID) -> AiProposal:
    row: AiProposal | None = await session.get(AiProposal, proposal_id)
    if row is None or row.entity_type != intake.ENTITY_TYPE:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vorschlag nicht gefunden.")
    if row.decision is not Decision.PENDING:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vorschlag ist bereits entschieden.")
    return row


@router.get("/documents/intake-proposals", summary="Vorschläge aus dem Dokumenteingang")
async def list_intake_proposals(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    decision: str = Query(
        default="pending", description="pending, accepted, modified, rejected, all"
    ),
    source: str | None = Query(default=None, max_length=32),
    page: Page = 1,
    page_size: PageSize = 50,
) -> IntakeProposalPage:
    async with tenant_tx(request, principal) as session:
        stmt = select(AiProposal).where(AiProposal.entity_type == intake.ENTITY_TYPE)
        if decision != "all":
            try:
                stmt = stmt.where(AiProposal.decision == Decision(decision))
            except ValueError:
                raise svc.invalid("Unbekannter Entscheidungsfilter.") from None
        if source:
            stmt = stmt.where(AiProposal.proposed["source"].astext == source)
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.scalars(
                stmt.order_by(AiProposal.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        data = []
        for row in rows:
            document = await session.get(Document, row.context_id) if row.context_id else None
            data.append(_out(row, document))
        return IntakeProposalPage(
            data=data, meta={"page": page, "per_page": page_size, "total": total}
        )


@router.get("/documents/intake-proposals/{proposal_id}", summary="Vorschlag lesen")
async def get_intake_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> IntakeProposalOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(AiProposal, proposal_id)
        if row is None or row.entity_type != intake.ENTITY_TYPE:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vorschlag nicht gefunden.")
        document = await session.get(Document, row.context_id) if row.context_id else None
        return _out(row, document)


def _pick(body: IntakeAcceptIn, name: str, proposed: dict[str, Any]) -> uuid.UUID | None:
    explicit: uuid.UUID | None = getattr(body, name)
    if explicit is not None:
        return explicit
    if name in body.model_fields_set or not body.use_proposed:
        return None
    value = proposed.get(name)
    return uuid.UUID(str(value)) if value else None


@router.post(
    "/documents/intake-proposals/{proposal_id}/accept",
    summary="Vorschlag bestätigen und Dokument zuordnen",
)
async def accept_intake_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: IntakeAcceptIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> IntakeProposalOut:
    body = body or IntakeAcceptIn()
    async with tenant_tx(request, principal) as session:
        proposal = await _pending(session, proposal_id)
        document = await session.get(Document, proposal.context_id) if proposal.context_id else None
        if document is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Das Dokument existiert nicht mehr."
            )
        proposed = proposal.proposed or {}
        chosen = {
            name: _pick(body, name, proposed)
            for name in ("property_id", "contact_id", "category_id")
        }
        if not any(chosen.values()):
            raise svc.invalid("Ohne Objekt, Kontakt oder Kategorie gibt es nichts zu übernehmen.")
        final: dict[str, Any] = {}
        for entity_type, key in (("property", "property_id"), ("contact", "contact_id")):
            entity_id = chosen[key]
            if entity_id is None:
                continue
            await svc.check_link_target(session, entity_type, entity_id)
            exists = await session.scalar(
                select(DocumentLink.id).where(
                    DocumentLink.document_id == document.id,
                    DocumentLink.entity_type == entity_type,
                    DocumentLink.entity_id == entity_id,
                    DocumentLink.role == LinkRole.ATTACHMENT,
                )
            )
            if exists is None:
                session.add(
                    DocumentLink(
                        tenant_id=principal.tenant_id,
                        document_id=document.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        role=LinkRole.ATTACHMENT,
                    )
                )
            final[key] = str(entity_id)
        if chosen["category_id"] is not None:
            if await session.get(DocumentCategory, chosen["category_id"]) is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kategorie fehlt.")
            document.category_id = chosen["category_id"]
            final["category_id"] = str(chosen["category_id"])
        unchanged = all(
            str(proposed.get(k) or "") == final.get(k, "")
            for k in ("property_id", "contact_id", "category_id")
        )
        proposal.decision = Decision.ACCEPTED if unchanged else Decision.MODIFIED
        proposal.decided_by = principal.user_id
        proposal.decided_at = datetime.now(UTC)
        proposal.final = final
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.intake_accepted",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"proposal_id": str(proposal.id), "decision": proposal.decision.value, **final},
        )
        return _out(proposal, document)


@router.post("/documents/intake-proposals/{proposal_id}/reject", summary="Vorschlag ablehnen")
async def reject_intake_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: IntakeRejectIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> IntakeProposalOut:
    body = body or IntakeRejectIn()
    async with tenant_tx(request, principal) as session:
        proposal = await _pending(session, proposal_id)
        document = await session.get(Document, proposal.context_id) if proposal.context_id else None
        proposed = proposal.proposed or {}
        proposal.decision = Decision.REJECTED
        proposal.decided_by = principal.user_id
        proposal.decided_at = datetime.now(UTC)
        proposal.final = {"reason": body.reason} if body.reason else None
        learned = False
        classification = proposed.get("classification") or {}
        if classification.get("rule_id"):
            # Structural features only (M7-04): which rule fired on which kind of file.
            session.add(
                AiExample(
                    tenant_id=principal.tenant_id,
                    task=AiTask.CLASSIFY_DOCUMENT,
                    features={
                        "rule_id": classification["rule_id"],
                        "pattern_type": classification.get("pattern_type"),
                        "source": proposed.get("source"),
                        "mime_type": document.mime_type if document is not None else None,
                        "decision": "rejected",
                    },
                    result={
                        "category_id": classification.get("category_id"),
                        "accepted": False,
                        "reason": body.reason,
                    },
                    proposal_id=proposal.id,
                )
            )
            learned = True
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.intake_rejected",
            entity_type="document",
            entity_id=proposal.context_id,
            actor_user_id=principal.user_id,
            payload={
                "proposal_id": str(proposal.id),
                "learned_example": learned,
                "reason": body.reason or "",
            },
        )
        return _out(proposal, document)
