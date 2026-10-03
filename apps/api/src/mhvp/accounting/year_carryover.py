"""Year end carry over of closing balances to opening balances (M10-07, 6.9.10, 7.3).

``GET /accounting/ledgers/{id}/year-carryover?fiscal_year=`` shows the closing balance per
balance sheet account at the end of the fiscal year. ``POST`` writes two drafts dated on the
first day of the following fiscal year: a closing entry (closing balances against the opening
balance account) and the opening entry (the same balances in the opposite direction). Both
are drafts: the opening entry needs the review of a second person (``approve``) before it can
be posted, exactly like every opening balance; nothing is posted here.

Only accounts of the categories bank, cash, reserve, loan and transit are carried. Debtor and
creditor accounts keep their open items across the year (an opening entry would create them a
second time); revenue, cost, tax, technical and opening balance accounts are never carried. The
result and tax treatment of the year (profit carried forward, tax accounts) is not decided
here: balances on excluded accounts are listed in ``not_carried`` so that a person decides
(docs/OPEN_QUESTIONS.md M10-07).
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
)
from mhvp.accounting.raw_responses import (
    AccountingYearCarryoverPreviewOut,
)
from mhvp.accounting.schemas import EntryOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")

CARRIED = (
    AccountCategory.BANK,
    AccountCategory.CASH,
    AccountCategory.RESERVE,
    AccountCategory.LOAN,
    AccountCategory.TRANSIT,
)
ZERO = Decimal("0.00")


def year_bounds(ledger: Ledger, fiscal_year: int) -> tuple[date, date]:
    """First and last day of the fiscal year labelled by its start year."""
    start = date(fiscal_year, ledger.fiscal_year_start_month, 1)
    following = date(fiscal_year + 1, ledger.fiscal_year_start_month, 1)
    return start, following - timedelta(days=1)


async def closing_balances(
    session: AsyncSession, ledger: Ledger, end: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(carried, not_carried): balance = debit minus credit of posted lines up to ``end``."""
    rows = (
        await session.execute(
            select(
                LedgerAccount.id,
                LedgerAccount.number,
                LedgerAccount.name,
                LedgerAccount.category,
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                LedgerAccount.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= end,
            )
            .group_by(LedgerAccount.id)
            .order_by(LedgerAccount.number)
        )
    ).all()
    carried: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for account_id, number, name, category, debit, credit in rows:
        balance = Decimal(debit) - Decimal(credit)
        if balance == 0:
            continue
        item = {
            "account_id": account_id,
            "number": number,
            "name": name,
            "category": category.value,
            "balance": balance,
        }
        (carried if category in CARRIED else other).append(item)
    return carried, other


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID, *, lock: bool = False) -> Ledger:
    query = select(Ledger).where(Ledger.id == ledger_id)
    if lock:
        query = query.with_for_update()
    ledger = await session.scalar(query)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


def _check_year(ledger: Ledger, fiscal_year: int) -> tuple[date, date]:
    start, end = year_bounds(ledger, fiscal_year)
    if end >= local_today():
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Geschäftsjahr ist noch nicht beendet."
        )
    return start, end


def _key(fiscal_year: int, part: str) -> str:
    return f"year-carryover-{fiscal_year}-{part}"


@router.get(
    "/ledgers/{ledger_id}/year-carryover",
    summary="Schlussbestände des Geschäftsjahres",
    response_model=AccountingYearCarryoverPreviewOut,
)
async def preview(
    ledger_id: uuid.UUID,
    request: Request,
    fiscal_year: int = Query(ge=2000, le=2100),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        start, end = year_bounds(ledger, fiscal_year)
        carried, other = await closing_balances(session, ledger, end)
        existing = await session.scalar(
            select(JournalEntry.id).where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.idempotency_key == _key(fiscal_year, "opening"),
            )
        )
        return {
            "fiscal_year": fiscal_year,
            "start": start,
            "end": end,
            "target_date": end + timedelta(days=1),
            "carried": carried,
            "not_carried": other,
            "already_drafted": existing is not None,
            "note": (
                "Nur Bank, Kasse, Rücklage, Darlehen und Durchlaufkonten werden übernommen; "
                "offene Posten bleiben auf Personenkonten bestehen. Ergebnis und Steuerkonten "
                "sind nicht übernommen."
            ),
        }


@router.post(
    "/ledgers/{ledger_id}/year-carryover",
    status_code=201,
    summary="Schlussbestand als Anfangsbestand übernehmen (Entwurf, Vier-Augen)",
)
async def create_drafts(
    ledger_id: uuid.UUID,
    request: Request,
    fiscal_year: int = Query(ge=2000, le=2100),
    principal: TenantPrincipal = Depends(CREATE),
) -> list[EntryOut]:
    from mhvp.accounting.routers import _outs  # shared entry serialisation

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        _start, end = _check_year(ledger, fiscal_year)
        target = end + timedelta(days=1)
        drafts = list(
            (
                await session.scalars(
                    select(JournalEntry).where(
                        JournalEntry.ledger_id == ledger.id,
                        JournalEntry.idempotency_key.in_(
                            [_key(fiscal_year, "closing"), _key(fiscal_year, "opening")]
                        ),
                    )
                )
            ).all()
        )
        if drafts:
            return await _outs(session, sorted(drafts, key=lambda e: e.idempotency_key or ""))
        carried, _other = await closing_balances(session, ledger, end)
        if not carried:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Es gibt keine Schlussbestände zur Übernahme."
            )
        counter = (
            await session.scalars(
                select(LedgerAccount).where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.category == AccountCategory.OPENING_BALANCE,
                )
            )
        ).all()
        if len(counter) != 1:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Genau ein Anfangsbestandskonto im Kontenplan ist erforderlich.",
            )
        net = sum((Decimal(c["balance"]) for c in carried), ZERO)
        entries: list[JournalEntry] = []
        for part, sign, text in (
            ("closing", -1, f"Schlussbestand Geschäftsjahr {fiscal_year}"),
            ("opening", 1, f"Anfangsbestand Geschäftsjahr {fiscal_year + 1}"),
        ):
            lines = []
            for item in carried:
                amount = Decimal(item["balance"]) * sign
                lines.append(
                    svc.LineIn(
                        item["account_id"],
                        amount if amount > 0 else ZERO,
                        -amount if amount < 0 else ZERO,
                        text,
                    )
                )
            offset = -net * sign
            if offset != 0:
                lines.append(
                    svc.LineIn(
                        counter[0].id,
                        offset if offset > 0 else ZERO,
                        -offset if offset < 0 else ZERO,
                        text,
                    )
                )
            entry = JournalEntry(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                ledger_id=ledger.id,
                source=EntrySource.MANUAL,
                kind=EntryKind.OPENING_BALANCE if part == "opening" else EntryKind.CUSTOM,
                booking_date=target,
                text=text,
                idempotency_key=_key(fiscal_year, part),
            )
            await svc.write_draft(session, ledger, entry, lines, [])
            entries.append(entry)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.year_carryover_drafted",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"fiscal_year": fiscal_year, "accounts": len(carried)},
        )
        return await _outs(session, sorted(entries, key=lambda e: e.idempotency_key or ""))
