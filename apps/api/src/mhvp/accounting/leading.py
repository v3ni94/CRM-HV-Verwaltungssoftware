"""Leading system per ledger, property, process kind and date (13.1 Ergänzung, GAC-05).

``is_leading`` is the single check of the runs (receivables, dunning, direct debit, payment
orders). It uses the newest approved ``ledger_leading_switch`` row valid on the date, a row
for the property before a row for the whole ledger, and falls back to
``Ledger.leading_system``. Without rows the behaviour is unchanged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import LeadingSystem, Ledger, LedgerLeadingSwitch
from mhvp.core.problems import ErrorCodes, ProblemError


class LeadingKind(StrEnum):
    RECEIVABLE_POSTING = "receivable_posting"
    DUNNING = "dunning"
    DIRECT_DEBIT = "direct_debit"
    PAYMENT_ORDER = "payment_order"


async def explicit(
    session: AsyncSession,
    ledger: Ledger,
    kind: LeadingKind | str,
    on_date: date,
    property_id: uuid.UUID | None = None,
) -> LeadingSystem | None:
    """Leading system from an approved switch row, or ``None`` without a matching row."""
    query = select(LedgerLeadingSwitch).where(
        LedgerLeadingSwitch.ledger_id == ledger.id,
        LedgerLeadingSwitch.kind == str(kind),
        LedgerLeadingSwitch.status == "approved",
        LedgerLeadingSwitch.valid_from <= on_date,
    )
    if property_id is None:
        query = query.where(LedgerLeadingSwitch.property_id.is_(None))
    else:
        query = query.where(
            or_(
                LedgerLeadingSwitch.property_id.is_(None),
                LedgerLeadingSwitch.property_id == property_id,
            )
        )
    rows = (await session.scalars(query)).all()
    if not rows:
        return None
    best = max(
        rows,
        key=lambda r: (r.property_id is not None, r.valid_from, r.decided_at or r.created_at),
    )
    return LeadingSystem(best.leading_system)


async def leading_system(
    session: AsyncSession,
    ledger: Ledger,
    kind: LeadingKind | str,
    on_date: date,
    property_id: uuid.UUID | None = None,
) -> LeadingSystem:
    found = await explicit(session, ledger, kind, on_date, property_id)
    return found if found is not None else ledger.leading_system


async def is_leading(
    session: AsyncSession,
    ledger: Ledger,
    kind: LeadingKind | str,
    on_date: date,
    property_id: uuid.UUID | None = None,
) -> bool:
    """True when the platform leads ``kind`` for the ledger on ``on_date``."""
    return (await leading_system(session, ledger, kind, on_date, property_id)) is LeadingSystem.MHVP


def request_switch(
    ledger: Ledger,
    *,
    kind: LeadingKind,
    leading: LeadingSystem,
    valid_from: date,
    property_id: uuid.UUID | None,
    comment: str | None,
    user_id: uuid.UUID,
) -> LedgerLeadingSwitch:
    return LedgerLeadingSwitch(
        tenant_id=ledger.tenant_id,
        ledger_id=ledger.id,
        property_id=property_id,
        kind=kind.value,
        leading_system=leading.value,
        valid_from=valid_from,
        status="requested",
        comment=comment,
        requested_by=user_id,
        created_by=user_id,
    )


def needs_g1(row: LedgerLeadingSwitch) -> bool:
    """All four kinds post or pay on the platform; leading back to the old system does not."""
    return row.leading_system == LeadingSystem.MHVP.value


def decide(
    row: LedgerLeadingSwitch,
    *,
    approve: bool,
    user_id: uuid.UUID | None,
    is_platform_admin: bool,
    comment: str | None,
) -> LedgerLeadingSwitch:
    if row.status != "requested":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Antrag ist bereits entschieden.")
    if user_id is None or user_id == row.requested_by or is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person vornehmen."
        )
    row.status = "approved" if approve else "rejected"
    row.decided_by, row.decided_at = user_id, datetime.now(UTC)
    row.decision_comment = comment
    row.updated_by = user_id
    return row
