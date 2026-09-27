"""Advance rule: new monthly advances from the statement result (M17-03, 7.6 A04/A07).

Rule (draft until the operator releases it, docs/rules/M17-03-vorschussregel.md): the
tenant's cost share of the settled period divided by twelve, optionally raised by a safety
surcharge in percent (tenant setting, default 0), rounded half up to the cent. The result is
a proposal that a second person confirms; confirming records the decision and the letter text
block only. Contract payments are never changed here: the adjustment of advances is a separate
step under § 560 BGB (R08, A04) and stays behind release gate G3.

* A tenancy that ended within the period gets no proposal (no future advances).
* A tenancy that started within the period gets the proposal with a note that the share
  covers a shorter period than the statement period.
* Every proposal keeps the snapshot hash it was derived from (A01: only released data).
"""

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.models import Statement, StatementSnapshot, _fk
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.problems import ErrorCodes, ProblemError

RULE_VERSION = "M17-03-advance-rule-v1"
MONTHS = 12
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")
MAX_SURCHARGE = Decimal("100.00")
PROPOSAL_LABEL = "Vorschlag, Anpassung erfolgt gesondert"


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AdvanceRuleSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Safety surcharge per tenant in percent (default 0); no other parameter is configurable."""

    __tablename__ = "statement_advance_rule"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_statement_advance_rule_tenant"),)

    surcharge_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=ZERO, server_default="0"
    )


class AdvanceProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "statement_advance_proposal"
    __table_args__ = (
        Index("ix_statement_advance_proposal_statement", "tenant_id", "statement_id"),
    )

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    unit_number: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_costs: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=MONTHS, server_default=str(MONTHS)
    )
    surcharge_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=ZERO, server_default="0"
    )
    proposed_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProposalStatus.PROPOSED.value,
        server_default=ProposalStatus.PROPOSED.value,
    )
    note: Mapped[str | None] = mapped_column(Text)
    letter_text: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def propose(previous_costs: Decimal, surcharge_percent: Decimal = ZERO) -> Decimal:
    """``previous_costs / 12 * (1 + surcharge / 100)`` rounded half up to the cent.

    Computed in one step so that the rounding happens once: 1.234,56 / 12 = 102,88 (0 %);
    with 5 % surcharge 1.234,56 * 105 / 1.200 = 108,024 -> 108,02.
    """
    if previous_costs <= 0:
        return ZERO
    if surcharge_percent < 0 or surcharge_percent > MAX_SURCHARGE:
        raise ValueError("surcharge_percent must be between 0 and 100")
    amount = previous_costs * (HUNDRED + surcharge_percent) / (HUNDRED * MONTHS)
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _eur(value: Decimal) -> str:
    from mhvp.billing.letters import fmt_eur

    return fmt_eur(value)


def letter_text(
    *,
    previous_costs: Decimal,
    surcharge_percent: Decimal,
    proposed_amount: Decimal,
    period_from: date,
    period_to: date,
    shorter_period: bool,
) -> str:
    """German text block for the tenant letter (draft, no legal effect, no deadline)."""
    lines = [
        "Vorschlag für die neue monatliche Betriebskostenvorauszahlung: "
        f"{_eur(proposed_amount)} ({PROPOSAL_LABEL}).",
        "Grundlage ist Ihr Kostenanteil des Abrechnungszeitraums "
        f"{period_from:%d.%m.%Y} bis {period_to:%d.%m.%Y} in Höhe von {_eur(previous_costs)}, "
        f"geteilt durch zwölf Monate"
        + (
            f", zuzüglich eines Sicherheitsaufschlags von {surcharge_percent.normalize():f} "
            "Prozent."
            if surcharge_percent > 0
            else "."
        ),
    ]
    if shorter_period:
        lines.append(
            "Ihr Nutzungszeitraum ist kürzer als der Abrechnungszeitraum; der Kostenanteil "
            "bezieht sich auf den Nutzungszeitraum."
        )
    lines.append(
        "Eine Anpassung der Vorauszahlung wird gesondert erklärt und tritt nicht durch dieses "
        "Schreiben ein."
    )
    return "\n".join(lines)


def build_proposals(
    snapshot_inputs: dict[str, Any],
    snapshot_results: dict[str, Any],
    surcharge_percent: Decimal,
) -> list[dict[str, Any]]:
    """Pure derivation from a snapshot (hand computable, rule 0.1.8)."""
    period_from = date.fromisoformat(snapshot_inputs["period"][0])
    period_to = date.fromisoformat(snapshot_inputs["period"][1])
    proposals = []
    for row in snapshot_results.get("results", []):
        row_to = date.fromisoformat(row["to"])
        row_from = date.fromisoformat(row["from"])
        if row_to < period_to:
            continue  # tenancy ended within the period: no future advances
        costs = Decimal(row["costs"])
        amount = propose(costs, surcharge_percent)
        shorter = row_from > period_from
        proposals.append(
            {
                "contract_id": row["contract_id"],
                "unit_number": row["unit_number"],
                "previous_costs": costs,
                "surcharge_percent": surcharge_percent,
                "proposed_amount": amount,
                "note": (
                    "Nutzungszeitraum kürzer als der Abrechnungszeitraum." if shorter else None
                ),
                "letter_text": letter_text(
                    previous_costs=costs,
                    surcharge_percent=surcharge_percent,
                    proposed_amount=amount,
                    period_from=period_from,
                    period_to=period_to,
                    shorter_period=shorter,
                ),
            }
        )
    return proposals


async def setting(session: AsyncSession, tenant_id: uuid.UUID) -> AdvanceRuleSetting:
    row = await session.scalar(select(AdvanceRuleSetting))
    if row is None:
        row = AdvanceRuleSetting(tenant_id=tenant_id, surcharge_percent=ZERO)
        session.add(row)
        await session.flush()
    return row


async def create_proposals(
    session: AsyncSession,
    statement: Statement,
    snapshot: StatementSnapshot,
    *,
    surcharge_percent: Decimal | None,
    user_id: uuid.UUID | None,
) -> list[AdvanceProposal]:
    """Replace the open proposals of the statement by proposals from its current snapshot.

    Confirmed or rejected proposals of an older snapshot are kept as history; open ones are
    replaced so that only one open proposal per contract exists.
    """
    if surcharge_percent is None:
        surcharge_percent = (await setting(session, statement.tenant_id)).surcharge_percent
    if surcharge_percent < 0 or surcharge_percent > MAX_SURCHARGE:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Sicherheitsaufschlag nur zwischen 0 und 100 Prozent."
        )
    existing = (
        await session.scalars(
            select(AdvanceProposal).where(
                AdvanceProposal.statement_id == statement.id,
                AdvanceProposal.status == ProposalStatus.PROPOSED.value,
            )
        )
    ).all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    rows = []
    for data in build_proposals(snapshot.inputs, snapshot.results, surcharge_percent):
        row = AdvanceProposal(
            tenant_id=statement.tenant_id,
            statement_id=statement.id,
            snapshot_hash=snapshot.hash,
            contract_id=uuid.UUID(data["contract_id"]),
            unit_number=data["unit_number"],
            previous_costs=data["previous_costs"],
            months=MONTHS,
            surcharge_percent=surcharge_percent,
            proposed_amount=data["proposed_amount"],
            status=ProposalStatus.PROPOSED.value,
            note=data["note"],
            letter_text=data["letter_text"],
            created_by=user_id,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


def out(row: AdvanceProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "statement_id": row.statement_id,
        "snapshot_hash": row.snapshot_hash,
        "contract_id": row.contract_id,
        "unit_number": row.unit_number,
        "previous_costs": str(Decimal(row.previous_costs).quantize(CENT)),
        "months": row.months,
        "surcharge_percent": str(Decimal(row.surcharge_percent).quantize(CENT)),
        "proposed_amount": str(Decimal(row.proposed_amount).quantize(CENT)),
        "status": row.status,
        "note": row.note,
        "letter_text": row.letter_text,
        "label": PROPOSAL_LABEL,
        "rule_version": RULE_VERSION,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "created_by": row.created_by,
    }
