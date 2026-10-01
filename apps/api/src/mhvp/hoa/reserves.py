"""Earmarked reserves per position (M24-01, 7.8 W08, 6.5 reserve).

Extends the reserve entity of migration 0256 and the Zweckbindung of migration 0278 instead
of replacing them: master data (name, purpose, ledger account, bank investment of the legal
entity of the ledger, opening balance), the entered uses of funds per statement and the
development per year (opening, contribution, withdrawal, taxes, fees, interest, closing).

Everything here is information for the statement and the asset report. Nothing is posted:
movements are entries of the manager with receipt and resolution reference, a real posting
stays in accounting behind G1 (rule M24-01).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import EconomicPlan, HoaReserve, HoaReserveMovement, HoaStatement, PlanItem
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")

ZERO = Decimal("0.00")
KINDS = ("withdrawal", "tax", "fee", "interest")
MAX_YEARS = 30


class HoaReservePatchIn(BaseModel):
    """Changes of an earmarked reserve (M24-01). Omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    purpose: str | None = Field(default=None, max_length=2000)
    account_id: uuid.UUID | None = None
    bank_account_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None
    active: bool | None = None
    opening_balance: Decimal | None = Field(default=None, decimal_places=2)
    opening_year: int | None = Field(default=None, ge=1990, le=2100)


async def check_reserve_refs(
    session: AsyncSession,
    ledger: Any,
    *,
    account_id: uuid.UUID | None,
    bank_account_id: uuid.UUID | None,
) -> None:
    """Ledger account of the same ledger, bank account of the ledger's legal entity (E01: the
    reserve belongs to the GdWE, never to the management company)."""
    from mhvp.accounting.models import LedgerAccount
    from mhvp.properties.models import PropertyBankAccount

    if account_id is not None:
        account = await session.get(LedgerAccount, account_id)
        if account is None or account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Konto aus anderem Buchungskreis.")
        # V11-06: an inactive ledger account is refused on the server, not only in the form.
        if not account.active:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Buchungskonto ist inaktiv.")
    if bank_account_id is not None:
        bank = await session.get(PropertyBankAccount, bank_account_id)
        if bank is None or bank.legal_entity_id != ledger.legal_entity_id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Bankkonto gehört nicht zum Rechtsträger der Gemeinschaft.",
            )
        # V11-06: an ended bank account (valid_to before today) is refused.
        if bank.valid_to is not None and bank.valid_to < datetime.now(UTC).date():
            raise ProblemError(ErrorCodes.VALIDATION, detail="Bankkonto ist beendet.")


def reserve_out(r: HoaReserve, legal_entity_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "ledger_id": r.ledger_id,
        "legal_entity_id": legal_entity_id,
        "name": r.name,
        "purpose": r.purpose,
        "account_id": r.account_id,
        "bank_account_id": r.bank_account_id,
        "resolution_id": r.resolution_id,
        "active": r.active,
        "opening_balance": str(r.opening_balance),
        "opening_year": r.opening_year,
    }


def _movement_out(m: HoaReserveMovement) -> dict[str, Any]:
    return {
        "id": m.id,
        "statement_id": m.statement_id,
        "reserve_id": m.reserve_id,
        "kind": m.kind,
        "amount": str(m.amount),
        "purpose": m.purpose,
        "document_id": m.document_id,
        "journal_entry_id": m.journal_entry_id,
        "resolution_id": m.resolution_id,
        "receipt_linked": m.document_id is not None or m.journal_entry_id is not None,
    }


def develop(opening: Decimal, figures: dict[str, Decimal]) -> Decimal:
    """Closing = opening + contribution - withdrawals - taxes - fees + interest."""
    return (
        opening
        + figures["contributions"]
        - figures["withdrawals"]
        - figures["taxes"]
        - figures["fees"]
        + figures["interest"]
    )


async def _year_figures(session: AsyncSession, reserve: HoaReserve, year: int) -> dict[str, Any]:
    """Figures of one year: from the newest calculated statement position when there is one,
    otherwise the resolved plan (Soll) with the movements entered on the newest draft."""
    statement = await session.scalar(
        select(HoaStatement)
        .where(HoaStatement.ledger_id == reserve.ledger_id, HoaStatement.year == year)
        .order_by(HoaStatement.version.desc())
        .limit(1)
    )
    block = ((statement.snapshot or {}).get("reserve") or {}) if statement else {}
    positions = block.get("positions")
    position = next((p for p in positions or [] if p.get("reserve_id") == str(reserve.id)), None)
    if position is not None and statement is not None:
        bound = bool(position.get("contributions_paid_bound"))
        return {
            "source": "statement",
            "statement_id": str(statement.id),
            "statement_version": statement.version,
            "contribution_basis": "paid" if bound else "planned",
            "contributions_planned": Decimal(position["contributions_planned"]),
            "contributions": Decimal(
                position["contributions_paid"] if bound else position["contributions_planned"]
            ),
            "withdrawals": Decimal(position["withdrawals"]),
            "taxes": Decimal(position["taxes"]),
            "fees": Decimal(position["fees"]),
            "interest": Decimal(position["interest"]),
        }
    plan = await session.scalar(
        select(EconomicPlan)
        .where(
            EconomicPlan.ledger_id == reserve.ledger_id,
            EconomicPlan.year == year,
            EconomicPlan.resolution_id.is_not(None),
        )
        .order_by(EconomicPlan.version.desc())
        .limit(1)
    )
    planned = ZERO
    if plan is not None:
        amounts = await session.scalars(
            select(PlanItem.amount).where(
                PlanItem.plan_id == plan.id, PlanItem.reserve_id == reserve.id
            )
        )
        planned = sum(amounts.all(), ZERO)
    sums = dict.fromkeys(KINDS, ZERO)
    if statement is not None:
        for m in (
            await session.scalars(
                select(HoaReserveMovement).where(
                    HoaReserveMovement.statement_id == statement.id,
                    HoaReserveMovement.reserve_id == reserve.id,
                )
            )
        ).all():
            sums[m.kind] = sums.get(m.kind, ZERO) + m.amount
    return {
        "source": "plan" if plan is not None else "none",
        "statement_id": str(statement.id) if statement else None,
        "statement_version": statement.version if statement else None,
        "contribution_basis": "planned",
        "contributions_planned": planned,
        "contributions": planned,
        "withdrawals": sums["withdrawal"],
        "taxes": sums["tax"],
        "fees": sums["fee"],
        "interest": sums["interest"],
    }


async def reserve_development(
    session: AsyncSession, reserve: HoaReserve, to_year: int
) -> list[dict[str, Any]]:
    """Development per year from ``opening_year`` (entered opening balance) up to
    ``to_year``; each opening is the closing of the year before. Without an opening year
    only ``to_year`` is shown and its opening is the entered balance."""
    start = reserve.opening_year if reserve.opening_year is not None else to_year
    start = max(start, to_year - MAX_YEARS + 1)
    rows: list[dict[str, Any]] = []
    opening = reserve.opening_balance
    for year in range(start, to_year + 1):
        fig = await _year_figures(session, reserve, year)
        closing = develop(opening, fig)
        rows.append(
            {
                "year": year,
                "opening": str(opening),
                "opening_entered": year == start,
                **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in fig.items()},
                "closing": str(closing),
            }
        )
        opening = closing
    return rows


async def opening_for_year(session: AsyncSession, reserve: HoaReserve, year: int) -> Decimal:
    """Opening of ``year``: the entered balance in the opening year, otherwise the closing of
    the year before (chained development)."""
    if reserve.opening_year is None or year <= reserve.opening_year:
        return reserve.opening_balance
    rows = await reserve_development(session, reserve, year - 1)
    return Decimal(rows[-1]["closing"])


async def add_opening_closing(
    session: AsyncSession, reserves: list[HoaReserve], positions: list[dict[str, Any]], year: int
) -> None:
    """M24-01: opening and closing per position of the statement (planned and paid basis)."""
    by_id = {str(r.id): r for r in reserves}
    for p in positions:
        reserve = by_id.get(p["reserve_id"])
        if reserve is None:
            continue
        opening = await opening_for_year(session, reserve, year)
        p["opening"] = str(opening)
        p["closing_planned"] = str(opening + Decimal(p["planned_change"]))
        p["closing_paid"] = str(opening + Decimal(p["paid_change"]))


async def _reserve_with_ledger(session: AsyncSession, reserve_id: uuid.UUID) -> tuple[Any, Any]:
    from mhvp.core.auth.scope import (
        ensure_session_legal_entity_allowed,
        ensure_session_property_allowed,
    )
    from mhvp.hoa.routers import _hoa_ledger

    reserve = await session.get(HoaReserve, reserve_id)
    if reserve is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ledger = await _hoa_ledger(session, reserve.ledger_id)
    # U15: ``reserve_id`` is not covered by HOA_GUARD; property and legal entity scope here.
    ensure_session_property_allowed(session, ledger.property_id)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return reserve, ledger


@router.get("/reserves/{reserve_id}", summary="Zweckgebundene Rücklage mit Rechtsträger")
async def get_reserve(
    reserve_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        reserve, ledger = await _reserve_with_ledger(session, reserve_id)
        return reserve_out(reserve, ledger.legal_entity_id)


async def _ensure_opening_unlocked(
    session: AsyncSession, reserve: HoaReserve, changes: dict[str, Any]
) -> None:
    """U15-03: once a statement of the opening year (old or new) or of a later year is
    calculated or further, opening balance and opening year are frozen; corrections only by a
    new movement."""
    touched = [
        key
        for key in ("opening_balance", "opening_year")
        if key in changes and changes[key] != getattr(reserve, key)
    ]
    if not touched:
        return
    # Review W79: the opening carries forward into every later year (``develop_years``) and,
    # without an opening year, is the opening of every year (``opening_for_year``). The lock
    # therefore covers each statement from the earlier of the old and new opening year on;
    # with no opening year on either side it covers every statement of the ledger.
    new_year = changes.get("opening_year", reserve.opening_year)
    conditions = [
        HoaStatement.ledger_id == reserve.ledger_id,
        HoaStatement.status != StatementStatus.DRAFT,
    ]
    if reserve.opening_year is not None and new_year is not None:
        conditions.append(HoaStatement.year >= min(reserve.opening_year, new_year))
    hit = await session.scalar(select(HoaStatement.id).where(*conditions).limit(1))
    if hit is not None:
        raise ProblemError(
            ErrorCodes.HOA_RESERVE_OPENING_LOCKED,
            detail="Abrechnung des Anfangsjahres ist berechnet oder freigegeben; "
            "Korrektur nur per neuer Bewegung.",
        )


@router.patch("/reserves/{reserve_id}", summary="Zweckgebundene Rücklage ändern (M24-01)")
async def patch_reserve(
    reserve_id: uuid.UUID,
    body: HoaReservePatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Name darf nicht leer sein.")
    for key in ("active", "opening_balance"):
        if key in changes and changes[key] is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"{key} darf nicht leer sein.")
    async with tenant_tx(request, principal) as session:
        reserve = await session.get(HoaReserve, reserve_id, with_for_update=True)
        if reserve is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _, ledger = await _reserve_with_ledger(session, reserve_id)
        await check_reserve_refs(
            session,
            ledger,
            account_id=changes.get("account_id"),
            bank_account_id=changes.get("bank_account_id"),
        )
        await _ensure_opening_unlocked(session, reserve, changes)
        for key, value in changes.items():
            setattr(reserve, key, value)
        reserve.updated_by = principal.user_id
        await session.flush()
        return reserve_out(reserve, ledger.legal_entity_id)


@router.get(
    "/reserves/{reserve_id}/development",
    summary="Entwicklung einer Rücklage je Jahr (Anfang, Zuführung, Entnahme, Zinsen, Ende)",
)
async def get_reserve_development(
    reserve_id: uuid.UUID,
    year: int,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    if not 1990 <= year <= 2100:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jahr außerhalb des Bereichs.")
    async with tenant_tx(request, principal) as session:
        reserve, ledger = await _reserve_with_ledger(session, reserve_id)
        return {
            "reserve": reserve_out(reserve, ledger.legal_entity_id),
            "years": await reserve_development(session, reserve, year),
            "note": "Information für Abrechnung und Vermögensbericht, keine Buchung (M24-01).",
        }


@router.get(
    "/statements/{statement_id}/reserve-movements",
    summary="Mittelverwendung je Rücklage einer Abrechnung",
    dependencies=[Depends(strict_query)],
)
async def list_reserve_movements(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(HoaStatement, statement_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(HoaReserveMovement)
            .where(HoaReserveMovement.statement_id == statement_id)
            .order_by(HoaReserveMovement.id)
        )
        return [_movement_out(m) for m in rows.all()]


@router.delete(
    "/statements/{statement_id}/reserve-movements/{movement_id}",
    status_code=204,
    summary="Erfasste Mittelverwendung im Entwurf entfernen",
)
async def delete_reserve_movement(
    statement_id: uuid.UUID,
    movement_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> Response:
    """Only while the statement is a draft: the entry is draft information, never a posting;
    after the calculation a change needs a new version."""
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        movement = await session.get(HoaReserveMovement, movement_id)
        if st is None or movement is None or movement.statement_id != st.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über neue Version."
            )
        await session.delete(movement)
    return Response(status_code=204)
