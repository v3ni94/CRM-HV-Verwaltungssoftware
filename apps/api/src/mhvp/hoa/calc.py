"""WEG calculations (7.8 W02, W05, W07, W08, W11; D01 to D03). The result of the annual
statement is computed against the resolved advances (Soll), never against payments; arrears
stay separate. Reserve development uses actual contributions."""

import hashlib
import json
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.calc import CENT, Share, days, distribute, overlap

ZERO = Decimal("0.00")


def digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


async def unit_weights(
    session: AsyncSession, property_id: uuid.UUID, key_id: uuid.UUID, start: date, end: date
) -> list[Share]:
    """Key value per unit, time weighted over the period (value periods, not owners)."""
    from mhvp.core.problems import ErrorCodes, ProblemError
    from mhvp.properties.models import Unit, UnitAllocationValue

    units = (
        await session.scalars(
            select(Unit).where(Unit.property_id == property_id).order_by(Unit.number)
        )
    ).all()
    shares = []
    total_days = days(start, end)
    for unit in units:
        values = (
            await session.scalars(
                select(UnitAllocationValue).where(
                    UnitAllocationValue.unit_id == unit.id,
                    UnitAllocationValue.allocation_key_id == key_id,
                )
            )
        ).all()
        weight, covered = Decimal(0), 0
        for v in values:
            span = overlap(start, end, v.valid_from, v.valid_to)
            if span:
                weight += v.value * days(*span)
                covered += days(*span)
        if covered == 0:
            continue  # unit not part of this key (e.g. other entrance), W03 needs documented scope
        if covered != total_days:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Schlüsselwert für Einheit {unit.number} deckt nicht den ganzen Zeitraum.",
            )
        shares.append(Share((unit.number, str(unit.id)), weight / total_days))
    if not shares or sum((s.weight for s in shares), Decimal(0)) <= 0:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Schlüsselsumme ist null oder negativ (W12)."
        )
    return shares


async def plan_results(
    session: AsyncSession, property_id: uuid.UUID, items: list[Any], start: date, end: date
) -> dict[str, Any]:
    per_unit: dict[str, dict[str, Decimal]] = {}
    numbers: dict[str, str] = {}
    for item in items:
        dist = distribute(
            item.amount,
            await unit_weights(session, property_id, item.allocation_key_id, start, end),
        )
        for (number, unit_id), value in dist.items():
            numbers[unit_id] = number
            bucket = per_unit.setdefault(unit_id, {"hoa_fee": ZERO, "reserve": ZERO})
            bucket[item.component] += value
    units = []
    for unit_id, comp in sorted(per_unit.items(), key=lambda kv: numbers[kv[0]]):
        monthly = {k: (v / 12).quantize(CENT, rounding=ROUND_HALF_UP) for k, v in comp.items()}
        units.append(
            {
                "unit_id": unit_id,
                "unit_number": numbers[unit_id],
                "annual": {k: str(v) for k, v in comp.items()},
                "monthly": {k: str(v) for k, v in monthly.items()},
                "rounding_difference": {k: str(comp[k] - monthly[k] * 12) for k in comp},
            }
        )
    totals = {
        c: str(sum((i.amount for i in items if i.component == c), ZERO))
        for c in ("hoa_fee", "reserve")
    }
    return {"units": units, "totals": totals}


async def advances(
    session: AsyncSession, unit_id: uuid.UUID, component: str, start: date, end: date
) -> tuple[Decimal, Decimal]:
    """Resolved advances (posted receivable items) and payments on them for a unit and year."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import ItemStatus, OpenItem, ReceivableItem
    from mhvp.contracts.models import Contract

    items = (
        await session.scalars(
            select(ReceivableItem)
            .join(Contract, Contract.id == ReceivableItem.contract_id)
            .where(
                Contract.unit_id == unit_id,
                ReceivableItem.payment_type_code == component,
                ReceivableItem.status == ItemStatus.POSTED,
                ReceivableItem.period_month.between(start, end),
            )
        )
    ).all()
    due = sum((i.amount for i in items), ZERO)
    paid = ZERO
    for i in items:
        oi = await session.scalar(
            select(OpenItem).where(OpenItem.journal_entry_id == i.journal_entry_id)
        )
        if oi is not None:
            paid += oi.amount - await acc.remaining(session, oi.id)
    return due, paid


async def statement_results(
    session: AsyncSession, statement: Any, ledger: Any, items: list[Any]
) -> dict[str, Any]:
    start, end = date(statement.year, 1, 1), date(statement.year, 12, 31)
    costs: dict[str, Decimal] = {}
    numbers: dict[str, str] = {}
    positions = []
    for item in items:
        dist = distribute(
            item.amount,
            await unit_weights(session, ledger.property_id, item.allocation_key_id, start, end),
        )
        positions.append(
            {
                "label": item.label,
                "amount": str(item.amount),
                "basis": item.basis,
                "split": {k[1]: str(v) for k, v in dist.items()},
            }
        )
        for (number, unit_id), value in dist.items():
            numbers[unit_id] = number
            costs[unit_id] = costs.get(unit_id, ZERO) + value
    units = []
    reserve_due = reserve_paid = ZERO
    for unit_id in sorted(costs, key=lambda u: numbers[u]):
        uid = uuid.UUID(unit_id)
        soll, paid = await advances(session, uid, "hoa_fee", start, end)
        r_due, r_paid = await advances(session, uid, "reserve", start, end)
        reserve_due += r_due
        reserve_paid += r_paid
        result = costs[unit_id] - soll
        arrears = soll - paid
        units.append(
            {
                "unit_id": unit_id,
                "unit_number": numbers[unit_id],
                "cost_share": str(costs[unit_id]),
                "advances_resolved": str(soll),
                "advances_paid": str(paid),
                "result": str(result),  # > 0 Nachschuss (Abrechnungsspitze), < 0 Anpassung
                "arrears": str(arrears),  # existing claims with their own legal basis (W05)
                "information_total": str(result + arrears),  # information only, not a new claim
                "reserve_due": str(r_due),
                "reserve_paid": str(r_paid),
                # M24-01 (decided 24.09.2026): information for buyer and seller only; the
                # result is owed by the owner at the resolution date, arrears stay with the
                # original debtor.
                "ownership_periods": await ownership_periods(session, uid, start, end),
            }
        )
    closing = (
        statement.reserve_opening
        + reserve_paid
        - statement.reserve_withdrawals
        + statement.reserve_interest
    )
    reserve = {
        "opening": str(statement.reserve_opening),
        "contributions_resolved": str(reserve_due),
        "contributions_paid": str(reserve_paid),
        "contributions_open": str(reserve_due - reserve_paid),  # not available funds (W08)
        "withdrawals": str(statement.reserve_withdrawals),
        "interest": str(statement.reserve_interest),
        "closing": str(closing),
    }
    return {
        "units": units,
        "positions": positions,
        "reserve": reserve,
        "total_costs": str(sum((i.amount for i in items), ZERO)),
    }


async def asset_report(
    session: AsyncSession, ledger: Any, year: int, reserve_closing: str
) -> dict[str, Any]:
    """§ 28 Abs. 4 WEG asset report basis (W11): reserves plus liquid funds, receivables,
    liabilities and loans as additional project figures."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import (
        AccountCategory,
        EntryStatus,
        JournalEntry,
        JournalLine,
        LedgerAccount,
    )

    end = date(year, 12, 31)

    async def balance(category: AccountCategory) -> Decimal:
        d, c = (
            await session.execute(
                select(
                    func.coalesce(func.sum(JournalLine.debit), 0),
                    func.coalesce(func.sum(JournalLine.credit), 0),
                )
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
                .where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.category == category,
                    JournalEntry.status == EntryStatus.POSTED,
                    JournalEntry.booking_date <= end,
                )
            )
        ).one()
        return Decimal(d) - Decimal(c)

    items = await acc.open_items(session, ledger, end)
    return {
        "year": year,
        "legal_minimum": {"reserve_closing": reserve_closing},
        "additional": {
            "liquid_funds": str(
                await balance(AccountCategory.BANK) + await balance(AccountCategory.CASH)
            ),
            "open_receivables": str(
                sum(
                    (
                        i["remaining"]
                        for i in items
                        if i["kind"] == "receivable" and i["remaining"] > 0
                    ),
                    ZERO,
                )
            ),
            "open_payables": str(
                sum((i["remaining"] for i in items if i["kind"] == "payable"), ZERO)
            ),
            "loans": str(-(await balance(AccountCategory.LOAN))),
        },
    }


async def owner_at(session: AsyncSession, unit_id: uuid.UUID, day: date) -> Any:
    """Owner contract of the unit on a day (rule owner-at-resolution-v1, open question M24-01)."""
    from mhvp.contracts.models import Contract, ContractKind

    return await session.scalar(
        select(Contract).where(
            Contract.unit_id == uuid.UUID(str(unit_id)),
            Contract.kind == ContractKind.OWNERSHIP,
            Contract.start_date <= day,
            or_(Contract.end_date.is_(None), Contract.end_date >= day),
        )
    )


async def ownership_periods(
    session: AsyncSession, unit_id: uuid.UUID, start: date, end: date
) -> list[dict[str, Any]]:
    from mhvp.contracts.models import Contract, ContractKind

    rows = (
        await session.scalars(
            select(Contract)
            .where(
                Contract.unit_id == unit_id,
                Contract.kind == ContractKind.OWNERSHIP,
                Contract.start_date <= end,
                or_(Contract.end_date.is_(None), Contract.end_date >= start),
            )
            .order_by(Contract.start_date)
        )
    ).all()
    out = []
    for c in rows:
        s_, e_ = max(c.start_date, start), min(c.end_date or end, end)
        out.append(
            {
                "contract_id": str(c.id),
                "party_id": str(c.party_id),
                "from": s_.isoformat(),
                "to": e_.isoformat(),
                "days": days(s_, e_),
            }
        )
    return out
