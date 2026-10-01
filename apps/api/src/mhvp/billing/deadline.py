"""Statement deadline per contract (M17-04, § 556 Abs. 3 BGB): orientation only, to be verified.

The end of the deadline is shown per contract, the access date is proposed from the dispatch
(never stored automatically, evidence stays mandatory) and a warning job reports statements
whose deadline approaches. What happens after expiry is a tenant switch (``policy``).
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc
from mhvp.billing.models import (
    Statement,
    StatementDeadlineSetting,
    StatementResult,
    StatementSnapshot,
)

POLICIES = ("block_claims", "notice")
NOTICE_TEXT = (
    "Fristende nur zur Orientierung, im Einzelfall zu verifizieren. "
    "Maßgeblich ist der Zugang beim Mieter."
)


async def setting(session: AsyncSession, tenant_id: uuid.UUID) -> StatementDeadlineSetting:
    row = await session.scalar(select(StatementDeadlineSetting))
    if row is None:
        row = StatementDeadlineSetting(
            tenant_id=tenant_id,
            policy="block_claims",
            watch_enabled=False,
            warn_days_first=60,
            warn_days_second=30,
        )
        session.add(row)
        await session.flush()
    return row


async def policy(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    return (await setting(session, tenant_id)).policy


def state_of(deadline: date, delivered_at: date | None, today: date, warn_days: int) -> str:
    if delivered_at is not None:
        return "delivered_in_time" if delivered_at <= deadline else "delivered_late"
    if today > deadline:
        return "expired"
    return "warning" if (deadline - today).days <= warn_days else "open"


async def access_suggestion(
    session: AsyncSession, document_id: uuid.UUID | None, contract_id: uuid.UUID
) -> dict[str, Any] | None:
    """Read only: newest dispatch of the statement document to a member of the tenancy party."""
    if document_id is None:
        return None
    from mhvp.communication.models import Dispatch
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.workspace.services import local_date

    contract = await session.get(Contract, contract_id)
    if contract is None:
        return None
    contact_ids = list(
        await session.scalars(
            select(PartyMember.contact_id).where(PartyMember.party_id == contract.party_id)
        )
    )
    if not contact_ids:
        return None
    rows = (
        await session.scalars(
            select(Dispatch)
            .where(Dispatch.document_id == document_id, Dispatch.contact_id.in_(contact_ids))
            .order_by(Dispatch.created_at.desc())
        )
    ).all()
    for d in rows:
        moment = d.delivered_at or d.sent_at
        if moment is not None:
            return {
                "dispatch_id": d.id,
                "date": local_date(moment),
                "channel": d.channel,
                "confirmed_delivery": d.delivered_at is not None,
            }
    return None


async def overview(
    session: AsyncSession, statement: Statement, snapshot: StatementSnapshot | None, today: date
) -> dict[str, Any]:
    cfg = await setting(session, statement.tenant_id)
    deadline = calc.deadline(statement.period_to)
    stored = {
        str(r.contract_id): r
        for r in await session.scalars(
            select(StatementResult).where(StatementResult.statement_id == statement.id)
        )
    }
    rows = []
    for r in snapshot.results["results"] if snapshot else []:
        res = stored.get(str(r["contract_id"]))
        delivered = res.delivered_at if res else None
        suggestion = (
            await access_suggestion(session, res.document_id, uuid.UUID(str(r["contract_id"])))
            if res and delivered is None
            else None
        )
        rows.append(
            {
                "contract_id": r["contract_id"],
                "unit_number": r["unit_number"],
                "balance": r["balance"],
                "deadline_orientation": deadline,
                "delivered_at": delivered,
                "delivery_method": res.delivery_method if res else None,
                "access_suggestion": suggestion,
                "days_left": (deadline - today).days,
                "state": state_of(deadline, delivered, today, cfg.warn_days_first),
            }
        )
    return {
        "statement_id": statement.id,
        "period_to": statement.period_to,
        "deadline_orientation": deadline,
        "policy": cfg.policy,
        "exception_effective": statement.deadline_exception_effective,
        "notice": NOTICE_TEXT,
        "contracts": rows,
    }
