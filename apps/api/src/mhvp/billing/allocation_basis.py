"""Report of missing allocation agreements before a rental statement is output (M17-01, AE17).

For every cost position with a catalogue type and every tenancy of the period the report asks:
is there a recorded agreement (clause reference, validity) that covers the span of the tenancy?
Nothing is derived from account names; a position without catalogue type is reported as
"Zuordnung fehlt". The report checks presence and validity period only, not whether the clause
is legally effective (human review, open question M17-01).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import LedgerAccount
from mhvp.billing import betrkv, services
from mhvp.billing.models import Statement, StatementCostItem
from mhvp.contracts.models import AllocationAgreement
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings

MISSING = "missing"
EXPIRED = "expired"
NO_TYPE = "no_type"
EXCLUDED = "excluded"
AGREED = "agreed"


async def blocking_enabled(session: AsyncSession) -> bool:
    value = await session.scalar(select(TenantSettings.allocation_basis_block))
    return True if value is None else bool(value)


def _covers(agreement: AllocationAgreement, start: Any, end: Any) -> bool:
    return agreement.valid_from <= start and (
        agreement.valid_to is None or agreement.valid_to >= end
    )


def _overlaps(agreement: AllocationAgreement, start: Any, end: Any) -> bool:
    return agreement.valid_from <= end and (
        agreement.valid_to is None or agreement.valid_to >= start
    )


async def report(session: AsyncSession, statement: Statement) -> dict[str, Any]:
    items = (
        await session.scalars(
            select(StatementCostItem)
            .where(StatementCostItem.statement_id == statement.id)
            .order_by(StatementCostItem.created_at)
        )
    ).all()
    leases = [o for o in await services.occupants(session, statement) if o["contract_id"]]
    contract_ids = {o["contract_id"] for o in leases}
    agreements: list[AllocationAgreement] = []
    if contract_ids:
        agreements = list(
            (
                await session.scalars(
                    select(AllocationAgreement).where(
                        AllocationAgreement.contract_id.in_(contract_ids)
                    )
                )
            ).all()
        )
    rows: list[dict[str, Any]] = []
    for item in items:
        account = await session.get(LedgerAccount, item.account_id) if item.account_id else None
        code = account.operating_cost_type if account else None
        if code is None or betrkv.get(code) is None:
            rows.append(
                {
                    "cost_item_id": item.id,
                    "label": item.label,
                    "operating_cost_type": None,
                    "contract_id": None,
                    "unit_number": None,
                    "state": NO_TYPE,
                    "blocking": True,
                    "hint": "Kostenkonto ohne Betriebskostenart, Zuordnung fehlt.",
                }
            )
            continue
        for lease in leases:
            found = [
                a
                for a in agreements
                if a.contract_id == lease["contract_id"]
                and a.operating_cost_type == code
                and _overlaps(a, lease["from"], lease["to"])
            ]
            covering = [a for a in found if _covers(a, lease["from"], lease["to"])]
            if covering and covering[0].status == "excluded":
                state, blocking = EXCLUDED, False
                hint = "Ausdrücklich nicht umlagefähig vereinbart."
            elif covering:
                state, blocking, hint = AGREED, False, ""
            elif found:
                state, blocking = EXPIRED, True
                hint = "Vereinbarung deckt den Mietzeitraum nur teilweise ab."
            else:
                state, blocking = MISSING, True
                hint = "Keine erfasste Umlagevereinbarung für diese Position."
            rows.append(
                {
                    "cost_item_id": item.id,
                    "label": item.label,
                    "operating_cost_type": code,
                    "contract_id": lease["contract_id"],
                    "unit_number": lease["unit_number"],
                    "state": state,
                    "blocking": blocking,
                    "hint": hint,
                }
            )
    missing = [r for r in rows if r["blocking"]]
    return {
        "statement_id": statement.id,
        "complete": not missing,
        "blocking_enabled": await blocking_enabled(session),
        "missing_count": len(missing),
        "rows": rows,
        "source": betrkv.SOURCE,
    }


async def ensure_complete(session: AsyncSession, statement: Statement) -> None:
    """Blocks the output while the tenant switch is on and bases are missing."""
    if not await blocking_enabled(session):
        return
    result = await report(session, statement)
    if not result["complete"]:
        raise ProblemError(
            ErrorCodes.BILLING_ALLOCATION_BASIS_MISSING,
            detail=f"{result['missing_count']} Umlagegrundlagen fehlen oder sind unvollständig.",
        )
