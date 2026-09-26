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

Permissions (M35 Stufe 4, docs/rules/M35-03.md): `objektakte:read` for list/get,
`objektakte:update` for decide/bulk decide/ask-ai. Until Stufe 4 these endpoints reused the
generic `documents:read`/`documents:update`; the objektakte keys separate review work from
plain document editing (mhvp.core.auth.permissions).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from mhvp.ai import gateway, jobs, tasks
from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink
from mhvp.objektakte.masking import mask_text
from mhvp.objektakte.models import (
    DocumentReviewCase,
    DocumentReviewDecision,
    ReviewCaseStatus,
)

router = APIRouter(prefix="/objektakte/review", tags=["objektakte-review"])
READ = require_permission("objektakte:read")
UPDATE = require_permission("objektakte:update")
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


@router.post("/{case_id}/ask-ai", summary="KI-Vorschlag anfordern (Stufe 3 von drei)")
async def ask_ai(
    request: Request, case_id: uuid.UUID, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """M35 Stufe 3 part 2: masked filename plus OCR text only (rule 0.1.13, no IBAN, e-mail,
    phone number or probable name ever leaves the CRM); the model's answer is written back as
    a proposal only, in `document.source_meta["classification"]` (`stage="ai"`) — never
    applied to `document.category_id` (rule 0.1.6). Only for an open case with a document."""
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        case = await session.get(DocumentReviewCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        if case.status not in (ReviewCaseStatus.OPEN, ReviewCaseStatus.IN_PROGRESS):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Prüffall ist bereits abgeschlossen.")
        if case.document_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Prüffall ohne Dokument kann nicht angefragt werden."
            )
        document = await session.get(Document, case.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        masked_filename = mask_text(document.filename)
        masked_body = mask_text(document.ocr_text)
        content = f"Dateiname: {masked_filename}\n\n{masked_body}".strip()
        prompt = tasks.prompt(AiTask.CLASSIFY_DOCUMENT)
        ref = {"instruction": content, "document_ids": [], "context": {}}
        run = AiTaskRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            task=AiTask.CLASSIFY_DOCUMENT,
            conversation_id=None,
            prompt_version=prompt.version,
            input_hash=gateway.input_hash(
                AiTask.CLASSIFY_DOCUMENT, prompt.version, content, {"case_id": str(case_id)}
            ),
            input_ref=ref,
            status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
    await jobs.run_and_propose(
        sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
    )
    async with tenant_tx(request, principal) as session:
        case = await session.get(DocumentReviewCase, case_id)
        run_row = await session.get(AiTaskRun, run_id)
        assert case is not None  # noqa: S101
        assert run_row is not None  # noqa: S101
        document = await session.get(Document, case.document_id) if case.document_id else None
        if run_row.status is RunStatus.SUCCEEDED and document is not None:
            output = run_row.output or {}
            meta = dict(document.source_meta or {})
            meta["classification"] = {
                **(meta.get("classification") or {}),
                "stage": "ai",
                "status": "proposal",
                "document_class": output.get("document_class"),
                "category": output.get("category"),
                "confidence": output.get("confidence"),
                "reasons": output.get("reasons"),
                "ai_task_run_id": str(run_row.id),
            }
            document.source_meta = meta
            case.candidates = {
                **(case.candidates or {}),
                "ai": {
                    "document_class": output.get("document_class"),
                    "category": output.get("category"),
                    "confidence": output.get("confidence"),
                    "reasons": output.get("reasons"),
                },
            }
            await session.flush()
            # See the note in `_apply_and_record`: `case.updated_at` (onupdate) is expired by
            # the flush above and must not be read implicitly outside this awaited call.
            await session.refresh(case)
        return {
            "run_status": run_row.status.value,
            "run_error": run_row.error,
            "case": _case_dict(case, document),
        }
