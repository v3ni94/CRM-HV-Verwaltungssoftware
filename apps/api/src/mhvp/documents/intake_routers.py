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
from mhvp.documents import intake, intake_followup
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
    unit_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
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
        document_ids = {row.context_id for row in rows if row.context_id}
        documents = {
            d.id: d
            for d in (
                await session.scalars(select(Document).where(Document.id.in_(document_ids)))
            ).all()
        }
        data = [
            _out(row, documents.get(row.context_id) if row.context_id else None) for row in rows
        ]
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
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise svc.invalid(f"Vorschlagswert für {name} ist keine gültige Kennung.") from None


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
            for name in ("property_id", "contact_id", "category_id", "unit_id", "contract_id")
        }
        if not any(chosen.values()):
            raise svc.invalid("Ohne Objekt, Kontakt oder Kategorie gibt es nichts zu übernehmen.")
        final: dict[str, Any] = {}
        for entity_type, key in (
            ("property", "property_id"),
            ("contact", "contact_id"),
            ("unit", "unit_id"),
            ("contract", "contract_id"),
        ):
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
            for k in ("property_id", "contact_id", "category_id", "unit_id", "contract_id")
        )
        proposal.decision = Decision.ACCEPTED if unchanged else Decision.MODIFIED
        proposal.decided_by = principal.user_id
        proposal.decided_at = datetime.now(UTC)
        # S12-01: ai_proposal.decided (decision of a person, never of the AI).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ai_proposal.decided",
            entity_type="ai_proposal",
            entity_id=proposal.id,
            actor_user_id=principal.user_id,
            payload={"decision": proposal.decision.value},
        )
        category = (
            await session.get(DocumentCategory, document.category_id)
            if document.category_id
            else None
        )
        text, _status = intake.document_text(document)
        final["followups"] = await intake_followup.suggest(
            session,
            document,
            category_name=category.name if category is not None else None,
            text=text,
            final=final,
        )
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


class IntakeFollowupConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_id: uuid.UUID | None = Field(
        default=None, description="Ticket oder Vertrag, falls der Vorschlag keines nennt"
    )


@router.post(
    "/documents/intake-proposals/{proposal_id}/followups/{kind}/confirm",
    summary="Folgevorschlag bestätigen (nur Verknüpfung, keine Buchung)",
)
async def confirm_intake_followup(
    proposal_id: uuid.UUID,
    kind: str,
    request: Request,
    body: IntakeFollowupConfirmIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> IntakeProposalOut:
    """Second human step after the filing (11.4). Ticket and contract file become a document
    link; invoice and meeting are only marked as handed over, the receipt and meeting
    workflows (with their own approvals) take it from there."""
    body = body or IntakeFollowupConfirmIn()
    async with tenant_tx(request, principal) as session:
        proposal = await session.get(AiProposal, proposal_id)
        if (
            proposal is None
            or proposal.entity_type != intake.ENTITY_TYPE
            or proposal.decision not in (Decision.ACCEPTED, Decision.MODIFIED)
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vorschlag nicht gefunden.")
        document = await session.get(Document, proposal.context_id) if proposal.context_id else None
        final = dict(proposal.final or {})
        followups = [dict(f) for f in final.get("followups", [])]
        item = next((f for f in followups if f.get("kind") == kind), None)
        if document is None or item is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Folgevorschlag nicht gefunden."
            )
        if item.get("status") != "proposed":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Folgevorschlag ist bereits erledigt."
            )
        entity_type = intake_followup.LINKABLE_KINDS.get(kind)
        if entity_type is not None:
            raw = body.target_id or (
                uuid.UUID(item["target_id"]) if item.get("target_id") else None
            )
            if raw is None:
                raise svc.invalid("Für diesen Folgevorschlag ist ein Ziel anzugeben.")
            await svc.check_link_target(session, entity_type, raw)
            exists = await session.scalar(
                select(DocumentLink.id).where(
                    DocumentLink.document_id == document.id,
                    DocumentLink.entity_type == entity_type,
                    DocumentLink.entity_id == raw,
                    DocumentLink.role == LinkRole.ATTACHMENT,
                )
            )
            if exists is None:
                session.add(
                    DocumentLink(
                        tenant_id=principal.tenant_id,
                        document_id=document.id,
                        entity_type=entity_type,
                        entity_id=raw,
                        role=LinkRole.ATTACHMENT,
                    )
                )
            item["target_id"] = str(raw)
        item["status"] = "confirmed"
        proposal.final = {**final, "followups": followups}
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.intake_followup_confirmed",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"proposal_id": str(proposal.id), "kind": kind},
        )
        return _out(proposal, document)


@router.post(
    "/documents/intake-proposals/{proposal_id}/revert-auto",
    summary="Automatische Ablage zurücknehmen",
)
async def revert_auto_filed(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> IntakeProposalOut:
    """GA10-03: undo a direct filing; the link is removed (unless it existed before) and the
    proposal returns to the review list."""
    async with tenant_tx(request, principal) as session:
        proposal = await session.get(AiProposal, proposal_id)
        if proposal is None or proposal.entity_type != intake.ENTITY_TYPE:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vorschlag nicht gefunden.")
        final = proposal.final or {}
        if not final.get("auto_filed"):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Vorschlag wurde nicht automatisch abgelegt."
            )
        document = await session.get(Document, proposal.context_id) if proposal.context_id else None
        if document is not None and not final.get("link_preexisted"):
            link = await session.scalar(
                select(DocumentLink).where(
                    DocumentLink.document_id == document.id,
                    DocumentLink.entity_type == "property",
                    DocumentLink.entity_id == uuid.UUID(final["property_id"]),
                    DocumentLink.role == LinkRole.ATTACHMENT,
                )
            )
            if link is not None:
                await session.delete(link)
        proposal.decision = Decision.PENDING
        proposal.decided_at = None
        proposal.final = None
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.intake_auto_file_reverted",
            entity_type="document",
            entity_id=proposal.context_id,
            actor_user_id=principal.user_id,
            payload={"proposal_id": str(proposal.id)},
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
        # S12-01: ai_proposal.decided (decision of a person, never of the AI).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ai_proposal.decided",
            entity_type="ai_proposal",
            entity_id=proposal.id,
            actor_user_id=principal.user_id,
            payload={"decision": proposal.decision.value},
        )
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
