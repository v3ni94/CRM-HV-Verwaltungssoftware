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
from mhvp.core.listparams import strict_query
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
_SUPPORTED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
    "application/xml",
    "text/xml",
}
# Types whose original bytes are read for the structured e-invoice part (13.5).
_EINVOICE_MIME = {"application/pdf", "application/xml", "text/xml"}


async def _draft(session: Any, draft_id: uuid.UUID) -> ReceiptDraft:
    row: ReceiptDraft | None = await session.get(ReceiptDraft, draft_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Belegentwurf nicht gefunden.")
    return row


async def _out(
    session: Any, draft: ReceiptDraft, *, account_proposals: dict[str, Any] | None = None
) -> s.ReceiptDraftOut:
    """Flush and refresh first: ``updated_at`` (server side ``onupdate``) is expired after a
    flush and must not be lazy loaded from an async session."""
    await session.flush()
    await session.refresh(draft)
    data: dict[str, Any] = {
        name: getattr(draft, name)
        for name in s.ReceiptDraftOut.model_fields
        if name not in ("iban_candidates", "account_proposals")
    }
    # The encrypted candidate list never leaves the API; only the masked view does.
    data["iban_candidates"] = [
        s.ReceiptIbanCandidateOut(**c) for c in extraction.masked_iban_candidates(draft)
    ]
    data["account_proposals"] = (
        s.ReceiptAccountProposalsOut(**account_proposals) if account_proposals else None
    )
    return s.ReceiptDraftOut(**data)


def _line_texts(draft: ReceiptDraft, count: int | None = None) -> list[str | None]:
    """Wording per new invoice line: the XML lines of an e-invoice, else one line."""
    texts: list[str | None] = [
        (ln.get("description") if isinstance(ln, dict) else None) for ln in draft.xml_lines or []
    ]
    if count is not None:
        texts = (texts + [None] * count)[:count]
    return texts or [None]


async def _account_proposals(
    session: Any,
    draft: ReceiptDraft,
    *,
    ledger_id: uuid.UUID | None,
    provider_contact_id: uuid.UUID | None,
    line_count: int | None = None,
) -> dict[str, Any]:
    """Cost account proposals per line from the creditor's history (plan M12 S7,
    ``mhvp.banking.history.creditor_account_history``), only with the tenant switch
    ``learning_bookkeeper_enabled``; ledger and provider must exist in the tenant (RLS)."""
    from mhvp.accounting.models import Ledger
    from mhvp.banking import history
    from mhvp.banking.proposals import learning_enabled
    from mhvp.contacts.models import Contact

    out: dict[str, Any] = {
        "enabled": await learning_enabled(session),
        "ledger_id": ledger_id,
        "provider_contact_id": provider_contact_id,
    }
    if not out["enabled"] or ledger_id is None or provider_contact_id is None:
        return out
    if await session.get(Ledger, ledger_id) is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    if await session.get(Contact, provider_contact_id) is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Aussteller nicht gefunden.")
    found = await history.creditor_account_history(
        session,
        ledger_id=ledger_id,
        provider_contact_id=provider_contact_id,
        line_texts=_line_texts(draft, line_count),
    )
    return {**out, **found}


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
                detail=(
                    "Nur PDF, Bild, Text oder XML-Belege (XRechnung) können als Rechnung "
                    "erfasst werden."
                ),
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
        data: bytes | None = None
        if document.mime_type in _EINVOICE_MIME:
            blobs = BlobStore(request.app.state.settings)
            data = blobs.get(BlobStore.key(principal.tenant_id, document.id))
        draft = await extraction.prepare(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            document=document,
            source=source,
            message_id=message_id,
            data=data,
        )
        await _event(
            session,
            principal,
            "receipt_draft.started",
            draft.id,
            source=source,
            e_invoice_format=draft.e_invoice_format,
            ai_run=draft.task_run_id is not None,
        )
        draft_id, run_id = draft.id, draft.task_run_id
    if run_id is not None:  # a plain XRechnung needs no provider call
        await _dispatch(request, principal, run_id)
    return await _read(request, principal, draft_id)


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
        # Same limit as an upload (A-016): Paperless is a configured DMS, not a trusted source
        # of unbounded files.
        if len(file.content) > request.app.state.settings.document_max_bytes:
            raise ProblemError(
                ErrorCodes.UPLOAD_REJECTED,
                detail="Das Paperless-Dokument überschreitet die zulässige Dateigröße.",
            )
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


@router.get("/drafts", summary="Belegentwürfe", dependencies=[Depends(strict_query)])
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
    draft_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    ledger_id: uuid.UUID | None = Query(
        default=None, description="Mit provider_contact_id: Kontovorschläge aus dem Verlauf"
    ),
    provider_contact_id: uuid.UUID | None = Query(default=None),
) -> s.ReceiptDraftOut:
    """With ``ledger_id`` and ``provider_contact_id`` the answer carries ``account_proposals``
    (plan M12 S7, source Verlauf): the cost accounts persons chose on earlier invoices and
    bank transactions of the same creditor in the same ledger, per line. Only with
    ``learning_bookkeeper_enabled``; reading never writes."""
    return await _read(
        request, principal, draft_id, ledger_id=ledger_id, provider_contact_id=provider_contact_id
    )


async def _read(
    request: Request,
    principal: TenantPrincipal,
    draft_id: uuid.UUID,
    *,
    ledger_id: uuid.UUID | None = None,
    provider_contact_id: uuid.UUID | None = None,
) -> s.ReceiptDraftOut:
    async with tenant_tx(request, principal) as session:
        draft = await extraction.materialize(session, await _draft(session, draft_id))
        proposals = None
        if draft.status == ReceiptDraftStatus.PROPOSED.value and (
            ledger_id is not None or provider_contact_id is not None
        ):
            proposals = await _account_proposals(
                session, draft, ledger_id=ledger_id, provider_contact_id=provider_contact_id
            )
        return await _out(session, draft, account_proposals=proposals)


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
        if draft.conflicts and not body.conflicts_acknowledged:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Der Entwurf weist Widersprüche zwischen XML und PDF aus; sie müssen "
                    "gesichtet werden (conflicts_acknowledged), keine automatische Auswahl (D42)."
                ),
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

        # Plan M12 S7: the account proposals of the creditor's history are recomputed for
        # the confirmed ledger and provider (before the new invoice exists) and compared with
        # the accounts the reviewer confirmed; the diff is stored on the draft and in the
        # event. Nothing is taken over from the proposal.
        from mhvp.banking import history as bank_history

        proposals = await _account_proposals(
            session,
            draft,
            ledger_id=data.ledger_id,
            provider_contact_id=data.provider_contact_id,
            line_count=len(data.lines),
        )
        decision = (
            bank_history.account_decision(proposals, [ln.account_id for ln in data.lines])
            if proposals.get("enabled")
            else None
        )
        summary = await imports.apply_invoice(session, import_run, principal, data)
        import_run.summary = summary
        draft.invoice_id = uuid.UUID(summary["invoice_id"])
        await _carry_over(session, draft)
        draft.status = ReceiptDraftStatus.CONFIRMED.value
        draft.decided_by, draft.decided_at = principal.user_id, datetime.now(UTC)
        if decision is not None:
            draft.account_proposal_decision = {
                **decision,
                "ledger_id": str(data.ledger_id),
                "provider_contact_id": str(data.provider_contact_id),
                "computed_at": datetime.now(UTC).isoformat(),
            }
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
            account_proposal_outcome=decision["outcome"] if decision else None,
            account_proposal_diff=decision["diff"] if decision else None,
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


@router.post(
    "/drafts/{draft_id}/validation", summary="Validierungsergebnis einer E-Rechnung speichern"
)
async def record_validation(
    draft_id: uuid.UUID,
    body: s.ReceiptValidationIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ReceiptDraftOut:
    """S711-01: variant, validator, version and result per e-invoice. The own formal check
    stays in ``validation.formal``; the reported run becomes the current result."""
    async with tenant_tx(request, principal) as session:
        draft = await _draft(session, draft_id)
        if draft.e_invoice_format == "none":
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der Beleg hat keinen strukturierten Teil."
            )
        previous = dict(draft.validation or {})
        formal = previous.get("formal") or (previous if not previous.get("official") else None)
        draft.validation = {
            **body.model_dump(),
            "official": True,
            "variant": draft.e_invoice_profile,
            "structured_sha256": draft.structured_sha256,
            "recorded_by": str(principal.user_id) if principal.user_id else None,
            "recorded_at": datetime.now(UTC).isoformat(),
            "formal": formal,
        }
        await _event(
            session,
            principal,
            "receipt_draft.validation_recorded",
            draft.id,
            validator=body.validator,
            result=body.result,
        )
        return await _out(session, draft)


async def _carry_over(session: Any, draft: ReceiptDraft) -> None:
    """What the intake knows and the apply schema cannot carry: e-invoice format, the printed
    recipient (PÜ01 check against the legal entity) and the intake findings (D42 conflicts,
    D44 unproven § 35a share) as review hints on the invoice. Findings are hints only; the
    review steps stay open (PÜ05)."""
    from mhvp.accounting import invoices as acc_invoices
    from mhvp.accounting.models import Invoice

    invoice = await session.get(Invoice, draft.invoice_id)
    if invoice is None:  # pragma: no cover - apply_invoice just created it
        return
    if draft.e_invoice_format in ("xrechnung", "zugferd"):
        invoice.e_invoice_format = draft.e_invoice_format
    recipient = (draft.fields.get("recipient_name") or {}).get("value")
    if recipient and not invoice.recipient_name:
        invoice.recipient_name = str(recipient)[:400]
    await acc_invoices.evaluate(session, invoice)
    extra: list[str] = []
    for conflict in draft.conflicts:
        other = conflict.get("other")
        extra.append(
            f"E-Rechnung: Widerspruch bei {conflict.get('field')} (XML: {conflict.get('xml')}, "
            f"{conflict.get('other_source')}: {other if other is not None else 'nicht gefunden'}); "
            "Zahlungsprüfung statt automatischer Auswahl (D42)"
        )
    extra.extend(f for f in draft.findings if f.startswith("§-35a"))
    extra.extend(
        f"E-Rechnung hybrid: {d.get('note')}" for d in (draft.hybrid_deviations or [])
    )  # S711-04: kept independently of the acknowledged D42 conflicts
    if extra:
        invoice.findings = [*invoice.findings, *extra]
    await session.flush()


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
