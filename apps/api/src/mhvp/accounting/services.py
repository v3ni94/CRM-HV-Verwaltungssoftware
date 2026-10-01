"""Ledger services (7.1 B01 to B09). All functions run inside the caller's tenant transaction;
a business transaction is complete or not at all (B02)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.defaults import (
    DEFAULT_CODE,
    DEFAULT_NAME,
    TEMPLATE_ACCOUNTS,
    fill_unset,
    merge_missing,
)
from mhvp.accounting.models import (
    AccountCategory,
    AccountType,
    ChartTemplate,
    EntryKind,
    EntryStatus,
    JournalEntry,
    JournalLine,
    JournalNumberCounter,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
    OpenItemSettlement,
    ReversalReason,
)
from mhvp.core.problems import ErrorCodes, ProblemError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# Kinds whose debit on a debtor (credit on a creditor) creates an open item.
OPEN_ITEM_KINDS = {
    EntryKind.RECEIVABLE,
    EntryKind.INVOICE,
    EntryKind.CUSTOM,
    EntryKind.OPENING_BALANCE,
    EntryKind.STATEMENT_RESULT,
    EntryKind.DUNNING_FEE,
    EntryKind.INTEREST,
}


@dataclass(frozen=True)
class LineIn:
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    text: str | None = None
    vat_percent: Decimal | None = None
    vat_amount: Decimal | None = None
    net_amount: Decimal | None = None
    unit_id: uuid.UUID | None = None
    cost_center: str | None = None
    # Object of the line (Q15-01): explicit here, otherwise derived in ``write_draft``.
    property_id: uuid.UUID | None = None


def fiscal_year(ledger: Ledger, day: date) -> int:
    """Fiscal years are labelled by their starting calendar year."""
    return day.year if day.month >= ledger.fiscal_year_start_month else day.year - 1


def _money(value: Decimal, label: str) -> Decimal:
    if value < 0 or value != value.quantize(CENT):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"{label}: Betrag mit höchstens zwei Nachkommastellen und nicht negativ.",
        )
    return value


# Templates and ledgers ----------------------------------------------------------------


async def default_template(session: AsyncSession, tenant_id: uuid.UUID) -> ChartTemplate:
    """Create the A.1 draft template or add template rows that are still missing.

    Idempotent: existing rows (including tenant edits) are never overwritten, only rows whose
    number is absent are appended (M10-01 proposal of 26.09.2026) and preset fields that are
    still unset ("none") are filled as a draft (M10-02 presets of 26.09.2026, ``fill_unset``).
    Ledgers already created from the template are not touched; their accounts are added per
    ledger (7.2).
    """
    row = await session.scalar(
        select(ChartTemplate).where(ChartTemplate.code == DEFAULT_CODE, ChartTemplate.version == 1)
    )
    if row is None:
        row = ChartTemplate(
            tenant_id=tenant_id,
            code=DEFAULT_CODE,
            name=DEFAULT_NAME,
            version=1,
            accounts=list(TEMPLATE_ACCOUNTS),
        )
        session.add(row)
        await session.flush()
        return row
    filled, changed = fill_unset(row.accounts, TEMPLATE_ACCOUNTS)
    merged = merge_missing(filled, TEMPLATE_ACCOUNTS)
    if changed or len(merged) != len(row.accounts):
        row.accounts = merged
        await session.flush()
    return row


async def sync_debtor_accounts(session: AsyncSession, ledger: Ledger) -> int:
    """Adopt the debtor numbers reserved with the contracts (M5) as ledger accounts."""
    from mhvp.contacts.models import Party
    from mhvp.contracts.models import DebtorAccountReservation
    from mhvp.properties.models import Unit

    rows = (
        await session.execute(
            select(DebtorAccountReservation, Party.name, Unit.number)
            .join(Party, Party.id == DebtorAccountReservation.party_id)
            .join(Unit, Unit.id == DebtorAccountReservation.unit_id)
            .where(DebtorAccountReservation.legal_entity_id == ledger.legal_entity_id)
        )
    ).all()
    existing = set(
        await session.scalars(
            select(LedgerAccount.number).where(LedgerAccount.ledger_id == ledger.id)
        )
    )
    created = 0
    for reservation, party_name, unit_number in rows:
        if reservation.number in existing:
            continue
        session.add(
            LedgerAccount(
                tenant_id=ledger.tenant_id,
                ledger_id=ledger.id,
                number=reservation.number,
                name=f"{unit_number} {party_name}"[:200],
                category=AccountCategory.DEBTOR,
                type=AccountType.ASSET,
                party_id=reservation.party_id,
                unit_id=reservation.unit_id,
                is_system=True,
            )
        )
        created += 1
    await session.flush()
    return created


async def create_ledger(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    legal_entity_id: uuid.UUID,
    template: ChartTemplate | None,
    fiscal_year_start_month: int,
    migration_cutoff: date | None,
) -> Ledger:
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, legal_entity_id)
    if entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Rechtsträger nicht gefunden.")
    if await session.scalar(select(Ledger.id).where(Ledger.legal_entity_id == legal_entity_id)):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diesen Rechtsträger besteht bereits ein Buchungskreis."
        )
    ledger = Ledger(
        tenant_id=tenant_id,
        created_by=user_id,
        legal_entity_id=entity.id,
        property_id=entity.property_id,
        name=entity.name,
        fiscal_year_start_month=fiscal_year_start_month,
        template_id=template.id if template else None,
        template_version=template.version if template else None,
        migration_cutoff=migration_cutoff,
    )
    session.add(ledger)
    await session.flush()
    for spec in template.accounts if template else []:
        if entity.kind.value not in spec.get("applies_to", []):
            continue
        session.add(
            LedgerAccount(
                tenant_id=tenant_id,
                ledger_id=ledger.id,
                number=spec["number"],
                name=spec["name"],
                category=AccountCategory(spec["category"]),
                type=AccountType(spec["type"]),
                statement_kind=spec.get("statement_kind", "none"),
                allocation_category=spec.get("allocation_category", "none"),
                vat_option=spec.get("vat_option", "none"),
                relevant_for_cash_report=bool(spec.get("relevant_for_cash_report")),
                review_status=spec.get("review_status") or "none",
                review_note=spec.get("review_note"),
                is_system=True,
            )
        )
    await session.flush()
    await _apply_template_splits(session, ledger, template)
    await sync_debtor_accounts(session, ledger)
    return ledger


async def _apply_template_splits(
    session: AsyncSession, ledger: Ledger, template: ChartTemplate | None
) -> int:
    """Adopt the template key distribution (U07-01) for cost accounts of a new ledger.

    Only keys that already exist in the property of the ledger are used; a split with a missing
    key is skipped as a whole (shares must stay at 100 %). Nothing is guessed or created.
    """
    from mhvp.accounting.models import LedgerAccountAllocation
    from mhvp.properties.models import AllocationKey

    if template is None or ledger.property_id is None:
        return 0
    key_rows = await session.execute(
        select(AllocationKey.code, AllocationKey.id).where(
            AllocationKey.property_id == ledger.property_id
        )
    )
    keys = dict(key_rows.tuples().all())
    splits = {
        str(r["number"]): r["allocation_split"]
        for r in template.accounts
        if r.get("allocation_split")
    }
    if not keys or not splits:
        return 0
    accounts = (
        await session.scalars(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.number.in_(splits),
                LedgerAccount.category == AccountCategory.COST,
            )
        )
    ).all()
    applied = 0
    for account in accounts:
        split = splits[account.number]
        if any(item["key_code"] not in keys for item in split):
            continue
        for item in split:
            session.add(
                LedgerAccountAllocation(
                    tenant_id=account.tenant_id,
                    ledger_account_id=account.id,
                    allocation_key_id=keys[item["key_code"]],
                    share_percent=Decimal(item["share_percent"]),
                )
            )
        applied += 1
    await session.flush()
    return applied


# Entries ------------------------------------------------------------------------------


async def _accounts(
    session: AsyncSession, ledger: Ledger, ids: set[uuid.UUID]
) -> dict[uuid.UUID, LedgerAccount]:
    rows = (await session.scalars(select(LedgerAccount).where(LedgerAccount.id.in_(ids)))).all()
    found = {a.id: a for a in rows}
    if len(found) != len(ids):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekanntes Konto.")
    if any(a.ledger_id != ledger.id for a in rows):
        raise ProblemError(
            ErrorCodes.ACC_WRONG_ENTITY,
            detail="Konten eines anderen Buchungskreises sind nicht zulässig.",
        )
    inactive = [a.number for a in rows if not a.active]
    if inactive:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Konto deaktiviert: {', '.join(sorted(inactive))}."
        )
    return found


def check_balanced(lines: list[LineIn]) -> None:
    if len(lines) < 2:
        raise ProblemError(
            ErrorCodes.ACC_UNBALANCED, detail="Ein Buchungssatz braucht mindestens zwei Zeilen."
        )
    for i, line in enumerate(lines, start=1):
        _money(line.debit, f"Zeile {i} Soll")
        _money(line.credit, f"Zeile {i} Haben")
        if (line.debit > 0) == (line.credit > 0):
            raise ProblemError(
                ErrorCodes.ACC_UNBALANCED, detail=f"Zeile {i}: genau Soll oder Haben größer null."
            )
    debit = sum((line.debit for line in lines), ZERO)
    credit = sum((line.credit for line in lines), ZERO)
    if debit != credit:
        raise ProblemError(
            ErrorCodes.ACC_UNBALANCED,
            detail=f"Soll {debit} und Haben {credit} stimmen nicht überein.",
        )


async def write_draft(
    session: AsyncSession,
    ledger: Ledger,
    entry: JournalEntry,
    lines: list[LineIn],
    settlement_plan: list[dict[str, Any]],
) -> JournalEntry:
    check_balanced(lines)
    await _accounts(session, ledger, {line.account_id for line in lines})
    entry.settlement_plan = [
        {
            "open_item_id": str(p["open_item_id"]),
            "amount": str(_money(Decimal(str(p["amount"])), "Ausgleich")),
        }
        for p in settlement_plan
    ]
    if entry not in session:
        session.add(entry)
    await session.flush()
    from mhvp.accounting import line_property

    properties = await line_property.resolve(session, entry, lines)
    await session.execute(delete(JournalLine).where(JournalLine.journal_entry_id == entry.id))
    for no, (line, property_id) in enumerate(zip(lines, properties, strict=True), start=1):
        session.add(
            JournalLine(
                tenant_id=entry.tenant_id,
                journal_entry_id=entry.id,
                line_no=no,
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
                text=line.text,
                vat_percent=line.vat_percent,
                vat_amount=line.vat_amount,
                net_amount=line.net_amount,
                unit_id=line.unit_id,
                cost_center=line.cost_center,
                property_id=property_id,
            )
        )
    await session.flush()
    return entry


async def entry_lines(session: AsyncSession, entry_id: uuid.UUID) -> list[JournalLine]:
    return list(
        (
            await session.scalars(
                select(JournalLine)
                .where(JournalLine.journal_entry_id == entry_id)
                .order_by(JournalLine.line_no)
            )
        ).all()
    )


async def entry_lines_of(
    session: AsyncSession, entry_ids: Sequence[uuid.UUID]
) -> list[JournalLine]:
    """Lines of several entries in one query, ordered by entry and line number."""
    if not entry_ids:
        return []
    return list(
        (
            await session.scalars(
                select(JournalLine)
                .where(JournalLine.journal_entry_id.in_(entry_ids))
                .order_by(JournalLine.journal_entry_id, JournalLine.line_no)
            )
        ).all()
    )


def ensure_open_period(ledger: Ledger, day: date) -> None:
    if ledger.locked_until is not None and day <= ledger.locked_until:
        raise ProblemError(
            ErrorCodes.ACC_PERIOD_LOCKED,
            detail=f"Der Zeitraum bis {ledger.locked_until:%d.%m.%Y} ist festgeschrieben.",
        )


async def next_number(session: AsyncSession, ledger: Ledger, year: int) -> int:
    """Gapless per ledger and fiscal year: the counter row is locked until commit (B04)."""
    await session.execute(
        insert(JournalNumberCounter)
        .values(tenant_id=ledger.tenant_id, ledger_id=ledger.id, fiscal_year=year, last_number=0)
        .on_conflict_do_nothing()
    )
    counter = await session.scalar(
        select(JournalNumberCounter)
        .where(
            JournalNumberCounter.ledger_id == ledger.id, JournalNumberCounter.fiscal_year == year
        )
        .with_for_update()
    )
    if counter is None:  # pragma: no cover - inserted above
        raise ProblemError(ErrorCodes.CONFLICT)
    counter.last_number += 1
    await session.flush()
    return counter.last_number


async def remaining(
    session: AsyncSession, item_id: uuid.UUID, as_of: date | None = None
) -> Decimal:
    item = await session.get(OpenItem, item_id)
    if item is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    query = select(func.coalesce(func.sum(OpenItemSettlement.amount), 0)).where(
        OpenItemSettlement.open_item_id == item_id
    )
    if as_of is not None:
        query = query.where(OpenItemSettlement.date <= as_of)
    settled = Decimal(await session.scalar(query) or 0)
    return item.amount - settled


async def _apply_open_items(
    session: AsyncSession,
    ledger: Ledger,
    entry: JournalEntry,
    lines: list[JournalLine],
    accounts: dict[uuid.UUID, LedgerAccount],
) -> None:
    by_account: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for line in lines:
        d, c = by_account.get(line.account_id, (ZERO, ZERO))
        by_account[line.account_id] = (d + line.debit, c + line.credit)
    reclass = entry.kind is EntryKind.CREDIT_RECLASS  # AE22: payable only, no receivable
    if entry.kind in OPEN_ITEM_KINDS or reclass:
        for account_id, (debit, credit) in by_account.items():
            account = accounts[account_id]
            amount, kind = ZERO, None
            if account.category is AccountCategory.DEBTOR and debit > credit and not reclass:
                amount, kind = debit - credit, OpenItemKind.RECEIVABLE
            elif account.category is AccountCategory.CREDITOR and credit > debit:
                amount, kind = credit - debit, OpenItemKind.PAYABLE
            if kind is not None:
                session.add(
                    OpenItem(
                        tenant_id=entry.tenant_id,
                        ledger_id=ledger.id,
                        account_id=account_id,
                        journal_entry_id=entry.id,
                        kind=kind,
                        booking_date=entry.booking_date,
                        due_date=entry.due_date or entry.booking_date,
                        amount=amount,
                        contract_id=entry.contract_id,
                    )
                )
    # Explicit settlement plan (payments, credit notes): per account never more than moved.
    used: dict[uuid.UUID, Decimal] = {}
    for plan in entry.settlement_plan:
        item = await session.scalar(
            select(OpenItem).where(OpenItem.id == uuid.UUID(plan["open_item_id"])).with_for_update()
        )
        if item is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Offener Posten nicht gefunden."
            )
        if item.ledger_id != ledger.id:
            raise ProblemError(
                ErrorCodes.ACC_WRONG_ENTITY, detail="Offener Posten eines anderen Rechtsträgers."
            )
        amount = Decimal(plan["amount"])
        debit, credit = by_account.get(item.account_id, (ZERO, ZERO))
        movable = (credit - debit) if item.kind is OpenItemKind.RECEIVABLE else (debit - credit)
        used[item.account_id] = used.get(item.account_id, ZERO) + amount
        if movable <= 0 or used[item.account_id] > movable:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Ausgleich höher als die Bewegung auf dem Personenkonto.",
            )
        if amount <= 0 or amount > await remaining(session, item.id):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Ausgleich höher als der offene Betrag."
            )
        session.add(
            OpenItemSettlement(
                tenant_id=entry.tenant_id,
                open_item_id=item.id,
                journal_entry_id=entry.id,
                amount=amount,
                date=entry.booking_date,
            )
        )


async def post(
    session: AsyncSession, ledger: Ledger, entry: JournalEntry, user_id: uuid.UUID | None
) -> JournalEntry:
    if entry.status is EntryStatus.POSTED:
        return entry  # repeated click: no second effect (B08)
    ensure_open_period(ledger, entry.booking_date)
    from mhvp.accounting import period_lock

    await period_lock.ensure_open_for_entry(session, ledger, entry.id, entry.booking_date)
    if entry.kind is EntryKind.OPENING_BALANCE and entry.approved_by is None:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Anfangsbestände brauchen die Prüfung durch eine zweite Person.",
        )
    lines = await entry_lines(session, entry.id)
    check_balanced([LineIn(line.account_id, line.debit, line.credit) for line in lines])
    accounts = await _accounts(session, ledger, {line.account_id for line in lines})
    year = fiscal_year(ledger, entry.booking_date)
    entry.fiscal_year, entry.number = year, await next_number(session, ledger, year)
    entry.status, entry.posted_at, entry.posted_by = EntryStatus.POSTED, datetime.now(UTC), user_id
    await session.flush()
    await _apply_open_items(session, ledger, entry, lines, accounts)
    await session.flush()
    return entry


async def reverse(
    session: AsyncSession,
    ledger: Ledger,
    entry: JournalEntry,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    booking_date: date,
    reason_code: ReversalReason = ReversalReason.OTHER,
) -> JournalEntry:
    """Reversal with swapped lines, reference, reason, reason code and author (B03); undoes
    open item effects. ``reason_code`` (``ReversalReason``) classifies the correction for the
    learning bookkeeper (ADR 0014); it never replaces the free text reason."""
    if entry.status is not EntryStatus.POSTED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nur gebuchte Sätze können storniert werden."
        )
    if entry.reversed_by_id is not None or entry.kind is EntryKind.REVERSAL:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Satz ist bereits storniert oder selbst ein Storno."
        )
    ensure_open_period(ledger, booking_date)
    from mhvp.accounting import period_lock

    await period_lock.ensure_open_for_entry(session, ledger, entry.id, booking_date)
    if booking_date < entry.booking_date:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Stornodatum liegt vor der Buchung.")
    items = (
        await session.scalars(
            select(OpenItem).where(OpenItem.journal_entry_id == entry.id).with_for_update()
        )
    ).all()
    for item in items:
        if await remaining(session, item.id) != item.amount:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    "Auf den offenen Posten sind Zahlungen verrechnet. "
                    "Bitte zuerst diese Zahlungen stornieren."
                ),
            )
    lines = await entry_lines(session, entry.id)
    reversal = JournalEntry(
        tenant_id=entry.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=booking_date,
        value_date=entry.value_date,
        accrual_date=entry.accrual_date or entry.booking_date,
        text=f"Storno Nr. {entry.fiscal_year}-{entry.number}: {entry.text}"[:500],
        kind=EntryKind.REVERSAL,
        reference=entry.reference,
        contract_id=entry.contract_id,
        reverses_id=entry.id,
        reversal_reason=reason,
        reversal_reason_code=ReversalReason(reason_code).value,
        source=entry.source,
    )
    swapped = [
        LineIn(
            ln.account_id,
            ln.credit,
            ln.debit,
            ln.text,
            ln.vat_percent,
            ln.vat_amount,
            ln.net_amount,
            ln.unit_id,
            ln.cost_center,
            ln.property_id,  # Q15-01: the reversal keeps the object of the original line
        )
        for ln in lines
    ]
    await write_draft(session, ledger, reversal, swapped, [])
    year = fiscal_year(ledger, booking_date)
    reversal.fiscal_year, reversal.number = year, await next_number(session, ledger, year)
    reversal.status, reversal.posted_at, reversal.posted_by = (
        EntryStatus.POSTED,
        datetime.now(UTC),
        user_id,
    )
    await session.flush()
    for item in items:  # the reversal settles the items created by the original
        session.add(
            OpenItemSettlement(
                tenant_id=entry.tenant_id,
                open_item_id=item.id,
                journal_entry_id=reversal.id,
                amount=item.amount,
                date=booking_date,
            )
        )
    settlements = (
        await session.scalars(
            select(OpenItemSettlement).where(OpenItemSettlement.journal_entry_id == entry.id)
        )
    ).all()
    for s in settlements:  # settlements made by the original are undone, history stays
        session.add(
            OpenItemSettlement(
                tenant_id=entry.tenant_id,
                open_item_id=s.open_item_id,
                journal_entry_id=reversal.id,
                amount=-s.amount,
                date=booking_date,
            )
        )
    entry.reversed_by_id = reversal.id
    await session.flush()
    return reversal


async def unreviewed_auto_accounts(session: AsyncSession, ledger: Ledger) -> set[uuid.UUID]:
    """Accounts touched by automatic postings of the bank runner whose review is still open
    (``journal_entry.auto_review_pending``, rule M12-05). Dunning, settlement proposal and
    direct debit runs leave these debtor accounts alone: an unreviewed automatic settlement
    is no basis for a reminder, an allocation or a collection."""
    rows = await session.scalars(
        select(JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalEntry.ledger_id == ledger.id,
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.auto_review_pending.is_(True),
        )
        .distinct()
    )
    return set(rows.all())


UNREVIEWED_AUTO_REASON = (
    "Automatikbuchung ohne abgeschlossene Nachkontrolle: zurückgestellt bis zur Nachkontrolle"
)


async def lock_period(session: AsyncSession, ledger: Ledger, until: date) -> int:
    """Festschreibung only moves forward; returns the number of drafts left in the period."""
    if ledger.locked_until is not None and until < ledger.locked_until:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Eine Festschreibung kann nicht zurückgenommen werden."
        )
    ledger.locked_until = until
    await session.flush()
    return int(
        await session.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.DRAFT,
                JournalEntry.booking_date <= until,
            )
        )
        or 0
    )


def default_reversal_date(ledger: Ledger, today: date) -> date:
    if ledger.locked_until is not None and today <= ledger.locked_until:
        return ledger.locked_until + timedelta(days=1)
    return today


# Reports ------------------------------------------------------------------------------


def _posted_lines(ledger_id: uuid.UUID) -> Any:
    return (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(JournalEntry.ledger_id == ledger_id, JournalEntry.status == EntryStatus.POSTED)
    )


async def account_sheet(
    session: AsyncSession, account: LedgerAccount, start: date, end: date
) -> dict[str, Any]:
    """Kontenblatt: opening balance + movements = closing balance (B09 for bank and cash)."""
    base = (
        select(
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(JournalLine.account_id == account.id, JournalEntry.status == EntryStatus.POSTED)
    )
    d0, c0 = (await session.execute(base.where(JournalEntry.booking_date < start))).one()
    opening = Decimal(d0) - Decimal(c0)
    rows = (
        await session.execute(
            _posted_lines(account.ledger_id)
            .where(
                JournalLine.account_id == account.id, JournalEntry.booking_date.between(start, end)
            )
            .order_by(
                JournalEntry.booking_date,
                JournalEntry.fiscal_year,
                JournalEntry.number,
                JournalLine.line_no,
            )
        )
    ).all()
    balance, movements = opening, []
    total_d, total_c = ZERO, ZERO
    for line, entry in rows:
        balance += line.debit - line.credit
        total_d += line.debit
        total_c += line.credit
        movements.append(
            {
                "entry_id": entry.id,
                "number": f"{entry.fiscal_year}-{entry.number}",
                "booking_date": entry.booking_date,
                "text": line.text or entry.text,
                "kind": entry.kind.value,
                "debit": line.debit,
                "credit": line.credit,
                "balance": balance,
            }
        )
    return {
        "account_id": account.id,
        "number": account.number,
        "name": account.name,
        "start": start,
        "end": end,
        "opening_balance": opening,
        "debit": total_d,
        "credit": total_c,
        "closing_balance": balance,
        "movements": movements,
    }


async def trial_balance(
    session: AsyncSession, ledger: Ledger, as_of: date, start: date | None
) -> dict[str, Any]:
    query = (
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
            JournalEntry.booking_date <= as_of,
        )
        .group_by(LedgerAccount.id)
        .order_by(LedgerAccount.number)
    )
    if start is not None:
        query = query.where(JournalEntry.booking_date >= start)
    rows = (await session.execute(query)).all()
    accounts = [
        {
            "account_id": r[0],
            "number": r[1],
            "name": r[2],
            "category": r[3].value,
            "debit": Decimal(r[4]),
            "credit": Decimal(r[5]),
            "balance": Decimal(r[4]) - Decimal(r[5]),
        }
        for r in rows
    ]
    debit = sum((a["debit"] for a in accounts), ZERO)
    credit = sum((a["credit"] for a in accounts), ZERO)
    return {
        "as_of": as_of,
        "start": start,
        "accounts": accounts,
        "debit": debit,
        "credit": credit,
        "balanced": debit == credit,
    }


async def open_items(
    session: AsyncSession, ledger: Ledger, as_of: date, account_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    settled = (
        select(OpenItemSettlement.open_item_id, func.sum(OpenItemSettlement.amount).label("s"))
        .where(OpenItemSettlement.date <= as_of)
        .group_by(OpenItemSettlement.open_item_id)
        .subquery()
    )
    query = (
        select(OpenItem, LedgerAccount.number, func.coalesce(settled.c.s, 0))
        .join(LedgerAccount, LedgerAccount.id == OpenItem.account_id)
        .outerjoin(settled, settled.c.open_item_id == OpenItem.id)
        .where(OpenItem.ledger_id == ledger.id, OpenItem.booking_date <= as_of)
        .order_by(LedgerAccount.number, OpenItem.due_date, OpenItem.id)
    )
    if account_id is not None:
        query = query.where(OpenItem.account_id == account_id)
    out = []
    for item, number, s in (await session.execute(query)).all():
        rest = item.amount - Decimal(s)
        if rest != 0:
            out.append(
                {
                    "id": item.id,
                    "account_id": item.account_id,
                    "account_number": number,
                    "kind": item.kind.value,
                    "journal_entry_id": item.journal_entry_id,
                    "booking_date": item.booking_date,
                    "due_date": item.due_date,
                    "amount": item.amount,
                    "remaining": rest,
                    "contract_id": item.contract_id,
                    "notice_received_on": item.notice_received_on,
                }
            )
    return out


async def checks(session: AsyncSession, ledger: Ledger) -> list[str]:
    """Consistency checks B02, B07, B09 on the stored data; expected to return no findings."""
    findings: list[str] = []
    params = {"ledger": ledger.id}
    unbalanced = await session.execute(
        text(
            """
            SELECT e.fiscal_year, e.number FROM journal_entry e JOIN journal_line l ON
            l.journal_entry_id = e.id WHERE e.ledger_id = :ledger AND e.status = 'posted'
            GROUP BY e.id HAVING sum(l.debit) <> sum(l.credit) OR count(*) < 2
            """
        ),
        params,
    )
    findings += [f"Satz {y}-{n} nicht ausgeglichen" for y, n in unbalanced.all()]
    bad_items = await session.execute(
        text(
            """
            SELECT i.id FROM open_item i LEFT JOIN open_item_settlement s ON s.open_item_id
            = i.id WHERE i.ledger_id = :ledger GROUP BY i.id HAVING coalesce(sum(s.amount),
            0) > i.amount OR coalesce(sum(s.amount), 0) < 0
            """
        ),
        params,
    )
    findings += [f"Offener Posten {i} über- oder negativ ausgeglichen" for (i,) in bad_items.all()]
    mismatch = await session.execute(
        text(
            """
            SELECT i.id FROM open_item i JOIN journal_line l ON l.journal_entry_id =
            i.journal_entry_id AND l.account_id = i.account_id WHERE i.ledger_id = :ledger
            GROUP BY i.id, i.amount, i.kind HAVING i.amount <> abs(sum(l.debit) -
            sum(l.credit))
            """
        ),
        params,
    )
    findings += [f"Offener Posten {i} passt nicht zur Buchungszeile" for (i,) in mismatch.all()]
    foreign = await session.execute(
        text(
            """
            SELECT e.id FROM journal_entry e JOIN journal_line l ON l.journal_entry_id =
            e.id JOIN ledger_account a ON a.id = l.account_id WHERE e.ledger_id = :ledger
            AND a.ledger_id <> e.ledger_id
            """
        ),
        params,
    )
    findings += [
        f"Satz {i} bucht auf Konten eines anderen Buchungskreises" for (i,) in foreign.all()
    ]
    total = await session.execute(
        text(
            """
            SELECT coalesce(sum(l.debit), 0), coalesce(sum(l.credit), 0) FROM journal_line l
            JOIN journal_entry e ON e.id = l.journal_entry_id WHERE e.ledger_id = :ledger
            AND e.status = 'posted'
            """
        ),
        params,
    )
    d, c = total.one()
    if d != c:
        findings.append(f"Summen Soll {d} und Haben {c} weichen ab")
    findings += await numbering_findings(session, ledger)
    findings += await subledger_findings(session, ledger)
    from mhvp.accounting import line_property

    findings += await line_property.findings(session, ledger)  # Q15-01 (AE21)
    return findings


async def numbering_findings(session: AsyncSession, ledger: Ledger) -> list[str]:
    """B04 sentence 3 (GA05-01): posted numbers per fiscal year run 1..n without gaps and the
    counter row equals the highest assigned number."""
    findings: list[str] = []
    params = {"ledger": ledger.id}
    gaps = await session.execute(
        text(
            """
            WITH y AS (SELECT fiscal_year, max(number) AS hi FROM journal_entry WHERE
            ledger_id = :ledger AND status = 'posted' GROUP BY fiscal_year)
            SELECT y.fiscal_year, g.n FROM y CROSS JOIN LATERAL generate_series(1, y.hi) AS
            g(n) WHERE NOT EXISTS (SELECT 1 FROM journal_entry e WHERE e.ledger_id = :ledger
            AND e.fiscal_year = y.fiscal_year AND e.number = g.n AND e.status = 'posted')
            ORDER BY 1, 2 LIMIT 1000
            """
        ),
        params,
    )
    findings += [f"Nummernlücke {y}-{n} im Buchungsregister" for y, n in gaps.all()]
    counter = await session.execute(
        text(
            """
            SELECT coalesce(c.fiscal_year, m.fiscal_year), coalesce(c.last_number, 0),
            coalesce(m.hi, 0) FROM (SELECT fiscal_year, last_number FROM
            journal_number_counter WHERE ledger_id = :ledger) c FULL JOIN (SELECT
            fiscal_year, max(number) AS hi FROM journal_entry WHERE ledger_id = :ledger AND
            status = 'posted' GROUP BY fiscal_year) m ON m.fiscal_year = c.fiscal_year
            WHERE coalesce(c.last_number, 0) <> coalesce(m.hi, 0) ORDER BY 1
            """
        ),
        params,
    )
    findings += [
        f"Zählerstand {last} weicht von höchster Nummer {hi} im Geschäftsjahr {y} ab"
        for y, last, hi in counter.all()
    ]
    return findings


async def subledger_findings(session: AsyncSession, ledger: Ledger) -> list[str]:
    """B09 sentence 4 (GA05-03), hard invariants: per debtor or creditor account the open
    items never exceed the postings on the account, settlements never exceed the opposite
    side, and settlements are aggregated per item before summing (no double counting)."""
    rows = await session.execute(
        text(
            """
            WITH s AS (SELECT open_item_id, sum(amount) AS settled FROM open_item_settlement
            GROUP BY open_item_id),
            oi AS (SELECT i.account_id, sum(i.amount) AS amt, sum(coalesce(s.settled, 0)) AS
            settled FROM open_item i LEFT JOIN s ON s.open_item_id = i.id WHERE i.ledger_id
            = :ledger GROUP BY i.account_id),
            gl AS (SELECT l.account_id, sum(l.debit) AS d, sum(l.credit) AS c FROM
            journal_line l JOIN journal_entry e ON e.id = l.journal_entry_id WHERE
            e.ledger_id = :ledger AND e.status = 'posted' GROUP BY l.account_id)
            SELECT a.number, a.category::text, oi.amt, oi.settled, coalesce(gl.d, 0),
            coalesce(gl.c, 0) FROM oi JOIN ledger_account a ON a.id = oi.account_id LEFT JOIN
            gl ON gl.account_id = oi.account_id WHERE (a.category = 'debtor' AND (oi.amt >
            coalesce(gl.d, 0) OR oi.settled > coalesce(gl.c, 0))) OR (a.category =
            'creditor' AND (oi.amt > coalesce(gl.c, 0) OR oi.settled > coalesce(gl.d, 0)))
            ORDER BY a.number
            """
        ),
        {"ledger": ledger.id},
    )
    return [
        f"Nebenbuch Konto {number} ({cat}) übersteigt Hauptbuch: Posten {amt}, "
        f"Ausgleich {settled}, Soll {d}, Haben {c}"
        for number, cat, amt, settled, d, c in rows.all()
    ]


async def subledger_exclude_switch(session: AsyncSession) -> bool:
    """AC01-02: tenant switch (default on) to hide written off items and items of reversed
    entries from the sub ledger difference. Read only, no row is created."""
    from mhvp.accounting.tax_models import AccountingTaxSettings

    value = await session.scalar(select(AccountingTaxSettings.subledger_exclude_written_off))
    return True if value is None else bool(value)


async def subledger_reconciliation(
    session: AsyncSession,
    ledger: Ledger,
    as_of: date | None = None,
    exclude_written_off: bool = True,
) -> list[dict[str, Any]]:
    """B09 sentence 4 (GA05-03): per debtor and creditor account the remaining open items
    (receivable positive, payable negative, settlements aggregated per item) against the
    general ledger balance (debit minus credit) as of a date. A difference is shown, it is
    not automatically an error: unapplied payments and postings without open item are
    legitimate and are listed for review.

    AC01-02: items written off and items of reversed entries are counted separately
    (``excluded_written_off``, ``excluded_reversed``). With ``exclude_written_off`` they stay
    out of ``open_items_remaining`` and ``difference``; otherwise they are included. Display
    only, nothing is posted."""
    rows = await session.execute(
        text(
            """
            WITH s AS (SELECT open_item_id, sum(amount) AS settled FROM open_item_settlement
            WHERE (CAST(:as_of AS date) IS NULL OR date <= CAST(:as_of AS date))
            GROUP BY open_item_id),
            it AS (SELECT i.account_id, i.written_off,
            EXISTS (SELECT 1 FROM journal_entry r WHERE r.reverses_id = i.journal_entry_id
            AND r.status = 'posted' AND (CAST(:as_of AS date) IS NULL OR r.booking_date <=
            CAST(:as_of AS date))) AS reversed,
            CASE WHEN i.kind = 'receivable' THEN 1 ELSE -1 END * (i.amount -
            coalesce(s.settled, 0)) AS rem FROM open_item i LEFT JOIN s ON s.open_item_id =
            i.id WHERE i.ledger_id = :ledger AND (CAST(:as_of AS date) IS NULL OR
            i.booking_date <= CAST(:as_of AS date))),
            oi AS (SELECT account_id,
            sum(CASE WHEN NOT reversed AND NOT written_off THEN rem ELSE 0 END) AS counted,
            sum(CASE WHEN reversed THEN rem ELSE 0 END) AS rev,
            sum(CASE WHEN written_off AND NOT reversed THEN rem ELSE 0 END) AS wo,
            count(*) FILTER (WHERE reversed AND rem <> 0) AS n_rev,
            count(*) FILTER (WHERE written_off AND NOT reversed AND rem <> 0) AS n_wo
            FROM it GROUP BY account_id),
            gl AS (SELECT l.account_id, sum(l.debit - l.credit) AS bal FROM journal_line l
            JOIN journal_entry e ON e.id = l.journal_entry_id WHERE e.ledger_id = :ledger AND
            e.status = 'posted' AND (CAST(:as_of AS date) IS NULL OR e.booking_date <=
            CAST(:as_of AS date)) GROUP BY l.account_id)
            SELECT a.id, a.number, a.name, a.category::text, coalesce(gl.bal, 0),
            coalesce(oi.counted, 0), coalesce(oi.wo, 0), coalesce(oi.rev, 0),
            coalesce(oi.n_wo, 0), coalesce(oi.n_rev, 0) FROM ledger_account a LEFT JOIN gl
            ON gl.account_id = a.id LEFT JOIN oi ON oi.account_id = a.id WHERE a.ledger_id =
            :ledger AND a.category IN ('debtor', 'creditor') AND (gl.bal IS NOT NULL OR
            oi.account_id IS NOT NULL) ORDER BY a.number
            """
        ),
        {"ledger": ledger.id, "as_of": as_of},
    )
    out: list[dict[str, Any]] = []
    for account_id, number, name, cat, bal, counted, wo, rev, n_wo, n_rev in rows.all():
        bal, counted, wo, rev = Decimal(bal), Decimal(counted), Decimal(wo), Decimal(rev)
        remaining = counted if exclude_written_off else counted + wo + rev
        out.append(
            {
                "account_id": str(account_id),
                "number": number,
                "name": name,
                "category": cat,
                "ledger_balance": str(bal),
                "open_items_remaining": str(remaining),
                "difference": str(bal - remaining),
                "excluded_written_off": str(wo),
                "excluded_written_off_count": int(n_wo),
                "excluded_reversed": str(rev),
                "excluded_reversed_count": int(n_rev),
                "excluded_applied": exclude_written_off,
            }
        )
    return out
