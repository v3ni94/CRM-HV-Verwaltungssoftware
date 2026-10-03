"""Write off of open items as its own procedure (AN15, GAK-104; 7.1 B03, B07).

``open_item.written_off`` used to be a bare flag without date, reason or author and without
any writing path. A write off is now proposed with reason, effective date and an optional
voucher (``open_item_write_off``). A proposal has no effect on balances or reports. Approval
by a second person is possible only with the tenant switch
``accounting_tax_settings.write_off_approval_enabled`` (default off, question AN15-02) and gate
G1 open; it sets ``written_off`` with date, time, reason and author on the item. Nothing is
posted here: the legal basis (waiver, uncollectibility) and the booking procedure stay an open
decision; reports read the flag only from ``written_off_on`` onwards (as of date, B07).

AO01 (GAK-104 rest): ``not_written_off_as_of`` is the shared date aware filter for selections
(direct debit, credit payables, AI lookup). ``GET /{id}/posting-preview`` shows the booking an
approved write off would need (credit of the receivable account at the remaining amount); the
counter account is not decided (AN15-02), so ``posting_allowed`` stays false and nothing is
posted, also with G1 open. A booking would never overwrite: a correction is a reversal. Taking
back an approval (switch ``accounting.write_off_revocation`` in ``tenant_settings.sources``,
default off) is only prepared: there is no route, the status says ``locked`` or
``awaiting_decision`` (AN15-02).

AP12 (GAK-104 rest, GAM-605): an approved write off can be posted, but only with the tenant
switch ``accounting.write_off_posting`` (``SWITCH_KEY``, default off), gate G1 open and a
counter account that the tenant set itself (``accounting.write_off_counter_account``, account
number in the ledger of the item, no default: AN15-02 is not decided here). The posting needs
the amount and counter account confirmed from the preview; it debits the counter account,
credits the receivable account and settles the open item. Repeating the call returns the same
entry (idempotency key ``write_off:<id>``, row lock against parallel calls, B08). A posted write
off is never changed: the correction is a reversal (``/posting/reversal``), which reopens the
remaining amount; the write off flag of the item stays (taking it back is AN15-02).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import period_lock
from mhvp.accounting import services as acc
from mhvp.accounting.audit_events import record_change, snap
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemWriteOff,
    ReversalReason,
)
from mhvp.accounting.tax_models import AccountingTaxSettings
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import (
    ClosedReleaseGateResolver,
    ReleaseGate,
    ensure_release_gate_open,
)

router = APIRouter(prefix="/open-item-write-offs", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")
SETTINGS = require_permission("tenant_settings:update")

QUESTION = "AN15-02"
REVOCATION_SWITCH = "accounting.write_off_revocation"
SWITCH_KEY = "accounting.write_off_posting"
COUNTER_ACCOUNT_KEY = "accounting.write_off_counter_account"
_FIELDS = ("status", "decided_by", "decided_at", "decision_note")
_ITEM_FIELDS = (
    "written_off",
    "written_off_on",
    "written_off_at",
    "written_off_reason",
    "written_off_by",
)


class AccountingWriteOffProposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    open_item_id: uuid.UUID
    effective_on: date
    reason: str = Field(min_length=10, max_length=500)
    document_id: uuid.UUID | None = None


class AccountingWriteOffDecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class AccountingWriteOffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    open_item_id: uuid.UUID
    status: str
    effective_on: date
    amount: Decimal
    reason: str
    document_id: uuid.UUID | None
    proposed_by: uuid.UUID | None
    proposed_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    posting_effect: bool = False
    approval_enabled: bool = False
    question: str = QUESTION
    # AO01: taking back an approval is only prepared (AN15-02 open, no route).
    revocation_status: Literal["locked", "awaiting_decision"] = "locked"
    # AP12: posting of an approved write off (switch, G1, counter account) and its reversal.
    posting_entry_id: uuid.UUID | None = None
    posting_reversal_id: uuid.UUID | None = None


class AccountingWriteOffPostingLineOut(BaseModel):
    side: Literal["debit", "credit"]
    account_id: uuid.UUID | None
    account_number: str | None
    amount: Decimal
    note: str | None = None


class AccountingWriteOffPostingPreviewOut(BaseModel):
    write_off_id: uuid.UUID
    status: str
    effective_on: date
    amount: Decimal
    lines: list[AccountingWriteOffPostingLineOut]
    posting_allowed: bool = False
    blockers: list[str]
    correction: str = "reversal"
    question: str = QUESTION
    posting_entry_id: uuid.UUID | None = None


class AccountingWriteOffPostingSettingsOut(BaseModel):
    posting_enabled: bool
    counter_account_number: str | None
    question: str = QUESTION


class AccountingWriteOffPostingSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_enabled: bool
    counter_account_number: str | None = Field(default=None, pattern=r"^[0-9]{4,6}$")


class AccountingWriteOffPostIn(BaseModel):
    """Values confirmed from the posting preview; a mismatch is refused (409)."""

    model_config = ConfigDict(extra="forbid")
    expected_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    counter_account_id: uuid.UUID


class AccountingWriteOffReverseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=500)
    booking_date: date | None = None


class AccountingWriteOffPostingOut(BaseModel):
    write_off_id: uuid.UUID
    journal_entry_id: uuid.UUID
    fiscal_year: int | None
    number: int | None
    booking_date: date
    amount: Decimal
    reversal_id: uuid.UUID | None = None
    repeated: bool = False


def not_written_off_as_of(as_of: date) -> ColumnElement[bool]:
    """Item counts as open on ``as_of``: not written off, or written off only later (B07).
    A legacy flag without date counts as written off for every date."""
    return or_(
        OpenItem.written_off.is_(False),
        OpenItem.written_off_on.is_not(None) & (OpenItem.written_off_on > as_of),
    )


async def approval_enabled(session: AsyncSession) -> bool:
    return bool(await session.scalar(select(AccountingTaxSettings.write_off_approval_enabled)))


async def revocation_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    sources = await session.scalar(select(TenantSettings.sources))
    return bool((sources or {}).get(REVOCATION_SWITCH) is True)


def _out(
    row: OpenItemWriteOff,
    enabled: bool,
    revocation: bool = False,
    entry: JournalEntry | None = None,
) -> AccountingWriteOffOut:
    out = AccountingWriteOffOut.model_validate(row)
    out.approval_enabled = enabled
    if row.status == "approved" and revocation:
        out.revocation_status = "awaiting_decision"
    if entry is not None:
        out.posting_effect = True
        out.posting_entry_id = entry.id
        out.posting_reversal_id = entry.reversed_by_id
    return out


def idempotency_key(write_off_id: uuid.UUID) -> str:
    return f"write_off:{write_off_id}"


async def posting_entry(session: AsyncSession, row: OpenItemWriteOff) -> JournalEntry | None:
    """The entry that posted this write off, if any (idempotency key, B08)."""
    entry: JournalEntry | None = await session.scalar(
        select(JournalEntry).where(JournalEntry.idempotency_key == idempotency_key(row.id))
    )
    return entry


async def posting_settings(session: AsyncSession) -> tuple[bool, str | None]:
    from mhvp.platform.models import TenantSettings

    sources = (await session.scalar(select(TenantSettings.sources))) or {}
    number = sources.get(COUNTER_ACCOUNT_KEY)
    return sources.get(SWITCH_KEY) is True, number if isinstance(number, str) and number else None


async def counter_account(
    session: AsyncSession, item: OpenItem, number: str | None
) -> LedgerAccount | None:
    """Counter account set by the tenant, in the ledger of the item; never a debtor or creditor
    account and never the receivable account itself."""
    if number is None:
        return None
    account = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == item.ledger_id, LedgerAccount.number == number
        )
    )
    if (
        account is None
        or not account.active
        or account.id == item.account_id
        or account.category in (AccountCategory.DEBTOR, AccountCategory.CREDITOR)
    ):
        return None
    return account


async def _g1_open(request: Request, principal: TenantPrincipal) -> bool:
    resolver = getattr(request.app.state, "release_gate_resolver", ClosedReleaseGateResolver())
    try:
        return (
            principal.tenant_id is not None
            and (await resolver.is_open(principal.tenant_id, ReleaseGate.G1)) is True
        )
    except Exception:
        return False


async def posting_preview(
    session: AsyncSession, row: OpenItemWriteOff, *, g1_open: bool
) -> AccountingWriteOffPostingPreviewOut:
    """Booking an approved write off would need; never posts (counter account AN15-02)."""
    item = await session.get(OpenItem, row.open_item_id)
    if item is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    account = await session.get(LedgerAccount, item.account_id) if item.account_id else None
    enabled, number = await posting_settings(session)
    counter = await counter_account(session, item, number)
    entry = await posting_entry(session, row)
    blockers = []
    if row.status != "approved":
        blockers.append("not_approved")
    if not g1_open:
        blockers.append("gate_g1_closed")
    if not enabled:
        blockers.append("posting_switch_off")
    if number is None:
        blockers.append("counter_account_undecided")
    elif counter is None:
        blockers.append("counter_account_invalid")
    if entry is not None:
        blockers.append("already_posted")
    elif row.status == "approved":
        current = await acc.remaining(session, item.id)
        if current != row.amount:
            blockers.append("amount_changed")
    counter_note = (
        f"Gegenkonto laut Mandanteneinstellung {COUNTER_ACCOUNT_KEY}"
        if counter is not None
        else f"Gegenkonto nicht festgelegt (offene Frage {QUESTION})"
    )
    return AccountingWriteOffPostingPreviewOut(
        write_off_id=row.id,
        status=row.status,
        effective_on=row.effective_on,
        amount=row.amount,
        lines=[
            AccountingWriteOffPostingLineOut(
                side="debit",
                account_id=counter.id if counter else None,
                account_number=counter.number if counter else None,
                amount=row.amount,
                note=counter_note,
            ),
            AccountingWriteOffPostingLineOut(
                side="credit",
                account_id=account.id if account else None,
                account_number=account.number if account else None,
                amount=row.amount,
                note="Forderungskonto des Postens",
            ),
        ],
        posting_allowed=not blockers,
        blockers=blockers,
        posting_entry_id=entry.id if entry else None,
    )


async def post_write_off(
    session: AsyncSession,
    row: OpenItemWriteOff,
    *,
    expected_amount: Decimal,
    counter_account_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[JournalEntry, bool]:
    """Post an approved write off once. The caller holds the row lock and checked G1.
    Returns the entry and whether it already existed (repeat, B08)."""
    existing = await posting_entry(session, row)
    if existing is not None:
        return existing, True
    if row.status != "approved":
        raise ProblemError(
            ErrorCodes.WRITE_OFF_POSTING_LOCKED, detail="Nur freigegebene Ausbuchungen."
        )
    enabled, number = await posting_settings(session)
    if not enabled:
        raise ProblemError(
            ErrorCodes.WRITE_OFF_POSTING_LOCKED,
            detail=f"Schalter {SWITCH_KEY} ist aus (offene Frage {QUESTION}).",
        )
    item = await session.get(OpenItem, row.open_item_id, with_for_update=True)
    if item is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    counter = await counter_account(session, item, number)
    if counter is None:
        raise ProblemError(
            ErrorCodes.WRITE_OFF_POSTING_LOCKED,
            detail=f"Kein gültiges Gegenkonto eingestellt (offene Frage {QUESTION}).",
        )
    if counter.id != counter_account_id or expected_amount != row.amount:
        raise ProblemError(
            ErrorCodes.WRITE_OFF_POSTING_LOCKED,
            detail="Betrag oder Gegenkonto weichen von der Buchungsvorschau ab.",
        )
    if item.account_id is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.WRITE_OFF_POSTING_LOCKED, detail="Posten ohne Konto.")
    current = await acc.remaining(session, item.id)
    if current != row.amount:
        raise ProblemError(
            ErrorCodes.WRITE_OFF_AMOUNT_CHANGED,
            detail=f"Restbetrag jetzt {current}, ausgebucht {row.amount}.",
        )
    ledger = await session.get(Ledger, item.ledger_id)
    if ledger is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    entry = JournalEntry(
        tenant_id=row.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=row.effective_on,
        accrual_date=row.effective_on,
        text=f"Ausbuchung Forderung: {row.reason}"[:500],
        kind=EntryKind.CUSTOM,
        source=EntrySource.MANUAL,
        reference=f"Ausbuchung {str(row.id)[:8]}",
        document_id=row.document_id,
        contract_id=item.contract_id,
        idempotency_key=idempotency_key(row.id),
    )
    lines = [
        acc.LineIn(counter.id, row.amount, Decimal("0"), "Ausbuchung Gegenkonto"),
        acc.LineIn(item.account_id, Decimal("0"), row.amount, "Ausbuchung Forderung"),
    ]
    await acc.write_draft(
        session, ledger, entry, lines, [{"open_item_id": item.id, "amount": row.amount}]
    )
    await acc.post(session, ledger, entry, user_id)
    await record_change(
        session,
        tenant_id=row.tenant_id,
        actor_user_id=user_id,
        type="open_item_write_off.posted",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before={},
        after={"journal_entry_id": str(entry.id), "amount": str(row.amount)},
    )
    return entry, False


async def reverse_write_off_posting(
    session: AsyncSession,
    row: OpenItemWriteOff,
    *,
    reason: str,
    booking_date: date,
    user_id: uuid.UUID,
) -> tuple[JournalEntry, JournalEntry, bool]:
    """Reversal of the posting (B03); never overwrites. Repeat returns the reversal."""
    entry = await posting_entry(session, row)
    if entry is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Ausbuchung ist nicht gebucht.")
    if entry.reversed_by_id is not None:
        reversal = await session.get(JournalEntry, entry.reversed_by_id)
        if reversal is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return entry, reversal, True
    if entry.status is not EntryStatus.POSTED:  # pragma: no cover
        raise ProblemError(ErrorCodes.CONFLICT)
    ledger = await session.get(Ledger, entry.ledger_id)
    if ledger is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    reversal = await acc.reverse(
        session,
        ledger,
        entry,
        user_id=user_id,
        reason=reason.strip(),
        booking_date=booking_date,
        reason_code=ReversalReason.OTHER,
    )
    await record_change(
        session,
        tenant_id=row.tenant_id,
        actor_user_id=user_id,
        type="open_item_write_off.posting_reversed",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before={"journal_entry_id": str(entry.id)},
        after={"reversal_id": str(reversal.id), "reason": reason.strip()},
    )
    return entry, reversal, False


async def propose(
    session: AsyncSession,
    item: OpenItem,
    *,
    effective_on: date,
    reason: str,
    document_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> OpenItemWriteOff:
    """Proposal without any effect; amount is the remaining amount as of ``effective_on``."""
    if user_id is None:  # AO12-05: without a person the four eyes rule could be bypassed
        raise ProblemError(ErrorCodes.WRITE_OFF_NEEDS_PERSON)
    if effective_on > local_today():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Datum liegt in der Zukunft.")
    if effective_on < item.booking_date:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Datum liegt vor der Entstehung des Postens."
        )
    if item.kind.value != "receivable":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur Forderungen können ausgebucht werden."
        )
    if item.written_off:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Posten ist bereits ausgebucht.")
    active = await session.scalar(
        select(OpenItemWriteOff.id).where(
            OpenItemWriteOff.open_item_id == item.id,
            OpenItemWriteOff.status.in_(("proposed", "approved")),
        )
    )
    if active is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Es liegt bereits ein Vorschlag vor.")
    remaining = await acc.remaining(session, item.id, effective_on)
    if remaining <= 0:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Posten ist zum Stichtag nicht mehr offen."
        )
    if document_id is not None:
        from mhvp.documents.models import Document

        if await session.get(Document, document_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Beleg nicht gefunden.")
    row = OpenItemWriteOff(
        tenant_id=item.tenant_id,
        open_item_id=item.id,
        status="proposed",
        effective_on=effective_on,
        amount=remaining,
        reason=reason.strip(),
        document_id=document_id,
        proposed_by=user_id,
    )
    session.add(row)
    await session.flush()
    await record_change(
        session,
        tenant_id=item.tenant_id,
        actor_user_id=user_id,
        type="open_item_write_off.proposed",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before={},
        after={
            "open_item_id": str(item.id),
            "effective_on": effective_on.isoformat(),
            "amount": str(remaining),
            "reason": row.reason,
        },
    )
    await session.refresh(row)
    return row


async def decide(
    session: AsyncSession,
    row: OpenItemWriteOff,
    *,
    decision: str,
    note: str | None,
    user_id: uuid.UUID,
) -> OpenItemWriteOff:
    """Reject is always possible; approve needs the switch, a second person and an open
    period. The G1 check sits in the route (gate resolver of the app)."""
    if row.status != "proposed":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vorschlag ist bereits entschieden.")
    item = await session.get(OpenItem, row.open_item_id, with_for_update=True)
    if item is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    before = snap(row, _FIELDS)
    if decision == "approve":
        if row.proposed_by is not None and row.proposed_by == user_id:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vier Augen: die vorschlagende Person kann nicht freigeben.",
            )
        if row.proposed_by is None:  # AO12-05: legacy proposal without a person
            raise ProblemError(ErrorCodes.WRITE_OFF_NEEDS_PERSON)
        # AO12-04: a payment between proposal and approval changes the remaining amount.
        current = await acc.remaining(session, item.id, row.effective_on)
        if current != row.amount:
            raise ProblemError(
                ErrorCodes.WRITE_OFF_AMOUNT_CHANGED,
                detail=(
                    f"Restbetrag zum Stichtag jetzt {current}, im Vorschlag {row.amount}; "
                    "bitte ablehnen und neu vorschlagen."
                ),
            )
        ledger = await session.get(Ledger, item.ledger_id)
        if ledger is not None:
            await period_lock.ensure_open_for_entry(
                session, ledger, item.journal_entry_id, row.effective_on
            )
        item_before = snap(item, _ITEM_FIELDS)
        now = datetime.now(UTC)
        item.written_off = True
        item.written_off_on = row.effective_on
        item.written_off_at = now
        item.written_off_reason = row.reason
        item.written_off_by = user_id
        row.status = "approved"
        row.decided_at = now
        await session.flush()
        await record_change(
            session,
            tenant_id=item.tenant_id,
            actor_user_id=user_id,
            type="open_item.written_off",
            entity_type="open_item",
            entity_id=item.id,
            before=item_before,
            after=snap(item, _ITEM_FIELDS),
            payload={"write_off_id": str(row.id)},
        )
    else:
        row.status = "rejected"
        row.decided_at = datetime.now(UTC)
    row.decided_by = user_id
    row.decision_note = note
    await session.flush()
    await record_change(
        session,
        tenant_id=row.tenant_id,
        actor_user_id=user_id,
        type=f"open_item_write_off.{row.status}",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before=before,
        after=snap(row, _FIELDS),
    )
    return row


@router.get(
    "",
    summary="Ausbuchungsvorschläge offener Posten (AN15, ohne Buchungswirkung)",
    response_model=list[AccountingWriteOffOut],
    dependencies=[Depends(strict_query)],
)
async def list_write_offs(
    request: Request,
    open_item_id: uuid.UUID | None = Query(default=None),
    status: Literal["proposed", "approved", "rejected"] | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[AccountingWriteOffOut]:
    async with tenant_tx(request, principal) as session:
        query = select(OpenItemWriteOff).order_by(OpenItemWriteOff.proposed_at.desc())
        if open_item_id is not None:
            query = query.where(OpenItemWriteOff.open_item_id == open_item_id)
        if status is not None:
            query = query.where(OpenItemWriteOff.status == status)
        enabled = await approval_enabled(session)
        revocation = await revocation_enabled(session)
        rows = (await session.scalars(query.limit(500))).all()
        keys = [idempotency_key(r.id) for r in rows]
        entries = (
            {
                e.idempotency_key: e
                for e in (
                    await session.scalars(
                        select(JournalEntry).where(JournalEntry.idempotency_key.in_(keys))
                    )
                ).all()
            }
            if keys
            else {}
        )
        return [_out(r, enabled, revocation, entries.get(idempotency_key(r.id))) for r in rows]


@router.get(
    "/settings",
    summary="Buchung von Ausbuchungen: Schalter und Gegenkonto des Mandanten (AN15-02 offen)",
    response_model=AccountingWriteOffPostingSettingsOut,
)
async def get_write_off_posting_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> AccountingWriteOffPostingSettingsOut:
    async with tenant_tx(request, principal) as session:
        enabled, number = await posting_settings(session)
        return AccountingWriteOffPostingSettingsOut(
            posting_enabled=enabled, counter_account_number=number
        )


@router.put(
    "/settings",
    summary="Buchung von Ausbuchungen einstellen (Standard aus, Gegenkonto ohne Vorgabe)",
    response_model=AccountingWriteOffPostingSettingsOut,
)
async def put_write_off_posting_settings(
    body: AccountingWriteOffPostingSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> AccountingWriteOffPostingSettingsOut:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        sources = dict(row.sources or {})
        before = {k: sources.get(k) for k in (SWITCH_KEY, COUNTER_ACCOUNT_KEY)}
        sources[SWITCH_KEY] = body.posting_enabled
        sources[COUNTER_ACCOUNT_KEY] = body.counter_account_number
        row.sources = sources
        row.version += 1
        row.updated_by = principal.user_id
        await session.flush()
        await record_change(
            session,
            tenant_id=row.tenant_id,
            actor_user_id=principal.user_id,
            type="tenant_settings.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            before=before,
            after={
                SWITCH_KEY: body.posting_enabled,
                COUNTER_ACCOUNT_KEY: body.counter_account_number,
            },
        )
        return AccountingWriteOffPostingSettingsOut(
            posting_enabled=body.posting_enabled,
            counter_account_number=body.counter_account_number,
        )


@router.get(
    "/{write_off_id}/posting-preview",
    summary="Buchungsvorschau einer Ausbuchung (nur Anzeige, Gegenkonto offen AN15-02, G1)",
    response_model=AccountingWriteOffPostingPreviewOut,
)
async def write_off_posting_preview(
    write_off_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> AccountingWriteOffPostingPreviewOut:
    g1_open = await _g1_open(request, principal)
    async with tenant_tx(request, principal) as session:
        row = await session.get(OpenItemWriteOff, write_off_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await posting_preview(session, row, g1_open=g1_open)


@router.post(
    "",
    status_code=201,
    summary="Ausbuchung eines offenen Postens vorschlagen (Grund, Datum, Beleg; keine Wirkung)",
    response_model=AccountingWriteOffOut,
)
async def propose_write_off(
    body: AccountingWriteOffProposeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountingWriteOffOut:
    async with tenant_tx(request, principal) as session:
        item = await session.get(OpenItem, body.open_item_id, with_for_update=True)
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await propose(
            session,
            item,
            effective_on=body.effective_on,
            reason=body.reason,
            document_id=body.document_id,
            user_id=principal.user_id,
        )
        return _out(row, await approval_enabled(session))


@router.post(
    "/{write_off_id}/decision",
    summary="Ausbuchungsvorschlag freigeben (Schalter, Vier Augen, G1) oder ablehnen",
    response_model=AccountingWriteOffOut,
)
async def decide_write_off(
    write_off_id: uuid.UUID,
    body: AccountingWriteOffDecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingWriteOffOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.WRITE_OFF_NEEDS_PERSON)
    async with tenant_tx(request, principal) as session:
        row = await session.get(OpenItemWriteOff, write_off_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        enabled = await approval_enabled(session)
        if body.decision == "approve":
            if not enabled:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=(
                        "Die Freigabe von Ausbuchungen ist für diesen Mandanten nicht "
                        f"eingeschaltet (offene Frage {QUESTION}); der Vorschlag bleibt ohne "
                        "Wirkung."
                    ),
                )
            await ensure_release_gate_open(
                ReleaseGate.G1, principal.tenant_id, request.app.state.release_gate_resolver
            )
        row = await decide(
            session, row, decision=body.decision, note=body.note, user_id=principal.user_id
        )
        return _out(row, enabled, await revocation_enabled(session))


@router.post(
    "/{write_off_id}/posting",
    summary="Freigegebene Ausbuchung buchen (Schalter, Gegenkonto, G1, Werte aus der Vorschau)",
    response_model=AccountingWriteOffPostingOut,
)
async def post_write_off_route(
    write_off_id: uuid.UUID,
    body: AccountingWriteOffPostIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingWriteOffPostingOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.WRITE_OFF_NEEDS_PERSON)
    await ensure_release_gate_open(
        ReleaseGate.G1, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        row = await session.get(OpenItemWriteOff, write_off_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        entry, repeated = await post_write_off(
            session,
            row,
            expected_amount=body.expected_amount,
            counter_account_id=body.counter_account_id,
            user_id=principal.user_id,
        )
        return AccountingWriteOffPostingOut(
            write_off_id=row.id,
            journal_entry_id=entry.id,
            fiscal_year=entry.fiscal_year,
            number=entry.number,
            booking_date=entry.booking_date,
            amount=row.amount,
            reversal_id=entry.reversed_by_id,
            repeated=repeated,
        )


@router.post(
    "/{write_off_id}/posting/reversal",
    summary="Buchung einer Ausbuchung stornieren (Storno statt Überschreiben, G1)",
    response_model=AccountingWriteOffPostingOut,
)
async def reverse_write_off_posting_route(
    write_off_id: uuid.UUID,
    body: AccountingWriteOffReverseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingWriteOffPostingOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.WRITE_OFF_NEEDS_PERSON)
    await ensure_release_gate_open(
        ReleaseGate.G1, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        row = await session.get(OpenItemWriteOff, write_off_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        entry, reversal, repeated = await reverse_write_off_posting(
            session,
            row,
            reason=body.reason,
            booking_date=body.booking_date or local_today(),
            user_id=principal.user_id,
        )
        return AccountingWriteOffPostingOut(
            write_off_id=row.id,
            journal_entry_id=entry.id,
            fiscal_year=reversal.fiscal_year,
            number=reversal.number,
            booking_date=reversal.booking_date,
            amount=row.amount,
            reversal_id=reversal.id,
            repeated=repeated,
        )
