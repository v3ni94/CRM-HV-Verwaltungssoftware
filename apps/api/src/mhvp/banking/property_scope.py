"""Property assignment of the membership in banking (M2-02/S16-02, Q13-01).

A bank account is visible to a restricted member when its home property or one of its
property assignments (``BankAccountAssignment``) lies inside ``Membership.property_ids``.
Transactions, payment configuration and reconciliation follow the account. Outside the
assignment single objects answer 404 and lists are filtered. Produktschutz, not a legal duty;
the axis sits next to tenant RLS and the legal entity scope (A37), never replaces them.
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import (
    BankAccountAssignment,
    BankTransaction,
    PaymentBatch,
    PaymentOrder,
)
from mhvp.core.auth.principal import get_principal, tenant_tx
from mhvp.core.auth.scope import allowed_property_ids, session_allowed_property_ids
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import PropertyBankAccount

# Path parameters naming a bank transaction, payment order, payment batch or a property bank
# account, mapped to the column holding the property bank account.
ACCOUNT_COLUMNS: dict[str, Any] = {
    "tx_id": BankTransaction.property_bank_account_id,
    "transaction_id": BankTransaction.property_bank_account_id,
    "order_id": PaymentOrder.property_bank_account_id,
    "batch_id": PaymentBatch.property_bank_account_id,
    "bank_account_id": PropertyBankAccount.id,
    "account_id": PropertyBankAccount.id,
}


def allowed_account_ids_query(allowed: frozenset[uuid.UUID]) -> Any:
    """Subquery of the property bank account ids visible for ``allowed`` properties."""
    assigned = select(BankAccountAssignment.property_bank_account_id).where(
        BankAccountAssignment.property_id.in_(allowed)
    )
    return select(PropertyBankAccount.id).where(
        or_(PropertyBankAccount.property_id.in_(allowed), PropertyBankAccount.id.in_(assigned))
    )


def session_account_filter(session: AsyncSession) -> Any | None:
    """``None`` when unrestricted, else the subquery of visible account ids."""
    allowed = session_allowed_property_ids(session)
    return None if allowed is None else allowed_account_ids_query(allowed)


async def account_visible(session: AsyncSession, account_id: uuid.UUID | None) -> bool:
    allowed = session_allowed_property_ids(session)
    if allowed is None:
        return True
    if account_id is None:
        return False
    hit = await session.scalar(
        select(PropertyBankAccount.id).where(
            PropertyBankAccount.id == account_id,
            PropertyBankAccount.id.in_(allowed_account_ids_query(allowed)),
        )
    )
    return hit is not None


async def ensure_account_visible(session: AsyncSession, account_id: uuid.UUID | None) -> None:
    if not await account_visible(session, account_id):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def _uuid(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


async def banking_path_guard(request: Request) -> None:
    """Router dependency: a transaction, payment order, batch or bank account in the path
    outside the membership's property assignment answers 404 before the endpoint runs.
    Unknown ids pass through so the endpoint keeps its own 404 or 422."""
    names = [n for n in ACCOUNT_COLUMNS if n in request.path_params]
    if not names:
        return
    principal = await get_principal(request)
    if allowed_property_ids(principal) is None or principal.tenant_id is None:
        return
    async with tenant_tx(request, principal) as session:
        for name in names:
            value = _uuid(request.path_params[name])
            if value is None:
                continue
            column = ACCOUNT_COLUMNS[name]
            account_id = await session.scalar(select(column).where(column.class_.id == value))
            if account_id is None:
                continue
            await ensure_account_visible(session, account_id)


async def visible_account_ids(
    session: AsyncSession, account_ids: list[uuid.UUID]
) -> frozenset[uuid.UUID] | None:
    """Subset of ``account_ids`` visible to the session's member, ``None`` when unrestricted."""
    allowed = session_allowed_property_ids(session)
    if allowed is None:
        return None
    if not account_ids:
        return frozenset()
    rows = await session.scalars(
        select(PropertyBankAccount.id).where(
            PropertyBankAccount.id.in_(account_ids),
            PropertyBankAccount.id.in_(allowed_account_ids_query(allowed)),
        )
    )
    return frozenset(rows.all())


# R08-01 (Welle 5): bank rules, rule proposals, sync logs and the clarification list.


def rule_property_filter(allowed: frozenset[uuid.UUID], rule_cls: Any) -> Any:
    """Where clause: a rule (or rule proposal) is visible when its own property, or else the
    property of its legal entity, lies in ``allowed``. Rules without either stay hidden."""
    from mhvp.properties.models import LegalEntity

    entity_property = (
        select(LegalEntity.property_id)
        .where(LegalEntity.id == rule_cls.legal_entity_id)
        .scalar_subquery()
    )
    own = getattr(rule_cls, "property_id", None)
    if own is None:
        return entity_property.in_(allowed)
    return or_(own.in_(allowed), (own.is_(None)) & entity_property.in_(allowed))


async def ensure_rule_visible(session: AsyncSession, rule: Any) -> None:
    """404 when ``rule`` (BankRule or BankRuleProposal) lies outside the assignment."""
    allowed = session_allowed_property_ids(session)
    if allowed is None:
        return
    cls = type(rule)
    hit = await session.scalar(
        select(cls.id).where(cls.id == rule.id, rule_property_filter(allowed, cls))
    )
    if hit is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def transaction_account_filter(allowed: frozenset[uuid.UUID], transaction_id_column: Any) -> Any:
    """Where clause on a column naming a bank transaction: visible through the account."""
    return transaction_id_column.in_(
        select(BankTransaction.id).where(
            BankTransaction.property_bank_account_id.in_(allowed_account_ids_query(allowed))
        )
    )
