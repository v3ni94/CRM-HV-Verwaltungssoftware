"""M35 Stufe 3 part 3, Review-Center (docs/plans/M35-objektakte-uebernahme.md section 4):
`/api/v1/objektakte/review`. List (filters status, property, priority, stage), get one case
with candidates and a document preview link, decide (accept a candidate, set the class
manually, reject, snooze) and bulk decide (several cases, one target class).

Every decision writes an `objektakte_document_review_decision` row with a before/after
snapshot and `decided_by` (audit, rule 0.1.7). Accepting or manually setting a class sets
`document.category_id` and `document.status`-equivalent (`source_meta["classification"]`) and,
per the task, moves the document to "filed"; this stage has no separate document status column
for "filed" beyond the existing `category_id`, so filing is recorded as
`source_meta["classification"]["status"] = "filed"` alongside the applied category (rule
0.1.7: the classification history in `source_meta["classification"]` is never silently dropped,
only superseded by the newer, human decided state).

Permissions: `documents:read` for list/get, `documents:update` for decide/bulk decide (existing
permission names, matches `mhvp.documents.routers`).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentLink
from mhvp.objektakte.models import (
    DocumentReviewCase,
    DocumentReviewDecision,
    ReviewCaseStatus,
)

router = APIRouter(prefix="/objektakte/review", tags=["objektakte-review"])
READ = require_permission("documents:read")
UPDATE = require_permission("documents:update")
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


def _case_dict(case: DocumentReviewCase, document: Document | None) -> dict[str, Any]:
    return {
        "id": str(case.id),
        "document_id": str(case.document_id) if case.document_id else None,
        "document_title": document.title if document else None,
        "document_preview_url": (f"/api/v1/documents/{document.id}/content" if document else None),
        "stage": case.stage,
        "candidates": case.candidates,
        "proposed_action": case.proposed_action,
        "priority": case.priority,
        "status": case.status.value,
        "snoozed_until": case.snoozed_until.isoformat() if case.snoozed_until else None,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


@router.get("", summary="Prüffälle auflisten")
async def list_cases(
    request: Request,
    status_: Literal["open", "in_progress", "resolved", "dismissed"] | None = Query(
        default=None, alias="status"
    ),
    property_id: uuid.UUID | None = Query(default=None),
    priority_min: int | None = Query(default=None),
    stage: str | None = Query(default=None),
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(DocumentReviewCase)
        if status_ is not None:
            stmt = stmt.where(DocumentReviewCase.status == ReviewCaseStatus(status_))
        if stage is not None:
            stmt = stmt.where(DocumentReviewCase.stage == stage)
        if priority_min is not None:
            stmt = stmt.where(DocumentReviewCase.priority >= priority_min)
        if property_id is not None:
            stmt = stmt.where(
                DocumentReviewCase.document_id.in_(
                    select(DocumentLink.document_id).where(
                        DocumentLink.entity_type == "property",
                        DocumentLink.entity_id == property_id,
                    )
                )
            )
        stmt = stmt.order_by(DocumentReviewCase.priority.desc(), DocumentReviewCase.created_at)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = list((await session.execute(stmt)).scalars().all())
        doc_ids = [r.document_id for r in rows if r.document_id]
        docs: dict[uuid.UUID, Document] = {}
        if doc_ids:
            doc_rows = (
                (await session.execute(select(Document).where(Document.id.in_(doc_ids))))
                .scalars()
                .all()
            )
            docs = {d.id: d for d in doc_rows}
        items = [_case_dict(r, docs.get(r.document_id) if r.document_id else None) for r in rows]
        return {"items": items, "page": page, "page_size": page_size}


@router.get("/{case_id}", summary="Prüffall abrufen")
async def get_case(
    request: Request, case_id: uuid.UUID, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(DocumentReviewCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        document = await session.get(Document, case.document_id) if case.document_id else None
        return _case_dict(case, document)


class DecisionIn(BaseModel):
    action: Literal["accept_candidate", "set_manually", "reject", "snooze"]
    candidate_index: int | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    document_type: str | None = None
    snoozed_until: datetime | None = None


class BulkDecisionIn(BaseModel):
    case_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    category_id: uuid.UUID
    document_type: str | None = None


def _candidate(case: DocumentReviewCase, index: int) -> dict[str, Any]:
    candidates = (case.candidates or {}).get("candidates") or []
    if index >= len(candidates):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Kandidat nicht vorhanden.")
    return candidates[index]  # type: ignore[no-any-return]


async def _apply_and_record(
    session: Any,
    principal: TenantPrincipal,
    case: DocumentReviewCase,
    *,
    action: str,
    category_id: uuid.UUID | None,
    document_type: str | None,
    snoozed_until: datetime | None = None,
) -> DocumentReviewDecision:
    before = {
        "status": case.status.value,
        "priority": case.priority,
        "snoozed_until": case.snoozed_until.isoformat() if case.snoozed_until else None,
    }
    document: Document | None = None
    if case.document_id:
        document = await session.get(Document, case.document_id)
    if action in ("accept_candidate", "set_manually"):
        if document is not None:
            document.category_id = category_id
            meta = dict(document.source_meta or {})
            meta["classification"] = {
                **(meta.get("classification") or {}),
                "stage": "review",
                "status": "filed",
                "category_id": str(category_id) if category_id else None,
                "document_type": document_type,
                "decided_by": str(principal.user_id) if principal.user_id else None,
                "decided_at": datetime.now(UTC).isoformat(),
            }
            document.source_meta = meta
        case.status = ReviewCaseStatus.RESOLVED
    elif action == "reject":
        case.status = ReviewCaseStatus.DISMISSED
    elif action == "snooze":
        case.status = ReviewCaseStatus.OPEN
        case.snoozed_until = snoozed_until
    after = {
        "status": case.status.value,
        "priority": case.priority,
        "snoozed_until": case.snoozed_until.isoformat() if case.snoozed_until else None,
        "applied_category_id": str(category_id) if category_id else None,
        "applied_document_type": document_type,
    }
    decision = DocumentReviewDecision(
        tenant_id=principal.tenant_id,
        review_case_id=case.id,
        decided_by=principal.user_id,
        before_state={"action": action, **before},
        after_state=after,
    )
    session.add(decision)
    await session.flush()
    # `case.updated_at` has an `onupdate` server default; after the flush above the ORM has
    # expired it (and the other server-computed columns), so a later plain attribute read
    # (e.g. building the response dict) would try an implicit lazy load outside the request's
    # greenlet and raise `MissingGreenlet`. Refresh explicitly while still inside the awaited
    # call.
    await session.refresh(case)
    return decision


@router.post("/{case_id}/decide", summary="Prüffall entscheiden")
async def decide_case(
    request: Request,
    case_id: uuid.UUID,
    body: DecisionIn,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(DocumentReviewCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        if case.status not in (ReviewCaseStatus.OPEN, ReviewCaseStatus.IN_PROGRESS):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Prüffall ist bereits abgeschlossen.")
        category_id = body.category_id
        document_type = body.document_type
        if body.action == "accept_candidate":
            if body.candidate_index is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="candidate_index fehlt für accept_candidate."
                )
            candidate = _candidate(case, body.candidate_index)
            cat = candidate.get("category_id")
            category_id = uuid.UUID(cat) if cat else None
            document_type = candidate.get("document_type")
        elif body.action == "set_manually" and category_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="category_id fehlt für set_manually.")
        elif body.action == "snooze" and body.snoozed_until is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="snoozed_until fehlt für snooze.")
        decision = await _apply_and_record(
            session,
            principal,
            case,
            action=body.action,
            category_id=category_id,
            document_type=document_type,
            snoozed_until=body.snoozed_until,
        )
        document = await session.get(Document, case.document_id) if case.document_id else None
        return {
            "case": _case_dict(case, document),
            "decision_id": str(decision.id),
        }


@router.post("/bulk-decide", summary="Mehrere Prüffälle mit derselben Klasse entscheiden")
async def bulk_decide(
    request: Request, body: BulkDecisionIn, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rows = (
            (
                await session.execute(
                    select(DocumentReviewCase).where(DocumentReviewCase.id.in_(body.case_ids))
                )
            )
            .scalars()
            .all()
        )
        found = {r.id for r in rows}
        missing = [str(i) for i in body.case_ids if i not in found]
        decided: list[str] = []
        skipped: list[dict[str, str]] = []
        for case in rows:
            if case.status not in (ReviewCaseStatus.OPEN, ReviewCaseStatus.IN_PROGRESS):
                skipped.append({"case_id": str(case.id), "reason": "already_decided"})
                continue
            await _apply_and_record(
                session,
                principal,
                case,
                action="set_manually",
                category_id=body.category_id,
                document_type=body.document_type,
            )
            decided.append(str(case.id))
        return {"decided": decided, "skipped": skipped, "missing": missing}
