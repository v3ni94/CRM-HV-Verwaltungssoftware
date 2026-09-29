"""Banking endpoints (/api/v1/banking, M11). Reading bank data needs accounting permissions;
no payment is initiated here (G2)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mhvp.accounting.models import EntrySource, LedgerAccount, ReversalReason
from mhvp.banking import account_selection, decisions, matching, payments, proposals, verifiers
from mhvp.banking import event_types as ev
from mhvp.banking import finapi as finapi_client
from mhvp.banking import learning as learning_svc
from mhvp.banking import levels as levels_svc
from mhvp.banking import matching_metrics as matching_metrics_svc
from mhvp.banking import review as review_svc
from mhvp.banking import runner as runner_svc
from mhvp.banking import services as svc
from mhvp.banking.connectors import FileConnector
from mhvp.banking.models import (
    AccountPurpose,
    BankConnection,
    BankRule,
    BankRuleProposal,
    BankSyncRun,
    BankTransaction,
    BookkeepingLevelRequest,
    ConnectionStatus,
    Connector,
    FinApiAccountLink,
    FinApiConnection,
    FinApiTenantConfig,
    OrderStatus,
    PaymentBankConfig,
    PaymentBatch,
    PaymentFileDownload,
    PaymentOrder,
    RuleState,
    TransactionStatus,
)
from mhvp.core.auth.permissions import ACCOUNTING_REVIEW
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_legal_entity_allowed
from mhvp.core.db.tenancy import after_commit
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.workspace.services import local_today

BANKING_APPROVE = require_permission("banking:approve")
FINAPI_SETTINGS = require_permission("tenant_settings:update")

router = APIRouter(prefix="/banking", tags=["Bank"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")
REVIEW = require_permission(ACCOUNTING_REVIEW)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionIn(_In):
    connector: Connector
    bank_name: str = Field(min_length=1, max_length=200)
    bic: str | None = Field(default=None, max_length=11)
    credentials: str | None = Field(default=None, max_length=20000)
    consent_valid_until: date | None = None


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    connector: Connector
    bank_name: str
    bic: str | None
    has_credentials: bool = False
    consent_valid_until: date | None
    status: ConnectionStatus
    error_message: str | None


class ImportIn(_In):
    document_id: uuid.UUID


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source: str
    status: str
    counts: dict[str, int]
    errors: list[str]
    property_bank_account_id: uuid.UUID | None
    document_id: uuid.UUID | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    property_bank_account_id: uuid.UUID
    legal_entity_id: uuid.UUID
    bank_reference: str | None
    booking_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    counterpart_name: str | None
    counterpart_iban_suffix: str | None = None
    purpose: str | None
    end_to_end_id: str | None
    mandate_reference: str | None
    status: TransactionStatus
    possible_duplicate_of_id: uuid.UUID | None
    transfer_pair_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None


class DuplicateReviewIn(_In):
    decision: str = Field(pattern="^(keep|ignore)$")
    reason: str = Field(min_length=3, max_length=2000)
    # Learning bookkeeper (ADR 0014): the pending decision round the person saw; a stale id
    # is refused with 409 ``MHVP-BANK-0021``. Optional, ignored while the switch is off.
    proposal_id: uuid.UUID | None = None


class ReopenIn(_In):
    reason: str = Field(min_length=3, max_length=2000)


class ProposalRejectIn(ReopenIn):
    """Reject the proposals of a transaction with a mandatory reason (plan M12 3.3). The
    transaction stays open; ``chosen`` names the proposal the reason refers to (index into
    the snapshot, default the best one); ``ai_proposal_id`` additionally closes a stored AI
    proposal as rejected (``mhvp.ai.examples.record_rejection``)."""

    proposal_id: uuid.UUID | None = None
    chosen: int | None = Field(default=None, ge=0, le=100)
    ai_proposal_id: uuid.UUID | None = None


class LearningSwitchIn(_In):
    enabled: bool
    reason: str = Field(min_length=3, max_length=2000)


class PostingDecisionOut(BaseModel):
    """One round of ``posting_decision`` (ADR 0014)."""

    id: uuid.UUID
    bank_transaction_id: uuid.UUID
    legal_entity_id: uuid.UUID
    round: int
    status: str
    bulk: bool
    engine_version: str
    rule_version: str
    features_hash: str
    features: dict[str, Any]
    proposals: list[dict[str, Any]]
    case_kind: str
    level: str
    best_source: str | None
    best_confidence: Decimal | None
    computed_at: datetime
    chosen_index: int | None
    final: dict[str, Any] | None
    diff: dict[str, Any] | None
    reason: str | None
    journal_entry_id: uuid.UUID | None
    ai_proposal_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    # Runner (S6): only on auto_posted rows.
    verifier_fingerprint: str | None = None
    review_due_on: date | None = None


def _conn_out(row: BankConnection) -> ConnectionOut:
    out = ConnectionOut.model_validate(row)
    out.has_credentials = bool(row.credentials)
    return out


def _tx_out(row: BankTransaction) -> TransactionOut:
    out = TransactionOut.model_validate(row)
    out.counterpart_iban_suffix = row.counterpart_iban[-4:] if row.counterpart_iban else None
    return out


@router.post("/connections", status_code=201, summary="Bankverbindung anlegen")
async def create_connection(
    body: ConnectionIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> ConnectionOut:
    async with tenant_tx(request, principal) as session:
        status = (
            ConnectionStatus.ACTIVE
            if body.connector is Connector.FILE_IMPORT
            else ConnectionStatus.NOT_CONFIGURED  # contracts and provider open (V2, V3)
        )
        row = BankConnection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            status=status,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return _conn_out(row)


@router.get("/connections", summary="Bankverbindungen (ohne Zugangsdaten)")
async def list_connections(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ConnectionOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(select(BankConnection).order_by(BankConnection.bank_name))
        return [_conn_out(r) for r in rows.all()]


@router.post("/imports", status_code=201, summary="Kontoauszug (CAMT.053) importieren")
async def import_statement(
    body: ImportIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> SyncRunOut:
    async with tenant_tx(request, principal) as session:
        document = await session.get(Document, body.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        try:
            parsed = FileConnector.parse(data, document.filename)  # CAMT.053 or MT940
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
        try:
            run = await svc.import_file(
                session,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                parsed=parsed,
                document_id=document.id,
            )
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Auszug wird gerade parallel importiert."
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_sync_run.completed",
            entity_type="bank_sync_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload=run.counts,
        )
        _queue_proposals(session, request, principal.tenant_id, run.id)
        return SyncRunOut.model_validate(run)


def _queue_proposals(
    session: Any, request: Request, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """Proposal snapshots of the learning bookkeeper (ADR 0014) are computed by the Celery task
    ``mhvp.banking.compute_proposals`` after the import committed, never inside the import
    request. The hook runs only after a successful commit; the task itself is a no-op for
    tenants without the switch. With ``ai_inline`` (development and tests, no worker) the
    computation runs in the calling process; a failure to enqueue is logged, the next import
    or the consumer recomputes."""
    import logging

    from mhvp.banking.tasks import compute_proposals_once

    settings = request.app.state.settings
    log = logging.getLogger(__name__)

    async def _start() -> None:
        if settings.ai_inline:
            await compute_proposals_once(settings, tenant_id, run_id)
            return
        try:
            from mhvp.worker import get_celery

            get_celery().send_task(
                "mhvp.banking.compute_proposals", args=[str(tenant_id), str(run_id)]
            )
        except Exception:
            log.exception("posting proposals not queued", extra={"run_id": str(run_id)})

    after_commit(session, _start)


@router.get("/runs", summary="Sync-Protokoll")
async def runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> list[SyncRunOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(BankSyncRun).order_by(BankSyncRun.created_at.desc()).limit(limit)
        )
        return [SyncRunOut.model_validate(r) for r in rows.all()]


@router.get("/transactions", summary="Bankumsätze")
async def transactions(
    request: Request,
    bank_account_id: uuid.UUID | None = None,
    status: TransactionStatus | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ),
) -> list[TransactionOut]:
    async with tenant_tx(request, principal) as session:
        query = select(BankTransaction)
        if bank_account_id:
            query = query.where(BankTransaction.property_bank_account_id == bank_account_id)
        if status:
            query = query.where(BankTransaction.status == status)
        if start:
            query = query.where(BankTransaction.booking_date >= start)
        if end:
            query = query.where(BankTransaction.booking_date <= end)
        rows = await session.scalars(
            query.order_by(BankTransaction.booking_date, BankTransaction.created_at)
            .offset(offset)
            .limit(limit)
        )
        return [_tx_out(r) for r in rows.all()]


@router.post("/transactions/{tx_id}/review", summary="Möglichen Doppelumsatz klären")
async def review(
    tx_id: uuid.UUID,
    body: DuplicateReviewIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TransactionOut:
    """A possible duplicate is kept as real payment or ignored; never deleted (B08, D05)."""
    async with tenant_tx(request, principal) as session:
        row = await session.get(BankTransaction, tx_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status is not TransactionStatus.NEEDS_REVIEW:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Umsatz ist nicht zur Prüfung vorgemerkt."
            )
        row.status = TransactionStatus.NEW if body.decision == "keep" else TransactionStatus.IGNORED
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_transaction.reviewed",
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"decision": body.decision, "reason": body.reason},
        )
        await session.flush()
        return _tx_out(row)


@router.get("/accounts/{bank_account_id}/reconciliation", summary="Bankabstimmung (B09)")
async def reconciliation(
    bank_account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        from mhvp.properties.models import PropertyBankAccount

        if await session.get(PropertyBankAccount, bank_account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await svc.reconcile(session, bank_account_id)


# Matching and controlled automation (M12, 7.4, 6.9.4) ---------------------------------


class SettleIn(_In):
    open_item_id: uuid.UUID
    amount: Decimal = Field(gt=0)


class BookIn(_In):
    settlements: list[SettleIn] = Field(default_factory=list, max_length=100)
    counter_account_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=500)
    # Skonto against ``counter_account_id`` (7.3); the personal account is settled by
    # amount plus discount.
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)
    # Learning bookkeeper (ADR 0014, plan M12 3.3): the pending decision round the person
    # booked from and the proposal chosen in it (index into the snapshot). A different
    # proposal is a choice, not a modification; the diff is computed against ``chosen``.
    # Both optional and ignored while ``learning_bookkeeper_enabled`` is off.
    proposal_id: uuid.UUID | None = None
    chosen: int | None = Field(default=None, ge=0, le=100)


class BulkItem(BookIn):
    transaction_id: uuid.UUID


class BankBulkIn(_In):
    items: list[BulkItem] = Field(min_length=1, max_length=1000)
    preview: bool = True


class RuleIn(_In):
    name: str = Field(min_length=1, max_length=200)
    legal_entity_id: uuid.UUID
    property_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    counterpart_iban: str | None = None
    name_contains: str | None = Field(default=None, max_length=200)
    purpose_regex: str | None = Field(default=None, max_length=500)
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_id: uuid.UUID | None = None
    priority: int = Field(default=100, ge=0, le=10000)


class ActivateIn(_In):
    max_amount: Decimal = Field(gt=0)
    test_evidence_document_id: uuid.UUID


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    legal_entity_id: uuid.UUID
    match: dict[str, Any]
    action: dict[str, Any]
    priority: int
    hit_count: int
    learned_from_ai: bool
    learned_from_transaction_id: uuid.UUID | None
    approval_state: str
    approved_by: uuid.UUID | None
    max_amount: Decimal | None
    test_evidence_document_id: uuid.UUID | None
    created_by: uuid.UUID | None
    learned_from_proposal_id: uuid.UUID | None = None
    contradiction_count: int = 0
    superseded_by_id: uuid.UUID | None = None


async def _tx(session: Any, tx_id: uuid.UUID) -> BankTransaction:
    row = await session.get(BankTransaction, tx_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row  # type: ignore[no-any-return]


@router.get("/transactions/{tx_id}/candidates", summary="Zuordnungsvorschläge mit Begründung")
async def tx_candidates(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _tx(session, tx_id)
        found = await matching.candidates(session, row)
        best = matching.unambiguous(found, row.amount)
        return {
            "candidates": [c.__dict__ for c in found],
            "unambiguous_open_item_id": best.open_item_id if best else None,
            "note": "Vorschlag, keine Buchung. Die IBAN allein beweist keinen Schuldner.",
        }


def _posting_out(proposal: Any) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "task_run_id": proposal.task_run_id,
        "entity_type": proposal.entity_type,
        "decision": proposal.decision.value,
        "created_at": proposal.created_at,
        "proposed": proposal.proposed,
    }


@router.post(
    "/transactions/{tx_id}/ai-posting",
    status_code=202,
    summary="KI-Kontierungsvorschlag anstoßen (nur Vorschlag, deaktiviert bis Freigabe)",
)
async def start_ai_posting(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """M7-09, M12-01: only with the tenant switch ``ai_posting_enabled`` and a released AI
    provider with DPA evidence, otherwise ``MHVP-AI-0001``. The result is an ``AiProposal``
    of entity type ``posting``; nothing is posted and the transaction is not changed."""
    from mhvp.ai import gateway, jobs
    from mhvp.banking import ai_posting
    from mhvp.core.auth.principal import sessions

    async with tenant_tx(request, principal) as session:
        blocked = await gateway.posting_block_reason(session)
        if blocked is not None:
            raise ProblemError(ErrorCodes.AI_POSTING_NOT_RELEASED, detail=blocked)
        row = await _tx(session, tx_id)
        payload, context = await ai_posting.payload_for(session, row)
        run = ai_posting.queue_run(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            payload=payload,
            context=context,
        )
        await session.flush()
        run_id = run.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_transaction.ai_posting_requested",
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"run_id": str(run_id)},
        )
    settings = request.app.state.settings
    if settings.ai_inline:
        await jobs.run_and_propose(
            sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
        )
    else:
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
    return await get_ai_posting(tx_id, request, principal)


@router.get("/transactions/{tx_id}/ai-posting", summary="KI-Kontierungsvorschläge lesen")
async def get_ai_posting(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.banking import ai_posting

    async with tenant_tx(request, principal) as session:
        if await session.get(BankTransaction, tx_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        proposals = await ai_posting.proposals_for(session, tx_id)
        return {
            "bank_transaction_id": tx_id,
            "proposals": [_posting_out(p) for p in proposals],
            "note": "Vorschlag der KI, keine Buchung.",
        }


@router.get(
    "/transactions/{tx_id}/posting-proposals",
    summary="Kontierungsvorschläge in zwei Stufen (Regel, Abgleich, KI) mit Konfidenz",
)
async def posting_proposals(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """M12-01: stage 1 is deterministic and always on (``mhvp.banking.posting_proposal``);
    stage 2 lists stored AI proposals and says why the AI stage is blocked. Every entry
    carries ``source`` (rule, match, ai), ``confidence`` and ``reasoning``; nothing is posted,
    booking stays with ``POST /transactions/{tx_id}/book``."""
    from mhvp.ai import gateway
    from mhvp.banking import ai_posting, posting_proposal
    from mhvp.banking.matching import ledger_for

    async with tenant_tx(request, principal) as session:
        row = await session.get(BankTransaction, tx_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        stage1 = [p.as_dict() for p in await posting_proposal.stage1_for_transaction(session, row)]
        # Web-CRM link from a split to its open item on the ledger page (Bankabgleich seite,
        # operator 27.09.2026 remainder); read only, no extra query beyond the ledger lookup
        # stage1_for_transaction already does.
        ledger, _bank = await ledger_for(session, row)
        ai_rows = await ai_posting.proposals_for(session, tx_id)
        ai_items = [
            {
                **_posting_out(p),
                "source": posting_proposal.SOURCE_AI,
                "confidence": (p.proposed or {}).get("confidence"),
                "reasoning": (p.proposed or {}).get("reasoning"),
            }
            for p in ai_rows
        ]
        blocked = await gateway.posting_block_reason(session)
        # Learning bookkeeper (ADR 0014): the pending decision round, when the switch is on
        # and the snapshot job already ran; the CRM passes ``proposal_id`` and ``chosen`` back
        # with the booking or rejection. Reading never writes a row.
        learning = await proposals.learning_enabled(session)
        pending = await proposals.pending_for(session, row.id) if learning else None
        return {
            "bank_transaction_id": tx_id,
            "amount": row.amount,
            "ledger_id": ledger.id,
            "stage1": stage1,
            "ai": ai_items,
            "ai_stage": {"enabled": blocked is None, "blocked_reason": blocked},
            "learning": {
                "enabled": learning,
                "decision_id": pending.id if pending is not None else None,
                "round": pending.round if pending is not None else None,
                "features_hash": pending.features_hash if pending is not None else None,
                "proposals": pending.proposals if pending is not None else None,
            },
            "note": "Vorschläge, keine Buchung. Buchung nur nach Prüfung und Freigabe.",
        }


async def _book(
    session: Any,
    principal: TenantPrincipal,
    row: BankTransaction,
    body: BookIn,
    *,
    bulk: bool = False,
) -> Any:
    reasons = await matching.allocation_reasons(
        session, row, [s.open_item_id for s in body.settlements]
    )
    entry = await matching.book_payment(
        session,
        row,
        settlements=[(s.open_item_id, s.amount) for s in body.settlements],
        counter_account_id=body.counter_account_id,
        user_id=principal.user_id,
        source=EntrySource.BANK_IMPORT,
        text=body.text,
        discount=body.discount,
    )
    counter_number = None
    if body.counter_account_id is not None:
        counter = await session.get(LedgerAccount, body.counter_account_id)
        counter_number = counter.number if counter is not None else None
    # Decision log (ADR 0014): the booking closes the pending round with the diff against the
    # chosen proposal; no-op while the tenant switch is off.
    decision = await proposals.record_booking(
        session,
        row,
        journal_entry_id=entry.id,
        user_id=principal.user_id,
        proposal_id=body.proposal_id,
        chosen=body.chosen,
        final=decisions.normalise_final(
            settlements=[
                {"open_item_id": s.open_item_id, "amount": s.amount} for s in body.settlements
            ],
            counter_account_number=counter_number,
            discount=body.discount,
            text=body.text,
        ),
        bulk=bulk,
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=ev.BANK_TRANSACTION_BOOKED,
        entity_type="bank_transaction",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={
            "journal_entry_id": str(entry.id),
            "allocations": [
                {
                    "open_item_id": str(s.open_item_id),
                    "amount": str(s.amount),
                    "allocation_reason": reasons[str(s.open_item_id)],
                }
                for s in body.settlements
            ],
            "counter_account_number": counter_number,
            "discount": str(body.discount),
            "bulk": bulk,
            "decision_id": str(decision.id) if decision is not None else None,
            "decision_status": decision.status if decision is not None else None,
            "proposal_source": (
                decision.proposals[decision.chosen_index].get("source")
                if decision is not None and decision.chosen_index is not None
                else None
            ),
        },
    )
    return entry


@router.post("/transactions/{tx_id}/book", status_code=201, summary="Umsatz buchen (bestätigt)")
async def book(
    tx_id: uuid.UUID, body: BookIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """A recognised transfer pair is booked once, from either half, against the partner bank
    account; that posting settles both halves. Booking the other half afterwards is refused
    with 409 ``MHVP-BANK-0019`` until the posting is reversed (D04, B08). If the partner half
    was booked against another account (e.g. Geldtransit) before the pair was recognised, that
    posting does not settle the pair: this half is booked on its own against a counter account
    (e.g. Geldtransit, clearing it); against the partner bank account it is refused with 409
    ``MHVP-BANK-0020``."""
    async with tenant_tx(request, principal) as session:
        entry = await _book(
            session, principal, await matching.lock_for_booking(session, tx_id), body
        )
        return {"journal_entry_id": entry.id, "number": f"{entry.fiscal_year}-{entry.number}"}


@router.post("/transactions/{tx_id}/ignore", summary="Umsatz ignorieren (mit Begründung)")
async def ignore(
    tx_id: uuid.UUID,
    body: DuplicateReviewIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TransactionOut:
    async with tenant_tx(request, principal) as session:
        row = await _tx(session, tx_id)
        if row.journal_entry_id is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Gebuchte Umsätze werden per Storno korrigiert."
            )
        row.status = TransactionStatus.IGNORED
        row.updated_by = principal.user_id
        await session.flush()
        decision = await proposals.record_ignore(
            session,
            row,
            user_id=principal.user_id,
            reason=body.reason,
            proposal_id=body.proposal_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=ev.BANK_TRANSACTION_IGNORED,
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "reason": body.reason,
                "decision_id": str(decision.id) if decision is not None else None,
            },
        )
        await session.flush()
        return _tx_out(row)


@router.post("/transactions/{tx_id}/reopen", summary="Ignorierten Umsatz wieder eröffnen")
async def reopen(
    tx_id: uuid.UUID,
    body: ReopenIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TransactionOut:
    """An ignored transaction becomes ``new`` again with a reason (plan M12 3.3, ignoring is
    no longer terminal). A transaction that carries a posting stays booked: corrections go
    through the reversal (B03)."""
    async with tenant_tx(request, principal) as session:
        row = await matching.lock_for_booking(session, tx_id)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        if row.status is not TransactionStatus.IGNORED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Umsatz ist nicht ignoriert.")
        if row.journal_entry_id is not None and await matching._effective_entry(
            session, row.journal_entry_id
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Gebuchte Umsätze werden per Storno korrigiert."
            )
        row.status = TransactionStatus.NEW
        row.updated_by = principal.user_id
        await session.flush()
        decision = await proposals.ensure_pending(session, row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=ev.BANK_TRANSACTION_REOPENED,
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "reason": body.reason,
                "decision_id": str(decision.id) if decision is not None else None,
            },
        )
        await session.flush()
        return _tx_out(row)


@router.post(
    "/transactions/{tx_id}/reject",
    summary="Vorschläge ablehnen (Pflichtgrund, Umsatz bleibt offen)",
)
async def reject_proposals(
    tx_id: uuid.UUID,
    body: ProposalRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> PostingDecisionOut | None:
    """Closes the pending decision round as ``rejected`` with the reason and opens the next
    round (ADR 0014, M12-04). Nothing is booked or ignored. With ``ai_proposal_id`` the stored
    AI proposal is marked rejected and, when the tenant records learning examples, handed to
    ``mhvp.ai.examples.record_rejection``. Returns ``null`` while the learning switch is off
    (the AI rejection is still recorded)."""
    from mhvp.ai import examples as ai_examples
    from mhvp.ai.models import AiProposal, AiTaskRun, Decision

    async with tenant_tx(request, principal) as session:
        row = await matching.lock_for_booking(session, tx_id)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        if row.status is not TransactionStatus.NEW:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur offene Umsätze haben ablehnbare Vorschläge."
            )
        ai_row = None
        if body.ai_proposal_id is not None:
            ai_row = await session.get(AiProposal, body.ai_proposal_id)
            if ai_row is None or ai_row.context_id != row.id:
                raise ProblemError(
                    ErrorCodes.RESOURCE_NOT_FOUND, detail="KI-Vorschlag nicht gefunden."
                )
            if ai_row.decision is Decision.PENDING:
                ai_row.decision = Decision.REJECTED
                ai_row.decided_by, ai_row.decided_at = principal.user_id, datetime.now(UTC)
                ai_row.rejection_reason = body.reason
                run = await session.get(AiTaskRun, ai_row.task_run_id)
                if run is not None:
                    await ai_examples.record_rejection(
                        session,
                        proposal=ai_row,
                        run=run,
                        reason=body.reason,
                        rejected_by=principal.user_id,
                    )
        decision = await proposals.record_rejection(
            session,
            row,
            user_id=principal.user_id,
            reason=body.reason,
            proposal_id=body.proposal_id,
            chosen=body.chosen,
            ai_proposal_id=ai_row.id if ai_row is not None else None,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=ev.BANK_TRANSACTION_PROPOSAL_REJECTED,
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "reason": body.reason,
                "decision_id": str(decision.id) if decision is not None else None,
                "chosen_index": decision.chosen_index if decision is not None else None,
                "ai_proposal_id": str(ai_row.id) if ai_row is not None else None,
            },
        )
        await session.flush()
        return (
            PostingDecisionOut(**proposals.decision_out(decision)) if decision is not None else None
        )


@router.get(
    "/transactions/{tx_id}/decisions",
    summary="Vorschlags- und Entscheidungsprotokoll eines Umsatzes (ADR 0014)",
)
async def list_decisions(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[PostingDecisionOut]:
    """Gated like the writes: with ``learning_bookkeeper_enabled`` off the answer is empty,
    existing rows stay stored (retention concept M12-06) and reappear when switched on."""
    async with tenant_tx(request, principal) as session:
        row = await _tx(session, tx_id)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        if not await proposals.learning_enabled(session):
            return []
        return [
            PostingDecisionOut(**proposals.decision_out(r))
            for r in await proposals.rounds_of(session, tx_id)
        ]


@router.post(
    "/bulk-confirm", summary="Massenbestätigung mit Vorschau (je Umsatz ganz oder gar nicht)"
)
async def bulk_confirm(
    body: BankBulkIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rows = []
        for item in body.items:
            rows.append((item, await matching.lock_for_booking(session, item.transaction_id)))
        summary = {
            "count": len(rows),
            "total": str(sum((abs(r.amount) for _, r in rows), Decimal("0.00"))),
            "legal_entities": sorted({str(r.legal_entity_id) for _, r in rows}),
            "exceptions": [
                str(r.id)
                for _, r in rows
                if r.status is not TransactionStatus.NEW or r.transfer_pair_id is not None
            ],
        }
        if body.preview:
            allocations: dict[str, list[dict[str, str]]] = {}
            for item, row in rows:
                reasons = await matching.allocation_reasons(
                    session, row, [s.open_item_id for s in item.settlements]
                )
                allocations[str(row.id)] = [
                    {
                        "open_item_id": str(s.open_item_id),
                        "amount": str(s.amount),
                        "allocation_reason": reasons[str(s.open_item_id)],
                    }
                    for s in item.settlements
                ]
            return {"preview": True, **summary, "allocations": allocations}
        results = []
        for item, row in rows:
            nested = await session.begin_nested()
            try:
                entry = await _book(session, principal, row, item, bulk=True)
                await nested.commit()
                results.append({"transaction_id": row.id, "ok": True, "journal_entry_id": entry.id})
            except ProblemError as exc:
                await nested.rollback()
                results.append({"transaction_id": row.id, "ok": False, "error": exc.detail})
        return {"preview": False, **summary, "results": results}


@router.post("/rules", status_code=201, summary="Bankregel vorschlagen (Zustand proposed)")
async def create_rule(
    body: RuleIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> RuleOut:
    from mhvp.core import crypto

    async with tenant_tx(request, principal) as session:
        match: dict[str, Any] = {
            "counterpart_iban_fingerprint": crypto.fingerprint(
                body.counterpart_iban.replace(" ", "").upper()
            )
            if body.counterpart_iban
            else None,
            "name_contains": body.name_contains,
            "purpose_regex": body.purpose_regex,
            "amount_min": str(body.amount_min) if body.amount_min is not None else None,
            "amount_max": str(body.amount_max) if body.amount_max is not None else None,
        }
        rule = BankRule(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            name=body.name,
            legal_entity_id=body.legal_entity_id,
            property_id=body.property_id,
            contract_id=body.contract_id,
            match={k: v for k, v in match.items() if v is not None},
            action={
                "kind": "debtor_payment",
                "account_id": str(body.account_id) if body.account_id else None,
            },
            priority=body.priority,
        )
        session.add(rule)
        await session.flush()
        await _rule_event(session, principal, rule, ev.BANK_RULE_PROPOSED, {"origin": "manual"})
        return RuleOut.model_validate(rule)


async def _rule_event(
    session: Any,
    principal: TenantPrincipal,
    rule: BankRule,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Lifecycle event of a bank rule (ADR 0014, plan M12 S0): proposed, approved, activated,
    disabled; ``superseded`` and ``downgraded`` follow with the learning module (S5, S6)."""
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=event_type,
        entity_type="bank_rule",
        entity_id=rule.id,
        actor_user_id=principal.user_id,
        payload={
            "approval_state": rule.approval_state.value,
            "legal_entity_id": str(rule.legal_entity_id),
            **(payload or {}),
        },
    )


@router.get("/rules", summary="Bankregeln")
async def list_rules(request: Request, principal: TenantPrincipal = Depends(READ)) -> list[RuleOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(BankRule).order_by(BankRule.priority, BankRule.created_at)
        )
        return [RuleOut.model_validate(r) for r in rows.all()]


async def _rule(session: Any, rule_id: uuid.UUID) -> BankRule:
    rule = await session.get(BankRule, rule_id, with_for_update=True)
    if rule is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return rule  # type: ignore[no-any-return]


@router.post("/rules/{rule_id}/approve", summary="Fachlich freigeben (zweite Person)")
async def approve_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> RuleOut:
    async with tenant_tx(request, principal) as session:
        rule = await _rule(session, rule_id)
        if rule.approval_state is not RuleState.PROPOSED:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur vorgeschlagene Regeln können freigegeben werden."
            )
        if rule.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
            )
        rule.approval_state, rule.approved_by = RuleState.APPROVED, principal.user_id
        rule.approved_at = datetime.now(UTC)
        await session.flush()
        await _rule_event(session, principal, rule, ev.BANK_RULE_APPROVED)
        return RuleOut.model_validate(rule)


@router.post("/rules/{rule_id}/activate", summary="Aktivieren mit Betragsgrenze und Testnachweis")
async def activate_rule(
    rule_id: uuid.UUID,
    body: ActivateIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> RuleOut:
    async with tenant_tx(request, principal) as session:
        rule = await _rule(session, rule_id)
        if rule.approval_state is not RuleState.APPROVED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Regel ist nicht freigegeben.")
        if await session.get(Document, body.test_evidence_document_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Testnachweis nicht gefunden.")
        rule.approval_state = RuleState.ACTIVE
        rule.max_amount, rule.test_evidence_document_id = (
            body.max_amount,
            body.test_evidence_document_id,
        )
        # Learned rule (S5): older learned rules of the same key are superseded (event).
        superseded = await learning_svc.supersede(session, rule, user_id=principal.user_id)
        await _rule_event(
            session,
            principal,
            rule,
            ev.BANK_RULE_ACTIVATED,
            {
                "max_amount": str(body.max_amount),
                "test_evidence_document_id": str(body.test_evidence_document_id),
                "superseded": [str(r.id) for r in superseded],
            },
        )
        await session.flush()
        return RuleOut.model_validate(rule)


@router.post("/rules/{rule_id}/disable", summary="Regel abschalten")
async def disable_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> RuleOut:
    async with tenant_tx(request, principal) as session:
        rule = await _rule(session, rule_id)
        before = rule.approval_state.value
        rule.approval_state = RuleState.DISABLED
        await session.flush()
        await _rule_event(session, principal, rule, ev.BANK_RULE_DISABLED, {"before": before})
        return RuleOut.model_validate(rule)


@router.post(
    "/transactions/{tx_id}/learn", status_code=201, summary="Regelvorschlag aus bestätigter Buchung"
)
async def learn(
    tx_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> RuleOut:
    """Learning only from a confirmed result (7.4.6); the rule starts as proposed."""
    from mhvp.accounting.models import JournalLine

    async with tenant_tx(request, principal) as session:
        row = await _tx(session, tx_id)
        if row.status is not TransactionStatus.BOOKED or row.journal_entry_id is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur aus gebuchten Umsätzen wird gelernt."
            )
        debtor = await session.scalar(
            select(JournalLine.account_id)
            .where(JournalLine.journal_entry_id == row.journal_entry_id, JournalLine.credit > 0)
            .limit(1)
        )
        rule = BankRule(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            name=f"Gelernt: {row.counterpart_name or 'Zahler'}"[:200],
            legal_entity_id=row.legal_entity_id,
            match={"counterpart_iban_fingerprint": row.counterpart_iban_fingerprint},
            action={"kind": "debtor_payment", "account_id": str(debtor) if debtor else None},
            learned_from_transaction_id=row.id,
        )
        session.add(rule)
        await session.flush()
        await _rule_event(
            session,
            principal,
            rule,
            ev.BANK_RULE_PROPOSED,
            {"origin": "learn", "bank_transaction_id": str(row.id)},
        )
        return RuleOut.model_validate(rule)


@router.post(
    "/auto-post", summary="Automatik über aktive Regeln (nur bei Freischaltung je Mandant)"
)
async def run_auto_post(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Manual start of the runner (``mhvp.banking.runner``): tenant switch, class level L2 or
    L3, active rule, deterministic verifier with fingerprint, G1 open or non leading ledger
    (operator decision M12-07), case limits, review item per posting. Chronological order:
    a later payment of the same contract must not see the earlier month still open."""
    from mhvp.core.release_gates import ClosedReleaseGateResolver, ReleaseGate

    resolver = getattr(request.app.state, "release_gate_resolver", ClosedReleaseGateResolver())
    gate_open = await resolver.is_open(principal.tenant_id, ReleaseGate.G1)
    async with tenant_tx(request, principal) as session:
        result = await runner_svc.run_for_tenant(
            session, principal.tenant_id, gate_open=gate_open, today=local_today()
        )
        return {
            "enabled": result["enabled"],
            "posted": result["posted"],
            **{k: v for k, v in result.items() if k not in ("enabled", "posted")},
        }


@router.get("/matching/metrics", summary="Abdeckung und Fehlerquote der Automatik getrennt")
async def metrics(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    """Coverage = automatically booked / incoming; error rate = automatic bookings later reversed
    / automatic bookings. Operational figures, no proof of safety (7.4)."""
    from mhvp.accounting.models import JournalEntry

    async with tenant_tx(request, principal) as session:
        incoming = (
            await session.scalars(select(BankTransaction).where(BankTransaction.amount > 0))
        ).all()
        auto = [t for t in incoming if t.matched_rule_id is not None and t.journal_entry_id]
        reversed_count = 0
        for t in auto:
            entry = await session.get(JournalEntry, t.journal_entry_id)
            reversed_count += int(entry is not None and entry.reversed_by_id is not None)
        return {
            "incoming": len(incoming),
            "auto_booked": len(auto),
            "coverage": round(len(auto) / len(incoming), 4) if incoming else None,
            "auto_reversed": reversed_count,
            "error_rate": round(reversed_count / len(auto), 4) if auto else None,
        }


@router.get(
    "/matching-metrics",
    summary="Abdeckungsgrad und Fehlerquote des Bankabgleichs je Zeitraum (getrennt)",
)
async def matching_metrics(
    request: Request,
    period_from: Annotated[date | None, Query(alias="from")] = None,
    period_to: Annotated[date | None, Query(alias="to")] = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Coverage = automatically and unambiguously assigned transactions / transactions of the
    period; error rate = automatic assignments later reversed (corrected or cancelled) /
    automatic assignments. See ``mhvp.banking.matching_metrics`` (M12 acceptance, A45)."""
    if period_from is not None and period_to is not None and period_from > period_to:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Zeitraum ist ungültig (von > bis).")
    async with tenant_tx(request, principal) as session:
        result = await matching_metrics_svc.compute(
            session, period_from=period_from, period_to=period_to
        )
        return result.as_dict()


class AutomationIn(_In):
    enabled: bool
    reason: str = Field(min_length=3, max_length=2000)


@router.put("/automation", summary="Automatik je Mandant ein- oder ausschalten (Standard aus)")
async def set_automation(
    body: AutomationIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, bool]:
    from mhvp.platform.models import TenantSettings

    if not principal.has("tenant_settings:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing tenant_settings:update."
        )
    async with tenant_tx(request, principal) as session:
        settings = await session.scalar(select(TenantSettings).with_for_update())
        if settings is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        settings.auto_posting_enabled = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="tenant.auto_posting_changed",
            entity_type="tenant_settings",
            entity_id=settings.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled, "reason": body.reason},
        )
        await session.flush()
        return {"enabled": body.enabled}


@router.get("/learning", summary="Lernender Buchhalter: Schalter je Mandant lesen")
async def get_learning(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.banking import features, posting_proposal

    async with tenant_tx(request, principal) as session:
        return {
            "enabled": await proposals.learning_enabled(session),
            "engine_version": posting_proposal.ENGINE_VERSION,
            "rule_version": features.RULE_VERSION,
            "note": (
                "Vorschlags- und Entscheidungsprotokoll je Umsatz; bucht nichts, öffnet kein "
                "Gate. Standard aus bis zur Datenschutzprüfung des Betreibers (M12-06)."
            ),
        }


@router.put(
    "/learning",
    summary="Lernender Buchhalter: Entscheidungsprotokoll je Mandant ein- oder ausschalten",
)
async def set_learning(
    body: LearningSwitchIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, bool]:
    """``tenant_settings.learning_bookkeeper_enabled`` (ADR 0014, M12-04): accounting:approve
    plus tenant_settings:update, reason and event, default off. Switching on starts the
    proposal snapshots with the next import; switching off stops writing, existing rows stay
    (retention, OPEN_QUESTIONS M12-06). Nothing is posted by the switch."""
    from mhvp.platform.models import TenantSettings

    if not principal.has("tenant_settings:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing tenant_settings:update."
        )
    async with tenant_tx(request, principal) as session:
        settings = await session.scalar(select(TenantSettings).with_for_update())
        if settings is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        before = settings.learning_bookkeeper_enabled
        settings.learning_bookkeeper_enabled = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=ev.TENANT_LEARNING_BOOKKEEPER_CHANGED,
            entity_type="tenant_settings",
            entity_id=settings.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled, "reason": body.reason},
            changes={"learning_bookkeeper_enabled": {"old": before, "new": body.enabled}},
        )
        await session.flush()
        return {"enabled": body.enabled}


# Automation levels, L1 acceptance, learned rules, review queue, correction (S4 to S6) --------


class LevelRequestIn(_In):
    case_kind: str = Field(min_length=1, max_length=24)
    level_to: str = Field(pattern="^L[1-3]$")
    reason: str = Field(min_length=3, max_length=2000)


class LevelDecisionIn(_In):
    comment: str | None = Field(default=None, max_length=2000)


class LevelLowerIn(_In):
    case_kind: str = Field(min_length=1, max_length=24)
    level: str = Field(pattern="^L[0-2]$")
    reason: str = Field(min_length=3, max_length=2000)


class OutgoingSwitchIn(_In):
    enabled: bool
    reason: str = Field(min_length=3, max_length=2000)


class AcceptIn(_In):
    """One click acceptance (L1): the pending round and the verified proposal in it."""

    proposal_id: uuid.UUID | None = None
    chosen: int | None = Field(default=None, ge=0, le=100)
    text: str | None = Field(default=None, max_length=500)


class RuleProposalAcceptIn(_In):
    name: str | None = Field(default=None, max_length=200)
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    purpose_tokens: list[str] | None = Field(default=None, max_length=10)


class ReviewDecisionIn(_In):
    outcome: str = Field(pattern="^(ok|corrected|cancelled)$")
    note: str | None = Field(default=None, max_length=2000)


class BankCorrectionIn(BookIn):
    """Korrigieren (B03): reversal with reason code and free text plus one new posting."""

    reason: str = Field(min_length=3, max_length=2000)
    reason_code: ReversalReason = ReversalReason.WRONG_ASSIGNMENT


def _actor(principal: TenantPrincipal) -> levels_svc.LevelActor:
    return levels_svc.LevelActor(
        principal.user_id, principal.tenant_id, is_platform_admin=principal.is_platform_admin
    )


@router.get("/automation/levels", summary="Automatikstufen je Fallklasse mit Anträgen")
async def get_levels(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        settings = await session.scalar(select(TenantSettings))
        current = await levels_svc.current_levels(session)
        requests = list(
            await session.scalars(
                select(BookkeepingLevelRequest)
                .order_by(BookkeepingLevelRequest.created_at.desc())
                .limit(100)
            )
        )
        return {
            "levels": current,
            "caps": levels_svc.CLASS_CAPS,
            "labels": levels_svc.CLASS_LABELS,
            "auto_posting_enabled": bool(settings and settings.auto_posting_enabled),
            "auto_posting_outgoing_enabled": bool(
                settings and settings.auto_posting_outgoing_enabled
            ),
            "learning_enabled": bool(settings and settings.learning_bookkeeper_enabled),
            "blocked": await levels_svc.overdue_reviews(session, today=local_today()),
            "thresholds": {
                k: {kk: str(vv) for kk, vv in v.items()} for k, v in levels_svc.ELIGIBILITY.items()
            },
            "requests": [levels_svc.request_out(r) for r in requests],
            "note": (
                "Stufen sind Produktschutz: L1 Ein-Klick, L2 Regelautomatik mit Tagesprüfung, "
                "L3 mit Stichprobe. Keine Stufe öffnet ein Gate; der Runner prüft G1 oder "
                "nicht führenden Buchungskreis selbst."
            ),
        }


@router.get("/automation/metrics", summary="Kennzahlen je Fallklasse und Rechtsträger")
async def automation_metrics(
    request: Request,
    period_from: Annotated[date | None, Query(alias="from")] = None,
    period_to: Annotated[date | None, Query(alias="to")] = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """precision_manual, n_decided, n_auto, error_rate_auto and coverage per class and legal
    entity from ``posting_decision`` (A45 style: operational figures, no proof of safety)."""
    today = local_today()
    window_to = period_to or today
    window_from = period_from or (window_to - timedelta(days=90))
    if window_from > window_to:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Zeitraum ist ungültig (von > bis).")
    async with tenant_tx(request, principal) as session:
        rows = await levels_svc.class_metrics(
            session, window_from=window_from, window_to=window_to, tenant_id=principal.tenant_id
        )
        allowed = [
            r
            for r in rows
            if r.legal_entity_id is None or _entity_allowed(principal, r.legal_entity_id)
        ]
        return {
            "window_from": window_from,
            "window_to": window_to,
            "levels": await levels_svc.current_levels(session),
            "classes": [r.as_dict() for r in allowed],
            "note": (
                "Betriebskennzahlen aus dem Entscheidungsprotokoll; eine hohe Präzision ist "
                "kein Nachweis und keine Freigabe der Automatik (7.4)."
            ),
        }


def _entity_allowed(principal: TenantPrincipal, legal_entity_id: uuid.UUID) -> bool:
    try:
        ensure_legal_entity_allowed(principal, legal_entity_id)
    except ProblemError:
        return False
    return True


@router.post("/automation/level-requests", status_code=201, summary="Stufenanhebung beantragen")
async def create_level_request(
    body: LevelRequestIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await levels_svc.request_level(
            session,
            _actor(principal),
            case_kind=body.case_kind,
            level_to=body.level_to,
            reason=body.reason,
            today=local_today(),
        )
        return levels_svc.request_out(row)


@router.post(
    "/automation/level-requests/{request_id}/approve",
    summary="Stufenanhebung freigeben (andere Person)",
)
async def approve_level_request(
    request_id: uuid.UUID,
    body: LevelDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await levels_svc.decide_level(
            session, _actor(principal), request_id=request_id, approve=True, comment=body.comment
        )
        return levels_svc.request_out(row)


@router.post("/automation/level-requests/{request_id}/reject", summary="Stufenanhebung ablehnen")
async def reject_level_request(
    request_id: uuid.UUID,
    body: LevelDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await levels_svc.decide_level(
            session, _actor(principal), request_id=request_id, approve=False, comment=body.comment
        )
        return levels_svc.request_out(row)


@router.put("/automation/levels", summary="Stufe absenken (sofort, eine Person)")
async def lower_level(
    body: LevelLowerIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, str]:
    async with tenant_tx(request, principal) as session:
        await levels_svc.lower_level(
            session,
            _actor(principal),
            case_kind=body.case_kind,
            level=body.level,
            reason=body.reason,
        )
        return await levels_svc.current_levels(session)


@router.put("/automation/outgoing", summary="Ausgangsautomatik je Mandant (Standard aus)")
async def set_outgoing(
    body: OutgoingSwitchIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, bool]:
    """``tenant_settings.auto_posting_outgoing_enabled`` (L2b, OPEN_QUESTIONS M12-05):
    accounting:approve plus tenant_settings:update, reason and event."""
    from mhvp.platform.models import TenantSettings

    if not principal.has("tenant_settings:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing tenant_settings:update."
        )
    async with tenant_tx(request, principal) as session:
        settings = await session.scalar(select(TenantSettings).with_for_update())
        if settings is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        before = settings.auto_posting_outgoing_enabled
        settings.auto_posting_outgoing_enabled = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=ev.TENANT_AUTO_POSTING_OUTGOING_CHANGED,
            entity_type="tenant_settings",
            entity_id=settings.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled, "reason": body.reason},
            changes={"auto_posting_outgoing_enabled": {"old": before, "new": body.enabled}},
        )
        await session.flush()
        return {"enabled": body.enabled}


@router.post(
    "/transactions/{tx_id}/accept", status_code=201, summary="Ein-Klick-Übernahme (Stufe L1)"
)
async def accept_proposal(
    tx_id: uuid.UUID, body: AcceptIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Books exactly the deterministically verified proposal of the pending round as a manual
    posting of the person (created_by set). Needs level L1 for the case class of the
    transaction (409 ``MHVP-BANK-0023``); history and AI proposals are never accepted here."""
    async with tenant_tx(request, principal) as session:
        row = await matching.lock_for_booking(session, tx_id)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        if row.status is not TransactionStatus.NEW:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Umsatz ist nicht offen.")
        collected, snapshot = await proposals.snapshot(session, row)
        case_kind = levels_svc.classify(collected.tx, snapshot)
        level = (await levels_svc.current_levels(session))[case_kind]
        if levels_svc.level_index(level) < levels_svc.level_index(levels_svc.L1):
            raise ProblemError(
                ErrorCodes.BANK_LEVEL_TOO_LOW,
                detail=f"Klasse {case_kind} steht auf {level}; Ein-Klick braucht L1.",
            )
        pending = await proposals.pending_for(session, row.id)
        shown = pending.proposals if pending is not None else snapshot
        if body.proposal_id is not None and (pending is None or pending.id != body.proposal_id):
            raise ProblemError(ErrorCodes.BANK_DECISION_STALE)
        verified = verifiers.l1_verified(case_kind, shown, row.amount)
        if verified is None:
            raise ProblemError(
                ErrorCodes.BANK_LEVEL_TOO_LOW, detail="Kein deterministisch geprüfter Vorschlag."
            )
        if body.chosen is not None and shown[body.chosen] is not verified:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der gewählte Vorschlag ist nicht der geprüfte."
            )
        chosen = shown.index(verified)
        counter_id = None
        if not verified.get("splits") and verified.get("account_number"):
            ledger, _bank = await matching.ledger_for(session, row)
            counter = await session.scalar(
                select(LedgerAccount).where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.number == str(verified["account_number"]),
                )
            )
            counter_id = counter.id if counter is not None else None
        book_in = BookIn(
            settlements=[
                SettleIn(open_item_id=uuid.UUID(s["open_item_id"]), amount=Decimal(s["amount"]))
                for s in verified.get("splits") or []
            ],
            counter_account_id=counter_id,
            text=body.text,
            proposal_id=pending.id if pending is not None else None,
            chosen=chosen,
        )
        entry = await _book(session, principal, row, book_in)
        return {
            "journal_entry_id": entry.id,
            "number": f"{entry.fiscal_year}-{entry.number}",
            "case_kind": case_kind,
            "level": level,
            "chosen": chosen,
        }


@router.post(
    "/transactions/{tx_id}/correct",
    status_code=201,
    summary="Korrigieren: Storno mit Grundcode und Neubuchung (B03)",
)
async def correct_transaction(
    tx_id: uuid.UUID,
    body: BankCorrectionIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """The posted entry is never edited: the posting in force is reversed with reason code
    and free text and the transaction is posted again in the same transaction, as a manual
    posting of the person with a fresh decision round (ADR 0014, rule M12-04 no. 5)."""
    async with tenant_tx(request, principal) as session:
        row = await _tx(session, tx_id)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        reversal, entry = await review_svc.correct(
            session,
            tx_id=tx_id,
            body=review_svc.CorrectionIn(
                reason=body.reason,
                reason_code=body.reason_code,
                settlements=[(s.open_item_id, s.amount) for s in body.settlements],
                counter_account_id=body.counter_account_id,
                text=body.text,
                discount=body.discount,
            ),
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            today=local_today(),
        )
        return {
            "reversal_id": reversal.id,
            "reversal_number": f"{reversal.fiscal_year}-{reversal.number}",
            "journal_entry_id": entry.id,
            "number": f"{entry.fiscal_year}-{entry.number}",
        }


@router.get("/rule-proposals", summary="Gelernte Regelvorschläge")
async def list_rule_proposals(
    request: Request,
    status: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(BankRuleProposal).order_by(BankRuleProposal.created_at.desc()).limit(200)
        if status:
            query = query.where(BankRuleProposal.status == status)
        rows = [
            r for r in await session.scalars(query) if _entity_allowed(principal, r.legal_entity_id)
        ]
        return [learning_svc.proposal_out(r) for r in rows]


@router.post(
    "/rule-proposals/{proposal_id}/accept",
    status_code=201,
    summary="Regelvorschlag annehmen (verengen erlaubt)",
)
async def accept_rule_proposal(
    proposal_id: uuid.UUID,
    body: RuleProposalAcceptIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> RuleOut:
    """Creates the BankRule in state proposed; the accepting person is its creator and may
    therefore not approve it (existing four eyes path)."""
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, detail="Annahme nur durch eine angemeldete Person."
        )
    async with tenant_tx(request, principal) as session:
        row = await session.get(BankRuleProposal, proposal_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        rule = await learning_svc.accept(
            session,
            proposal_id=proposal_id,
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            name=body.name,
            amount_min=body.amount_min,
            amount_max=body.amount_max,
            tokens=body.purpose_tokens,
        )
        return RuleOut.model_validate(rule)


@router.post("/rule-proposals/{proposal_id}/reject", summary="Regelvorschlag ablehnen (Grund)")
async def reject_rule_proposal(
    proposal_id: uuid.UUID,
    body: ReopenIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, detail="Ablehnung nur durch eine angemeldete Person."
        )
    async with tenant_tx(request, principal) as session:
        row = await session.get(BankRuleProposal, proposal_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        row = await learning_svc.reject(
            session,
            proposal_id=proposal_id,
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            reason=body.reason,
        )
        return learning_svc.proposal_out(row)


@router.get("/auto-posting/reviews", summary="Nachkontrolle automatischer Buchungen")
async def list_reviews(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        items = await review_svc.open_items(session, today=local_today())
        return [i for i in items if _entity_allowed(principal, i["legal_entity_id"])]


@router.post(
    "/auto-posting/reviews/{item_id}", summary="Nachkontrolle abschließen (accounting:review)"
)
async def decide_review(
    item_id: uuid.UUID,
    body: ReviewDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(REVIEW),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await review_svc.decide(
            session,
            item_id=item_id,
            outcome=body.outcome,
            note=body.note,
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
        )
        ensure_legal_entity_allowed(principal, row.legal_entity_id)
        return await review_svc.item_out(session, row, today=local_today())


# Payment runs (M15, 7.5, 6.9.9); export requires G2 ------------------------------------


class PaymentOrderIn(_In):
    invoice_id: uuid.UUID
    property_bank_account_id: uuid.UUID
    execution_date: date


class OrderPatch(_In):
    execution_date: date | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=140)
    # D35: amount and payee IBAN are payment relevant; a change voids all approvals.
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    counterpart_iban: str | None = Field(default=None, min_length=15, max_length=34)


class BatchIn(_In):
    order_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class BankStatusIn(_In):
    status: str = Field(pattern="^(submitted|accepted_by_bank|rejected|executed|returned)$")
    reason: str | None = Field(default=None, max_length=2000)
    bank_transaction_id: uuid.UUID | None = None
    order_ids: list[uuid.UUID] | None = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    invoice_id: uuid.UUID | None
    property_bank_account_id: uuid.UUID
    amount: Decimal
    discount: Decimal
    counterpart_name: str
    counterpart_iban_suffix: str | None = None
    purpose: str
    end_to_end_id: str
    execution_date: date
    status: str
    executed_amount: Decimal | None
    batch_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None
    approvals: int = 0


async def _order_out(session: Any, order: PaymentOrder) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.counterpart_iban_suffix = order.counterpart_iban[-4:]
    out.approvals = len(await payments.valid_approvals(session, order))
    return out


async def _order(session: Any, order_id: uuid.UUID) -> PaymentOrder:
    order = await session.get(PaymentOrder, order_id, with_for_update=True)
    if order is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return order  # type: ignore[no-any-return]


@router.get("/payment-orders", summary="Zahlungsaufträge")
async def list_orders(
    request: Request,
    status: str | None = Query(
        default=None, pattern="^(" + "|".join(s.value for s in OrderStatus) + ")$"
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> list[OrderOut]:
    async with tenant_tx(request, principal) as session:
        query = select(PaymentOrder).order_by(PaymentOrder.execution_date.desc(), PaymentOrder.id)
        if status is not None:
            query = query.where(PaymentOrder.status == OrderStatus(status))
        rows = (await session.scalars(query.limit(limit))).all()
        return [await _order_out(session, o) for o in rows]


@router.post("/payment-orders", status_code=201, summary="Zahlungsauftrag aus Rechnung (Entwurf)")
async def create_order(
    body: PaymentOrderIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> OrderOut:
    from mhvp.accounting.models import Invoice

    async with tenant_tx(request, principal) as session:
        invoice = await session.get(Invoice, body.invoice_id)
        if invoice is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        order = await payments.order_from_invoice(
            session,
            invoice=invoice,
            bank_account_id=body.property_bank_account_id,
            execution_date=body.execution_date,
            user_id=principal.user_id,
        )
        return await _order_out(session, order)


@router.patch("/payment-orders/{order_id}", summary="Auftrag ändern (Freigaben entfallen)")
async def patch_order(
    order_id: uuid.UUID,
    body: OrderPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> OrderOut:
    async with tenant_tx(request, principal) as session:
        order = await _order(session, order_id)
        changed = await payments.change_order(session, order, body.model_dump(exclude_none=True))
        if changed:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="payment_order.approvals_invalidated",
                entity_type="payment_order",
                entity_id=order.id,
                actor_user_id=principal.user_id,
                payload={"fields": sorted(body.model_dump(exclude_none=True))},
            )
        return await _order_out(session, order)


@router.post("/payment-orders/{order_id}/approve", summary="Freigabe (zwei verschiedene Personen)")
async def approve_order(
    order_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> OrderOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Approvals need a person.")
    async with tenant_tx(request, principal) as session:
        order = await _order(session, order_id)
        await payments.approve(session, order, principal.user_id, principal.is_platform_admin)
        return await _order_out(session, order)


@router.post("/payment-orders/{order_id}/cancel", summary="Auftrag verwerfen")
async def cancel_order(
    order_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> OrderOut:
    async with tenant_tx(request, principal) as session:
        order = await _order(session, order_id)
        if order.status not in (OrderStatus.DRAFT, OrderStatus.APPROVED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Eingereichte Aufträge werden über die Bank storniert."
            )
        order.status = OrderStatus.CANCELLED
        await payments.invalidate(session, order)
        return await _order_out(session, order)


@router.post("/payment-batches", status_code=201, summary="Zahlungsdatei erzeugen (G2)")
async def create_batch(
    body: BatchIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
    from mhvp.properties.models import PropertyBankAccount

    await ensure_release_gate_open(
        ReleaseGate.G2, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        orders = [await _order(session, oid) for oid in sorted(set(body.order_ids))]
        banks = {o.property_bank_account_id for o in orders}
        if len(banks) != 1:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Eine Datei je Auftraggeberkonto.")
        for o in orders:
            if (
                o.status is not OrderStatus.APPROVED
                or len({a.user_id for a in await payments.valid_approvals(session, o)}) < 2
            ):
                raise ProblemError(
                    ErrorCodes.GATE_FOUR_EYES, detail="Nur vollständig freigegebene Aufträge."
                )
        from mhvp.accounting.models import LeadingSystem, Ledger

        for ledger_id in {o.ledger_id for o in orders}:
            ledger = await session.get(Ledger, ledger_id)
            if ledger is None or ledger.leading_system is not LeadingSystem.MHVP:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Zahlungsaufträge löst nur das führende System aus (13.1, 6.9.10).",
                )
        bank = await session.get(PropertyBankAccount, banks.pop())
        if bank is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        config = await _bank_config(session, bank.id)
        version = config.pain001_version if config else payments.PAIN_FORMAT
        batch = PaymentBatch(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_bank_account_id=bank.id,
            message_id=f"MHVP{uuid.uuid4().hex[:24]}".upper(),
            format=version,
            status="file_generated",
            transaction_count=len(orders),
            control_sum=payments.control_sum(orders),
        )
        session.add(batch)
        await session.flush()
        xml = payments.pain001(
            batch.message_id, bank.holder, bank.iban, orders, version=version, debtor_bic=bank.bic
        )
        problems = payments.validate_pain001(xml)
        if problems:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Zahlungsdatei fehlerhaft: " + " ".join(problems)
            )
        from mhvp.documents import services as docs
        from mhvp.documents.models import DocumentSource, LinkRole

        document = await docs.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=xml,
            title=f"Zahlungsdatei {batch.message_id} ({version}), nicht übermittelt",
            filename=f"{batch.message_id}.xml",
            mime_type="application/xml",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("legal_entity", bank.legal_entity_id, LinkRole.GENERATED)],
            created_by=principal.user_id,
            scan_for_malware=False,
        )
        batch.document_id, batch.file_sha256 = document.id, payments.file_sha256(xml)
        for o in orders:
            o.status, o.batch_id = OrderStatus.EXPORTED, batch.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_batch.exported",
            entity_type="payment_batch",
            entity_id=batch.id,
            actor_user_id=principal.user_id,
            payload={
                "orders": len(orders),
                "format": batch.format,
                "control_sum": str(batch.control_sum),
                "sha256": batch.file_sha256,
            },
        )
        await session.flush()
        return {**_batch_out(batch), "xml": xml.decode()}


def _batch_out(batch: PaymentBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "message_id": batch.message_id,
        "format": batch.format,
        "status": batch.status,
        "property_bank_account_id": batch.property_bank_account_id,
        "transaction_count": batch.transaction_count,
        "control_sum": str(batch.control_sum),
        "file_sha256": batch.file_sha256,
        "document_id": batch.document_id,
        "submission_channel": batch.submission_channel,
        "submission_reference": batch.submission_reference,
        "submitted_at": batch.submitted_at,
        "submitted_by": batch.submitted_by,
        "created_at": batch.created_at,
    }


async def _bank_config(session: Any, account_id: uuid.UUID) -> PaymentBankConfig | None:
    config: PaymentBankConfig | None = await session.scalar(
        select(PaymentBankConfig).where(PaymentBankConfig.property_bank_account_id == account_id)
    )
    return config


async def _batch(session: Any, batch_id: uuid.UUID, *, lock: bool = False) -> PaymentBatch:
    batch: PaymentBatch | None = await session.get(PaymentBatch, batch_id, with_for_update=lock)
    if batch is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Sammler nicht gefunden.")
    return batch


@router.get("/payment-batches", summary="Zahlungsdateien (Sammler)")
async def list_batches(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(PaymentBatch).order_by(PaymentBatch.created_at.desc(), PaymentBatch.id)
        )
        return [_batch_out(b) for b in rows]


@router.get("/payment-batches/{batch_id}", summary="Sammler mit Download-Protokoll")
async def get_batch(
    batch_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        batch = await _batch(session, batch_id)
        downloads = list(
            await session.scalars(
                select(PaymentFileDownload)
                .where(PaymentFileDownload.batch_id == batch.id)
                .order_by(PaymentFileDownload.downloaded_at)
            )
        )
        return {
            **_batch_out(batch),
            "downloads": [
                {
                    "id": d.id,
                    "user_id": d.user_id,
                    "downloaded_at": d.downloaded_at,
                    "file_sha256": d.file_sha256,
                    "purpose": d.purpose,
                }
                for d in downloads
            ],
        }


@router.get(
    "/payment-batches/{batch_id}/file",
    summary="Zahlungsdatei herunterladen (G2, protokolliert)",
    response_class=Response,
)
async def download_batch_file(
    batch_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    """Hand-out for the manual upload in the online banking (FileDownloadSubmitter). Every
    hand-out is logged with user, time and checksum; the stored bytes are re-checked against
    the checksum recorded at generation, so a manipulated document is never handed out."""
    from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open

    await ensure_release_gate_open(
        ReleaseGate.G2, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        batch = await _batch(session, batch_id, lock=True)
        if batch.document_id is None or not batch.file_sha256:
            raise ProblemError(ErrorCodes.PAYMENT_FILE_STATE, detail="Keine Datei abgelegt.")
        data = await _load_document_bytes(session, request, batch.document_id)
        digest = payments.file_sha256(data)
        if digest != batch.file_sha256 or payments.validate_pain001(data):
            raise ProblemError(
                ErrorCodes.PAYMENT_FILE_STATE,
                detail="Die abgelegte Datei stimmt nicht mit der Prüfsumme des Sammlers überein.",
            )
        session.add(
            PaymentFileDownload(
                tenant_id=principal.tenant_id,
                batch_id=batch.id,
                user_id=principal.user_id,
                file_sha256=digest,
                purpose="download",
                client_ip=(request.client.host if request.client else None),
            )
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_batch.downloaded",
            entity_type="payment_batch",
            entity_id=batch.id,
            actor_user_id=principal.user_id,
            payload={"sha256": digest, "format": batch.format},
        )
        await session.flush()
        return Response(
            content=data,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{batch.message_id}.xml"',
                "X-Content-SHA256": digest,
            },
        )


class PaymentBatchSubmitIn(_In):
    channel: str | None = Field(default=None, pattern="^(file|fints|ebics)$")
    reference: str | None = Field(default=None, max_length=140)


@router.post("/payment-batches/{batch_id}/submit", summary="Einreichung (G2)")
async def submit_batch(
    batch_id: uuid.UUID,
    body: PaymentBatchSubmitIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Channel ``file``: a person confirms the manual upload with the bank reference after at
    least one logged download. ``fints`` and ``ebics`` are scaffolds and refuse
    (MHVP-BANK-0017) until released by the operator (V2)."""
    from mhvp.banking import payment_submitters
    from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open

    await ensure_release_gate_open(
        ReleaseGate.G2, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        batch = await _batch(session, batch_id, lock=True)
        config = await _bank_config(session, batch.property_bank_account_id)
        channel = body.channel or (config.submission_channel if config else "file")
        submitter = payment_submitters.submitter_for(channel)
        if channel == "file":
            downloaded = await session.scalar(
                select(PaymentFileDownload.id).where(PaymentFileDownload.batch_id == batch.id)
            )
            if downloaded is None:
                raise ProblemError(
                    ErrorCodes.PAYMENT_FILE_STATE,
                    detail="Die Datei wurde noch nicht heruntergeladen.",
                )
        data = b""
        if batch.document_id is not None:
            data = await _load_document_bytes(session, request, batch.document_id)
        result = await submitter.submit(
            session, batch, data, user_id=principal.user_id, reference=body.reference
        )
        if result.submitted:
            for o in await session.scalars(
                select(PaymentOrder).where(PaymentOrder.batch_id == batch.id)
            ):
                if o.status is OrderStatus.EXPORTED:
                    o.status = OrderStatus.SUBMITTED
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="payment_batch.submitted",
                entity_type="payment_batch",
                entity_id=batch.id,
                actor_user_id=principal.user_id,
                payload={"channel": result.channel, "reference": result.reference},
            )
        await session.flush()
        return {**_batch_out(batch), "channel": result.channel, "submitted": result.submitted}


class BankConfigIn(_In):
    pain001_version: str = Field(default=payments.PAIN_FORMAT)
    pain008_version: str = Field(default="pain.008.001.02")
    submission_channel: str = Field(default="file", pattern="^(file|fints|ebics)$")
    confirmed_with_bank_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


def _config_out(config: PaymentBankConfig) -> dict[str, Any]:
    return {
        "property_bank_account_id": config.property_bank_account_id,
        "pain001_version": config.pain001_version,
        "pain008_version": config.pain008_version,
        "submission_channel": config.submission_channel,
        "confirmed_with_bank_on": config.confirmed_with_bank_on,
        "notes": config.notes,
        "supported": {
            "pain001": list(payments.PAIN001_VERSIONS),
            "pain008": list(payments.PAIN008_VERSIONS),
            "channels": list(payments.SUBMISSION_CHANNELS),
        },
    }


@router.get("/payment-bank-config/{account_id}", summary="Zahlungsformat je Bankkonto")
async def get_bank_config(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        config = await _bank_config(session, account_id)
        if config is None:
            config = PaymentBankConfig(  # defaults, not stored
                tenant_id=principal.tenant_id,
                property_bank_account_id=account_id,
                pain001_version=payments.PAIN_FORMAT,
                pain008_version=payments.PAIN008_VERSIONS[0],
                submission_channel="file",
            )
        return _config_out(config)


@router.put("/payment-bank-config/{account_id}", summary="Zahlungsformat je Bankkonto setzen")
async def put_bank_config(
    account_id: uuid.UUID,
    body: BankConfigIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Operator input of the version and channel agreed with the bank (M15-01). Only the
    versions the platform can generate and validate are accepted."""
    from mhvp.properties.models import PropertyBankAccount

    if body.pain001_version not in payments.PAIN001_VERSIONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="pain.001-Version nicht unterstützt.")
    if body.pain008_version not in payments.PAIN008_VERSIONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="pain.008-Version nicht unterstützt.")
    async with tenant_tx(request, principal) as session:
        if await session.get(PropertyBankAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankkonto nicht gefunden.")
        config = await _bank_config(session, account_id)
        if config is None:
            config = PaymentBankConfig(
                tenant_id=principal.tenant_id,
                property_bank_account_id=account_id,
                created_by=principal.user_id,
            )
            session.add(config)
        for key, value in body.model_dump().items():
            setattr(config, key, value)
        config.updated_by = principal.user_id
        await session.flush()
        return _config_out(config)


@router.post("/payment-batches/{batch_id}/bank-status", summary="Bankrückmeldung erfassen")
async def bank_status(
    batch_id: uuid.UUID,
    body: BankStatusIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> list[OrderOut]:
    """Export or submission alone never settles an invoice; only proven execution does (D06)."""
    async with tenant_tx(request, principal) as session:
        batch = await session.get(PaymentBatch, batch_id, with_for_update=True)
        if batch is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        orders = (
            await session.scalars(select(PaymentOrder).where(PaymentOrder.batch_id == batch.id))
        ).all()
        if body.order_ids:
            orders = [o for o in orders if o.id in set(body.order_ids)]
        batch.bank_response = [
            *batch.bank_response,
            {"status": body.status, "reason": body.reason, "at": datetime.now(UTC).isoformat()},
        ]
        for order in orders:
            if body.status in ("submitted", "accepted_by_bank"):
                if order.status in (OrderStatus.EXPORTED, OrderStatus.SUBMITTED):
                    order.status = OrderStatus(body.status)
            elif body.status == "rejected":
                if order.status in (OrderStatus.EXECUTED, OrderStatus.PARTIALLY_EXECUTED):
                    raise ProblemError(
                        ErrorCodes.CONFLICT,
                        detail="Ausgeführte Aufträge werden über die Rückgabe korrigiert.",
                    )
                if order.status is OrderStatus.REJECTED:
                    continue
                order.status = OrderStatus.REJECTED  # D37: the payable stays fully open
                await emit(
                    session,
                    tenant_id=principal.tenant_id,
                    type="payment_order.rejected",
                    entity_type="payment_order",
                    entity_id=order.id,
                    actor_user_id=principal.user_id,
                    payload={"reason": body.reason, "open_amount": str(order.amount)},
                )
            elif body.status == "executed":
                if body.bank_transaction_id is None:
                    raise ProblemError(
                        ErrorCodes.VALIDATION, detail="Ausführung nur mit Bankumsatz als Nachweis."
                    )
                before = order.status
                await payments.record_execution(
                    session,
                    order,
                    bank_transaction_id=body.bank_transaction_id,
                    user_id=principal.user_id,
                )
                if before is not order.status and order.status is OrderStatus.PARTIALLY_EXECUTED:
                    # D37: only the confirmed part is settled; the rest stays open with a note.
                    await emit(
                        session,
                        tenant_id=principal.tenant_id,
                        type="payment_order.partially_executed",
                        entity_type="payment_order",
                        entity_id=order.id,
                        actor_user_id=principal.user_id,
                        payload={
                            "reason": body.reason,
                            "executed_amount": str(order.executed_amount),
                            "open_amount": str(order.amount - (order.executed_amount or 0)),
                        },
                    )
            elif body.status == "returned":
                reversal = await payments.record_return(
                    session,
                    order,
                    reason=body.reason,
                    bank_transaction_id=body.bank_transaction_id,
                    user_id=principal.user_id,
                    booking_date=local_today(),
                )
                if reversal is not None:  # D38: reversal, never an edit of the posting
                    await emit(
                        session,
                        tenant_id=principal.tenant_id,
                        type="payment_order.returned",
                        entity_type="payment_order",
                        entity_id=order.id,
                        actor_user_id=principal.user_id,
                        payload={
                            "reason": body.reason,
                            "reversal_id": str(reversal.id),
                            "reversed_entry_id": str(reversal.reverses_id),
                            "bank_transaction_id": (
                                str(body.bank_transaction_id) if body.bank_transaction_id else None
                            ),
                        },
                    )
        batch.status = body.status
        await session.flush()
        return [await _order_out(session, o) for o in orders]


# --- finAPI (M11-finapi, read only): connect, assign, refresh on click, disconnect --------

finapi_router = APIRouter(prefix="/banking/finapi", tags=["Bank"])


class FinApiConfigIn(_In):
    client_id: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=1, max_length=200)
    mandator_id: str | None = Field(default=None, max_length=64)
    # Empty: the default host of the chosen data center from the settings
    # (``MHVP_FINAPI_BASE_URL_SANDBOX``/``_LIVE``, [laut finAPI-Doku]).
    base_url: str | None = Field(default=None, max_length=300)
    sandbox: bool = True
    # M11-finapi Stage 2: scheduled daily fetch, default off; omitted keeps the current value.
    auto_fetch_enabled: bool | None = None


class FinApiConfigOut(BaseModel):
    configured: bool
    base_url: str | None = None
    mandator_id: str | None = None
    sandbox: bool | None = None
    auto_fetch_enabled: bool = False


class FinApiAccountOut(BaseModel):
    id: uuid.UUID
    finapi_account_id: str
    account_holder_name: str | None
    account_type: str | None
    account_name: str | None
    iban_suffix: str | None
    property_bank_account_id: uuid.UUID | None
    balance_booked: Decimal | None
    balance_available: Decimal | None
    balance_currency: str | None
    balance_as_of: datetime | None
    balance_fetched_at: datetime | None
    last_transactions_fetch_at: datetime | None


class FinApiConnectionOut(BaseModel):
    id: uuid.UUID
    bank_connection_id: uuid.UUID
    bank_name: str
    status: ConnectionStatus
    web_form_url: str | None
    web_form_status: str | None
    consent_valid_until: date | None
    last_error: str | None
    auto_update_enabled: bool
    accounts: list[FinApiAccountOut]


class WebFormRefIn(_In):
    bank_name: str = Field(min_length=1, max_length=200)


class AssignAccountIn(_In):
    property_bank_account_id: uuid.UUID


async def _finapi_credentials(session: Any, tenant_id: uuid.UUID) -> FinApiTenantConfig:
    cfg: FinApiTenantConfig | None = await session.scalar(select(FinApiTenantConfig))
    if cfg is None:
        raise ProblemError(ErrorCodes.FINAPI_NOT_CONFIGURED)
    return cfg


def _finapi_client(
    cfg: FinApiTenantConfig, fa: FinApiConnection | None = None
) -> finapi_client.FinApiClient:
    """Client with the tenant's application credentials and, when `fa` carries a finAPI user
    identity, that connection's user token (OAuth2 password grant). Shared with
    `mhvp.banking.tasks` so the job and the click use the same credentials path."""
    return finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            base_url=cfg.base_url,
            mandator_id=cfg.mandator_id,
            user_id=fa.finapi_user_id if fa else None,
            user_password=fa.finapi_user_password if fa else None,
            sandbox=cfg.sandbox,
        )
    )


def _ensure_finapi_user(cfg: FinApiTenantConfig, fa: FinApiConnection) -> None:
    """Creates the technical finAPI user of this connection once (`POST /users`, auto update
    off) and stores id and generated password encrypted on the connection. Never a bank
    credential (rule M11-04); the WebForm afterwards runs under this user's token."""
    if fa.finapi_user_id:
        return
    user = _finapi_client(cfg).create_user()
    fa.finapi_user_id = user.user_id
    fa.finapi_user_password = user.password


def _can_see_unassigned(principal: TenantPrincipal) -> bool:
    return principal.has("banking:approve") or principal.has("tenant_settings:update")


async def _account_out(
    session: Any, link: FinApiAccountLink, principal: TenantPrincipal
) -> FinApiAccountOut | None:
    if link.property_bank_account_id is None and not _can_see_unassigned(principal):
        return None  # 6.9.7 / prompt section 4: unassigned accounts stay hidden

    iban_suffix = None
    if link.iban_fingerprint and link.account_name:
        iban_suffix = None  # fingerprint is not reversible; suffix comes only from source data
    return FinApiAccountOut(
        id=link.id,
        finapi_account_id=link.finapi_account_id,
        account_holder_name=link.account_holder_name,
        account_type=link.account_type,
        account_name=link.account_name,
        iban_suffix=iban_suffix,
        property_bank_account_id=link.property_bank_account_id,
        balance_booked=link.balance_booked,
        balance_available=link.balance_available,
        balance_currency=link.balance_currency,
        balance_as_of=link.balance_as_of,
        balance_fetched_at=link.balance_fetched_at,
        last_transactions_fetch_at=link.last_transactions_fetch_at,
    )


@finapi_router.put("/config", summary="finAPI-Zugangsdaten hinterlegen (Einstellungen, Bank)")
async def set_finapi_config(
    body: FinApiConfigIn, request: Request, principal: TenantPrincipal = Depends(FINAPI_SETTINGS)
) -> FinApiConfigOut:
    async with tenant_tx(request, principal) as session:
        cfg = await session.scalar(select(FinApiTenantConfig))
        if cfg is None:
            cfg = FinApiTenantConfig(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(cfg)
        cfg.client_id = body.client_id
        cfg.client_secret = body.client_secret
        cfg.mandator_id = body.mandator_id
        settings = request.app.state.settings
        base_url = (body.base_url or "").strip()
        if base_url and not base_url.startswith("https://"):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die finAPI-Basis-URL muss mit https:// beginnen."
            )
        cfg.base_url = base_url.rstrip("/") or finapi_client.default_base_url(
            body.sandbox,
            sandbox_url=settings.finapi_base_url_sandbox,
            live_url=settings.finapi_base_url_live,
        )
        cfg.sandbox = body.sandbox
        if body.auto_fetch_enabled is not None:
            cfg.auto_fetch_enabled = body.auto_fetch_enabled
        cfg.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi.config_changed",
            entity_type="finapi_tenant_config",
            entity_id=cfg.id,
            actor_user_id=principal.user_id,
            payload={
                "base_url": cfg.base_url,
                "sandbox": cfg.sandbox,
                "auto_fetch_enabled": cfg.auto_fetch_enabled,
            },
        )
        await session.flush()
        return FinApiConfigOut(
            configured=True,
            base_url=cfg.base_url,
            mandator_id=cfg.mandator_id,
            sandbox=cfg.sandbox,
            auto_fetch_enabled=cfg.auto_fetch_enabled,
        )


@finapi_router.get("/config", summary="finAPI-Konfigurationsstatus (ohne Zugangsdaten)")
async def get_finapi_config(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> FinApiConfigOut:
    async with tenant_tx(request, principal) as session:
        cfg = await session.scalar(select(FinApiTenantConfig))
        if cfg is None:
            return FinApiConfigOut(configured=False)
        return FinApiConfigOut(
            configured=True,
            base_url=cfg.base_url,
            mandator_id=cfg.mandator_id,
            sandbox=cfg.sandbox,
            auto_fetch_enabled=cfg.auto_fetch_enabled,
        )


@finapi_router.post("/connections", status_code=201, summary="Bankverbindung anlegen (WebForm)")
async def create_finapi_connection(
    body: WebFormRefIn, request: Request, principal: TenantPrincipal = Depends(BANKING_APPROVE)
) -> FinApiConnectionOut:
    """Starts the documented WebForm import (docs/integrations/finapi.md section 2). The
    browser redirect that follows is not itself an authorization result: `get_connection`
    below re-checks the WebForm and bank connection status with the provider before any
    account is trusted (banking master prompt section 6)."""
    async with tenant_tx(request, principal) as session:
        cfg = await _finapi_credentials(session, principal.tenant_id)
        conn = BankConnection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            connector=Connector.AGGREGATOR_FINAPI,
            bank_name=body.bank_name,
            status=ConnectionStatus.NOT_CONFIGURED,
        )
        session.add(conn)
        await session.flush()
        fa = FinApiConnection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            bank_connection_id=conn.id,
            responsible_user_id=principal.user_id,
            auto_update_enabled=False,  # provider auto update stays off (master prompt section 2)
        )
        session.add(fa)
        _ensure_finapi_user(cfg, fa)
        web_form = _finapi_client(cfg, fa).create_bank_connection_import_web_form()
        conn.status = ConnectionStatus.WEB_FORM_PENDING
        fa.web_form_id = web_form.web_form_id
        fa.web_form_url = web_form.url
        fa.web_form_status = web_form.status
        fa.finapi_bank_connection_id = web_form.finapi_bank_connection_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi_connection.created",
            entity_type="bank_connection",
            entity_id=conn.id,
            actor_user_id=principal.user_id,
            payload={"web_form_id": web_form.web_form_id},
        )
        await session.flush()
        return FinApiConnectionOut(
            id=fa.id,
            bank_connection_id=conn.id,
            bank_name=conn.bank_name,
            status=conn.status,
            web_form_url=fa.web_form_url,
            web_form_status=fa.web_form_status,
            consent_valid_until=fa.consent_valid_until,
            last_error=fa.last_error,
            auto_update_enabled=fa.auto_update_enabled,
            accounts=[],
        )


@finapi_router.get("/connections", summary="Bankverbindungen (finAPI) mit Konten")
async def list_finapi_connections(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[FinApiConnectionOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(FinApiConnection).join(
                    BankConnection, BankConnection.id == FinApiConnection.bank_connection_id
                )
            )
        ).all()
        out = []
        for fa in rows:
            conn = await session.get(BankConnection, fa.bank_connection_id)
            if conn is None:  # pragma: no cover
                continue
            links = (
                await session.scalars(
                    select(FinApiAccountLink).where(FinApiAccountLink.finapi_connection_id == fa.id)
                )
            ).all()
            accounts = [
                a for a in [await _account_out(session, link, principal) for link in links] if a
            ]
            out.append(
                FinApiConnectionOut(
                    id=fa.id,
                    bank_connection_id=conn.id,
                    bank_name=conn.bank_name,
                    status=conn.status,
                    web_form_url=fa.web_form_url,
                    web_form_status=fa.web_form_status,
                    consent_valid_until=fa.consent_valid_until,
                    last_error=fa.last_error,
                    auto_update_enabled=fa.auto_update_enabled,
                    accounts=accounts,
                )
            )
        return out


@finapi_router.post(
    "/connections/{finapi_connection_id}/check",
    summary="WebForm-/Verbindungsstatus serverseitig prüfen",
)
async def check_finapi_connection(
    finapi_connection_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinApiConnectionOut:
    """A browser return from the WebForm is not proof of success (master prompt section 6):
    this endpoint re-reads the WebForm and, once it finished, the bank connection and its
    accounts directly from finAPI with the tenant's own credentials."""
    async with tenant_tx(request, principal) as session:
        fa = await session.get(FinApiConnection, finapi_connection_id, with_for_update=True)
        if fa is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        conn = await session.get(BankConnection, fa.bank_connection_id, with_for_update=True)
        if conn is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        cfg = await _finapi_credentials(session, principal.tenant_id)
        client = _finapi_client(cfg, fa)
        if fa.web_form_id and conn.status in (
            ConnectionStatus.WEB_FORM_PENDING,
            ConnectionStatus.UPDATE_REQUIRED,
        ):
            web_form = client.get_web_form(fa.web_form_id)
            fa.web_form_status = web_form.status
            fa.finapi_bank_connection_id = (
                web_form.finapi_bank_connection_id or fa.finapi_bank_connection_id
            )
            if web_form.status not in ("FINISHED",):
                await session.flush()
                return await _finapi_connection_out(session, fa, conn, principal)
        if fa.finapi_bank_connection_id:
            details = client.get_bank_connection(fa.finapi_bank_connection_id)
            fa.last_update_status = str(details.get("status") or fa.last_update_status)
            fa.last_error = details.get("errorMessage")
            conn.status = ConnectionStatus.ACTIVE if not fa.last_error else ConnectionStatus.ERROR
            conn.error_message = fa.last_error
            accounts = client.list_accounts(bank_connection_id=fa.finapi_bank_connection_id)
            for acc in accounts:
                link = await session.scalar(
                    select(FinApiAccountLink).where(
                        FinApiAccountLink.finapi_connection_id == fa.id,
                        FinApiAccountLink.finapi_account_id == acc.account_id,
                    )
                )
                if link is None:
                    link = FinApiAccountLink(
                        tenant_id=principal.tenant_id,
                        created_by=principal.user_id,
                        finapi_connection_id=fa.id,
                        finapi_account_id=acc.account_id,
                    )
                    session.add(link)
                from mhvp.core import crypto as _crypto

                link.iban_fingerprint = _crypto.fingerprint(acc.iban) if acc.iban else None
                link.account_holder_name = acc.account_holder_name
                link.account_type = acc.account_type
                link.account_name = acc.account_name
                link.balance_booked = Decimal(acc.balance_booked) if acc.balance_booked else None
                link.balance_available = (
                    Decimal(acc.balance_available) if acc.balance_available else None
                )
                link.balance_currency = acc.balance_currency
                link.balance_fetched_at = datetime.now(UTC)
                await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="finapi_connection.checked",
                entity_type="bank_connection",
                entity_id=conn.id,
                actor_user_id=principal.user_id,
                payload={"status": conn.status.value, "accounts": len(accounts)},
            )
        await session.flush()
        return await _finapi_connection_out(session, fa, conn, principal)


async def _finapi_connection_out(
    session: Any, fa: FinApiConnection, conn: BankConnection, principal: TenantPrincipal
) -> FinApiConnectionOut:
    links = (
        await session.scalars(
            select(FinApiAccountLink).where(FinApiAccountLink.finapi_connection_id == fa.id)
        )
    ).all()
    accounts = [a for a in [await _account_out(session, link, principal) for link in links] if a]
    return FinApiConnectionOut(
        id=fa.id,
        bank_connection_id=conn.id,
        bank_name=conn.bank_name,
        status=conn.status,
        web_form_url=fa.web_form_url,
        web_form_status=fa.web_form_status,
        consent_valid_until=fa.consent_valid_until,
        last_error=fa.last_error,
        auto_update_enabled=fa.auto_update_enabled,
        accounts=accounts,
    )


@finapi_router.post(
    "/connections/{finapi_connection_id}/reauthorize",
    summary="Erneute Freigabe (WebForm erneut starten)",
)
async def reauthorize_finapi_connection(
    finapi_connection_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinApiConnectionOut:
    async with tenant_tx(request, principal) as session:
        fa = await session.get(FinApiConnection, finapi_connection_id, with_for_update=True)
        if fa is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        conn = await session.get(BankConnection, fa.bank_connection_id, with_for_update=True)
        if conn is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        cfg = await _finapi_credentials(session, principal.tenant_id)
        _ensure_finapi_user(cfg, fa)
        web_form = _finapi_client(cfg, fa).create_bank_connection_import_web_form()
        fa.web_form_id = web_form.web_form_id
        fa.web_form_url = web_form.url
        fa.web_form_status = web_form.status
        conn.status = ConnectionStatus.UPDATE_REQUIRED
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi_connection.reauthorize_started",
            entity_type="bank_connection",
            entity_id=conn.id,
            actor_user_id=principal.user_id,
        )
        await session.flush()
        return await _finapi_connection_out(session, fa, conn, principal)


@finapi_router.post(
    "/accounts/{link_id}/assign", summary="Konto einem Buchungskreis/Objekt zuordnen"
)
async def assign_finapi_account(
    link_id: uuid.UUID,
    body: AssignAccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinApiAccountOut:
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        link = await session.get(FinApiAccountLink, link_id, with_for_update=True)
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        target = await session.get(PropertyBankAccount, body.property_bank_account_id)
        if target is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kein passendes internes Konto.")
        link.property_bank_account_id = target.id
        link.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi_account.assigned",
            entity_type="finapi_account_link",
            entity_id=link.id,
            actor_user_id=principal.user_id,
            payload={"property_bank_account_id": str(target.id)},
        )
        await session.flush()
        out = await _account_out(session, link, principal)
        if out is None:  # pragma: no cover - principal just assigned/approved this link
            raise ProblemError(ErrorCodes.INTERNAL)
        return out


class FetchRangeIn(_In):
    """Optional date range for a manual fetch (Stage 2). The provider is never asked to
    filter by date (docs/integrations/finapi.md, "zu prüfen"); the range only bounds what is
    kept from the rows finAPI actually returned -- nothing is synthesized for a gap the
    provider does not cover."""

    since: date | None = None
    until: date | None = None


_EMPTY_FETCH_RANGE = FetchRangeIn()


async def _queue_finapi_fetch(
    session: Any,
    *,
    principal: TenantPrincipal,
    link: FinApiAccountLink,
    conn: BankConnection,
    body: FetchRangeIn,
) -> BankSyncRun:
    run = BankSyncRun(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        connection_id=conn.id,
        property_bank_account_id=link.property_bank_account_id,
        source="aggregator_finapi",
        status="queued",
        counts={},
    )
    session.add(run)
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="bank_sync_run.queued",
        entity_type="bank_sync_run",
        entity_id=run.id,
        actor_user_id=principal.user_id,
        payload={
            "trigger": "user_click",
            "finapi_account_link_id": str(link.id),
            "since": body.since.isoformat() if body.since else None,
            "until": body.until.isoformat() if body.until else None,
        },
    )
    await session.flush()
    return run


def _fetch_ready_or_raise(
    fa: FinApiConnection | None, conn: BankConnection | None
) -> tuple[FinApiConnection, BankConnection]:
    if (
        fa is None
        or conn is None
        or conn.status not in (ConnectionStatus.ACTIVE, ConnectionStatus.ERROR)
    ):
        raise ProblemError(ErrorCodes.FINAPI_STATE, detail="Bankverbindung ist nicht abrufbereit.")
    return fa, conn


@finapi_router.post(
    "/accounts/{link_id}/fetch", summary="Umsätze abrufen (asynchron, nur auf Klick, mit Zeitraum)"
)
async def fetch_finapi_transactions(
    link_id: uuid.UUID,
    request: Request,
    body: FetchRangeIn = _EMPTY_FETCH_RANGE,
    principal: TenantPrincipal = Depends(UPDATE),
) -> SyncRunOut:
    """A real click only: this never runs on a schedule by itself (master prompt section 2;
    the tenant-wide scheduled fetch, Stage 2, is a separate opt-in flag, see `/config`). The
    fetch itself completes asynchronously in the existing Celery worker
    (`banking.finapi_fetch`); `body.since`/`body.until` bound what is kept, also historical,
    as far as the provider actually delivers (rule 0.1.3)."""
    from mhvp.banking.tasks import finapi_fetch

    async with tenant_tx(request, principal) as session:
        link = await session.get(FinApiAccountLink, link_id)
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if link.property_bank_account_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Konto ist noch keinem Buchungskreis zugeordnet."
            )
        fa = await session.get(FinApiConnection, link.finapi_connection_id)
        conn = await session.get(BankConnection, fa.bank_connection_id) if fa else None
        _, conn = _fetch_ready_or_raise(fa, conn)
        run = await _queue_finapi_fetch(
            session, principal=principal, link=link, conn=conn, body=body
        )
        run_id = run.id
        tenant_id = principal.tenant_id
        bank_account_id = link.property_bank_account_id
    finapi_fetch.delay(
        str(tenant_id),
        str(run_id),
        str(link_id),
        body.since.isoformat() if body.since else None,
        body.until.isoformat() if body.until else None,
    )
    return SyncRunOut(
        id=run_id,
        source="aggregator_finapi",
        status="queued",
        counts={},
        errors=[],
        property_bank_account_id=bank_account_id,
        document_id=None,
    )


@finapi_router.post(
    "/connections/{finapi_connection_id}/fetch",
    summary="Umsätze für alle zugeordneten Konten dieser Bank abrufen",
)
async def fetch_finapi_connection_transactions(
    finapi_connection_id: uuid.UUID,
    request: Request,
    body: FetchRangeIn = _EMPTY_FETCH_RANGE,
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[SyncRunOut]:
    """Per bank fetch (Stage 2): queues one run per account already assigned to a Buchungskreis
    under this connection; unassigned accounts are skipped (nothing to post transactions to
    yet), same date-range semantics as the per-account endpoint."""
    from mhvp.banking.tasks import finapi_fetch

    async with tenant_tx(request, principal) as session:
        fa = await session.get(FinApiConnection, finapi_connection_id)
        conn = await session.get(BankConnection, fa.bank_connection_id) if fa else None
        fa, conn = _fetch_ready_or_raise(fa, conn)
        links = (
            await session.scalars(
                select(FinApiAccountLink).where(
                    FinApiAccountLink.finapi_connection_id == fa.id,
                    FinApiAccountLink.property_bank_account_id.is_not(None),
                )
            )
        ).all()
        queued: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
        for link in links:
            run = await _queue_finapi_fetch(
                session, principal=principal, link=link, conn=conn, body=body
            )
            queued.append((run.id, link.id, link.property_bank_account_id))  # type: ignore[arg-type]
        tenant_id = principal.tenant_id
    for run_id, link_id, _bank_account_id in queued:
        finapi_fetch.delay(
            str(tenant_id),
            str(run_id),
            str(link_id),
            body.since.isoformat() if body.since else None,
            body.until.isoformat() if body.until else None,
        )
    return [
        SyncRunOut(
            id=run_id,
            source="aggregator_finapi",
            status="queued",
            counts={},
            errors=[],
            property_bank_account_id=bank_account_id,
            document_id=None,
        )
        for run_id, _link_id, bank_account_id in queued
    ]


@finapi_router.post("/connections/{finapi_connection_id}/disconnect", summary="Verbindung trennen")
async def disconnect_finapi_connection(
    finapi_connection_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinApiConnectionOut:
    """Blocks further use locally first (master prompt section 12). The provider side
    (revoking the finAPI bank connection) uses an endpoint marked "zu prüfen" in
    docs/integrations/finapi.md, so this only records that the provider side is unconfirmed;
    it never claims the bank-side consent was revoked."""
    async with tenant_tx(request, principal) as session:
        fa = await session.get(FinApiConnection, finapi_connection_id, with_for_update=True)
        if fa is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        conn = await session.get(BankConnection, fa.bank_connection_id, with_for_update=True)
        if conn is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        conn.status = ConnectionStatus.DISABLED
        provider_note = (
            "Provider-Trennung nicht bestätigt (Endpunkt zu prüfen, docs/integrations/finapi.md)."
        )
        fa.last_error = provider_note
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi_connection.disconnected",
            entity_type="bank_connection",
            entity_id=conn.id,
            actor_user_id=principal.user_id,
            payload={"provider_note": provider_note},
        )
        await session.flush()
        return await _finapi_connection_out(session, fa, conn, principal)


# --- Invoice to transaction matching (M11-finapi Stage 3) -------------------------------


class InvoiceMatchOut(BaseModel):
    id: uuid.UUID
    bank_transaction_id: uuid.UUID
    match_basis: str
    amount: Decimal


class ProposePaymentIn(_In):
    """Only used when `match` found no candidate transaction; creates a draft `PaymentOrder`
    (gate G2 stays closed, "vorbereitet, nicht ausgeführt")."""

    bank_account_id: uuid.UUID
    execution_date: date


class InvoiceMatchResultOut(BaseModel):
    invoice_id: uuid.UUID
    matches: list[InvoiceMatchOut]
    proposal: OrderOut | None = None
    proposal_note: str | None = None


@router.post(
    "/invoice-matching/{invoice_id}/match",
    summary="Rechnung mit Bankumsätzen abgleichen (Betrag + Rechnungsnummer/IBAN)",
)
async def match_invoice_transactions(
    invoice_id: uuid.UUID,
    request: Request,
    body: ProposePaymentIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> InvoiceMatchResultOut:
    """Finds and links matching imported bank transactions (evidence only, never books by
    itself). When nothing matches and `body` names a bank account and execution date, a draft
    payment PROPOSAL is created via the existing `mhvp.banking.payments.order_from_invoice`;
    gate G2 stays closed, so this never submits or initiates a payment (rule 0.1.6)."""
    from mhvp.accounting.models import Invoice
    from mhvp.banking import invoice_matching

    async with tenant_tx(request, principal) as session:
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechnung nicht gefunden.")
        created = await invoice_matching.match_invoice(
            session, invoice=invoice, user_id=principal.user_id
        )
        all_links = await invoice_matching.existing_links(session, invoice_id)
        matches = [
            InvoiceMatchOut(
                id=row.id,
                bank_transaction_id=row.bank_transaction_id,
                match_basis=row.match_basis.value,
                amount=row.amount,
            )
            for row in all_links
        ]
        proposal_out = None
        proposal_note = None
        if not all_links:
            if body is not None:
                order = await invoice_matching.propose_payment(
                    session,
                    invoice=invoice,
                    bank_account_id=body.bank_account_id,
                    execution_date=body.execution_date,
                    user_id=principal.user_id,
                )
                proposal_out = await _order_out(session, order)
                proposal_note = "vorbereitet, nicht ausgeführt"
            else:
                proposal_note = (
                    "Kein passender Bankumsatz gefunden; für einen Zahlungsvorschlag "
                    "bank_account_id und execution_date angeben."
                )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.matched",
            entity_type="invoice",
            entity_id=invoice_id,
            actor_user_id=principal.user_id,
            payload={
                "new_links": len(created),
                "total_links": len(all_links),
                "proposal_created": proposal_out is not None,
            },
        )
        await session.flush()
        return InvoiceMatchResultOut(
            invoice_id=invoice_id,
            matches=matches,
            proposal=proposal_out,
            proposal_note=proposal_note,
        )


@router.get(
    "/invoice-matching/{invoice_id}",
    summary="Verknüpfte Bankumsätze einer Rechnung (nur lesen)",
)
async def get_invoice_matches(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[InvoiceMatchOut]:
    from mhvp.banking import invoice_matching

    async with tenant_tx(request, principal) as session:
        rows = await invoice_matching.existing_links(session, invoice_id)
        return [
            InvoiceMatchOut(
                id=row.id,
                bank_transaction_id=row.bank_transaction_id,
                match_basis=row.match_basis.value,
                amount=row.amount,
            )
            for row in rows
        ]


# --- Bank account selection (Bankkontenauswahl): list, assign, defaults; no payments (G2) ---


class RecentTransactionOut(BaseModel):
    id: uuid.UUID
    booking_date: date
    amount: Decimal
    counterpart_name: str | None
    purpose: str | None


class AccountAssignmentOut(BaseModel):
    property_id: uuid.UUID
    property_number: str | None
    property_name: str | None
    purpose: AccountPurpose
    is_default: bool


class BankAccountListOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    property_number: str | None
    property_name: str | None
    legal_entity_id: uuid.UUID
    legal_entity_name: str | None
    legal_entity_kind: str | None
    kind: str
    iban_masked: str
    bic: str | None
    bank_name: str | None
    holder: str
    valid_from: date
    valid_to: date | None
    source: str
    balance: Decimal | None
    balance_as_of: datetime | None
    balance_source: str | None
    default_for_legal_entity: bool
    assignments: list[AccountAssignmentOut]
    recent_transactions: list[RecentTransactionOut]


def account_list_out(item: account_selection.AccountListItem) -> BankAccountListOut:
    return BankAccountListOut(
        id=item.id,
        property_id=item.property_id,
        property_number=item.property_number,
        property_name=item.property_name,
        legal_entity_id=item.legal_entity_id,
        legal_entity_name=item.legal_entity_name,
        legal_entity_kind=item.legal_entity_kind,
        kind=item.kind,
        iban_masked=item.iban_masked,
        bic=item.bic,
        bank_name=item.bank_name,
        holder=item.holder,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        source=item.source,
        balance=item.balance,
        balance_as_of=item.balance_as_of,
        balance_source=item.balance_source,
        default_for_legal_entity=item.default_for_legal_entity,
        assignments=[AccountAssignmentOut(**vars(a)) for a in item.assignments],
        recent_transactions=[RecentTransactionOut(**vars(t)) for t in item.recent_transactions],
    )


class AssignPropertyIn(_In):
    property_id: uuid.UUID
    purpose: AccountPurpose = AccountPurpose.GENERAL
    is_default: bool = False


class LegalEntityDefaultIn(_In):
    is_default: bool


@router.get(
    "/accounts",
    summary="Bankkonten je Objekt und Rechtsträger (mit Kontostand und letzten Umsätzen)",
)
async def list_bank_accounts(
    request: Request,
    property_id: uuid.UUID | None = None,
    legal_entity_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=account_selection.MAX_ACCOUNTS),
    principal: TenantPrincipal = Depends(READ),
) -> list[BankAccountListOut]:
    async with tenant_tx(request, principal) as session:
        items = await account_selection.list_accounts(
            session, property_id=property_id, legal_entity_id=legal_entity_id, q=q, limit=limit
        )
        return [account_list_out(i) for i in items]


@router.put(
    "/accounts/{bank_account_id}/assignments",
    summary="Konto einem Objekt zuordnen, optional als Standard (Hausgeld/Miete)",
)
async def assign_bank_account(
    bank_account_id: uuid.UUID,
    body: AssignPropertyIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> BankAccountListOut:
    async with tenant_tx(request, principal) as session:
        await account_selection.assign_to_property(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            account_id=bank_account_id,
            property_id=body.property_id,
            purpose=body.purpose,
            is_default=body.is_default,
        )
        return await _single_account_out(session, bank_account_id)


@router.delete(
    "/accounts/{bank_account_id}/assignments/{property_id}",
    status_code=204,
    summary="Zuordnung Konto zu Objekt lösen",
)
async def unassign_bank_account(
    bank_account_id: uuid.UUID,
    property_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        await account_selection.unassign_from_property(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            account_id=bank_account_id,
            property_id=property_id,
        )


@router.put(
    "/accounts/{bank_account_id}/legal-entity-default",
    summary="Standardkonto des Rechtsträgers markieren oder aufheben",
)
async def set_legal_entity_default(
    bank_account_id: uuid.UUID,
    body: LegalEntityDefaultIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> BankAccountListOut:
    async with tenant_tx(request, principal) as session:
        await account_selection.set_legal_entity_default(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            account_id=bank_account_id,
            is_default=body.is_default,
        )
        return await _single_account_out(session, bank_account_id)


async def _single_account_out(session: Any, bank_account_id: uuid.UUID) -> BankAccountListOut:
    from mhvp.properties.models import PropertyBankAccount

    account = await session.get(PropertyBankAccount, bank_account_id)
    if account is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    items = await account_selection.list_accounts(session, legal_entity_id=account.legal_entity_id)
    for item in items:
        if item.id == bank_account_id:
            return account_list_out(item)
    raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # pragma: no cover


# --- Bank specific CSV import (M11-02, docs/integrations/bank-csv.md) ----------------------

from mhvp.banking import csv_formats  # noqa: E402
from mhvp.banking.models import BankCsvMapping  # noqa: E402


class CsvColumnMappingIn(_In):
    booking_date: str
    amount: str | None = None
    amount_debit: str | None = None
    amount_credit: str | None = None
    value_date: str | None = None
    counterpart_name: str | None = None
    counterpart_iban: str | None = None
    counterpart_bic: str | None = None
    purpose: str | None = None
    purpose_extra: list[str] = Field(default_factory=list)
    end_to_end_id: str | None = None
    mandate_reference: str | None = None
    creditor_id: str | None = None
    own_iban: str | None = None
    bank_reference: str | None = None
    currency: str | None = None


def _column_mapping(body: CsvColumnMappingIn | dict[str, Any]) -> csv_formats.ColumnMapping:
    data = body if isinstance(body, dict) else body.model_dump()
    data = dict(data)
    data["purpose_extra"] = tuple(data.get("purpose_extra") or ())
    return csv_formats.ColumnMapping(**data)


class CsvPreviewIn(_In):
    document_id: uuid.UUID
    mapping: CsvColumnMappingIn | None = None
    own_iban: str | None = None


class RowErrorOut(BaseModel):
    line: int
    message: str


class CsvPreviewOut(BaseModel):
    format_id: str
    label: str
    confidence: str
    encoding: str
    delimiter: str
    headers: list[str]
    row_count: int
    sample_rows: list[dict[str, str]]
    errors: list[RowErrorOut]
    ready_to_import: bool


class CsvImportIn(_In):
    document_id: uuid.UUID
    property_bank_account_id: uuid.UUID | None = None
    mapping: CsvColumnMappingIn | None = None
    mapping_id: uuid.UUID | None = None


class CsvMappingIn(_In):
    property_bank_account_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    mapping: CsvColumnMappingIn


class CsvMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    property_bank_account_id: uuid.UUID
    label: str
    mapping: dict[str, Any]


async def _load_document_bytes(session: Any, request: Request, document_id: uuid.UUID) -> bytes:
    document = await session.get(Document, document_id)
    if document is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return BlobStore(request.app.state.settings).get(document.storage_ref)


@router.post(
    "/imports/csv/preview",
    summary="Bank-CSV vor dem Import prüfen (erkanntes Format, Zeilen, Fehler)",
)
async def preview_csv_import(
    body: CsvPreviewIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> CsvPreviewOut:
    async with tenant_tx(request, principal) as session:
        data = await _load_document_bytes(session, request, body.document_id)
        try:
            result = csv_formats.preview(
                data,
                mapping_override=_column_mapping(body.mapping) if body.mapping else None,
                own_iban_override=body.own_iban,
            )
        except csv_formats.CsvImportError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
        return CsvPreviewOut(
            format_id=result.format_id,
            label=result.label,
            confidence=result.confidence,
            encoding=result.encoding,
            delimiter=result.delimiter,
            headers=result.headers,
            row_count=result.row_count,
            sample_rows=result.sample_rows,
            errors=[RowErrorOut(line=e.line, message=e.message) for e in result.errors],
            ready_to_import=result.parsed is not None and not result.errors,
        )


@router.post(
    "/imports/csv",
    status_code=201,
    summary="Bank-CSV importieren (erkanntes Format oder benutzerdefiniertes Mapping)",
)
async def import_csv(
    body: CsvImportIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> SyncRunOut:
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        data = await _load_document_bytes(session, request, body.document_id)
        mapping_override = None
        if body.mapping:
            mapping_override = _column_mapping(body.mapping)
        elif body.mapping_id:
            stored = await session.get(BankCsvMapping, body.mapping_id)
            if stored is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            mapping_override = _column_mapping(stored.mapping)
        account = None
        if body.property_bank_account_id:
            account = await session.get(PropertyBankAccount, body.property_bank_account_id)
            if account is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        try:
            result = csv_formats.preview(
                data,
                mapping_override=mapping_override,
                own_iban_override=account.iban if account else None,
            )
        except csv_formats.CsvImportError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
        if result.errors:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"{len(result.errors)} Zeile(n) nicht lesbar, z. B. Zeile "
                    f"{result.errors[0].line}: {result.errors[0].message}."
                ),
            )
        if result.parsed is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Kein bekanntes Format erkannt und keine eigene IBAN ermittelbar; "
                    "bitte Konto oder Mapping angeben."
                ),
            )
        try:
            run = await svc.import_file(
                session,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                parsed=result.parsed,
                document_id=body.document_id,
            )
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Import läuft gerade parallel."
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_sync_run.completed",
            entity_type="bank_sync_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload=run.counts,
        )
        _queue_proposals(session, request, principal.tenant_id, run.id)
        return SyncRunOut.model_validate(run)


@router.post(
    "/csv-mappings", status_code=201, summary="Benutzerdefiniertes CSV-Mapping je Konto speichern"
)
async def create_csv_mapping(
    body: CsvMappingIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> CsvMappingOut:
    async with tenant_tx(request, principal) as session:
        row = BankCsvMapping(
            tenant_id=principal.tenant_id,
            property_bank_account_id=body.property_bank_account_id,
            label=body.label,
            mapping=body.mapping.model_dump(),
        )
        session.add(row)
        await session.flush()
        return CsvMappingOut.model_validate(row)


@router.get("/csv-mappings", summary="Gespeicherte CSV-Mappings eines Kontos")
async def list_csv_mappings(
    request: Request,
    property_bank_account_id: uuid.UUID,
    principal: TenantPrincipal = Depends(READ),
) -> list[CsvMappingOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(BankCsvMapping)
            .where(BankCsvMapping.property_bank_account_id == property_bank_account_id)
            .order_by(BankCsvMapping.label)
        )
        return [CsvMappingOut.model_validate(r) for r in rows.all()]
