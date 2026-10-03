"""Payment run endpoints (/api/v1/accounting/payment-runs, 7.5 Zahllauf, M15-02 to M15-07,
S15-02).

Rights as for payment orders: ``accounting:read`` to look, ``accounting:create`` for draft
orders, ``accounting:approve`` for bank agreements and bank status imports. Nothing here
approves an order, generates or hands out a file or posts: approvals stay four eyes on the
order, the file stays behind release gate G2.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_models import (
    BankStatusReport,
    PaymentRunPreview,
    PaymentRunSetting,
)
from mhvp.banking import bank_status, payment_run
from mhvp.banking.models import PaymentBankConfig
from mhvp.banking.payment_run_tasks import store_preview
from mhvp.banking.routers import OrderOut, _order_out
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.listparams import MAX_PAGE_SIZE, strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting/payment-runs", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
SETTINGS = require_permission("tenant_settings:update")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaymentRunOrderItemIn(_In):
    invoice_id: uuid.UUID
    property_bank_account_id: uuid.UUID


class PaymentRunOrdersIn(_In):
    execution_date: date
    items: list[PaymentRunOrderItemIn] = Field(min_length=1, max_length=500)


class PaymentRunOrdersOut(BaseModel):
    created: list[OrderOut]
    failed: list[dict[str, Any]]
    limit_warnings: list[str]


class PaymentRunPayoutIn(_In):
    open_item_id: uuid.UUID
    contact_bank_account_id: uuid.UUID
    property_bank_account_id: uuid.UUID
    execution_date: date
    reason: str = Field(pattern="^(" + "|".join(payment_run.PAYOUT_REASONS) + ")$")
    purpose: str | None = Field(default=None, min_length=1, max_length=140)


class PaymentRunBankLimitsIn(_In):
    single_order_limit: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    daily_limit: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    dd_lead_days_frst: int | None = Field(default=None, ge=0, le=60)
    dd_lead_days_rcur: int | None = Field(default=None, ge=0, le=60)
    pre_notification_days: int | None = Field(default=None, ge=0, le=60)


class PaymentRunStatusReportIn(_In):
    xml: str = Field(min_length=20, max_length=bank_status.MAX_BYTES)


class PaymentRunStatusReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    message_id: str | None
    original_message_id: str | None
    file_sha256: str
    result: list[dict[str, Any]]
    created: bool = False


class PaymentRunSettingIn(_In):
    weekly_preview_enabled: bool


class PaymentRunPreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    as_of: date
    trigger: str
    summary: dict[str, Any]


@router.get("/preview", summary="Zahllauf-Vorschau (zahlbare Rechnungen, fällige Lastschriften)")
async def preview(
    request: Request,
    as_of: date | None = None,
    horizon_days: int = Query(default=7, ge=0, le=90),
    ledger_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await payment_run.preview(
            session, as_of=as_of or local_today(), horizon_days=horizon_days, ledger_id=ledger_id
        )


@router.post("/orders", status_code=201, summary="Zahlungsaufträge sammeln (Entwürfe)")
async def create_orders(
    body: PaymentRunOrdersIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> PaymentRunOrdersOut:
    if len({i.invoice_id for i in body.items}) != len(body.items):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jede Rechnung nur einmal angeben.")
    async with tenant_tx(request, principal) as session:
        result = await payment_run.create_orders(
            session,
            items=[(i.invoice_id, i.property_bank_account_id) for i in body.items],
            execution_date=body.execution_date,
            user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_run.orders_created",
            entity_type="tenant",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            payload={"created": len(result["created"]), "failed": len(result["failed"])},
        )
        return PaymentRunOrdersOut(
            created=[await _order_out(session, o) for o in result["created"]],
            failed=result["failed"],
            limit_warnings=result["limit_warnings"],
        )


@router.post("/payout-orders", status_code=201, summary="Auszahlung ohne Rechnung (Entwurf)")
async def create_payout(
    body: PaymentRunPayoutIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> OrderOut:
    # AK14 (GAI-402, AJ28-02): a payout order is a payment instruction, behind G2 like the
    # payment batches; checked before any lookup.
    await ensure_release_gate_open(
        ReleaseGate.G2, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        order = await payment_run.order_for_payout(
            session,
            open_item_id=body.open_item_id,
            contact_bank_account_id=body.contact_bank_account_id,
            bank_account_id=body.property_bank_account_id,
            execution_date=body.execution_date,
            reason=body.reason,
            purpose=body.purpose,
            user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_order.payout_created",
            entity_type="payment_order",
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={"reason": body.reason, "amount": str(order.amount)},
        )
        return await _order_out(session, order)


def _limits_out(account_id: uuid.UUID, config: PaymentBankConfig | None) -> dict[str, Any]:
    return {
        "property_bank_account_id": str(account_id),
        **payment_run.limits_out(config),
        "lead_times": dd.lead_time_rules(config),
    }


@router.get("/bank-limits/{account_id}", summary="Banklimits und Fristen je Auftraggeberkonto")
async def get_limits(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        if await session.get(PropertyBankAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankkonto nicht gefunden.")
        return _limits_out(account_id, await payment_run.bank_config(session, account_id))


@router.put("/bank-limits/{account_id}", summary="Banklimits und Fristen setzen (Bankvereinbarung)")
async def put_limits(
    account_id: uuid.UUID,
    body: PaymentRunBankLimitsIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Operator input of what was agreed with the bank (M15-04, M15-06); no legal default."""
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        if await session.get(PropertyBankAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankkonto nicht gefunden.")
        config = await payment_run.bank_config(session, account_id)
        if config is None:
            config = PaymentBankConfig(
                tenant_id=principal.tenant_id,
                property_bank_account_id=account_id,
                pain001_version="pain.001.001.09",
                pain008_version="pain.008.001.02",
                submission_channel="file",
                created_by=principal.user_id,
            )
            session.add(config)
        for key, value in body.model_dump().items():
            setattr(config, key, value)
        config.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_bank_config.limits_changed",
            entity_type="property_bank_account",
            entity_id=account_id,
            actor_user_id=principal.user_id,
            payload={k: (str(v) if v is not None else None) for k, v in body.model_dump().items()},
        )
        return _limits_out(account_id, config)


@router.post(
    "/bank-status-reports",
    status_code=201,
    summary="Bankstatusbericht einlesen (pain.002, camt.054)",
)
async def import_status_report(
    body: PaymentRunStatusReportIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> PaymentRunStatusReportOut:
    async with tenant_tx(request, principal) as session:
        report, created = await bank_status.import_report(
            session, body.xml.encode(), tenant_id=principal.tenant_id, user_id=principal.user_id
        )
        out = PaymentRunStatusReportOut.model_validate(report)
        out.created = created
        return out


@router.get(
    "/bank-status-reports",
    summary="Eingelesene Bankstatusberichte",
    dependencies=[Depends(strict_query)],
)
async def list_status_reports(
    request: Request,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    principal: TenantPrincipal = Depends(READ),
) -> list[PaymentRunStatusReportOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(BankStatusReport)
                .order_by(BankStatusReport.created_at.desc(), BankStatusReport.id)
                .limit(limit)
            )
        ).all()
        return [PaymentRunStatusReportOut.model_validate(r) for r in rows]


@router.get("/settings", summary="Wöchentliche Zahllauf-Vorschau (Einstellung)")
async def get_setting(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        enabled = await session.scalar(select(PaymentRunSetting.weekly_preview_enabled))
        return {"weekly_preview_enabled": bool(enabled), "schedule": "Montag 08:00"}


class PaymentRunSettingOut(BaseModel):
    """Response of the weekly preview switch (GAI-304)."""

    model_config = ConfigDict(extra="allow")
    weekly_preview_enabled: bool
    schedule: str


@router.put(
    "/settings",
    summary="Wöchentliche Zahllauf-Vorschau ein- oder ausschalten",
    response_model=PaymentRunSettingOut,
)
async def put_setting(
    body: PaymentRunSettingIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(PaymentRunSetting))
        if row is None:
            row = PaymentRunSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        old_enabled = bool(row.weekly_preview_enabled)
        row.weekly_preview_enabled = body.weekly_preview_enabled
        row.updated_by = principal.user_id
        await session.flush()
        # GAI-307: payment configuration stays traceable (B07).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_run_setting.updated",
            entity_type="payment_run_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"weekly_preview_enabled": row.weekly_preview_enabled},
            changes=diff(
                {"weekly_preview_enabled": old_enabled},
                {"weekly_preview_enabled": row.weekly_preview_enabled},
            ),
        )
        return {"weekly_preview_enabled": row.weekly_preview_enabled, "schedule": "Montag 08:00"}


@router.post("/previews", status_code=201, summary="Zahllauf-Vorschau speichern")
async def create_preview(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> PaymentRunPreviewOut:
    async with tenant_tx(request, principal) as session:
        row = await store_preview(
            session, principal.tenant_id, trigger="manual", user_id=principal.user_id
        )
        return PaymentRunPreviewOut.model_validate(row)


@router.get(
    "/previews", summary="Gespeicherte Zahllauf-Vorschauen", dependencies=[Depends(strict_query)]
)
async def list_previews(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    as_of: date | None = Query(default=None, description="Stichtag der Vorschau (exakt)"),
    trigger: str | None = Query(
        default=None, pattern="^(manual|schedule|failed)$", description="Auslöser der Vorschau"
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[PaymentRunPreviewOut]:
    stmt = select(PaymentRunPreview)
    if as_of is not None:
        stmt = stmt.where(PaymentRunPreview.as_of == as_of)
    if trigger is not None:
        stmt = stmt.where(PaymentRunPreview.trigger == trigger)
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                stmt.order_by(PaymentRunPreview.created_at.desc(), PaymentRunPreview.id).limit(
                    limit
                )
            )
        ).all()
        return [PaymentRunPreviewOut.model_validate(r) for r in rows]
