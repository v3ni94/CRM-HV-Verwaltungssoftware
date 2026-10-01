"""Verwalterhonorar: settings, service periods and issued invoices (18 M13, M13-03 to M13-06).

Settings can be listed, changed and ended; a setting with issued invoices is never deleted
(evidence), only ended by ``end_date``. Invoices carry a service period (calendar aligned
per interval, docs/ASSUMPTIONS.md) and exist once per setting and period while they are not
cancelled (status ``cancelled``). An issued invoice is never changed: a correction is a
credit note with its own gapless number that cancels the invoice (rule 0.1.7). Revenue
posting drafts: ``admin_fee_posting`` (M13-07, behind G1).
"""

import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import numbering, receivables
from mhvp.accounting.models import AdminFeeInvoice, AdminFeeInvoiceStatus, AdminFeeSetting
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")

KIND_INVOICE = "invoice"
KIND_CREDIT_NOTE = "credit_note"
PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12, "annual": 12}


def period_for(interval: str, day: date) -> tuple[date, date]:
    """Calendar aligned service period of ``interval`` containing ``day``."""
    months = PERIOD_MONTHS.get(interval)
    if months is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Abrechnungsintervall {interval} ist nicht bekannt."
        )
    first_month = (day.month - 1) // months * months + 1
    last_month = first_month + months - 1
    start = date(day.year, first_month, 1)
    end = date(day.year, last_month, calendar.monthrange(day.year, last_month)[1])
    return start, end


def effective_end(fee: AdminFeeSetting) -> date | None:
    """Last day of the fee: the earlier of ``end_date`` and ``termination_date`` (GA03-06)."""
    ends = [d for d in (fee.end_date, fee.termination_date) if d is not None]
    return min(ends) if ends else None


def fee_due_date(fee: AdminFeeSetting, period_start: date) -> date | None:
    """Due date of the fee invoice from ``due_day_rule`` in the month of the service period
    start (rules day, last_day, day_next_month); None without rule (the contract decides)."""
    if fee.due_day_rule is None:
        return None
    return receivables.due_date(fee.due_day_rule, fee.due_day or 1, period_start)


async def check_fee_refs(
    session: AsyncSession,
    property_id: uuid.UUID,
    manager_contact_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
) -> None:
    """Manager contact and revenue account must exist; the account belongs to a ledger of the
    property (RLS makes foreign tenants invisible)."""
    from mhvp.accounting.models import Ledger, LedgerAccount
    from mhvp.contacts.models import Contact

    if manager_contact_id is not None and await session.get(Contact, manager_contact_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Verwalterkontakt existiert nicht.")
    if account_id is not None:
        account = await session.get(LedgerAccount, account_id)
        ledger = await session.get(Ledger, account.ledger_id) if account else None
        if ledger is None or ledger.property_id not in (None, property_id):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Das Erlöskonto gehört nicht zum Objekt."
            )


def check_period(fee: AdminFeeSetting, start: date, end: date) -> None:
    last = effective_end(fee)
    if end < fee.start_date or (last is not None and start > last):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Leistungszeitraum liegt außerhalb der Laufzeit des Verwalterhonorars.",
        )


async def issued_for_period(
    session: AsyncSession, fee_id: uuid.UUID, start: date
) -> AdminFeeInvoice | None:
    row: AdminFeeInvoice | None = await session.scalar(
        select(AdminFeeInvoice).where(
            AdminFeeInvoice.fee_setting_id == fee_id,
            AdminFeeInvoice.period_start == start,
            AdminFeeInvoice.kind == KIND_INVOICE,
            AdminFeeInvoice.cancelled_at.is_(None),
        )
    )
    return row


# Schemas ---------------------------------------------------------------------------------


class AdminFeeSettingOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    start_date: date
    end_date: date | None
    interval: str
    vat_percent: Decimal
    min_amount: Decimal | None
    max_amount: Decimal | None
    amounts_per_unit_type: dict[str, str]
    invoice_debtor_party_id: uuid.UUID | None
    contract_document_id: uuid.UUID | None
    manager_contact_id: uuid.UUID | None = None
    termination_date: date | None = None
    due_day_rule: str | None = None
    due_day: int | None = None
    account_id: uuid.UUID | None = None
    sev_fee_amount: Decimal | None = None
    invoice_count: int = 0


class AdminFeeSettingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    end_date: date | None = None
    interval: str | None = Field(default=None, pattern="^(monthly|quarterly|semiannual|yearly)$")
    vat_percent: Decimal | None = Field(default=None, ge=0, le=100)
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    amounts_per_unit_type: dict[str, Decimal] | None = None
    contract_document_id: uuid.UUID | None = None
    manager_contact_id: uuid.UUID | None = None
    termination_date: date | None = None
    due_day_rule: str | None = Field(default=None, pattern="^(day|last_day|day_next_month)$")
    due_day: int | None = Field(default=None, ge=1, le=31)
    account_id: uuid.UUID | None = None
    sev_fee_amount: Decimal | None = Field(default=None, ge=0)


class AdminFeeInvoiceOut(BaseModel):
    id: uuid.UUID
    fee_setting_id: uuid.UUID
    property_id: uuid.UUID
    number: str
    kind: str
    invoice_date: date
    period_start: date | None
    period_end: date | None
    status: str
    net: Decimal
    vat_percent: Decimal
    vat: Decimal
    gross: Decimal
    currency: str
    lines: list[dict[str, Any]]
    debtor_legal_entity_id: uuid.UUID | None
    invoice_debtor_party_id: uuid.UUID | None
    corrects_invoice_id: uuid.UUID | None
    corrected_by_id: uuid.UUID | None = None
    xml_document_id: uuid.UUID | None
    pdf_document_id: uuid.UUID | None = None
    released_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    xrechnung_url: str | None
    payer_entry_id: uuid.UUID | None = None
    manager_entry_id: uuid.UUID | None = None


class AdminFeeCancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)
    credit_note_date: date | None = None


def _fee_out(row: AdminFeeSetting, count: int = 0) -> AdminFeeSettingOut:
    return AdminFeeSettingOut(
        id=row.id,
        property_id=row.property_id,
        start_date=row.start_date,
        end_date=row.end_date,
        interval=row.interval,
        vat_percent=row.vat_percent,
        min_amount=row.min_amount,
        max_amount=row.max_amount,
        amounts_per_unit_type=dict(row.amounts_per_unit_type or {}),
        invoice_debtor_party_id=row.invoice_debtor_party_id,
        contract_document_id=row.contract_document_id,
        manager_contact_id=row.manager_contact_id,
        termination_date=row.termination_date,
        due_day_rule=row.due_day_rule,
        due_day=row.due_day,
        account_id=row.account_id,
        sev_fee_amount=row.sev_fee_amount,
        invoice_count=count,
    )


def invoice_out(row: AdminFeeInvoice, corrected_by: uuid.UUID | None = None) -> AdminFeeInvoiceOut:
    return AdminFeeInvoiceOut(
        id=row.id,
        fee_setting_id=row.fee_setting_id,
        property_id=row.property_id,
        number=row.number,
        kind=row.kind,
        invoice_date=row.invoice_date,
        period_start=row.period_start,
        period_end=row.period_end,
        status=row.status.value,
        net=row.net,
        vat_percent=row.vat_percent,
        vat=row.vat,
        gross=row.gross,
        currency=row.currency,
        lines=list(row.lines or []),
        debtor_legal_entity_id=row.debtor_legal_entity_id,
        invoice_debtor_party_id=row.invoice_debtor_party_id,
        corrects_invoice_id=row.corrects_invoice_id,
        corrected_by_id=corrected_by,
        xml_document_id=row.xml_document_id,
        pdf_document_id=row.pdf_document_id,
        released_at=row.released_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
        payer_entry_id=row.payer_entry_id,
        manager_entry_id=row.manager_entry_id,
        xrechnung_url=(
            f"/api/v1/accounting/invoices/{row.id}/xrechnung.xml"
            if row.kind == KIND_INVOICE
            else None
        ),
    )


async def _count(session: AsyncSession, fee_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(AdminFeeInvoice)
            .where(AdminFeeInvoice.fee_setting_id == fee_id)
        )
        or 0
    )


async def _fee(session: AsyncSession, fee_id: uuid.UUID, *, lock: bool = False) -> AdminFeeSetting:
    row = await session.get(AdminFeeSetting, fee_id, with_for_update=lock)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _invoice(
    session: AsyncSession, invoice_id: uuid.UUID, *, lock: bool = False
) -> AdminFeeInvoice:
    row = await session.get(AdminFeeInvoice, invoice_id, with_for_update=lock)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


# Settings ----------------------------------------------------------------------------------


@router.get("/admin-fees", summary="Verwalterhonorare", responses=PAGE_HEADERS)
async def list_fees(
    request: Request,
    response: Response,
    property_id: uuid.UUID | None = None,
    active_on: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[AdminFeeSettingOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AdminFeeSetting)
        if property_id is not None:
            query = query.where(AdminFeeSetting.property_id == property_id)
        if active_on is not None:
            query = query.where(
                AdminFeeSetting.start_date <= active_on,
                (AdminFeeSetting.end_date.is_(None)) | (AdminFeeSetting.end_date >= active_on),
                (AdminFeeSetting.termination_date.is_(None))
                | (AdminFeeSetting.termination_date >= active_on),
            )
        query = query.order_by(AdminFeeSetting.start_date, AdminFeeSetting.created_at)
        rows = await paginate(
            session, query, response, page=page, page_size=page_size, limit=page_size
        )
        return [_fee_out(r, await _count(session, r.id)) for r in rows]


@router.get("/admin-fees/{fee_id}", summary="Verwalterhonorar")
async def get_fee(
    fee_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> AdminFeeSettingOut:
    async with tenant_tx(request, principal) as session:
        row = await _fee(session, fee_id)
        return _fee_out(row, await _count(session, row.id))


@router.patch("/admin-fees/{fee_id}", summary="Verwalterhonorar ändern oder beenden")
async def patch_fee(
    fee_id: uuid.UUID,
    body: AdminFeeSettingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AdminFeeSettingOut:
    """Changes apply to invoices issued afterwards; issued invoices keep their frozen amounts.
    ``end_date`` ends the fee; it may not end before an already invoiced period."""
    async with tenant_tx(request, principal) as session:
        row = await _fee(session, fee_id, lock=True)
        data = body.model_dump(exclude_unset=True)
        if "end_date" in data and data["end_date"] is not None:
            if data["end_date"] < row.start_date:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Das Ende liegt vor dem Beginn.")
            last = await session.scalar(
                select(func.max(AdminFeeInvoice.period_end)).where(
                    AdminFeeInvoice.fee_setting_id == row.id,
                    AdminFeeInvoice.kind == KIND_INVOICE,
                    AdminFeeInvoice.cancelled_at.is_(None),
                )
            )
            if last is not None and data["end_date"] < last:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Für einen späteren Zeitraum ist bereits eine Rechnung ausgestellt.",
                )
        if "amounts_per_unit_type" in data and data["amounts_per_unit_type"] is not None:
            data["amounts_per_unit_type"] = {
                k: str(v) for k, v in data["amounts_per_unit_type"].items()
            }
        if data.get("manager_contact_id") or data.get("account_id"):
            await check_fee_refs(
                session, row.property_id, data.get("manager_contact_id"), data.get("account_id")
            )
        for key in ("interval", "vat_percent", "amounts_per_unit_type"):
            if key in data and data[key] is None:
                del data[key]  # not nullable
        for key, value in data.items():
            setattr(row, key, value)
        if (
            row.min_amount is not None
            and row.max_amount is not None
            and row.min_amount > row.max_amount
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Mindesthonorar liegt über dem Höchsthonorar."
            )
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee.updated",
            entity_type="admin_fee_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(data)},
        )
        return _fee_out(row, await _count(session, row.id))


@router.delete("/admin-fees/{fee_id}", status_code=204, summary="Verwalterhonorar löschen")
async def delete_fee(
    fee_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    """Only without issued invoices; otherwise 409, the fee is ended by ``end_date``."""
    async with tenant_tx(request, principal) as session:
        row = await _fee(session, fee_id, lock=True)
        if await _count(session, row.id):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Es sind Rechnungen ausgestellt; das Honorar wird über das Ende beendet.",
            )
        await session.delete(row)
        await session.flush()
    return Response(status_code=204)


@router.get("/admin-fees-periods", summary="Honorarlauf: fällige Zeiträume (Vorschau)")
async def period_preview(
    request: Request,
    period_date: date | None = None,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Periodic fee run as preview (M13-06): for every fee active in the period containing
    ``period_date`` the draft amounts and whether the period is already invoiced. Nothing is
    written; each invoice is issued per fee with ``period_start`` (number allocation)."""
    day = period_date or local_today()
    async with tenant_tx(request, principal) as session:
        query = select(AdminFeeSetting).order_by(AdminFeeSetting.start_date)
        if property_id is not None:
            query = query.where(AdminFeeSetting.property_id == property_id)
        rows = []
        for fee in (await session.scalars(query)).all():
            start, end = period_for(fee.interval, day)
            last_day = effective_end(fee)
            if end < fee.start_date or (last_day is not None and start > last_day):
                continue
            existing = await issued_for_period(session, fee.id, start)
            counts = await receivables.fee_unit_counts(session, fee, min(end, day))
            draft = await receivables.admin_fee_draft(session, fee, counts)
            rows.append(
                {
                    "fee_setting_id": fee.id,
                    "property_id": fee.property_id,
                    "interval": fee.interval,
                    "period_start": start,
                    "period_end": end,
                    "status": "issued" if existing else "due",
                    "invoice_id": existing.id if existing else None,
                    "number": existing.number if existing else None,
                    "draft": draft,
                }
            )
        return {"period_date": day, "rows": rows}


# Invoices ----------------------------------------------------------------------------------


@router.get("/admin-fee-invoices", summary="Honorarrechnungen", responses=PAGE_HEADERS)
async def list_invoices(
    request: Request,
    response: Response,
    fee_setting_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    year: int | None = Query(default=None, ge=2000, le=2100),
    status: AdminFeeInvoiceStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[AdminFeeInvoiceOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AdminFeeInvoice)
        if fee_setting_id is not None:
            query = query.where(AdminFeeInvoice.fee_setting_id == fee_setting_id)
        if property_id is not None:
            query = query.where(AdminFeeInvoice.property_id == property_id)
        if status is not None:
            query = query.where(AdminFeeInvoice.status == status)
        if year is not None:
            query = query.where(
                AdminFeeInvoice.invoice_date >= date(year, 1, 1),
                AdminFeeInvoice.invoice_date <= date(year, 12, 31),
            )
        query = query.order_by(AdminFeeInvoice.invoice_date.desc(), AdminFeeInvoice.number.desc())
        rows = await paginate(
            session, query, response, page=page, page_size=page_size, limit=page_size
        )
        return [invoice_out(r) for r in rows]


@router.get("/admin-fee-invoices/{invoice_id}", summary="Honorarrechnung")
async def get_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> AdminFeeInvoiceOut:
    async with tenant_tx(request, principal) as session:
        row = await _invoice(session, invoice_id)
        credit = await session.scalar(
            select(AdminFeeInvoice.id).where(AdminFeeInvoice.corrects_invoice_id == row.id)
        )
        return invoice_out(row, credit)


@router.post("/admin-fee-invoices/{invoice_id}/release", summary="Honorarrechnung freigeben")
async def release_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> AdminFeeInvoiceOut:
    """Issued to released (for sending by the operator; nothing is sent here). Idempotent."""
    async with tenant_tx(request, principal) as session:
        row = await _invoice(session, invoice_id, lock=True)
        if row.cancelled_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Rechnung ist storniert.")
        if row.status is not AdminFeeInvoiceStatus.RELEASED:
            row.status = AdminFeeInvoiceStatus.RELEASED
            row.released_at, row.released_by = datetime.now(UTC), principal.user_id
            row.updated_by = principal.user_id
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="admin_fee_invoice.released",
                entity_type="admin_fee_invoice",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"number": row.number},
            )
        return invoice_out(row)


def _negated_lines(lines: list[dict[str, Any]], number: str) -> list[dict[str, Any]]:
    out = []
    for line in lines:
        item = dict(line)
        item["amount"] = str(-Decimal(str(line["amount"])))
        item["text"] = f"Gutschrift zu Rechnung {number}: {line.get('text', '')}".strip()
        out.append(item)
    return out


@router.post(
    "/admin-fee-invoices/{invoice_id}/cancel",
    status_code=201,
    summary="Honorarrechnung stornieren (Gutschrift mit eigener Nummer)",
)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    body: AdminFeeCancelIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AdminFeeInvoiceOut:
    """The invoice stays unchanged apart from the cancellation mark; the credit note mirrors its
    amounts negatively under the next gapless number. The period can then be invoiced again."""
    async with tenant_tx(request, principal) as session:
        row = await _invoice(session, invoice_id, lock=True)
        if row.kind != KIND_INVOICE:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Eine Gutschrift wird nicht erneut storniert."
            )
        if row.cancelled_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Rechnung ist bereits storniert.")
        credit_date = body.credit_note_date or local_today()
        if credit_date < row.invoice_date:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Gutschrift liegt vor dem Rechnungsdatum."
            )
        number = await numbering.allocate_invoice_number(
            session, principal.tenant_id, credit_date.year
        )
        credit = AdminFeeInvoice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            fee_setting_id=row.fee_setting_id,
            property_id=row.property_id,
            number=number,
            invoice_date=credit_date,
            status=AdminFeeInvoiceStatus.ISSUED,
            currency=row.currency,
            net=-row.net,
            vat_percent=row.vat_percent,
            vat=-row.vat,
            gross=-row.gross,
            lines=_negated_lines(list(row.lines or []), row.number),
            debtor_legal_entity_id=row.debtor_legal_entity_id,
            invoice_debtor_party_id=row.invoice_debtor_party_id,
            buyer_reference=row.buyer_reference,
            period_start=row.period_start,
            period_end=row.period_end,
            kind=KIND_CREDIT_NOTE,
            corrects_invoice_id=row.id,
            cancel_reason=body.reason,
        )
        session.add(credit)
        row.cancelled_at, row.cancelled_by = datetime.now(UTC), principal.user_id
        row.cancel_reason = body.reason
        row.status = AdminFeeInvoiceStatus.CANCELLED
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.cancelled",
            entity_type="admin_fee_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"number": row.number, "credit_note_id": str(credit.id), "credit_note": number},
        )
        return invoice_out(credit)
