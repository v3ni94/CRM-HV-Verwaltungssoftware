"""Maintained open item remainders as of a cut-off date (6.9.13, E15, B07, S69-04).

A plain table instead of a materialized view: PostgreSQL materialized views know no RLS, so a
tenant table with the usual policies keeps the tenant separation (ADR 0002). Every refresh
recomputes from ``open_item_settlement`` via :func:`mhvp.accounting.services.open_items`,
which stays the source of truth; the table is a read copy for lists and reports.

* ``source='job'``: the nightly job ``mhvp.accounting.open_item_balance_refresh`` writes the
  current day and removes older job rows of the ledger.
* ``source='manual'``: a refresh for a chosen cut-off date via the API; kept until refreshed.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import Ledger, OpenItemBalance


async def refresh(
    session: AsyncSession, ledger: Ledger, as_of: date, *, source: str = "manual"
) -> int:
    """Rewrite the rows of ``ledger`` for ``as_of``; returns the number of open items."""
    await session.execute(
        delete(OpenItemBalance).where(
            OpenItemBalance.ledger_id == ledger.id, OpenItemBalance.as_of == as_of
        )
    )
    if source == "job":
        await session.execute(
            delete(OpenItemBalance).where(
                OpenItemBalance.ledger_id == ledger.id,
                OpenItemBalance.source == "job",
                OpenItemBalance.as_of < as_of,
            )
        )
    now = datetime.now(UTC)
    rows = await acc.open_items(session, ledger, as_of)
    for item in rows:
        session.add(
            OpenItemBalance(
                tenant_id=ledger.tenant_id,
                ledger_id=ledger.id,
                open_item_id=item["id"],
                account_id=item["account_id"],
                as_of=as_of,
                kind=item["kind"],
                due_date=item["due_date"],
                amount=Decimal(item["amount"]),
                remaining=Decimal(item["remaining"]),
                contract_id=item["contract_id"],
                source=source,
                refreshed_at=now,
            )
        )
    await session.flush()
    return len(rows)


async def rows_of(
    session: AsyncSession, ledger_id: uuid.UUID, as_of: date | None
) -> tuple[date | None, list[OpenItemBalance]]:
    """Rows of the given cut-off date, or of the latest one when ``as_of`` is ``None``."""
    if as_of is None:
        as_of = await session.scalar(
            select(OpenItemBalance.as_of)
            .where(OpenItemBalance.ledger_id == ledger_id)
            .order_by(OpenItemBalance.as_of.desc())
            .limit(1)
        )
        if as_of is None:
            return None, []
    items = (
        await session.scalars(
            select(OpenItemBalance)
            .where(OpenItemBalance.ledger_id == ledger_id, OpenItemBalance.as_of == as_of)
            .order_by(OpenItemBalance.due_date, OpenItemBalance.id)
        )
    ).all()
    return as_of, list(items)
