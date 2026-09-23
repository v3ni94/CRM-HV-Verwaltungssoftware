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
from mhvp.banking import camt, matching
from mhvp.banking import services as svc
from mhvp.banking.models import (
    BankConnection,
    BankRule,
    BankSyncRun,
    BankTransaction,
    ConnectionStatus,
    Connector,
    RuleState,
    TransactionStatus,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document

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


class RunOut(BaseModel):
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


class ReviewIn(_In):
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
) -> RunOut:
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
        return RunOut.model_validate(run)


@router.get("/runs", summary="Sync-Protokoll")
async def runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> list[RunOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(BankSyncRun).order_by(BankSyncRun.created_at.desc()).limit(limit)
        )
        return [RunOut.model_validate(r) for r in rows.all()]


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
    tx_id: uuid.UUID, body: ReviewIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
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


class BulkIn(_In):
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
    tx_id: uuid.UUID, body: ReviewIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
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
    body: BulkIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
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
