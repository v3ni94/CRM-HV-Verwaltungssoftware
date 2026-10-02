"""Evidence chain of unposted bank movements (B05, rule M12-05, ADR 0014 addendum 2).

MASTER-PROMPT 7.1 B05: an unclarified bank movement gets a visible clarification status
and a responsible task; a missing invoice is never replaced by an invented document. Here:

* the runner opens a row (``ensure_open``) when the deterministic verifier of
  ``recurring_expense`` finds neither a linked posted invoice nor a person's decision that
  no document is required; a ticket "Beleg fehlt" is created with the row (responsible task);
* a person moves the row (``decide``): ``in_clarification`` (optionally with an assignee),
  ``no_document_required`` (reason mandatory, the decision of a person, never of a rule or
  a model), ``resolved`` (document of the tenant mandatory); ``open`` reopens;
* ``list_rows`` is the list "Buchungen ohne Beleg" per ledger (before the period lock) and
  the source of the audit export table ``belegkette``;
* ``for_transaction`` feeds the verifier (``features``): a resolved row or a person's
  ``no_document_required`` completes the evidence chain, everything else leaves the
  transaction in clarification.

Nothing here posts; the clarification status changes no booking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import event_types as ev
from mhvp.banking.models import (
    BankClarification,
    BankTransaction,
    ClarificationStatus,
    TransactionStatus,
)
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

OPEN_STATUSES = (
    ClarificationStatus.OPEN.value,
    ClarificationStatus.IN_CLARIFICATION.value,
    ClarificationStatus.RECEIPT_REQUESTED.value,
)


async def for_transaction(session: AsyncSession, tx_id: uuid.UUID) -> BankClarification | None:
    row = await session.scalar(
        select(BankClarification).where(BankClarification.bank_transaction_id == tx_id)
    )
    return row if isinstance(row, BankClarification) else None


def evidence_of(row: BankClarification | None) -> dict[str, Any] | None:
    """The clarification facts the verifier sees (``tx["clarification"]``)."""
    if row is None:
        return None
    return {
        "status": row.status,
        "document_id": str(row.document_id) if row.document_id else None,
        "decided_by_person": row.decided_by is not None,
    }


def evidence_complete(clarification: dict[str, Any] | None) -> bool:
    """B05: a person's ``no_document_required`` with reason or a resolved row with document."""
    if not clarification:
        return False
    status = clarification.get("status")
    if status == ClarificationStatus.RESOLVED.value:
        return bool(clarification.get("document_id"))
    if status == ClarificationStatus.NO_DOCUMENT_REQUIRED.value:
        return bool(clarification.get("decided_by_person"))
    return False


async def ensure_open(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    tenant_id: uuid.UUID,
    reasons: list[str],
    rule_id: uuid.UUID | None,
) -> tuple[BankClarification, bool]:
    """The clarification row of a transaction; created as ``open`` with a responsible ticket
    when missing. Returns (row, created). A row a person already decided is left alone."""
    row = await for_transaction(session, tx.id)
    if row is not None:
        return row, False
    row = BankClarification(
        tenant_id=tenant_id,
        bank_transaction_id=tx.id,
        legal_entity_id=tx.legal_entity_id,
        status=ClarificationStatus.OPEN.value,
        reasons=list(reasons),
        rule_id=rule_id,
    )
    session.add(row)
    await session.flush()
    row.ticket_id = await _create_ticket(session, tx, tenant_id=tenant_id)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_CLARIFICATION_OPENED,
        entity_type="bank_clarification",
        entity_id=row.id,
        actor_user_id=None,
        payload={
            "bank_transaction_id": str(tx.id),
            "legal_entity_id": str(tx.legal_entity_id),
            "rule_id": str(rule_id) if rule_id else None,
            "ticket_id": str(row.ticket_id) if row.ticket_id else None,
            "reasons": list(reasons),
        },
    )
    return row, True


async def open_by_person(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    reason: str,
    assignee_user_id: uuid.UUID | None,
) -> tuple[BankClarification, bool]:
    """A person reports a bank movement as unreceipted (B05): the row is opened with the
    responsible ticket like the runner does; an existing row is returned unchanged."""
    if tx.status is not TransactionStatus.NEW:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur offene Bankbewegungen erhalten eine Klärung."
        )
    row, created = await ensure_open(
        session, tx, tenant_id=tenant_id, reasons=[reason.strip()], rule_id=None
    )
    if created:
        row.created_by = user_id
        if assignee_user_id is not None:
            row.assignee_user_id = assignee_user_id
        await session.flush()
    return row, created


async def ensure_booking_allowed(session: AsyncSession, tx: BankTransaction) -> None:
    """Booking lock (B05): a bank movement with a clarification row is booked only once the
    evidence chain is complete (resolved with document or a person's no document required).
    A movement without row is not affected; nothing is decided automatically."""
    row = await for_transaction(session, tx.id)
    if row is not None and not evidence_complete(evidence_of(row)):
        raise ProblemError(
            ErrorCodes.BANK_RECEIPT_MISSING,
            detail="Beleg verknüpfen oder „kein Beleg erforderlich“ mit Begründung entscheiden.",
        )


async def _create_ticket(
    session: AsyncSession, tx: BankTransaction, *, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    """Responsible task (B05): a ticket of the tenant without template, source manual,
    linked to the property of the bank account. Never fails the runner."""
    from datetime import timedelta

    from mhvp.core.numbering import next_number
    from mhvp.properties.models import PropertyBankAccount
    from mhvp.tickets.models import Priority, Ticket, TicketSource

    account = await session.get(PropertyBankAccount, tx.property_bank_account_id)
    ticket = Ticket(
        tenant_id=tenant_id,
        created_by=None,
        number=await next_number(session, tenant_id, "ticket"),
        title=(
            f"Beleg fehlt: Bankbewegung {tx.booking_date:%d.%m.%Y} {tx.amount} EUR "
            f"{tx.counterpart_name or ''}"
        ).strip()[:300],
        internal_description=(
            "Unbelegte Bankbewegung (B05): Beleg verknüpfen oder mit Begründung "
            "„kein Beleg erforderlich“ entscheiden. Bis dahin bucht die Automatik nicht."
        ),
        priority=Priority.NORMAL,
        property_id=account.property_id if account is not None else None,
        source=TicketSource.MANUAL,
        sla_due_at=datetime.now(UTC) + timedelta(hours=72),
    )
    session.add(ticket)
    await session.flush()
    return ticket.id


async def list_rows(
    session: AsyncSession,
    *,
    legal_entity_id: uuid.UUID | None = None,
    ledger_id: uuid.UUID | None = None,
    until: Any = None,
    open_only: bool = True,
) -> list[BankClarification]:
    query = select(BankClarification).join(
        BankTransaction, BankTransaction.id == BankClarification.bank_transaction_id
    )
    if open_only:
        query = query.where(BankClarification.status.in_(OPEN_STATUSES))
    if legal_entity_id is not None:
        query = query.where(BankClarification.legal_entity_id == legal_entity_id)
    if ledger_id is not None:
        from mhvp.accounting.models import Ledger

        entity_id = await session.scalar(
            select(Ledger.legal_entity_id).where(Ledger.id == ledger_id)
        )
        query = query.where(BankClarification.legal_entity_id == entity_id)
    if until is not None:
        query = query.where(BankTransaction.booking_date <= until)
    rows = await session.scalars(
        query.order_by(BankTransaction.booking_date, BankClarification.created_at)
    )
    return list(rows)


async def row_out(session: AsyncSession, row: BankClarification) -> dict[str, Any]:
    tx = await session.get(BankTransaction, row.bank_transaction_id)
    return {
        "id": row.id,
        "bank_transaction_id": row.bank_transaction_id,
        "legal_entity_id": row.legal_entity_id,
        "status": row.status,
        "reasons": row.reasons,
        "rule_id": row.rule_id,
        "reason": row.reason,
        "document_id": row.document_id,
        "ticket_id": row.ticket_id,
        "assignee_user_id": row.assignee_user_id,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "created_at": row.created_at,
        "age_days": ((local_today() - tx.booking_date).days if tx and tx.booking_date else None),
        "booking_date": tx.booking_date if tx else None,
        "amount": tx.amount if tx else None,
        "counterpart_name": tx.counterpart_name if tx else None,
        "purpose": tx.purpose if tx else None,
        "transaction_status": tx.status.value if tx else None,
    }


async def decide(
    session: AsyncSession,
    *,
    row_id: uuid.UUID,
    status: str,
    reason: str | None,
    document_id: uuid.UUID | None,
    assignee_user_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
) -> BankClarification:
    """A person sets the clarification status. ``no_document_required`` needs a reason,
    ``resolved`` a document of the tenant; both are the decision of the logged in person."""
    row = await session.get(BankClarification, row_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if status not in ClarificationStatus.__members__.values():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Klärungsstatus.")
    if status == ClarificationStatus.NO_DOCUMENT_REQUIRED.value:
        if not (reason or "").strip():
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="„Kein Beleg erforderlich“ braucht eine Begründung der Person.",
            )
        if user_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Entscheidung braucht eine angemeldete Person."
            )
    if status == ClarificationStatus.RESOLVED.value:
        if document_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Erledigt braucht den verknüpften Beleg."
            )
        from mhvp.documents.models import Document

        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Beleg nicht gefunden.")
    before = row.status
    row.status = status
    row.reason = (reason or "").strip() or None
    row.document_id = document_id if status == ClarificationStatus.RESOLVED.value else None
    if assignee_user_id is not None:
        row.assignee_user_id = assignee_user_id
    if status in OPEN_STATUSES:
        row.decided_by = None
        row.decided_at = None
    else:
        row.decided_by = user_id
        row.decided_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.flush()
    tx = await session.get(BankTransaction, row.bank_transaction_id, with_for_update=True)
    if tx is not None and tx.status is TransactionStatus.NEW:
        # The facts of the transaction changed: the next snapshot opens a fresh round.
        from mhvp.banking import proposals

        await proposals.ensure_pending(session, tx)
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_CLARIFICATION_DECIDED,
        entity_type="bank_clarification",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={
            "bank_transaction_id": str(row.bank_transaction_id),
            "before": before,
            "after": status,
            "document_id": str(document_id) if document_id else None,
            "reason": row.reason,
        },
    )
    return row
