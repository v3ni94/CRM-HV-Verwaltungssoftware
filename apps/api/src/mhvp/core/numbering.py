"""Tenant wide business number sequences (section 4.1: contract, document, ticket numbers).

A row per scope is locked (SELECT ... FOR UPDATE) inside the business transaction, so numbers
are unique and, while the transaction commits, gapless. Aborted transactions do not consume a
number because the increment rolls back with them (B04 is decided for ledgers in M10).
"""

import uuid

from sqlalchemy import BigInteger, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin


class NumberSequence(IdMixin, TenantMixin, Base):
    __tablename__ = "number_sequence"
    __table_args__ = (UniqueConstraint("tenant_id", "scope"),)

    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False)


async def next_number(
    session: AsyncSession, tenant_id: uuid.UUID, scope: str, *, start: int = 1
) -> int:
    row = await session.scalar(
        select(NumberSequence).where(NumberSequence.scope == scope).with_for_update()
    )
    if row is None:
        row = NumberSequence(tenant_id=tenant_id, scope=scope, next_value=start)
        session.add(row)
        await session.flush()
        row = await session.scalar(
            select(NumberSequence).where(NumberSequence.scope == scope).with_for_update()
        )
        assert row is not None  # noqa: S101 - inserted above in this transaction
    value = row.next_value
    row.next_value = value + 1
    await session.flush()
    return value
