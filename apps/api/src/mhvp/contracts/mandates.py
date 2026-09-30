"""SEPA mandate lifecycle (M5-03): expiry by ``valid_until`` and usage bookkeeping.

Recording only. ``mark_mandate_used`` is called by the collection once it is released
(gate G2); until then nothing calls it. No expiry rule beyond the explicit ``valid_until``
of the mandate is derived (uncertainty is no legal basis)."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contracts.models import Contract, MandateSequence, MandateStatus, SepaMandate
from mhvp.core.events import emit


def mark_mandate_used(mandate: SepaMandate, at: datetime | None = None) -> None:
    """Set ``last_used_at`` and advance a ``first`` mandate to ``recurring``."""
    mandate.last_used_at = at or datetime.now(UTC)
    if mandate.sequence is MandateSequence.FIRST:
        mandate.sequence = MandateSequence.RECURRING


async def expire_due_mandates(session: AsyncSession, today: date) -> int:
    """Active mandates whose ``valid_until`` lies before ``today`` become ``expired``; direct
    debit of the contracts using them stops (like a revocation). Returns the number."""
    rows = (
        await session.scalars(
            select(SepaMandate).where(
                SepaMandate.status == MandateStatus.ACTIVE,
                SepaMandate.valid_until.is_not(None),
                SepaMandate.valid_until < today,
            )
        )
    ).all()
    for mandate in rows:
        mandate.status = MandateStatus.EXPIRED
        users = (
            await session.scalars(
                select(Contract).where(
                    Contract.sepa_mandate_id == mandate.id, Contract.direct_debit.is_(True)
                )
            )
        ).all()
        for contract in users:
            contract.direct_debit = False
        await emit(
            session,
            tenant_id=mandate.tenant_id,
            type="sepa_mandate.expired",
            entity_type="sepa_mandate",
            entity_id=mandate.id,
            actor_user_id=None,
            payload={"valid_until": str(mandate.valid_until), "contracts": len(users)},
        )
    await session.flush()
    return len(rows)
