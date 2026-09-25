"""Banking endpoints (/api/v1/banking, M11). Reading bank data needs accounting permissions;
no payment is initiated here (G2)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mhvp.accounting.models import EntrySource
from mhvp.banking import camt, matching, payments
from mhvp.banking import finapi as finapi_client
from mhvp.banking import services as svc
from mhvp.banking.models import (
    BankConnection,
    BankRule,
    BankSyncRun,
    BankTransaction,
    ConnectionStatus,
    Connector,
    FinApiAccountLink,
    FinApiConnection,
    FinApiTenantConfig,
    OrderStatus,
    PaymentBatch,
    PaymentOrder,
    RuleState,
    TransactionStatus,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
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
            parsed = camt.parse(data)
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
        return SyncRunOut.model_validate(run)


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
        return await svc.reconcile(session, bank_account_id)


# Matching and controlled automation (M12, 7.4, 6.9.4) ---------------------------------


class SettleIn(_In):
    open_item_id: uuid.UUID
    amount: Decimal = Field(gt=0)


class BookIn(_In):
    settlements: list[SettleIn] = Field(default_factory=list, max_length=100)
    counter_account_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=500)


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


async def _book(
    session: Any, principal: TenantPrincipal, row: BankTransaction, body: BookIn
) -> Any:
    entry = await matching.book_payment(
        session,
        row,
        settlements=[(s.open_item_id, s.amount) for s in body.settlements],
        counter_account_id=body.counter_account_id,
        user_id=principal.user_id,
        source=EntrySource.BANK_IMPORT,
        text=body.text,
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="bank_transaction.booked",
        entity_type="bank_transaction",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"journal_entry_id": str(entry.id)},
    )
    return entry


@router.post("/transactions/{tx_id}/book", status_code=201, summary="Umsatz buchen (bestätigt)")
async def book(
    tx_id: uuid.UUID, body: BookIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        entry = await _book(session, principal, await _tx(session, tx_id), body)
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
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_transaction.ignored",
            entity_type="bank_transaction",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"reason": body.reason},
        )
        await session.flush()
        return _tx_out(row)


@router.post(
    "/bulk-confirm", summary="Massenbestätigung mit Vorschau (je Umsatz ganz oder gar nicht)"
)
async def bulk_confirm(
    body: BankBulkIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        rows = []
        for item in body.items:
            rows.append((item, await _tx(session, item.transaction_id)))
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
            return {"preview": True, **summary}
        results = []
        for item, row in rows:
            nested = await session.begin_nested()
            try:
                entry = await _book(session, principal, row, item)
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
        return RuleOut.model_validate(rule)


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
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="bank_rule.activated",
            entity_type="bank_rule",
            entity_id=rule.id,
            actor_user_id=principal.user_id,
            payload={"max_amount": str(body.max_amount)},
        )
        await session.flush()
        return RuleOut.model_validate(rule)


@router.post("/rules/{rule_id}/disable", summary="Regel abschalten")
async def disable_rule(
    rule_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> RuleOut:
    async with tenant_tx(request, principal) as session:
        rule = await _rule(session, rule_id)
        rule.approval_state = RuleState.DISABLED
        await session.flush()
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
        return RuleOut.model_validate(rule)


@router.post(
    "/auto-post", summary="Automatik über aktive Regeln (nur bei Freischaltung je Mandant)"
)
async def run_auto_post(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        settings = await session.scalar(select(TenantSettings))
        enabled = bool(settings and settings.auto_posting_enabled)
        if not enabled:
            return {"enabled": False, "posted": 0}
        posted = 0
        new = (
            await session.scalars(
                select(BankTransaction).where(BankTransaction.status == TransactionStatus.NEW)
            )
        ).all()
        for row in new:
            nested = await session.begin_nested()
            try:
                if await matching.auto_post(session, row, enabled):
                    posted += 1
                await nested.commit()
            except ProblemError:
                await nested.rollback()
        return {"enabled": True, "posted": posted, "checked": len(new)}


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


# Payment runs (M15, 7.5, 6.9.9); export requires G2 ------------------------------------


class PaymentOrderIn(_In):
    invoice_id: uuid.UUID
    property_bank_account_id: uuid.UUID
    execution_date: date


class OrderPatch(_In):
    execution_date: date | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=140)


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
        if order.status not in (OrderStatus.DRAFT, OrderStatus.APPROVED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Eingereichte Aufträge sind unveränderlich."
            )
        before = payments.snapshot(order)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(order, key, value)
        if payments.snapshot(order) != before:
            await payments.invalidate(session, order)
        await session.flush()
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
        batch = PaymentBatch(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_bank_account_id=bank.id,
            message_id=f"MHVP{uuid.uuid4().hex[:24]}".upper(),
            format=payments.PAIN_FORMAT,
        )
        session.add(batch)
        await session.flush()
        xml = payments.pain001(batch.message_id, bank.holder, bank.iban, orders)
        for o in orders:
            o.status, o.batch_id = OrderStatus.EXPORTED, batch.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_batch.exported",
            entity_type="payment_batch",
            entity_id=batch.id,
            actor_user_id=principal.user_id,
            payload={"orders": len(orders), "format": batch.format},
        )
        await session.flush()
        return {
            "id": batch.id,
            "message_id": batch.message_id,
            "format": batch.format,
            "xml": xml.decode(),
        }


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
                order.status = OrderStatus.REJECTED
            elif body.status == "executed":
                if body.bank_transaction_id is None:
                    raise ProblemError(
                        ErrorCodes.VALIDATION, detail="Ausführung nur mit Bankumsatz als Nachweis."
                    )
                await payments.record_execution(
                    session,
                    order,
                    bank_transaction_id=body.bank_transaction_id,
                    user_id=principal.user_id,
                )
            elif body.status == "returned":
                if order.status is OrderStatus.RETURNED:
                    continue
                if order.journal_entry_id is None:
                    raise ProblemError(
                        ErrorCodes.CONFLICT, detail="Nur ausgeführte Aufträge können zurückkommen."
                    )
                from mhvp.accounting import services as acc_svc
                from mhvp.accounting.models import JournalEntry, Ledger

                entry = await session.get(
                    JournalEntry, order.journal_entry_id, with_for_update=True
                )
                ledger = await session.get(Ledger, order.ledger_id)
                if entry is None or ledger is None:  # pragma: no cover
                    raise ProblemError(ErrorCodes.CONFLICT)
                await acc_svc.reverse(
                    session,
                    ledger,
                    entry,
                    user_id=principal.user_id,
                    reason=body.reason or "Rückgabe durch die Bank",
                    booking_date=local_today(),
                )
                order.status = OrderStatus.RETURNED
        batch.status = body.status
        await session.flush()
        return [await _order_out(session, o) for o in orders]


# --- finAPI (M11-finapi, read only): connect, assign, refresh on click, disconnect --------

finapi_router = APIRouter(prefix="/banking/finapi", tags=["Bank"])


class FinApiConfigIn(_In):
    client_id: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=1, max_length=200)
    mandator_id: str | None = Field(default=None, max_length=64)
    base_url: str = Field(min_length=8, max_length=300)
    sandbox: bool = True


class FinApiConfigOut(BaseModel):
    configured: bool
    base_url: str | None = None
    mandator_id: str | None = None
    sandbox: bool | None = None


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


def _finapi_client(cfg: FinApiTenantConfig) -> finapi_client.FinApiClient:
    return finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            base_url=cfg.base_url,
            mandator_id=cfg.mandator_id,
        )
    )


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
        cfg.base_url = body.base_url.rstrip("/")
        cfg.sandbox = body.sandbox
        cfg.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="finapi.config_changed",
            entity_type="finapi_tenant_config",
            entity_id=cfg.id,
            actor_user_id=principal.user_id,
            payload={"base_url": cfg.base_url, "sandbox": cfg.sandbox},
        )
        await session.flush()
        return FinApiConfigOut(
            configured=True, base_url=cfg.base_url, mandator_id=cfg.mandator_id, sandbox=cfg.sandbox
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
            configured=True, base_url=cfg.base_url, mandator_id=cfg.mandator_id, sandbox=cfg.sandbox
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
        try:
            web_form = _finapi_client(cfg).create_bank_connection_import_web_form()
        except finapi_client.FinApiNotVerifiedError:
            raise
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
        client = _finapi_client(cfg)
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
        web_form = _finapi_client(cfg).create_bank_connection_import_web_form()
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


@finapi_router.post(
    "/accounts/{link_id}/fetch", summary="Umsätze abrufen (asynchron, nur auf Klick)"
)
async def fetch_finapi_transactions(
    link_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> SyncRunOut:
    """A real click only: this never runs on a schedule (master prompt section 2). The fetch
    itself completes asynchronously in the existing Celery worker (`banking.finapi_fetch`)."""
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
        if (
            fa is None
            or conn is None
            or conn.status
            not in (
                ConnectionStatus.ACTIVE,
                ConnectionStatus.ERROR,
            )
        ):
            raise ProblemError(
                ErrorCodes.FINAPI_STATE, detail="Bankverbindung ist nicht abrufbereit."
            )
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
            payload={"trigger": "user_click", "finapi_account_link_id": str(link.id)},
        )
        await session.flush()
        run_id = run.id
        tenant_id = principal.tenant_id
        bank_account_id = link.property_bank_account_id
    finapi_fetch.delay(str(tenant_id), str(run_id), str(link_id))
    return SyncRunOut(
        id=run_id,
        source="aggregator_finapi",
        status="queued",
        counts={},
        errors=[],
        property_bank_account_id=bank_account_id,
        document_id=None,
    )


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
