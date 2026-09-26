"""Belegeingang API (M14, `/api/v1/receipts`): start an extraction, list and read drafts,
confirm (creates the invoice as an open, unposted draft) or reject. Permissions:
``accounting:read`` for reads, ``accounting:create`` for everything that starts a run or
decides a draft, mirroring the invoice intake actions in `mhvp.accounting.routers`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from mhvp.ai import jobs
from mhvp.ai.models import Decision, ImportRun, ImportStatus
from mhvp.communication.models import Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentSource
from mhvp.receipts import extraction
from mhvp.receipts import schemas as s
from mhvp.receipts.masking import normalize_iban
from mhvp.receipts.models import ReceiptDraft, ReceiptDraftSource, ReceiptDraftStatus

router = APIRouter(prefix="/receipts", tags=["Belegeingang"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")

_STATUS_FILTER = "^(open|extracting|proposed|failed|confirmed|rejected)$"
_SUPPORTED_MIME = {"application/pdf", "image/png", "image/jpeg", "text/plain"}


async def _draft(session: Any, draft_id: uuid.UUID) -> ReceiptDraft:
    row: ReceiptDraft | None = await session.get(ReceiptDraft, draft_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Belegentwurf nicht gefunden.")
    return row


async def _out(session: Any, draft: ReceiptDraft) -> s.ReceiptDraftOut:
    """Flush and refresh first: ``updated_at`` (server side ``onupdate``) is expired after a
    flush and must not be lazy loaded from an async session."""
    await session.flush()
    await session.refresh(draft)
    data: dict[str, Any] = {
        name: getattr(draft, name)
        for name in s.ReceiptDraftOut.model_fields
        if name != "iban_candidates"
    }
    # The encrypted candidate list never leaves the API; only the masked view does.
    data["iban_candidates"] = [
        s.ReceiptIbanCandidateOut(**c) for c in extraction.masked_iban_candidates(draft)
    ]
    return s.ReceiptDraftOut(**data)


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type="receipt_draft",
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )


async def _dispatch(request: Request, principal: TenantPrincipal, run_id: uuid.UUID) -> None:
    """Same execution path as the assistant (inline in tests, Celery ``io`` queue otherwise)."""
    settings = request.app.state.settings
    if settings.ai_inline:
        await jobs.run_and_propose(
            sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
        )
        return
    from mhvp.worker import get_celery

    get_celery().send_task(
        "mhvp.ai.run",
        args=[
            str(principal.tenant_id),
            str(run_id),
            str(principal.user_id) if principal.user_id else None,
        ],
        queue="io",
    )


async def _start(
    request: Request,
    principal: TenantPrincipal,
    document_id: uuid.UUID,
    source: str,
    message_id: uuid.UUID | None,
) -> s.ReceiptDraftOut:
    async with tenant_tx(request, principal) as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
        if document.mime_type not in _SUPPORTED_MIME:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Nur PDF, Bild oder Textbelege können als Rechnung erfasst werden.",
            )
        if source == ReceiptDraftSource.MAIL_ATTACHMENT.value:
            if message_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Nachricht des Anhangs fehlt.")
            message = await session.get(Message, message_id)
            if message is None or document_id not in message.attachment_document_ids:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Anhang gehört nicht zu dieser Nachricht."
                )
        open_draft = await session.scalar(
            select(ReceiptDraft).where(
                ReceiptDraft.document_id == document_id,
                ReceiptDraft.status.in_(
                    [ReceiptDraftStatus.EXTRACTING.value, ReceiptDraftStatus.PROPOSED.value]
                ),
            )
        )
        if open_draft is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für dieses Dokument liegt bereits ein offener Belegentwurf vor.",
            )
        draft = await extraction.prepare(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            document=document,
            source=source,
            message_id=message_id,
        )
        await _event(session, principal, "receipt_draft.started", draft.id, source=source)
        draft_id, run_id = draft.id, draft.task_run_id
    assert run_id is not None  # noqa: S101 - prepare always queues a run
    await _dispatch(request, principal, run_id)
    return await get_draft(draft_id, request, principal)


@router.post("/drafts", status_code=202, summary="Beleg erfassen (KI-Entwurf aus Dokument)")
async def create_draft(
    body: s.ReceiptDraftFromDocumentIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ReceiptDraftOut:
    """Starts the extraction on an existing document (upload or mail attachment). The result
    is a draft for review, never an invoice and never a posting (rule 0.1.6)."""
    return await _start(request, principal, body.document_id, body.source, body.message_id)


@router.post("/drafts/paperless", status_code=202, summary="Beleg aus Paperless holen und erfassen")
async def create_draft_from_paperless(
    body: s.ReceiptDraftFromPaperlessIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ReceiptDraftOut:
    """Pulls one document by id from Paperless-ngx (read only client of M31) into the document
    store and starts the extraction. Manual action per document, no polling (M14-05)."""
    from mhvp.documents import services as doc_services
    from mhvp.documents.paperless_search import PaperlessSearchError
    from mhvp.documents.routers import _paperless_client

    async with tenant_tx(request, principal) as session:
        client = await _paperless_client(session)
        try:
            file = await client.fetch_file(body.paperless_document_id, "download")
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        filename = file.filename or f"paperless-{body.paperless_document_id}.pdf"
        document = await doc_services.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=file.content,
            title=filename,
            filename=filename,
            mime_type=file.content_type,
            source=DocumentSource.IMPORT,
            category_id=None,
            links=[],
            created_by=principal.user_id,
        )
        document_id = document.id
    return await _start(request, principal, document_id, ReceiptDraftSource.PAPERLESS.value, None)


@router.get("/drafts", summary="Belegentwürfe")
async def list_drafts(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    status: str | None = Query(default=None, pattern=_STATUS_FILTER),
    limit: int = Query(default=100, ge=1, le=500),
) -> s.ReceiptDraftListOut:
    """``status=open`` lists what still needs a decision (extracting, proposed, failed)."""
    async with tenant_tx(request, principal) as session:
        stmt = select(ReceiptDraft)
        if status == "open":
            stmt = stmt.where(
                ReceiptDraft.status.in_(
                    [
                        ReceiptDraftStatus.EXTRACTING.value,
                        ReceiptDraftStatus.PROPOSED.value,
                        ReceiptDraftStatus.FAILED.value,
                    ]
                )
            )
        elif status:
            stmt = stmt.where(ReceiptDraft.status == status)
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (
            await session.scalars(stmt.order_by(ReceiptDraft.created_at.desc()).limit(limit))
        ).all()
        items = [await _out(session, await extraction.materialize(session, row)) for row in rows]
        return s.ReceiptDraftListOut(items=items, total=int(total))


@router.get("/drafts/{draft_id}", summary="Belegentwurf lesen")
async def get_draft(
    draft_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ReceiptDraftOut:
    async with tenant_tx(request, principal) as session:
        draft = await extraction.materialize(session, await _draft(session, draft_id))
        return await _out(session, draft)


async def _open(session: Any, draft_id: uuid.UUID) -> ReceiptDraft:
    draft = await extraction.materialize(session, await _draft(session, draft_id))
    if draft.status in (ReceiptDraftStatus.CONFIRMED.value, ReceiptDraftStatus.REJECTED.value):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Über den Belegentwurf wurde bereits entschieden."
        )
    return draft


@router.post("/drafts/{draft_id}/confirm", status_code=201, summary="Belegentwurf bestätigen")
async def confirm_draft(
    draft_id: uuid.UUID,
    body: s.ReceiptConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ReceiptDraftOut:
    """Creates the invoice as an open, unposted draft from the reviewer's values (review and
    posting stay separate steps in the accounting module, 6.9.9). An IBAN is written only with
    ``iban_confirmed=true``; a proposal alone never sets one (rule 0.1.6)."""
    async with tenant_tx(request, principal) as session:
        draft = await _open(session, draft_id)
        if draft.status == ReceiptDraftStatus.EXTRACTING.value:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Die Extraktion läuft noch; bitte kurz warten."
            )
        data = body.invoice
        if data.payee_iban:
            if not body.iban_confirmed:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=(
                        "IBAN wird nur mit ausdrücklicher Bestätigung übernommen (iban_confirmed)."
                    ),
                )
            data = data.model_copy(update={"payee_iban": normalize_iban(data.payee_iban)})
        if data.document_id is None:
            data = data.model_copy(update={"document_id": draft.document_id})
        elif data.document_id != draft.document_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument weicht vom Belegentwurf ab.")
        import_run = ImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            source=f"receipt:{draft.source}",
            status=ImportStatus.APPLIED,
            document_ids=[draft.document_id],
        )
        session.add(import_run)
        await session.flush()
        from mhvp.ai import imports

        summary = await imports.apply_invoice(session, import_run, principal, data)
        import_run.summary = summary
        draft.invoice_id = uuid.UUID(summary["invoice_id"])
        draft.status = ReceiptDraftStatus.CONFIRMED.value
        draft.decided_by, draft.decided_at = principal.user_id, datetime.now(UTC)
        if body.note:
            draft.questions = [*draft.questions, f"Prüfvermerk: {body.note}"]
        await _close_proposal(session, draft, Decision.MODIFIED, principal)
        await _event(
            session,
            principal,
            "receipt_draft.confirmed",
            draft.id,
            invoice_id=summary["invoice_id"],
            iban_confirmed=bool(data.payee_iban),
            import_run_id=str(import_run.id),
        )
        return await _out(session, draft)


@router.post("/drafts/{draft_id}/reject", summary="Belegentwurf verwerfen")
async def reject_draft(
    draft_id: uuid.UUID,
    body: s.ReceiptRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ReceiptDraftOut:
    async with tenant_tx(request, principal) as session:
        draft = await _open(session, draft_id)
        draft.status = ReceiptDraftStatus.REJECTED.value
        draft.decided_by, draft.decided_at = principal.user_id, datetime.now(UTC)
        if body.reason:
            draft.error = body.reason
        await _close_proposal(session, draft, Decision.REJECTED, principal)
        await _event(session, principal, "receipt_draft.rejected", draft.id, reason=body.reason)
        return await _out(session, draft)


async def _close_proposal(
    session: Any, draft: ReceiptDraft, decision: Decision, principal: TenantPrincipal
) -> None:
    """The gateway job also records an `AiProposal` for the run; keep it in step so the
    chat audit trail shows the decision taken here."""
    from mhvp.ai.models import AiProposal

    if draft.task_run_id is None:
        return
    proposal = await session.scalar(
        select(AiProposal).where(AiProposal.task_run_id == draft.task_run_id)
    )
    if proposal is not None and proposal.decision is Decision.PENDING:
        proposal.decision = decision
        proposal.decided_by, proposal.decided_at = principal.user_id, datetime.now(UTC)
        proposal.final = {"receipt_draft_id": str(draft.id)}
