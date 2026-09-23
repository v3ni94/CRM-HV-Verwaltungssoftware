"""Receivable runs (7.5 Sollstellung, 7.3): preview, post, reverse.

Monthly components only. Proration within a month, non monthly intervals, workday due rules and
VAT on receivables need a released rule (7.5: no free 30/360 method; M13-01 to M13-03) and are
listed as manual items, never computed by assumption.
"""

import calendar
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    EntryKind,
    EntrySource,
    ItemStatus,
    JournalEntry,
    Ledger,
    LedgerAccount,
    PaymentTypeAccount,
    ReceivableItem,
    ReceivableRun,
    RunStatus,
)
from mhvp.core.problems import ErrorCodes, ProblemError

PRORATION = "Unterjähriger Beginn oder Wechsel: zeitanteilige Regel nicht freigegeben"


def month_bounds(period: date) -> tuple[date, date]:
    first = period.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def due_date(rule: str, day: int, first: date) -> date | None:
    last = calendar.monthrange(first.year, first.month)[1]
    if rule == "day":
        return first.replace(day=min(day, last))
    if rule == "last_day":
        return first.replace(day=last)
    if rule == "day_next_month":
        nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        return nxt.replace(day=min(day, calendar.monthrange(nxt.year, nxt.month)[1]))
    return None  # workday: holiday calendar not released (M13-02)


async def compute(
    session: AsyncSession, period: date, scope: str, scope_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    from mhvp.contracts.models import (
        Contract,
        ContractPayment,
        PaymentSchedule,
    )

    first, last = month_bounds(period)
    query = select(Contract).where(
        Contract.start_date <= last, or_(Contract.end_date.is_(None), Contract.end_date >= first)
    )
    if scope == "property" and scope_id:
        query = query.where(Contract.property_id == scope_id)
    elif scope == "contract" and scope_id:
        query = query.where(Contract.id == scope_id)
    contracts = (await session.scalars(query.order_by(Contract.number))).all()
    ledgers = {x.legal_entity_id: x for x in (await session.scalars(select(Ledger))).all()}
    mapping = {
        (m.ledger_id, m.payment_type_code): m.account_id
        for m in (await session.scalars(select(PaymentTypeAccount))).all()
    }
    posted = {
        (i.contract_id, i.payment_type_code)
        for i in (
            await session.scalars(
                select(ReceivableItem).where(
                    ReceivableItem.period_month == first, ReceivableItem.status == ItemStatus.POSTED
                )
            )
        ).all()
    }
    items: list[dict[str, Any]] = []
    for contract in contracts:
        ledger = ledgers.get(contract.legal_entity_id)
        schedule = await session.scalar(
            select(PaymentSchedule).where(
                PaymentSchedule.contract_id == contract.id,
                PaymentSchedule.valid_from <= first,
                or_(PaymentSchedule.valid_to.is_(None), PaymentSchedule.valid_to >= last),
            )
        )
        payments = (
            await session.scalars(
                select(ContractPayment).where(
                    ContractPayment.contract_id == contract.id,
                    ContractPayment.valid_from <= last,
                    or_(ContractPayment.valid_to.is_(None), ContractPayment.valid_to >= first),
                )
            )
        ).all()
        partial_contract = contract.start_date > first or (
            contract.end_date is not None and contract.end_date < last
        )
        for p in sorted(payments, key=lambda x: (x.payment_type_code, x.valid_from)):
            item: dict[str, Any] = {
                "contract_id": contract.id,
                "contract_number": contract.number,
                "contract_payment_id": p.id,
                "ledger_id": ledger.id if ledger else None,
                "payment_type_code": p.payment_type_code,
                "amount": p.gross,
                "vat_percent": p.vat_percent,
                "due_date": None,
                "status": ItemStatus.READY,
                "message": None,
            }

            def mark(status: ItemStatus, message: str, item: dict[str, Any] = item) -> None:
                if item["status"] is ItemStatus.READY:
                    item["status"], item["message"] = status, message

            if (contract.id, p.payment_type_code) in posted:
                continue  # already posted for this period (B08)
            if (
                partial_contract
                or p.valid_from > first
                or (p.valid_to is not None and p.valid_to < last)
            ):
                mark(ItemStatus.MANUAL, PRORATION)
            if ledger is None:
                mark(ItemStatus.BLOCKED, "Kein Buchungskreis für den Gläubiger")
            elif (ledger.id, p.payment_type_code) not in mapping:
                mark(ItemStatus.BLOCKED, f"Kein Erlöskonto für Zahlungsart {p.payment_type_code}")
            if schedule is None:
                mark(ItemStatus.BLOCKED, "Kein Zahlungsintervall für den ganzen Monat")
            elif schedule.interval.value != "monthly":
                mark(ItemStatus.MANUAL, "Nicht monatliches Intervall: Regel nicht freigegeben")
            else:
                item["due_date"] = due_date(schedule.due_day_rule.value, schedule.due_day, first)
                if item["due_date"] is None:
                    mark(ItemStatus.MANUAL, "Fälligkeit nach Werktag: Feiertagskalender offen")
            if p.vat_percent != 0:
                mark(
                    ItemStatus.MANUAL,
                    "Umsatzsteuer auf Sollstellung: Steuerbehandlung nicht freigegeben",
                )
            if p.gross <= 0:
                mark(ItemStatus.MANUAL, "Betrag nicht positiv (Minderung): gesondert prüfen")
            items.append(item)
    return items


def digest(items: list[dict[str, Any]]) -> str:
    stable = [
        {
            k: str(v)
            for k, v in sorted(i.items())
            if k in {"contract_payment_id", "amount", "status", "due_date", "ledger_id"}
        }
        for i in items
    ]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"count": len(items)}
    for status in ItemStatus:
        chosen = [i for i in items if i["status"] is status]
        if chosen:
            out[status.value] = {
                "count": len(chosen),
                "amount": str(sum((i["amount"] for i in chosen), Decimal("0.00"))),
            }
    return out


async def create_preview(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    period: date,
    scope: str,
    scope_id: uuid.UUID | None,
) -> ReceivableRun:
    first, _ = month_bounds(period)
    items = await compute(session, first, scope, scope_id)
    run = ReceivableRun(
        tenant_id=tenant_id,
        created_by=user_id,
        period_month=first,
        scope=scope,
        scope_id=scope_id,
        preview_hash=digest(items),
        totals=totals(items),
    )
    session.add(run)
    await session.flush()
    for i in items:
        session.add(
            ReceivableItem(
                tenant_id=tenant_id,
                run_id=run.id,
                period_month=first,
                **{k: v for k, v in i.items() if k != "contract_number"},
            )
        )
    await session.flush()
    return run


async def post_run(
    session: AsyncSession, run: ReceivableRun, user_id: uuid.UUID | None
) -> ReceivableRun:
    """Post exactly the previewed ready items; a changed basis invalidates the preview."""
    if run.status is RunStatus.POSTED:
        return run  # repeated click (B08)
    if run.status is not RunStatus.PREVIEW:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Lauf ist storniert.")
    current = await compute(session, run.period_month, run.scope, run.scope_id)
    if digest(current) != run.preview_hash:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Die Grundlagen haben sich geändert. Bitte neue Vorschau erstellen.",
        )
    from mhvp.contracts.models import Contract, DebtorAccountReservation

    mapping = {
        (m.ledger_id, m.payment_type_code): m.account_id
        for m in (await session.scalars(select(PaymentTypeAccount))).all()
    }
    items = (
        await session.scalars(
            select(ReceivableItem).where(
                ReceivableItem.run_id == run.id, ReceivableItem.status == ItemStatus.READY
            )
        )
    ).all()
    for item in items:
        ledger = await session.get(Ledger, item.ledger_id)
        contract = await session.get(Contract, item.contract_id)
        if ledger is None or contract is None:  # pragma: no cover - checked in compute
            raise ProblemError(ErrorCodes.CONFLICT)
        reservation = await session.get(DebtorAccountReservation, contract.debtor_account_id)
        debtor = await session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.number == (reservation.number if reservation else ""),
            )
        )
        if debtor is None:
            await acc.sync_debtor_accounts(session, ledger)
            debtor = await session.scalar(
                select(LedgerAccount).where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.number == (reservation.number if reservation else ""),
                )
            )
        if debtor is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"Debitorenkonto für Vertrag {contract.number} fehlt."
            )
        entry = JournalEntry(
            tenant_id=run.tenant_id,
            created_by=user_id,
            ledger_id=ledger.id,
            booking_date=item.due_date or run.period_month,
            due_date=item.due_date,
            accrual_date=run.period_month,
            text=(
                f"Sollstellung {run.period_month:%m/%Y} {item.payment_type_code} "
                f"Vertrag {contract.number}"
            ),
            kind=EntryKind.RECEIVABLE,
            contract_id=contract.id,
            source=EntrySource.AUTO_RECEIVABLE,
            idempotency_key=f"receivable:{contract.id}:{item.payment_type_code}:{run.period_month.isoformat()}",
        )
        lines = [
            acc.LineIn(debtor.id, item.amount, Decimal("0")),
            acc.LineIn(mapping[(ledger.id, item.payment_type_code)], Decimal("0"), item.amount),
        ]
        await acc.write_draft(session, ledger, entry, lines, [])
        await acc.post(session, ledger, entry, user_id)
        item.status, item.journal_entry_id = ItemStatus.POSTED, entry.id
    run.status, run.posted_at, run.posted_by = RunStatus.POSTED, datetime.now(UTC), user_id
    await session.flush()
    return run


async def reverse_run(
    session: AsyncSession,
    run: ReceivableRun,
    user_id: uuid.UUID | None,
    reason: str,
    booking_date: date,
) -> int:
    if run.status is not RunStatus.POSTED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur gebuchte Läufe können storniert werden."
        )
    items = (
        await session.scalars(
            select(ReceivableItem).where(
                ReceivableItem.run_id == run.id, ReceivableItem.status == ItemStatus.POSTED
            )
        )
    ).all()
    for item in items:
        entry = await session.get(JournalEntry, item.journal_entry_id, with_for_update=True)
        ledger = await session.get(Ledger, item.ledger_id)
        if entry is None or ledger is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.CONFLICT)
        await acc.reverse(
            session, ledger, entry, user_id=user_id, reason=reason, booking_date=booking_date
        )
        item.status = ItemStatus.REVERSED
    run.status = RunStatus.REVERSED
    await session.flush()
    return len(items)


def admin_fee(setting: Any, unit_counts: dict[str, int]) -> dict[str, Any]:
    """Net fee per interval from amounts per unit type with min/max (draft, 6.4)."""
    lines = []
    net = Decimal("0.00")
    for unit_type, count in sorted(unit_counts.items()):
        rate = setting.amounts_per_unit_type.get(unit_type)
        if rate is None or count == 0:
            continue
        amount = (Decimal(rate) * count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        lines.append({"unit_type": unit_type, "count": count, "rate": rate, "amount": str(amount)})
        net += amount
    if setting.min_amount is not None and net < setting.min_amount:
        net = setting.min_amount
    if setting.max_amount is not None and net > setting.max_amount:
        net = setting.max_amount
    net = net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat = (net * setting.vat_percent / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "lines": lines,
        "net": str(net),
        "vat_percent": str(setting.vat_percent),
        "vat": str(vat),
        "gross": str(net + vat),
        "status": "draft",
    }
