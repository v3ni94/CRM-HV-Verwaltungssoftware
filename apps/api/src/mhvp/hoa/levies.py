"""Special levies (W09, M24 extension): drafting, calculation per unit and instalment, binding
to a positive resolution on the calculated snapshot, application as contract payments of type
special_levy, and an earmarked funds report (resolved, charged, received, used, remaining)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.calc import distribute
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa import calc
from mhvp.hoa.models import Resolution, SpecialLevy

router = APIRouter(prefix="/hoa", tags=["hoa"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
BINDING = {"positive", "final", "legally_binding"}
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
CODE = "special_levy"


class LevyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    purpose: str = Field(min_length=3, max_length=4000)
    total: Decimal = Field(gt=0, decimal_places=2)
    allocation_key_id: uuid.UUID
    unit_ids: list[uuid.UUID] = Field(default_factory=list)
    first_due: date
    instalments: int = Field(default=1, ge=1, le=60)
    account_id: uuid.UUID | None = None


class LevyResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_id: uuid.UUID


def _month(start: date, offset: int) -> date:
    y, m = divmod(start.month - 1 + offset, 12)
    return date(start.year + y, m + 1, 1)


def _month_end(first: date) -> date:
    return _month(first, 1) - timedelta(days=1)


def _out(lv: SpecialLevy) -> dict[str, Any]:
    return {
        "id": lv.id,
        "legal_entity_id": lv.legal_entity_id,
        "ledger_id": lv.ledger_id,
        "purpose": lv.purpose,
        "total": lv.total,
        "allocation_key_id": lv.allocation_key_id,
        "unit_ids": lv.unit_ids,
        "first_due": lv.first_due,
        "instalments": lv.instalments,
        "account_id": lv.account_id,
        "status": lv.status,
        "snapshot": lv.snapshot,
        "snapshot_hash": lv.snapshot_hash,
        "resolution_id": lv.resolution_id,
        "applied_at": lv.applied_at,
    }


async def _levy(session: AsyncSession, levy_id: uuid.UUID, lock: bool = False) -> SpecialLevy:
    row = await session.get(SpecialLevy, levy_id, with_for_update=lock)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.post("/special-levies", status_code=201, summary="Sonderumlage (Entwurf)")
async def create_levy(
    body: LevyIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.hoa.routers import _hoa_ledger

    if body.first_due.day != 1:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Fälligkeit ab dem Monatsersten.")
    async with tenant_tx(request, principal) as session:
        ledger = await _hoa_ledger(session, body.ledger_id)
        row = SpecialLevy(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=ledger.legal_entity_id,
            **(body.model_dump() | {"unit_ids": [str(u) for u in body.unit_ids]}),
        )
        session.add(row)
        await session.flush()
        return _out(row)


@router.get("/special-levies", summary="Sonderumlagen einer GdWE")
async def list_levies(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(SpecialLevy)
            .where(SpecialLevy.legal_entity_id == legal_entity_id)
            .order_by(SpecialLevy.first_due.desc())
        )
        return [_out(r) | {"snapshot": None} for r in rows.all()]


@router.get("/special-levies/{levy_id}", summary="Sonderumlage")
async def get_levy(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _levy(session, levy_id))


@router.post("/special-levies/{levy_id}/calculate", summary="Verteilung je Einheit und Rate")
async def calculate_levy(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.hoa.routers import _hoa_ledger

    async with tenant_tx(request, principal) as session:
        lv = await _levy(session, levy_id, lock=True)
        if lv.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits berechnet.")
        ledger = await _hoa_ledger(session, lv.ledger_id)
        shares = await calc.unit_weights(
            session, ledger.property_id, lv.allocation_key_id, lv.first_due, lv.first_due
        )
        if lv.unit_ids:
            chosen = set(lv.unit_ids)
            shares = [s for s in shares if s.key[1] in chosen]
            if len(shares) != len(chosen):
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Betroffene Einheit ohne Schlüsselwert."
                )
        parts = distribute(lv.total, shares)
        units = []
        for (number, unit_id), amount in sorted(parts.items()):
            base = (amount / lv.instalments).quantize(CENT, rounding="ROUND_DOWN")
            rates = [base] * lv.instalments
            rates[-1] = amount - base * (lv.instalments - 1)  # remainder on the last instalment
            units.append(
                {
                    "unit_id": unit_id,
                    "unit_number": number,
                    "amount": str(amount),
                    "instalments": [
                        {"due_month": _month(lv.first_due, i).isoformat(), "amount": str(r)}
                        for i, r in enumerate(rates)
                    ],
                }
            )
        snapshot = {"total": str(lv.total), "units": units, "purpose": lv.purpose}
        lv.snapshot, lv.snapshot_hash, lv.status = snapshot, calc.digest(snapshot), "calculated"
        await session.flush()
        return _out(lv)


@router.post("/special-levies/{levy_id}/resolve", summary="Beschluss zuordnen (W06, W09)")
async def resolve_levy(
    levy_id: uuid.UUID,
    body: LevyResolveIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        lv = await _levy(session, levy_id, lock=True)
        res = await session.get(Resolution, body.resolution_id)
        if lv.status != "calculated":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Erst berechnen.")
        if res is None or res.legal_entity_id != lv.legal_entity_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Beschluss fehlt.")
        if res.status not in BINDING:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beschluss ist nicht positiv gefasst.")
        if res.snapshot_hash != lv.snapshot_hash:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Beschluss bezieht sich auf einen anderen Stand."
            )
        lv.resolution_id, lv.status = res.id, "resolved"
        await session.flush()
        return _out(lv)


@router.post("/special-levies/{levy_id}/apply", summary="Raten als Vertragszahlungen übernehmen")
async def apply_levy(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """One payment row per instalment month (valid for that month only), so each receivable run
    charges an instalment once. Overlapping applied levies of the same community are refused,
    because receivables of type special_levy could not be told apart in the report (A-038)."""
    from mhvp.contracts.models import ContractPayment, PaymentReason

    async with tenant_tx(request, principal) as session:
        lv = await _levy(session, levy_id, lock=True)
        if lv.status == "applied":
            return _out(lv)
        if lv.status != "resolved":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Raten erst nach Beschluss (W06).")
        last = _month_end(_month(lv.first_due, lv.instalments - 1))
        others = (
            await session.scalars(
                select(SpecialLevy).where(
                    SpecialLevy.legal_entity_id == lv.legal_entity_id,
                    SpecialLevy.status == "applied",
                    SpecialLevy.id != lv.id,
                )
            )
        ).all()
        for o in others:
            o_last = _month_end(_month(o.first_due, o.instalments - 1))
            if o.first_due <= last and lv.first_due <= o_last:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Zeitraum überschneidet sich mit einer anderen Sonderumlage.",
                )
        created = 0
        for unit in (lv.snapshot or {}).get("units", []):
            contract = await calc.owner_at(session, uuid.UUID(unit["unit_id"]), lv.first_due)
            if contract is None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=f"Kein Eigentümer für Einheit {unit['unit_number']} zur Fälligkeit.",
                )
            for inst in unit["instalments"]:
                first = date.fromisoformat(inst["due_month"])
                amount = Decimal(inst["amount"])
                if amount <= 0:
                    continue
                session.add(
                    ContractPayment(
                        tenant_id=principal.tenant_id,
                        created_by=principal.user_id,
                        contract_id=contract.id,
                        payment_type_code=CODE,
                        net=amount,
                        gross=amount,
                        valid_from=first,
                        valid_to=_month_end(first),
                        reason=PaymentReason.OTHER,
                    )
                )
                created += 1
        lv.status, lv.applied_at = "applied", datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="special_levy.applied",
            entity_type="special_levy",
            entity_id=lv.id,
            actor_user_id=principal.user_id,
            payload={"payments": created},
        )
        await session.flush()
        return _out(lv) | {"payments_created": created}


@router.get("/special-levies/{levy_id}/report", summary="Zweckgebundener Bestand (W09)")
async def levy_report(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Resolved total, charged (posted receivables), received, open, used (postings on the use
    account) and remaining earmarked funds (received minus used), kept apart from HOA fees."""
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine

    async with tenant_tx(request, principal) as session:
        lv = await _levy(session, levy_id)
        start = lv.first_due
        end = _month_end(_month(lv.first_due, lv.instalments - 1))
        charged = received = ZERO
        per_unit = []
        for unit in (lv.snapshot or {}).get("units", []):
            due, paid = await calc.advances(session, uuid.UUID(unit["unit_id"]), CODE, start, end)
            charged += due
            received += paid
            per_unit.append(
                {
                    "unit_number": unit["unit_number"],
                    "resolved": unit["amount"],
                    "charged": str(due),
                    "received": str(paid),
                    "open": str(due - paid),
                }
            )
        used = ZERO
        if lv.account_id is not None:
            used = Decimal(
                await session.scalar(
                    select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .where(
                        JournalLine.account_id == lv.account_id,
                        JournalEntry.status == EntryStatus.POSTED,
                        JournalEntry.booking_date >= start,
                    )
                )
                or 0
            )
        return {
            "status": lv.status,
            "resolved": str(lv.total if lv.status in ("resolved", "applied") else ZERO),
            "charged": str(charged),
            "received": str(received),
            "open": str(charged - received),
            "used": str(used),
            "earmarked_remaining": str(received - used),
            "units": per_unit,
            "note": "Zweckgebunden, nicht frei verfügbares Hausgeld (W09).",
        }
