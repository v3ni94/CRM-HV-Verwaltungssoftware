"""WEG calculations (7.8 W02, W05, W07, W08, W11; D01 to D03). The result of the annual
statement is computed against the resolved advances (Soll), never against payments; arrears
stay separate. Reserve development uses actual contributions."""

import hashlib
import json
import uuid
from datetime import date, timedelta
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
    bank = await reserve_bank_balance(session, ledger, end)
    reserve = {
        "opening": str(statement.reserve_opening),
        "contributions_resolved": str(reserve_due),
        "contributions_paid": str(reserve_paid),
        "contributions_open": str(reserve_due - reserve_paid),  # not available funds (W08)
        "withdrawals": str(statement.reserve_withdrawals),
        "interest": str(statement.reserve_interest),
        "closing": str(closing),
        # W08, D19: the bank balance of the reserve accounts is shown apart from the accounting
        # reserve; a difference is explained here, never settled by an automatic entry.
        "bank_balance": str(bank),
        "bank_difference": str(bank - closing),
        "bank_difference_note": (
            "Bankanlage entspricht dem Rücklagenbestand."
            if bank == closing
            else "Bankanlage und Rücklagenbestand weichen ab; Differenz erklären "
            "(offene Beiträge sind kein vorhandenes Geld), keine Ausgleichsbuchung."
        ),
    }
    return {
        "units": units,
        "positions": positions,
        "reserve": reserve,
        "total_costs": str(sum((i.amount for i in items), ZERO)),
    }


async def reserve_bank_balance(session: AsyncSession, ledger: Any, as_of: date) -> Decimal:
    """Balance of the reserve bank accounts of the ledger (same identification as 7.5
    liquidity: bank account of kind reserve, or the default account 001201)."""
    from mhvp.accounting.models import AccountCategory, LedgerAccount
    from mhvp.accounting.reports import _balance
    from mhvp.properties.models import BankAccountKind, PropertyBankAccount

    total = ZERO
    for account in (
        await session.scalars(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category == AccountCategory.BANK,
            )
        )
    ).all():
        if account.property_bank_account_id:
            bank = await session.get(PropertyBankAccount, account.property_bank_account_id)
            is_reserve = bank is not None and bank.kind is BankAccountKind.RESERVE
        else:
            is_reserve = account.number == "001201"
        if is_reserve:
            total += await _balance(session, account.id, as_of)
    return total


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


# W04 (A60): cash flow reconciliation ---------------------------------------------------------

# Codes the manager may use for an explained difference (statement.reconciliation_notes).
RECONCILIATION_NOTE_CODES = ("heating_accrual", "creditor_timing", "prior_year", "other")
_CASH = ("bank", "cash")


def _category(account: Any) -> str:
    """Flow category of a counter account: cost, creditor, debtor, loan, reserve, revenue,
    other (transit, tax, technical, opening balance)."""
    cat = str(account.category.value)
    if cat in ("cost", "creditor", "debtor", "loan", "reserve", "revenue"):
        return cat
    if cat == "technical" and account.statement_kind.value == "reserve":
        return "reserve"
    return "other"


async def cash_flow_reconciliation(
    session: AsyncSession,
    ledger: Any,
    year: int,
    cost_total: Decimal,
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Gesamtgeldfluss and Überleitung (W04): opening and closing balances of the bank and cash
    accounts, in and out flows by counter account category, and the bridge from the cash paid
    for costs over the costs booked in the year to the distribution relevant costs of the
    statement. Automatic explanations: creditor timing (invoice booked against payment), loan
    positions (W10 items or loan accounts), reserve, owner refunds, transit. Manual explanations
    come from `notes` (heating accrual and the like). The unexplained rest is returned as a
    finding; the package blocks while it is not zero. Transfers between own bank and cash
    accounts carry no counter line and are therefore neither inflow nor outflow."""
    from mhvp.accounting.models import (
        AccountCategory,
        EntryStatus,
        JournalEntry,
        JournalLine,
        LedgerAccount,
    )
    from mhvp.accounting.reports import _balance
    from mhvp.hoa.models import HoaLoanItem

    start, end = date(year, 1, 1), date(year, 12, 31)
    accounts = {
        a.id: a
        for a in (
            await session.scalars(select(LedgerAccount).where(LedgerAccount.ledger_id == ledger.id))
        ).all()
    }
    cash_ids = {a.id for a in accounts.values() if a.category.value in _CASH}
    cash_accounts = []
    opening_total = closing_total = ZERO
    for a in sorted((accounts[i] for i in cash_ids), key=lambda x: x.number):
        opening = await _balance(session, a.id, start - timedelta(days=1)) + ZERO
        closing = await _balance(session, a.id, end) + ZERO
        opening_total += opening
        closing_total += closing
        cash_accounts.append(
            {
                "number": a.number,
                "name": a.name,
                "category": a.category.value,
                "opening": str(opening),
                "closing": str(closing),
            }
        )
    # Entries linked to a loan item (W10): their counter lines are loan positions by kind.
    loan_entries: dict[uuid.UUID, str] = {
        r.journal_entry_id: r.kind
        for r in (
            await session.scalars(
                select(HoaLoanItem).where(HoaLoanItem.journal_entry_id.is_not(None))
            )
        ).all()
        if r.journal_entry_id is not None
    }
    rows = (
        await session.execute(
            select(JournalLine, JournalEntry.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
        )
    ).all()
    by_entry: dict[uuid.UUID, list[Any]] = {}
    for line, entry_id in rows:
        by_entry.setdefault(entry_id, []).append(line)
    inflows: dict[str, Decimal] = {}
    outflows: dict[str, Decimal] = {}
    cost_booked = ZERO  # net debit on cost accounts, all posted entries, without loan entries
    cost_via_creditor = ZERO  # cost booked in entries with a creditor line and no cash line
    for entry_id, lines in by_entry.items():
        has_cash = any(ln.account_id in cash_ids for ln in lines)
        has_creditor = any(
            accounts[ln.account_id].category is AccountCategory.CREDITOR for ln in lines
        )
        loan_kind = loan_entries.get(entry_id)
        for ln in lines:
            if ln.account_id in cash_ids:
                continue
            account = accounts[ln.account_id]
            value = ln.debit - ln.credit
            if account.category is AccountCategory.COST and loan_kind is None:
                cost_booked += value
                if has_creditor and not has_cash:
                    cost_via_creditor += value
            if not has_cash:
                continue
            category = f"loan_{loan_kind}" if loan_kind else _category(account)
            if value > 0:
                outflows[category] = outflows.get(category, ZERO) + value
            elif value < 0:
                inflows[category] = inflows.get(category, ZERO) - value
    inflows_total = sum(inflows.values(), ZERO)
    outflows_total = sum(outflows.values(), ZERO)

    def flow(bucket: dict[str, Decimal], *keys: str) -> Decimal:
        return sum((v for k, v in bucket.items() if k in keys or k.startswith(keys)), ZERO)

    loan_out = flow(outflows, "loan")
    non_cost_out = (
        flow(outflows, "reserve")
        + loan_out
        + flow(outflows, "debtor")
        + flow(outflows, "other")
        + flow(outflows, "revenue")
    )
    cost_refunds = flow(inflows, "cost") + flow(inflows, "creditor")
    cost_paid = outflows_total - non_cost_out - cost_refunds
    creditor_paid = flow(outflows, "creditor") - flow(inflows, "creditor")
    creditor_timing = creditor_paid - cost_via_creditor
    structure_residual = cost_paid - creditor_timing - cost_booked
    manual = []
    manual_total = ZERO
    for n in notes:
        amount = Decimal(str(n["amount"]))
        manual_total += amount
        manual.append({"code": n["code"], "amount": str(amount), "note": n["note"]})
    unexplained = cost_total - cost_booked - manual_total + structure_residual
    bridge = [
        {"code": "outflows", "amount": str(outflows_total)},
        {"code": "reserve", "amount": str(-flow(outflows, "reserve"))},
        {"code": "loan", "amount": str(-loan_out)},
        {"code": "owner_refund", "amount": str(-flow(outflows, "debtor"))},
        {
            "code": "other_non_cost",
            "amount": str(-(flow(outflows, "other") + flow(outflows, "revenue"))),
        },
        {"code": "cost_refunds", "amount": str(-cost_refunds)},
        {"code": "cost_paid", "amount": str(cost_paid), "subtotal": True},
        {"code": "creditor_timing", "amount": str(-creditor_timing)},
        {"code": "structure_residual", "amount": str(-structure_residual)},
        {"code": "cost_booked", "amount": str(cost_booked), "subtotal": True},
        *[
            {"code": m["code"], "amount": m["amount"], "note": m["note"], "manual": True}
            for m in manual
        ],
        {"code": "cost_distributed", "amount": str(cost_total), "subtotal": True},
        {"code": "unexplained", "amount": str(unexplained)},
    ]
    return {
        "year": year,
        "cash": {
            "accounts": cash_accounts,
            "opening": str(opening_total),
            "inflows": str(inflows_total),
            "outflows": str(outflows_total),
            "closing": str(closing_total),
            # opening + inflows - outflows == closing by construction of the posted lines
            "check_ok": opening_total + inflows_total - outflows_total == closing_total,
        },
        "inflows": {k: str(v) for k, v in sorted(inflows.items())},
        "outflows": {k: str(v) for k, v in sorted(outflows.items())},
        "loan_positions": {
            k.removeprefix("loan_"): str(v)
            for k, v in sorted({**inflows, **outflows}.items())
            if k.startswith("loan_")
        },
        "bridge": bridge,
        "cost_booked": str(cost_booked),
        "cost_distributed": str(cost_total),
        "explained_manual": manual,
        "unexplained": str(unexplained),
        "note": (
            "Überleitung stimmt: Geldfluss, gebuchte und verteilte Kosten sind abgestimmt."
            if unexplained == ZERO
            else "Unerklärte Differenz zwischen gebuchten und verteilten Kosten; erklären "
            "(Heizkostenabgrenzung, Zeitbezug, Vorjahr) oder Positionen korrigieren (W04)."
        ),
    }
