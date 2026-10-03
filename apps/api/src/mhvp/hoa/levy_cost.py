"""AP21: sub community per WEG cost position (GAM-109) and special levy payment status and
refund proposals (GAM-110).

* GAM-109: ``hoa_cost_item.sub_community_id`` assigns a cost position to a sub community of
  the same property. A position with a sub community but without a structured basis
  (``basis_resolution_id`` or ``basis_document_id``) carries the hint
  ``sub_community_basis_missing``. With the tenant switch ``sub_community_basis_lock`` the
  internal approval of the statement is refused (MHVP-HOA-0046); default off is the behaviour
  before AP21 (hint only). Which bases are admissible is open (AP21-01, G4).
* GAM-110: payment status per unit and instalment (charged, received, open from the posted
  receivable items) and the postings on the use account. A refund is a proposal with
  resolution and reason, only with the tenant switch ``levy_refund_proposals`` (default off,
  MHVP-HOA-0047). Nothing is paid or posted here; a payout through a payment run stays locked
  (G2, G4, open question AP21-02).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.money import round_cents
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa import calc
from mhvp.hoa.models import (
    HoaCostItem,
    HoaLevyCostSetting,
    HoaSpecialLevyRefund,
    Resolution,
    SpecialLevy,
)
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")
BINDING = {"positive", "final", "legally_binding"}
CODE = "special_levy"
ZERO = Decimal("0.00")
USAGE_LIMIT = 200
PAYOUT_NOTE = (
    "Vorschlag, keine Auszahlung und keine Buchung. Die Auszahlung über einen Zahllauf ist "
    "gesperrt, bis das Erstattungsverfahren entschieden ist (AP21-02, Gate G2 und G4)."
)
SETTING_NOTE = (
    "Standard aus: Hinweis ohne Sperre, keine Erstattungsvorschläge (heutiges Verhalten). "
    "Zulässige Grundlagen (AP21-01) und Erstattungsverfahren (AP21-02) sind offen."
)


# Settings ---------------------------------------------------------------------------------


class HoaLevyCostSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub_community_basis_lock: bool
    levy_refund_proposals: bool


class HoaLevyCostSettingOut(BaseModel):
    sub_community_basis_lock: bool
    levy_refund_proposals: bool
    note: str


async def _settings(session: AsyncSession) -> tuple[bool, bool]:
    row = await session.scalar(select(HoaLevyCostSetting))
    if row is None:
        return False, False
    return row.sub_community_basis_lock, row.levy_refund_proposals


@router.get(
    "/levy-cost-settings",
    response_model=HoaLevyCostSettingOut,
    summary="Untergemeinschaft und Sonderumlage (Schalter)",
)
async def get_levy_cost_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> HoaLevyCostSettingOut:
    async with tenant_tx(request, principal) as session:
        lock, refunds = await _settings(session)
        return HoaLevyCostSettingOut(
            sub_community_basis_lock=lock, levy_refund_proposals=refunds, note=SETTING_NOTE
        )


@router.put(
    "/levy-cost-settings",
    response_model=HoaLevyCostSettingOut,
    summary="Untergemeinschaft und Sonderumlage (Schalter setzen)",
)
async def put_levy_cost_settings(
    body: HoaLevyCostSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> HoaLevyCostSettingOut:
    from mhvp.accounting.audit_events import record_change

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaLevyCostSetting).with_for_update())
        before = (
            {}
            if row is None
            else {
                "sub_community_basis_lock": row.sub_community_basis_lock,
                "levy_refund_proposals": row.levy_refund_proposals,
            }
        )
        if row is None:
            row = HoaLevyCostSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        row.sub_community_basis_lock = body.sub_community_basis_lock
        row.levy_refund_proposals = body.levy_refund_proposals
        row.updated_by = principal.user_id
        await session.flush()
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="hoa_levy_cost_setting.updated",
            entity_type="hoa_levy_cost_setting",
            entity_id=row.id,
            before=before,
            after=body.model_dump(),
        )
        return HoaLevyCostSettingOut(**body.model_dump(), note=SETTING_NOTE)


# GAM-109 ----------------------------------------------------------------------------------


async def check_sub_community(
    session: AsyncSession, ledger_id: uuid.UUID, sub_community_id: uuid.UUID
) -> None:
    """The sub community must belong to the property of the WEG ledger (else 422)."""
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import SubCommunity

    ledger = await session.get(Ledger, ledger_id)
    sub = await session.get(SubCommunity, sub_community_id)
    if sub is None or ledger is None or sub.property_id != ledger.property_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Untergemeinschaft gehört nicht zu diesem Objekt."
        )


async def sub_community_problems(
    session: AsyncSession, statement_id: uuid.UUID
) -> list[HoaCostItem]:
    """Positions with a sub community and neither basis resolution nor basis document."""
    return list(
        (
            await session.scalars(
                select(HoaCostItem)
                .where(
                    HoaCostItem.statement_id == statement_id,
                    HoaCostItem.sub_community_id.is_not(None),
                    HoaCostItem.basis_resolution_id.is_(None),
                    HoaCostItem.basis_document_id.is_(None),
                )
                .order_by(HoaCostItem.label)
            )
        ).all()
    )


async def ensure_sub_community_basis(session: AsyncSession, statement_id: uuid.UUID) -> None:
    """Internal approval: with the switch on, positions without basis lock (MHVP-HOA-0046)."""
    lock, _ = await _settings(session)
    if not lock:
        return
    missing = await sub_community_problems(session, statement_id)
    if missing:
        raise ProblemError(
            ErrorCodes.HOA_SUB_COMMUNITY_BASIS_MISSING,
            detail="Ohne Beschluss oder Dokument als Grundlage: "
            + ", ".join(i.label for i in missing[:10]),
        )


class HoaSubCommunityIssueOut(BaseModel):
    cost_item_id: uuid.UUID
    label: str
    amount: Decimal
    sub_community_id: uuid.UUID


class HoaSubCommunityCheckOut(BaseModel):
    lock_active: bool
    blocks_internal_approval: bool
    issues: list[HoaSubCommunityIssueOut]
    note: str


@router.get(
    "/statements/{statement_id}/sub-community-check",
    response_model=HoaSubCommunityCheckOut,
    summary="Prüfhinweis Untergemeinschaft ohne Grundlage",
    dependencies=[Depends(strict_query)],
)
async def sub_community_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> HoaSubCommunityCheckOut:
    from mhvp.hoa.models import HoaStatement

    async with tenant_tx(request, principal) as session:
        if await session.get(HoaStatement, statement_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        lock, _ = await _settings(session)
        items = await sub_community_problems(session, statement_id)
        return HoaSubCommunityCheckOut(
            lock_active=lock,
            blocks_internal_approval=lock and bool(items),
            issues=[
                HoaSubCommunityIssueOut(
                    cost_item_id=i.id,
                    label=i.label,
                    amount=i.amount,
                    sub_community_id=i.sub_community_id,
                )
                for i in items
            ],
            note="Kostenposition einer Untergemeinschaft braucht einen Beschluss oder ein "
            "Dokument als Grundlage. Zulässige Grundlagen sind offen (AP21-01, G4).",
        )


# GAM-110 payment status -------------------------------------------------------------------


class HoaLevyInstalmentStatusOut(BaseModel):
    due_month: date
    charged: Decimal
    received: Decimal
    open: Decimal


class HoaLevyUnitStatusOut(BaseModel):
    unit_id: uuid.UUID
    unit_number: str
    charged: Decimal
    received: Decimal
    open: Decimal
    refunds_proposed: Decimal
    instalments: list[HoaLevyInstalmentStatusOut]


class HoaLevyUsageOut(BaseModel):
    journal_entry_id: uuid.UUID
    booking_date: date
    text: str
    amount: Decimal


class HoaLevyPaymentStatusOut(BaseModel):
    levy_id: uuid.UUID
    status: str
    units: list[HoaLevyUnitStatusOut]
    usage: list[HoaLevyUsageOut]
    usage_truncated: bool
    note: str


def _months(lv: SpecialLevy) -> list[date]:
    from mhvp.hoa.levies import _month

    return [_month(lv.first_due, i) for i in range(lv.instalments)]


async def _proposed(session: AsyncSession, levy_id: uuid.UUID) -> dict[str | None, Decimal]:
    out: dict[str | None, Decimal] = {}
    rows = await session.scalars(
        select(HoaSpecialLevyRefund).where(
            HoaSpecialLevyRefund.levy_id == levy_id, HoaSpecialLevyRefund.status == "proposed"
        )
    )
    for r in rows.all():
        key = str(r.unit_id) if r.unit_id else None
        out[key] = out.get(key, ZERO) + r.amount
    return out


async def _unit_status(session: AsyncSession, lv: SpecialLevy) -> list[HoaLevyUnitStatusOut]:
    from mhvp.hoa.levies import _chain_months, _month_end

    months = sorted(await _chain_months(session, lv)) if lv.snapshot else _months(lv)
    proposed = await _proposed(session, lv.id)
    units = []
    for unit in (lv.snapshot or {}).get("units", []):
        rows = []
        for first in months:
            due, paid = await calc.advances(
                session, uuid.UUID(unit["unit_id"]), CODE, first, _month_end(first)
            )
            due, paid = round_cents(due), round_cents(paid)
            rows.append(
                HoaLevyInstalmentStatusOut(
                    due_month=first, charged=due, received=paid, open=due - paid
                )
            )
        charged = sum((r.charged for r in rows), ZERO)
        received = sum((r.received for r in rows), ZERO)
        units.append(
            HoaLevyUnitStatusOut(
                unit_id=uuid.UUID(unit["unit_id"]),
                unit_number=str(unit["unit_number"]),
                charged=charged,
                received=received,
                open=charged - received,
                refunds_proposed=proposed.get(unit["unit_id"], ZERO),
                instalments=rows,
            )
        )
    return units


@router.get(
    "/special-levies/{levy_id}/payment-status",
    response_model=HoaLevyPaymentStatusOut,
    summary="Ist und Rückstand je Rate, Verwendung (GAM-110)",
    dependencies=[Depends(strict_query)],
)
async def levy_payment_status(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> HoaLevyPaymentStatusOut:
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine

    async with tenant_tx(request, principal) as session:
        lv = await session.get(SpecialLevy, levy_id)
        if lv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        units = await _unit_status(session, lv)
        usage: list[HoaLevyUsageOut] = []
        truncated = False
        if lv.account_id is not None:
            rows = (
                await session.execute(
                    select(
                        JournalEntry.id,
                        JournalEntry.booking_date,
                        JournalEntry.text,
                        JournalLine.debit - JournalLine.credit,
                    )
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .where(
                        JournalLine.account_id == lv.account_id,
                        JournalEntry.ledger_id == lv.ledger_id,
                        JournalEntry.status == EntryStatus.POSTED,
                        JournalEntry.booking_date >= lv.first_due,
                    )
                    .order_by(JournalEntry.booking_date, JournalEntry.id)
                    .limit(USAGE_LIMIT + 1)
                )
            ).all()
            truncated = len(rows) > USAGE_LIMIT
            usage = [
                HoaLevyUsageOut(
                    journal_entry_id=r[0], booking_date=r[1], text=r[2], amount=round_cents(r[3])
                )
                for r in rows[:USAGE_LIMIT]
            ]
        return HoaLevyPaymentStatusOut(
            levy_id=lv.id,
            status=lv.status,
            units=units,
            usage=usage,
            usage_truncated=truncated,
            note="Ist und Rückstand aus den gebuchten Forderungen je Rate; Verwendung aus den "
            "Buchungen auf dem Verwendungskonto ab der ersten Fälligkeit (W09).",
        )


# GAM-110 refund proposals -----------------------------------------------------------------


class HoaLevyRefundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0, decimal_places=2, max_digits=14)
    reason: str = Field(min_length=3, max_length=4000)
    resolution_id: uuid.UUID


class HoaLevyRefundWithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=4000)


class HoaLevyRefundOut(BaseModel):
    id: uuid.UUID
    levy_id: uuid.UUID
    unit_id: uuid.UUID | None
    amount: Decimal
    reason: str
    resolution_id: uuid.UUID
    status: str
    withdrawn_reason: str | None
    payout_locked: bool
    note: str


def _refund_out(r: HoaSpecialLevyRefund) -> HoaLevyRefundOut:
    return HoaLevyRefundOut(
        id=r.id,
        levy_id=r.levy_id,
        unit_id=r.unit_id,
        amount=r.amount,
        reason=r.reason,
        resolution_id=r.resolution_id,
        status=r.status,
        withdrawn_reason=r.withdrawn_reason,
        payout_locked=True,
        note=PAYOUT_NOTE,
    )


@router.get(
    "/special-levies/{levy_id}/refunds",
    response_model=list[HoaLevyRefundOut],
    summary="Erstattungsvorschläge einer Sonderumlage",
    dependencies=[Depends(strict_query)],
)
async def list_levy_refunds(
    levy_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[HoaLevyRefundOut]:
    async with tenant_tx(request, principal) as session:
        if await session.get(SpecialLevy, levy_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(HoaSpecialLevyRefund)
            .where(HoaSpecialLevyRefund.levy_id == levy_id)
            .order_by(HoaSpecialLevyRefund.created_at, HoaSpecialLevyRefund.id)
        )
        return [_refund_out(r) for r in rows.all()]


@router.post(
    "/special-levies/{levy_id}/refunds",
    status_code=201,
    response_model=HoaLevyRefundOut,
    summary="Erstattung als Vorschlag erfassen (keine Auszahlung, G2/G4)",
)
async def propose_levy_refund(
    levy_id: uuid.UUID,
    body: HoaLevyRefundIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> HoaLevyRefundOut:
    from mhvp.accounting.audit_events import record_change

    async with tenant_tx(request, principal) as session:
        lv = await session.get(SpecialLevy, levy_id, with_for_update=True)
        if lv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        _, enabled = await _settings(session)
        if not enabled:
            raise ProblemError(ErrorCodes.HOA_LEVY_REFUND_DISABLED)
        if lv.status != "applied":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Erstattung nur zu einer übernommenen Sonderumlage."
            )
        res = await session.get(Resolution, body.resolution_id)
        if res is None or res.legal_entity_id != lv.legal_entity_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Beschluss fehlt.")
        if res.status not in BINDING:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beschluss ist nicht positiv gefasst.")
        units = await _unit_status(session, lv)
        if body.unit_id is not None:
            match = [u for u in units if u.unit_id == body.unit_id]
            if not match:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Einheit ist nicht an der Sonderumlage beteiligt."
                )
            available = match[0].received - match[0].refunds_proposed
        else:
            proposed = await _proposed(session, lv.id)
            available = sum((u.received for u in units), ZERO) - sum(proposed.values(), ZERO)
        if body.amount > available:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Erstattung über dem eingegangenen, nicht vorgeschlagenen Betrag "
                f"({available} EUR).",
            )
        row = HoaSpecialLevyRefund(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            levy_id=lv.id,
            unit_id=body.unit_id,
            amount=body.amount,
            reason=body.reason,
            resolution_id=res.id,
        )
        session.add(row)
        await session.flush()
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="special_levy_refund.proposed",
            entity_type="hoa_special_levy_refund",
            entity_id=row.id,
            before={},
            after={
                "levy_id": str(lv.id),
                "unit_id": str(body.unit_id) if body.unit_id else None,
                "amount": str(body.amount),
                "resolution_id": str(res.id),
                "status": "proposed",
            },
        )
        return _refund_out(row)


@router.post(
    "/special-levies/{levy_id}/refunds/{refund_id}/withdraw",
    response_model=HoaLevyRefundOut,
    summary="Erstattungsvorschlag zurückziehen",
)
async def withdraw_levy_refund(
    levy_id: uuid.UUID,
    refund_id: uuid.UUID,
    body: HoaLevyRefundWithdrawIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> HoaLevyRefundOut:
    from mhvp.accounting.audit_events import record_change

    async with tenant_tx(request, principal) as session:
        row = await session.get(HoaSpecialLevyRefund, refund_id, with_for_update=True)
        if row is None or row.levy_id != levy_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "proposed":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Vorschlag ist bereits zurückgezogen.")
        row.status, row.withdrawn_reason = "withdrawn", body.reason
        row.updated_by = principal.user_id
        await session.flush()
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="special_levy_refund.withdrawn",
            entity_type="hoa_special_levy_refund",
            entity_id=row.id,
            before={"status": "proposed"},
            after={"status": "withdrawn", "reason": body.reason},
        )
        return _refund_out(row)
