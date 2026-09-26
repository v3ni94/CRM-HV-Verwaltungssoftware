"""Bank account selection (Bankkontenauswahl): list bank accounts (finAPI linked and manual)
per property and per legal entity with balance and latest transactions, assign accounts to
properties, mark default accounts per property (Hausgeld/Miete) and per legal entity.

Read only plus organisation: nothing here posts, pays or moves money (G2 stays closed).
Legal entity separation (CLAUDE.md section 8, B01): an account belongs to exactly one legal
entity; it can only be made selectable for a property that legal entity acts for, and it is
never re-assigned to another legal entity.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import (
    AccountPurpose,
    BankAccountAssignment,
    BankStatement,
    BankTransaction,
    FinApiAccountLink,
)
from mhvp.contacts.validation import mask_iban
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import LegalEntity, Property, PropertyBankAccount

RECENT_TRANSACTIONS = 5
MAX_ACCOUNTS = 200


@dataclass(frozen=True)
class RecentTransaction:
    id: uuid.UUID
    booking_date: date
    amount: Decimal
    counterpart_name: str | None
    purpose: str | None


@dataclass(frozen=True)
class AssignmentInfo:
    property_id: uuid.UUID
    property_number: str | None
    property_name: str | None
    purpose: AccountPurpose
    is_default: bool


@dataclass
class AccountListItem:
    id: uuid.UUID
    property_id: uuid.UUID
    property_number: str | None
    property_name: str | None
    legal_entity_id: uuid.UUID
    legal_entity_name: str | None
    legal_entity_kind: str | None
    kind: str
    iban_masked: str
    bic: str | None
    bank_name: str | None
    holder: str
    valid_from: date
    valid_to: date | None
    source: str  # "finapi" | "manual"
    balance: Decimal | None = None
    balance_as_of: datetime | None = None
    balance_source: str | None = None  # "finapi" | "statement"
    default_for_legal_entity: bool = False
    assignments: list[AssignmentInfo] = field(default_factory=list)
    recent_transactions: list[RecentTransaction] = field(default_factory=list)


def _base_query(
    *, property_id: uuid.UUID | None, legal_entity_id: uuid.UUID | None, q: str | None
) -> Select[tuple[PropertyBankAccount]]:
    query = select(PropertyBankAccount)
    if property_id is not None:
        assigned = select(BankAccountAssignment.property_bank_account_id).where(
            BankAccountAssignment.property_id == property_id
        )
        query = query.where(
            or_(
                PropertyBankAccount.property_id == property_id,
                PropertyBankAccount.id.in_(assigned),
            )
        )
    if legal_entity_id is not None:
        query = query.where(PropertyBankAccount.legal_entity_id == legal_entity_id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                PropertyBankAccount.holder.ilike(pattern),
                PropertyBankAccount.bank_name.ilike(pattern),
                PropertyBankAccount.iban_suffix.ilike(pattern),
            )
        )
    return query.order_by(PropertyBankAccount.holder, PropertyBankAccount.iban_suffix)


async def list_accounts(
    session: AsyncSession,
    *,
    property_id: uuid.UUID | None = None,
    legal_entity_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = MAX_ACCOUNTS,
    with_money: bool = True,
) -> list[AccountListItem]:
    """Accounts visible in the tenant, optionally filtered by property (home property or
    assignment) and by owning legal entity. ``with_money=False`` leaves balance and recent
    transactions empty (for callers without accounting rights)."""
    accounts = (
        await session.scalars(
            _base_query(property_id=property_id, legal_entity_id=legal_entity_id, q=q).limit(limit)
        )
    ).all()
    if not accounts:
        return []
    ids = [a.id for a in accounts]

    props = {
        p.id: p
        for p in (
            await session.scalars(
                select(Property).where(Property.id.in_({a.property_id for a in accounts}))
            )
        ).all()
    }
    entities = {
        e.id: e
        for e in (
            await session.scalars(
                select(LegalEntity).where(LegalEntity.id.in_({a.legal_entity_id for a in accounts}))
            )
        ).all()
    }
    assignments = (
        await session.scalars(
            select(BankAccountAssignment).where(
                BankAccountAssignment.property_bank_account_id.in_(ids)
            )
        )
    ).all()
    assigned_property_ids = {a.property_id for a in assignments if a.property_id is not None}
    if assigned_property_ids - set(props):
        for p in (
            await session.scalars(
                select(Property).where(Property.id.in_(assigned_property_ids - set(props)))
            )
        ).all():
            props[p.id] = p

    links = (
        await session.scalars(
            select(FinApiAccountLink)
            .where(FinApiAccountLink.property_bank_account_id.in_(ids))
            .order_by(FinApiAccountLink.balance_as_of.desc().nulls_last())
        )
    ).all()
    link_by_account: dict[uuid.UUID, FinApiAccountLink] = {}
    for linked in links:
        if linked.property_bank_account_id is not None:
            link_by_account.setdefault(linked.property_bank_account_id, linked)

    statements: dict[uuid.UUID, BankStatement] = {}
    recent: dict[uuid.UUID, list[RecentTransaction]] = {}
    if with_money:
        stmt_rows = (
            await session.scalars(
                select(BankStatement)
                .where(
                    BankStatement.property_bank_account_id.in_(ids),
                    BankStatement.closing_balance.is_not(None),
                )
                .order_by(
                    BankStatement.closing_date.desc().nulls_last(),
                    BankStatement.to_date.desc().nulls_last(),
                    BankStatement.created_at.desc(),
                )
            )
        ).all()
        for statement in stmt_rows:
            statements.setdefault(statement.property_bank_account_id, statement)

        rank = (
            func.row_number()
            .over(
                partition_by=BankTransaction.property_bank_account_id,
                order_by=(
                    BankTransaction.booking_date.desc(),
                    BankTransaction.created_at.desc(),
                ),
            )
            .label("rn")
        )
        ranked = (
            select(BankTransaction, rank)
            .where(BankTransaction.property_bank_account_id.in_(ids))
            .subquery()
        )
        tx_query = (
            select(ranked)
            .where(ranked.c.rn <= RECENT_TRANSACTIONS)
            .order_by(ranked.c.property_bank_account_id, ranked.c.rn)
        )
        for row in (await session.execute(tx_query)).all():
            recent.setdefault(row.property_bank_account_id, []).append(
                RecentTransaction(
                    id=row.id,
                    booking_date=row.booking_date,
                    amount=row.amount,
                    counterpart_name=row.counterpart_name,
                    purpose=row.purpose,
                )
            )

    items: list[AccountListItem] = []
    for a in accounts:
        home = props.get(a.property_id)
        entity = entities.get(a.legal_entity_id)
        link: FinApiAccountLink | None = link_by_account.get(a.id)
        item = AccountListItem(
            id=a.id,
            property_id=a.property_id,
            property_number=home.number if home else None,
            property_name=home.name if home else None,
            legal_entity_id=a.legal_entity_id,
            legal_entity_name=entity.name if entity else None,
            legal_entity_kind=entity.kind.value if entity else None,
            kind=a.kind.value,
            iban_masked=mask_iban(a.iban),
            bic=a.bic,
            bank_name=a.bank_name,
            holder=a.holder,
            valid_from=a.valid_from,
            valid_to=a.valid_to,
            source="finapi" if link is not None else "manual",
        )
        if with_money:
            if link is not None and link.balance_booked is not None:
                item.balance = link.balance_booked
                item.balance_as_of = link.balance_as_of or link.balance_fetched_at
                item.balance_source = "finapi"
            elif (stmt_row := statements.get(a.id)) is not None:
                item.balance = stmt_row.closing_balance
                closing = stmt_row.closing_date or stmt_row.to_date
                item.balance_as_of = (
                    datetime.combine(closing, time(), tzinfo=UTC) if closing else None
                )
                item.balance_source = "statement"
            item.recent_transactions = recent.get(a.id, [])
        for asg in assignments:
            if asg.property_bank_account_id != a.id:
                continue
            if asg.legal_entity_id is not None:
                item.default_for_legal_entity = item.default_for_legal_entity or asg.is_default
                continue
            if asg.property_id is None:  # pragma: no cover - check constraint
                continue
            target = props.get(asg.property_id)
            item.assignments.append(
                AssignmentInfo(
                    property_id=asg.property_id,
                    property_number=target.number if target else None,
                    property_name=target.name if target else None,
                    purpose=asg.purpose,
                    is_default=asg.is_default,
                )
            )
        items.append(item)
    return items


async def _account(session: AsyncSession, account_id: uuid.UUID) -> PropertyBankAccount:
    account = await session.get(PropertyBankAccount, account_id)
    if account is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return account


async def _check_property_scope(
    session: AsyncSession, account: PropertyBankAccount, property_id: uuid.UUID
) -> Property:
    """Legal entity separation: the account's owner (or the same party through its legal
    entity for the target property) must act for the target property."""
    prop = await session.get(Property, property_id)
    if prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    entity = await session.get(LegalEntity, account.legal_entity_id)
    if entity is None:  # pragma: no cover - FK guarantees the row
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if entity.property_id is not None and entity.property_id != property_id:
        # The same party (owner) may act for the target property through its own legal
        # entity there (rental owner entities exist per party and property).
        same_party = (
            entity.party_id is not None
            and await session.scalar(
                select(LegalEntity.id).where(
                    LegalEntity.property_id == property_id,
                    LegalEntity.party_id == entity.party_id,
                )
            )
            is not None
        )
        if same_party:
            return prop
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Das Konto gehört einem Rechtsträger eines anderen Objekts und kann diesem "
                "Objekt nicht zugeordnet werden (Rechtsträgertrennung)."
            ),
        )
    return prop


async def assign_to_property(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    account_id: uuid.UUID,
    property_id: uuid.UUID,
    purpose: AccountPurpose,
    is_default: bool,
) -> BankAccountAssignment:
    """Create or update the property assignment; a new default replaces the previous default
    of the same property and purpose (unique per property and purpose)."""
    account = await _account(session, account_id)
    await _check_property_scope(session, account, property_id)
    if purpose is AccountPurpose.HAUSGELD and account.kind.value not in ("hoa", "hoa_fee"):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Als Hausgeldkonto kommt nur ein WEG-Konto (hoa, hoa_fee) in Frage.",
        )
    if purpose is AccountPurpose.MIETE and account.kind.value != "rent":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Als Mietkonto kommt nur ein Mietkonto (rent) in Frage."
        )
    row = await session.scalar(
        select(BankAccountAssignment).where(
            BankAccountAssignment.property_bank_account_id == account.id,
            BankAccountAssignment.property_id == property_id,
        )
    )
    if is_default:
        others = (
            await session.scalars(
                select(BankAccountAssignment).where(
                    BankAccountAssignment.property_id == property_id,
                    BankAccountAssignment.purpose == purpose,
                    BankAccountAssignment.is_default.is_(True),
                    BankAccountAssignment.property_bank_account_id != account.id,
                )
            )
        ).all()
        for other in others:
            other.is_default = False
            other.updated_by = user_id
        await session.flush()
    if row is None:
        row = BankAccountAssignment(
            tenant_id=tenant_id,
            created_by=user_id,
            property_bank_account_id=account.id,
            property_id=property_id,
            purpose=purpose,
            is_default=is_default,
        )
        session.add(row)
    else:
        row.purpose = purpose
        row.is_default = is_default
        row.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.assigned",
        entity_type="property_bank_account",
        entity_id=account.id,
        actor_user_id=user_id,
        payload={
            "property_id": str(property_id),
            "purpose": purpose.value,
            "is_default": is_default,
        },
    )
    return row


async def unassign_from_property(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    account_id: uuid.UUID,
    property_id: uuid.UUID,
) -> None:
    account = await _account(session, account_id)
    if account.property_id == property_id:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Das Stammobjekt eines Kontos kann nicht gelöst werden; nur zusätzliche "
                "Zuordnungen sind lösbar."
            ),
        )
    result: Any = await session.execute(
        delete(BankAccountAssignment).where(
            BankAccountAssignment.property_bank_account_id == account.id,
            BankAccountAssignment.property_id == property_id,
        )
    )
    if result.rowcount == 0:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.unassigned",
        entity_type="property_bank_account",
        entity_id=account.id,
        actor_user_id=user_id,
        payload={"property_id": str(property_id)},
    )


async def set_legal_entity_default(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    account_id: uuid.UUID,
    is_default: bool,
) -> bool:
    """Mark or unmark the account as default of its own legal entity (never another one)."""
    account = await _account(session, account_id)
    entity_id = account.legal_entity_id
    row = await session.scalar(
        select(BankAccountAssignment).where(
            BankAccountAssignment.property_bank_account_id == account.id,
            BankAccountAssignment.legal_entity_id == entity_id,
        )
    )
    if is_default:
        others = (
            await session.scalars(
                select(BankAccountAssignment).where(
                    BankAccountAssignment.legal_entity_id == entity_id,
                    BankAccountAssignment.is_default.is_(True),
                    BankAccountAssignment.property_bank_account_id != account.id,
                )
            )
        ).all()
        for other in others:
            other.is_default = False
            other.updated_by = user_id
        await session.flush()
        if row is None:
            session.add(
                BankAccountAssignment(
                    tenant_id=tenant_id,
                    created_by=user_id,
                    property_bank_account_id=account.id,
                    legal_entity_id=entity_id,
                    purpose=AccountPurpose.GENERAL,
                    is_default=True,
                )
            )
        else:
            row.is_default = True
            row.updated_by = user_id
    elif row is not None:
        await session.delete(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.legal_entity_default",
        entity_type="property_bank_account",
        entity_id=account.id,
        actor_user_id=user_id,
        payload={"legal_entity_id": str(entity_id), "is_default": is_default},
    )
    return is_default
