"""Additional evaluations of section 7.7 (M18-01 to M18-04, M18-06): common header, month matrix,
target/actual receivables, bank account statement and the draft VAT overview.

Every evaluation is per legal entity (one ledger each, B01), built from posted entries only
(B03) and carries the common header of ``report_header`` (M18-04). All results are drafts for
internal use; none of them is a tax return, an EÜR or a certificate. Amounts are ``Decimal``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
    OpenItemSettlement,
)
from mhvp.core.problems import ErrorCodes, ProblemError

ZERO = Decimal("0.00")
DRAFT_NOTE = (
    "Entwurf zur internen Verwendung: Auswertung aus gebuchten Sätzen, keine Steuererklärung, "
    "keine Bescheinigung und keine Bewertung durch einen Steuerberater."
)
MAX_MONTHS = 60


async def report_header(
    session: AsyncSession,
    ledger: Ledger,
    *,
    report: str,
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Common header (7.7 Absatz 1, M18-04): legal entity, period, key date, data state
    (time of generation), applied filters and draft status."""
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, ledger.legal_entity_id)
    return {
        "report": report,
        "legal_entity_id": ledger.legal_entity_id,
        "legal_entity_name": entity.name if entity is not None else None,
        "legal_entity_kind": entity.kind.value
        if entity is not None and hasattr(entity.kind, "value")
        else (entity.kind if entity is not None else None),
        "ledger_id": ledger.id,
        "ledger_name": ledger.name,
        "period_start": start,
        "period_end": end,
        "as_of": as_of,
        "generated_at": datetime.now(UTC),
        "filters": {k: v for k, v in (filters or {}).items() if v not in (None, "")},
        "status": "draft",
        "status_note": DRAFT_NOTE,
    }


def month_keys(start: date, end: date) -> list[str]:
    if end < start:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Zeitraumende liegt vor dem Beginn.")
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    if len(keys) > MAX_MONTHS:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"Die Monatsmatrix umfasst höchstens {MAX_MONTHS} Monate.",
        )
    return keys


def _natural(category: AccountCategory, debit: Decimal, credit: Decimal) -> Decimal:
    """Revenue and liability like accounts read on the credit side, everything else debit."""
    if category is AccountCategory.REVENUE:
        return credit - debit
    return debit - credit


async def monthly_matrix(
    session: AsyncSession,
    ledger: Ledger,
    start: date,
    end: date,
    categories: list[AccountCategory] | None = None,
    eur_only: bool = False,
    property_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Accounts (default revenue and cost) by month (M18-01). Amount sign: revenue accounts
    credit minus debit, all others debit minus credit. Totals per account and per month.
    ``property_id`` keeps only lines of that object (``journal_line.property_id``, Q15-01)."""
    months = month_keys(start, end)
    wanted = categories or [AccountCategory.REVENUE, AccountCategory.COST]
    year = extract("year", JournalEntry.booking_date)
    month = extract("month", JournalEntry.booking_date)
    query = (
        select(
            LedgerAccount.number,
            LedgerAccount.name,
            LedgerAccount.category,
            year,
            month,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.category.in_(wanted),
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.booking_date.between(start, end),
        )
        .group_by(LedgerAccount.number, LedgerAccount.name, LedgerAccount.category, year, month)
        .order_by(LedgerAccount.number)
    )
    if eur_only:
        query = query.where(LedgerAccount.eur_relevant.is_(True))
    if property_id is not None:
        query = query.where(JournalLine.property_id == property_id)
    rows: dict[str, dict[str, Any]] = {}
    for number, name, category, y, m, debit, credit in (await session.execute(query)).all():
        row = rows.setdefault(
            number,
            {
                "number": number,
                "name": name,
                "category": category.value,
                "months": dict.fromkeys(months, ZERO),
                "total": ZERO,
            },
        )
        value = _natural(category, Decimal(debit), Decimal(credit))
        row["months"][f"{int(y):04d}-{int(m):02d}"] += value
        row["total"] += value
    accounts = [rows[k] for k in sorted(rows)]
    totals_by_category: dict[str, dict[str, Decimal]] = {}
    for row in accounts:
        bucket = totals_by_category.setdefault(
            row["category"], {**dict.fromkeys(months, ZERO), "total": ZERO}
        )
        for key in months:
            bucket[key] += row["months"][key]
        bucket["total"] += row["total"]
    return {
        "header": await report_header(
            session,
            ledger,
            report="monthly_matrix",
            start=start,
            end=end,
            filters={
                "categories": ",".join(c.value for c in wanted),
                "eur_only": eur_only or None,
                "property_id": str(property_id) if property_id else None,
            },
        ),
        "months": months,
        "accounts": accounts,
        "totals_by_category": totals_by_category,
        "sign_note": "Ertragskonten Haben minus Soll, alle anderen Konten Soll minus Haben.",
    }


async def target_actual(
    session: AsyncSession,
    ledger: Ledger,
    start: date,
    end: date,
    unit_id: uuid.UUID | None = None,
    component: str | None = None,
) -> dict[str, Any]:
    """Target/actual comparison of receivables (M18-02). Target: open items of kind receivable
    whose due date (booking date when none) lies in the period. Actual on target: the
    settlements of those items up to the end of the period (reversals net out). Additionally
    the receipts of the period: all settlements dated in the period on receivable items of
    the ledger. Difference target minus actual on target; nothing is offset across
    debtors (B01)."""
    due = func.coalesce(OpenItem.due_date, OpenItem.booking_date)
    target_q = (
        select(
            LedgerAccount.id,
            LedgerAccount.number,
            LedgerAccount.name,
            LedgerAccount.unit_id,
            func.sum(OpenItem.amount),
            func.count(OpenItem.id),
        )
        .join(LedgerAccount, LedgerAccount.id == OpenItem.account_id)
        .where(
            OpenItem.ledger_id == ledger.id,
            OpenItem.kind == OpenItemKind.RECEIVABLE,
            OpenItem.written_off.is_(False),
            due.between(start, end),
        )
        .group_by(LedgerAccount.id)
        .order_by(LedgerAccount.number)
    )
    if unit_id is not None:
        target_q = target_q.where(LedgerAccount.unit_id == unit_id)
    if component:
        target_q = target_q.where(OpenItem.component == component)
    target = {r[0]: r for r in (await session.execute(target_q)).all()}

    actual_q = (
        select(OpenItem.account_id, func.coalesce(func.sum(OpenItemSettlement.amount), 0))
        .join(OpenItem, OpenItem.id == OpenItemSettlement.open_item_id)
        .where(
            OpenItem.ledger_id == ledger.id,
            OpenItem.kind == OpenItemKind.RECEIVABLE,
            OpenItem.written_off.is_(False),
            due.between(start, end),
            OpenItemSettlement.date <= end,
        )
        .group_by(OpenItem.account_id)
    )
    receipts_q = (
        select(OpenItem.account_id, func.coalesce(func.sum(OpenItemSettlement.amount), 0))
        .join(OpenItem, OpenItem.id == OpenItemSettlement.open_item_id)
        .where(
            OpenItem.ledger_id == ledger.id,
            OpenItem.kind == OpenItemKind.RECEIVABLE,
            OpenItemSettlement.date.between(start, end),
        )
        .group_by(OpenItem.account_id)
    )
    if component:
        actual_q = actual_q.where(OpenItem.component == component)
        receipts_q = receipts_q.where(OpenItem.component == component)
    actual = {r[0]: Decimal(r[1]) for r in (await session.execute(actual_q)).all()}
    receipts = {r[0]: Decimal(r[1]) for r in (await session.execute(receipts_q)).all()}
    rows = []
    for account_id, (_, number, name, unit, soll, count) in target.items():
        soll_d = Decimal(soll)
        ist = actual.get(account_id, ZERO)
        rows.append(
            {
                "account_id": account_id,
                "number": number,
                "name": name,
                "unit_id": unit,
                "items": int(count),
                "target": soll_d,
                "actual_on_target": ist,
                "difference": soll_d - ist,
                "receipts_in_period": receipts.get(account_id, ZERO),
            }
        )
    total_target = sum((r["target"] for r in rows), ZERO)
    total_actual = sum((r["actual_on_target"] for r in rows), ZERO)
    return {
        "header": await report_header(
            session,
            ledger,
            report="target_actual",
            start=start,
            end=end,
            filters={"unit_id": str(unit_id) if unit_id else None, "component": component},
        ),
        "rows": rows,
        "total_target": total_target,
        "total_actual_on_target": total_actual,
        "total_difference": total_target - total_actual,
        "total_receipts_in_period": sum((r["receipts_in_period"] for r in rows), ZERO),
        "note": (
            "Soll: Forderungen mit Fälligkeit im Zeitraum. Ist: Ausgleiche dieser Forderungen "
            "bis Zeitraumende. Zahlungseingänge im Zeitraum können frühere Forderungen betreffen."
        ),
    }


async def bank_statement(
    session: AsyncSession, ledger: Ledger, account_id: uuid.UUID, start: date, end: date
) -> dict[str, Any]:
    """Bank account statement per bank or cash account and period (M18-03): opening balance,
    movements, closing balance and the comparison with the bank balance of the latest imported
    statement that closes within the period (B09). A difference is shown, never booked."""
    from mhvp.banking.models import BankStatement

    account = await session.get(LedgerAccount, account_id)
    if (
        account is None
        or account.ledger_id != ledger.id
        or account.category not in (AccountCategory.BANK, AccountCategory.CASH)
    ):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    sheet = await acc.account_sheet(session, account, start, end)
    reconciliation: dict[str, Any] | None = None
    if account.property_bank_account_id is not None:
        statement = await session.scalar(
            select(BankStatement)
            .where(
                BankStatement.property_bank_account_id == account.property_bank_account_id,
                BankStatement.closing_balance.is_not(None),
                BankStatement.closing_date.is_not(None),
                BankStatement.closing_date.between(start, end),
            )
            .order_by(BankStatement.closing_date.desc(), BankStatement.created_at.desc())
            .limit(1)
        )
        if statement is not None and statement.closing_date is not None:
            d, c = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(JournalLine.debit), 0),
                        func.coalesce(func.sum(JournalLine.credit), 0),
                    )
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .where(
                        JournalLine.account_id == account.id,
                        JournalEntry.status == EntryStatus.POSTED,
                        JournalEntry.booking_date <= statement.closing_date,
                    )
                )
            ).one()
            ledger_balance = Decimal(d) - Decimal(c)
            bank_balance = Decimal(statement.closing_balance or 0)
            reconciliation = {
                "statement_ref": statement.statement_ref,
                "closing_date": statement.closing_date,
                "bank_closing_balance": bank_balance,
                "ledger_balance": ledger_balance,
                "difference": ledger_balance - bank_balance,
                "matches": ledger_balance == bank_balance,
            }
    return {
        "header": await report_header(
            session,
            ledger,
            report="bank_statement",
            start=start,
            end=end,
            filters={"account": f"{account.number} {account.name}"},
        ),
        "account": {"id": account.id, "number": account.number, "name": account.name},
        "opening_balance": sheet["opening_balance"],
        "movements": sheet["movements"],
        "closing_balance": sheet["closing_balance"],
        "debit": sheet["debit"],
        "credit": sheet["credit"],
        "reconciliation": reconciliation,
    }


# Tax evaluations (M18-06, decision 11 a, draft) ------------------------------------------

TAX_CHECKPOINTS: list[dict[str, str]] = [
    {
        "id": "S711-03",
        "topic": "Ausstellungs- und Empfangspflicht der E-Rechnung je Beteiligtem",
        "status": "offen",
        "owner": "Steuerberater (Entscheidung P03)",
        "note": "Ausnahme, Übergangsfrist und Unternehmereigenschaft der WEG sind nicht bewertet.",
    },
    {
        "id": "S711-05",
        "topic": "Vorsteuerberichtigung und Aufteilung gemischt genutzter Eingangsleistungen",
        "status": "offen",
        "owner": "Steuerberater (Entscheidung P03)",
        "note": "Konten mit Prüfkennzeichen sind aufgeführt, es findet keine Berechnung statt.",
    },
    {
        "id": "V8",
        "topic": "Kontenrahmen und steuerliche Kennzeichen je Konto",
        "status": "offen",
        "owner": "Steuerberater",
        "note": "Kennzeichen EÜR und USt sind Eingaben einer Person, keine Steuerbewertung.",
    },
]


async def vat_overview(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> dict[str, Any]:
    """Draft overview of VAT amounts per legal entity and month (M18-06, decision 11 a). Sums
    the ``vat_amount`` recorded on posted lines of accounts flagged as VAT relevant (or with a
    VAT option): on revenue accounts as Umsatzsteuer, on cost accounts as Vorsteuer before any
    deduction rule. No deductibility, Vorsteuerberichtigung, rate check or return field is
    applied. Not a Voranmeldung."""
    months = month_keys(start, end)
    year = extract("year", JournalEntry.booking_date)
    month = extract("month", JournalEntry.booking_date)
    from mhvp.accounting.models import AccountVatOption

    query = (
        select(
            LedgerAccount.category,
            JournalLine.vat_percent,
            year,
            month,
            func.coalesce(func.sum(JournalLine.vat_amount), 0),
            func.coalesce(func.sum(JournalLine.net_amount), 0),
            func.count(JournalLine.id),
        )
        .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.category.in_((AccountCategory.REVENUE, AccountCategory.COST)),
            (LedgerAccount.ust_relevant.is_(True))
            | (LedgerAccount.vat_option != AccountVatOption.NONE),
            JournalLine.vat_amount.is_not(None),
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.booking_date.between(start, end),
        )
        .group_by(LedgerAccount.category, JournalLine.vat_percent, year, month)
        .order_by(year, month, JournalLine.vat_percent)
    )
    by_month: dict[str, dict[str, Decimal]] = {
        key: {"output_vat": ZERO, "input_vat_before_deduction": ZERO} for key in months
    }
    by_rate: dict[str, dict[str, Any]] = {}
    for category, percent, y, m, vat, net, count in (await session.execute(query)).all():
        key = f"{int(y):04d}-{int(m):02d}"
        field = (
            "output_vat" if category is AccountCategory.REVENUE else "input_vat_before_deduction"
        )
        by_month[key][field] += Decimal(vat)
        rate_key = "ohne Satz" if percent is None else f"{Decimal(percent).normalize():f}"
        bucket = by_rate.setdefault(
            rate_key,
            {
                "vat_percent": percent,
                "output_vat": ZERO,
                "input_vat_before_deduction": ZERO,
                "net": ZERO,
                "lines": 0,
            },
        )
        bucket[field] += Decimal(vat)
        bucket["net"] += Decimal(net)
        bucket["lines"] += int(count)
    review_accounts = (
        await session.execute(
            select(LedgerAccount.number, LedgerAccount.name)
            .where(LedgerAccount.ledger_id == ledger.id, LedgerAccount.mixed_use_review.is_(True))
            .order_by(LedgerAccount.number)
        )
    ).all()
    flagged = await session.scalar(
        select(func.count(LedgerAccount.id)).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.ust_relevant.is_(True)
        )
    )
    output = sum((v["output_vat"] for v in by_month.values()), ZERO)
    inp = sum((v["input_vat_before_deduction"] for v in by_month.values()), ZERO)
    return {
        "header": await report_header(session, ledger, report="vat_overview", start=start, end=end),
        "months": months,
        "by_month": by_month,
        "by_rate": [by_rate[k] for k in sorted(by_rate)],
        "total_output_vat": output,
        "total_input_vat_before_deduction": inp,
        "ust_flagged_accounts": int(flagged or 0),
        "mixed_use_review_accounts": [{"number": n, "name": name} for n, name in review_accounts],
        "checkpoints": TAX_CHECKPOINTS,
        "note": (
            "Entwurf, keine Umsatzsteuer-Voranmeldung. Vorsteuer ist vor jeder Abzugsregel "
            "ausgewiesen, Berichtigung und Aufteilung sind nicht bewertet."
        ),
    }


async def income_expense(
    session: AsyncSession,
    ledger: Ledger,
    start: date,
    end: date,
    eur_only: bool = False,
    property_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Income and expenses per account from the postings (M18-06): for a HOA an income and
    expense statement of the community, explicitly no EÜR. Only account categories are read,
    no tax classification is made."""
    matrix = await monthly_matrix(session, ledger, start, end, None, eur_only, property_id)
    revenue = [a for a in matrix["accounts"] if a["category"] == AccountCategory.REVENUE.value]
    cost = [a for a in matrix["accounts"] if a["category"] == AccountCategory.COST.value]
    total_rev = sum((a["total"] for a in revenue), ZERO)
    total_cost = sum((a["total"] for a in cost), ZERO)
    header = matrix["header"] | {"report": "income_expense"}
    return {
        "header": header,
        "revenue": [{k: a[k] for k in ("number", "name", "total")} for a in revenue],
        "cost": [{k: a[k] for k in ("number", "name", "total")} for a in cost],
        "total_revenue": total_rev,
        "total_cost": total_cost,
        "surplus": total_rev - total_cost,
        "note": (
            "Einnahmen-/Ausgabenrechnung aus den gebuchten Sätzen, keine "
            "Einnahmenüberschussrechnung (EÜR) und keine Jahresabrechnung der Gemeinschaft."
        ),
    }


async def vat_overview_by_property(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> dict[str, Any]:
    """VAT overview grouped by object and cost center (M18-06, 7.7).

    The object is the line's own ``journal_line.property_id`` (Q15-01, AE21: explicit, from the
    unit or from the contract of the entry); lines without object are listed under "ohne
    Objekt", the cost center text of the line is the second grouping level. Same selection as
    ``vat_overview`` (VAT relevant accounts, posted entries only); no deduction rule, no return
    field. The sums of all groups equal the totals of ``vat_overview`` for the same period."""
    from mhvp.accounting.models import AccountVatOption
    from mhvp.properties.models import Property

    query = (
        select(
            JournalLine.property_id,
            JournalLine.cost_center,
            LedgerAccount.category,
            func.coalesce(func.sum(JournalLine.vat_amount), 0),
            func.coalesce(func.sum(JournalLine.net_amount), 0),
            func.count(JournalLine.id),
        )
        .select_from(LedgerAccount)
        .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.category.in_((AccountCategory.REVENUE, AccountCategory.COST)),
            (LedgerAccount.ust_relevant.is_(True))
            | (LedgerAccount.vat_option != AccountVatOption.NONE),
            JournalLine.vat_amount.is_not(None),
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.booking_date.between(start, end),
        )
        .group_by(JournalLine.property_id, JournalLine.cost_center, LedgerAccount.category)
    )
    groups: dict[tuple[Any, str], dict[str, Any]] = {}
    for prop_id, cost_center, category, vat, net, count in (await session.execute(query)).all():
        key = (prop_id, cost_center or "")
        bucket = groups.setdefault(
            key,
            {
                "property_id": prop_id,
                "cost_center": cost_center,
                "output_vat": ZERO,
                "input_vat_before_deduction": ZERO,
                "net_revenue": ZERO,
                "net_cost": ZERO,
                "lines": 0,
            },
        )
        if category is AccountCategory.REVENUE:
            bucket["output_vat"] += Decimal(vat)
            bucket["net_revenue"] += Decimal(net)
        else:
            bucket["input_vat_before_deduction"] += Decimal(vat)
            bucket["net_cost"] += Decimal(net)
        bucket["lines"] += int(count)
    ids = {k[0] for k in groups if k[0] is not None}
    labels: dict[uuid.UUID, str] = {}
    if ids:
        for prop in (await session.scalars(select(Property).where(Property.id.in_(ids)))).all():
            labels[prop.id] = " ".join(
                p for p in (prop.street, prop.house_number, prop.city) if p
            ) or str(prop.id)
    rows = sorted(
        groups.values(),
        key=lambda g: (
            g["property_id"] is None,
            labels.get(g["property_id"], ""),
            g["cost_center"] or "",
        ),
    )
    for row in rows:
        row["property_label"] = labels.get(row["property_id"], "ohne Objekt")
    return {
        "header": await report_header(
            session, ledger, report="vat_overview_by_property", start=start, end=end
        ),
        "rows": rows,
        "total_output_vat": sum((r["output_vat"] for r in rows), ZERO),
        "total_input_vat_before_deduction": sum(
            (r["input_vat_before_deduction"] for r in rows), ZERO
        ),
        "note": (
            "Entwurf, keine Umsatzsteuer-Voranmeldung. Das Objekt ist das der Buchungszeile "
            "(aus der Zeile, der Einheit oder dem Vertrag); Zeilen ohne Objekt stehen unter "
            "ohne Objekt."
        ),
    }
