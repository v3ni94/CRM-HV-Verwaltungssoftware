"""Ledger operations of M10 (Lueckenliste 30.09.2026, M10-01, M10-05, M10-06).

* Cost account allocation: shares of allocation keys per cost account, total exactly 100 %
  (6.4 ``ledger_account_allocation``, 7.2).
* Creditor accounts per service provider relation (7.2, 070000 to 079999).
* Dedicated drafts for cost transfer (``EntryKind.COST_TRANSFER``) and interest
  (``EntryKind.INTEREST``) (7.3). Both only create drafts; posting uses the regular posting
  path (B03 to B09). No tax rule for interest (withholding tax) is applied here: the gross
  amount is booked as entered, the tax treatment stays an open question (OPEN_QUESTIONS).
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import invoices
from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    JournalEntry,
    Ledger,
    LedgerAccount,
    LedgerAccountAllocation,
)
from mhvp.core.problems import ErrorCodes, ProblemError

if TYPE_CHECKING:
    from mhvp.properties.models import ServiceProviderRelation

HUNDRED = Decimal("100")


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


async def ledger_account(
    session: AsyncSession, ledger: Ledger, account_id: uuid.UUID
) -> LedgerAccount:
    account = await session.get(LedgerAccount, account_id)
    if account is None or account.ledger_id != ledger.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return account


# Allocation -----------------------------------------------------------------------------


async def allocations(
    session: AsyncSession, account: LedgerAccount
) -> list[tuple[LedgerAccountAllocation, str, str]]:
    from mhvp.properties.models import AllocationKey

    rows = await session.execute(
        select(LedgerAccountAllocation, AllocationKey.code, AllocationKey.name)
        .join(AllocationKey, AllocationKey.id == LedgerAccountAllocation.allocation_key_id)
        .where(LedgerAccountAllocation.ledger_account_id == account.id)
        .order_by(AllocationKey.sort_order, AllocationKey.code)
    )
    return [(r[0], r[1], r[2]) for r in rows.all()]


def check_allocation_total(shares: list[Decimal]) -> None:
    """The shares of one cost account add up to exactly 100 % (or the list is empty)."""
    if shares and sum(shares, Decimal("0")) != HUNDRED:
        raise _invalid(
            f"Die Anteile ergeben {sum(shares, Decimal('0')).normalize():f} %, erforderlich "
            "sind genau 100 %."
        )


async def replace_allocations(
    session: AsyncSession,
    ledger: Ledger,
    account: LedgerAccount,
    items: list[tuple[uuid.UUID, Decimal]],
) -> None:
    from mhvp.properties.models import AllocationKey

    if account.category is not AccountCategory.COST:
        raise _invalid("Nur Kostenkonten werden auf Umlageschlüssel verteilt.")
    keys = [key_id for key_id, _ in items]
    if len(set(keys)) != len(keys):
        raise _invalid("Jeder Umlageschlüssel darf nur einmal vorkommen.")
    check_allocation_total([share for _, share in items])
    if items:
        if ledger.property_id is None:
            raise _invalid("Der Buchungskreis ist keinem Objekt zugeordnet.")
        found = set(
            await session.scalars(
                select(AllocationKey.id).where(
                    AllocationKey.id.in_(keys), AllocationKey.property_id == ledger.property_id
                )
            )
        )
        if found != set(keys):
            raise _invalid("Umlageschlüssel gehört nicht zum Objekt des Buchungskreises.")
    await session.execute(
        delete(LedgerAccountAllocation).where(
            LedgerAccountAllocation.ledger_account_id == account.id
        )
    )
    for key_id, share in items:
        session.add(
            LedgerAccountAllocation(
                tenant_id=account.tenant_id,
                ledger_account_id=account.id,
                allocation_key_id=key_id,
                share_percent=share,
            )
        )
    await session.flush()


# Creditors ------------------------------------------------------------------------------


async def ensure_creditor_for_relation(
    session: AsyncSession, relation: "ServiceProviderRelation"
) -> int:
    """Create the creditor account of one provider relation in every ledger of its property
    and link the first one when the relation has none (7.2). Returns the new accounts."""
    ledgers = (
        await session.scalars(
            select(Ledger).where(Ledger.property_id == relation.property_id).order_by(Ledger.name)
        )
    ).all()
    created = 0
    for ledger in ledgers:
        before = await session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category == AccountCategory.CREDITOR,
                LedgerAccount.contact_id == relation.contact_id,
            )
        )
        account = await invoices.creditor_account(session, ledger, relation.contact_id)
        created += before is None
        if relation.creditor_account_id is None:
            relation.creditor_account_id = account.id
    await session.flush()
    return created


async def sync_creditor_accounts(session: AsyncSession, ledger: Ledger) -> tuple[int, int]:
    """Creditor accounts for all provider relations of the ledger's property (M10-05)."""
    from mhvp.properties.models import ServiceProviderRelation

    if ledger.property_id is None:
        return 0, 0
    relations = (
        await session.scalars(
            select(ServiceProviderRelation)
            .where(ServiceProviderRelation.property_id == ledger.property_id)
            .order_by(ServiceProviderRelation.created_at)
        )
    ).all()
    created = linked = 0
    for relation in relations:
        exists = await session.scalar(
            select(LedgerAccount.id).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category == AccountCategory.CREDITOR,
                LedgerAccount.contact_id == relation.contact_id,
            )
        )
        account = await invoices.creditor_account(session, ledger, relation.contact_id)
        created += exists is None
        if relation.creditor_account_id is None:
            relation.creditor_account_id = account.id
            linked += 1
    await session.flush()
    return created, linked


# Cost transfer and interest -------------------------------------------------------------


def _active(account: LedgerAccount, label: str) -> None:
    if not account.active:
        raise _invalid(f"{label} ist deaktiviert.")


async def cost_transfer_draft(
    session: AsyncSession,
    ledger: Ledger,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    booking_date: object,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: Decimal,
    text: str,
    unit_id: uuid.UUID | None = None,
    reference: str | None = None,
    document_id: uuid.UUID | None = None,
) -> JournalEntry:
    """Kostenkorrektur: moves an amount from one cost account to another (7.3)."""
    if from_account_id == to_account_id:
        raise _invalid("Quell- und Zielkonto müssen verschieden sein.")
    source = await ledger_account(session, ledger, from_account_id)
    target = await ledger_account(session, ledger, to_account_id)
    for account, label in ((source, "Das Quellkonto"), (target, "Das Zielkonto")):
        if account.category is not AccountCategory.COST:
            raise _invalid(f"{label} ist kein Kostenkonto.")
        _active(account, label)
    entry = JournalEntry(
        tenant_id=tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        source=EntrySource.MANUAL,
        kind=EntryKind.COST_TRANSFER,
        booking_date=booking_date,
        text=text,
        reference=reference,
        document_id=document_id,
    )
    lines = [
        svc.LineIn(target.id, amount, Decimal("0"), text=text, unit_id=unit_id),
        svc.LineIn(source.id, Decimal("0"), amount, text=text, unit_id=unit_id),
    ]
    await svc.write_draft(session, ledger, entry, lines, [])
    return entry


async def interest_draft(
    session: AsyncSession,
    ledger: Ledger,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    booking_date: object,
    value_date: object | None,
    bank_account_id: uuid.UUID,
    interest_account_id: uuid.UUID,
    amount: Decimal,
    direction: str,
    text: str,
    reference: str | None = None,
    document_id: uuid.UUID | None = None,
) -> JournalEntry:
    """Zinsbuchung between a bank (or reserve) account and an interest account (7.3).

    ``credit``: interest received, bank debit against a revenue account; ``debit``: interest
    charged, cost account debit against the bank. Gross amount as entered, no withholding
    tax logic (open question, no invented tax rule)."""
    bank = await ledger_account(session, ledger, bank_account_id)
    interest = await ledger_account(session, ledger, interest_account_id)
    if bank.category not in (AccountCategory.BANK, AccountCategory.RESERVE):
        raise _invalid("Das Geldkonto muss ein Bank- oder Rücklagenkonto sein.")
    wanted = AccountCategory.REVENUE if direction == "credit" else AccountCategory.COST
    if interest.category is not wanted:
        raise _invalid(
            "Habenzinsen werden auf ein Erlöskonto, Sollzinsen auf ein Kostenkonto gebucht."
        )
    _active(bank, "Das Geldkonto")
    _active(interest, "Das Zinskonto")
    entry = JournalEntry(
        tenant_id=tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        source=EntrySource.MANUAL,
        kind=EntryKind.INTEREST,
        booking_date=booking_date,
        value_date=value_date,
        text=text,
        reference=reference,
        document_id=document_id,
    )
    zero = Decimal("0")
    if direction == "credit":
        lines = [
            svc.LineIn(bank.id, amount, zero, text=text),
            svc.LineIn(interest.id, zero, amount, text=text),
        ]
    else:
        lines = [
            svc.LineIn(interest.id, amount, zero, text=text),
            svc.LineIn(bank.id, zero, amount, text=text),
        ]
    await svc.write_draft(session, ledger, entry, lines, [])
    return entry
