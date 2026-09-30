"""Bank feedback and reconciliation of direct debit runs (M15-01, 7.5 SEPA).

After the file was handed out (run ``exported``) the bank reports per collection: accepted,
rejected before settlement, collected (actual amount) or returned (Rücklastschrift with an
ISO 20022 reason code). The feedback is recorded on the order, entered manually or taken from
an imported pain.002 or camt.054 report (``mhvp.banking.bank_status``). Nothing here posts:
settlement of the receivable happens only through the bank statement (D06); a return after
settlement is shown as a reconciliation finding and corrected by a reversal a person books
(rule 0.1.7). Repeated feedback with the same status has no effect (B08).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.direct_debit_models import (
    DirectDebitOrder,
    DirectDebitOrderStatus,
    DirectDebitRun,
    DirectDebitRunStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

S = DirectDebitOrderStatus
# Allowed predecessor states of each reported status.
_FROM: dict[DirectDebitOrderStatus, tuple[DirectDebitOrderStatus, ...]] = {
    S.ACCEPTED: (S.OPEN,),
    S.REJECTED: (S.OPEN, S.ACCEPTED),
    S.COLLECTED: (S.OPEN, S.ACCEPTED),
    S.RETURNED: (S.OPEN, S.ACCEPTED, S.COLLECTED),
}


async def apply_status(
    session: AsyncSession,
    run: DirectDebitRun,
    order: DirectDebitOrder,
    status: DirectDebitOrderStatus,
    *,
    reason: str | None = None,
    reason_code: str | None = None,
    collected_amount: Decimal | None = None,
    bank_transaction_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    source: str = "manual",
) -> bool:
    """Record one bank feedback; returns False when it repeats the current state (B08)."""
    from mhvp.banking.models import BankTransaction

    if run.status is not DirectDebitRunStatus.EXPORTED:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Bankrückmeldungen gibt es nur zu ausgegebenen Lastschriftdateien.",
        )
    current = DirectDebitOrderStatus(order.bank_status)
    if current is status:
        return False
    if current not in _FROM[status]:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=f"Rückmeldung {status.value} nach Status {current.value} nicht zulässig.",
        )
    if collected_amount is not None and status is not S.COLLECTED and status is not S.RETURNED:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Betrag nur bei Einzug oder Rückgabe.")
    amount = collected_amount if collected_amount is not None else order.amount
    if amount <= 0 or amount > order.amount:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Der gemeldete Betrag muss positiv sein und darf die Lastschrift nicht übersteigen."
            ),
        )
    if bank_transaction_id is not None:
        tx = await session.get(BankTransaction, bank_transaction_id)
        if tx is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankumsatz nicht gefunden.")
        if tx.property_bank_account_id != run.property_bank_account_id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Umsatz gehört nicht zum Gläubigerkonto des Laufs.",
            )
        if status is S.COLLECTED and tx.amount <= 0:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ein Einzug ist eine Gutschrift.")
        if status is S.RETURNED and tx.amount >= 0:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Eine Rücklastschrift ist eine Belastung."
            )
        order.bank_transaction_id = tx.id
    order.bank_status = status.value
    order.bank_status_reason = (reason or None) and reason[:500]
    order.bank_status_reason_code = (reason_code or None) and reason_code[:8]
    order.bank_status_at = datetime.now(UTC)
    if status in (S.COLLECTED, S.RETURNED):
        order.collected_amount = amount if status is S.COLLECTED else order.collected_amount
    await emit(
        session,
        tenant_id=order.tenant_id,
        type=f"direct_debit_order.{status.value}",
        entity_type="direct_debit_order",
        entity_id=order.id,
        actor_user_id=user_id,
        payload={
            "run_id": str(run.id),
            "reason": reason,
            "reason_code": reason_code,
            "amount": str(amount),
            "source": source,
        },
    )
    await session.flush()
    return True


def _finding(order: DirectDebitOrder, remaining: Decimal) -> str | None:
    """Reconciliation finding of one collection against its open item (M15-01)."""
    status = DirectDebitOrderStatus(order.bank_status)
    settled = order.amount - remaining
    if status is S.COLLECTED:
        collected = order.collected_amount or order.amount
        if collected != order.amount:
            return "Teileinzug: Differenz bleibt offen, Zahler informieren"
        if remaining > 0:
            return "Einzug gemeldet, Sollstellung noch nicht ausgeglichen (Kontoauszug zuordnen)"
    if status is S.RETURNED and settled > 0:
        return "Rücklastschrift nach Ausgleich: Ausgleichsbuchung per Storno korrigieren"
    if status is S.REJECTED and settled > 0:
        return "Abgelehnt, Sollstellung trotzdem ausgeglichen: Zuordnung prüfen"
    return None


async def reconciliation(session: AsyncSession, run: DirectDebitRun) -> dict[str, Any]:
    """Per order: bank status, collected amount, remaining amount of the open item and a
    finding; totals per status. Read only."""
    orders = (
        await session.scalars(
            select(DirectDebitOrder)
            .where(DirectDebitOrder.run_id == run.id)
            .order_by(DirectDebitOrder.id)
        )
    ).all()
    rows = []
    totals: dict[str, Decimal] = {}
    for o in orders:
        remaining = await acc.remaining(session, o.open_item_id)
        totals[o.bank_status] = totals.get(o.bank_status, Decimal("0.00")) + o.amount
        rows.append(
            {
                "order_id": str(o.id),
                "open_item_id": str(o.open_item_id),
                "debtor_name": o.debtor_name,
                "end_to_end_id": o.end_to_end_id,
                "amount": str(o.amount),
                "bank_status": o.bank_status,
                "reason_code": o.bank_status_reason_code,
                "reason": o.bank_status_reason,
                "collected_amount": str(o.collected_amount) if o.collected_amount else None,
                "open_item_remaining": str(remaining),
                "bank_transaction_id": str(o.bank_transaction_id)
                if o.bank_transaction_id
                else None,
                "finding": _finding(o, remaining),
            }
        )
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "control_sum": str(run.control_sum),
        "totals": {k: str(v) for k, v in sorted(totals.items())},
        "open_findings": sum(1 for r in rows if r["finding"]),
        "orders": rows,
    }
