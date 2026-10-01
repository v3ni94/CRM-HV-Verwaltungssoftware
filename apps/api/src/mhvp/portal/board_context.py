"""Board portal: navigation from an audit position to its context (PÜ07, M25-04), read only.

``GET /portal/board/engagements/{id}/positions/{item_id}/context`` returns next to each other
the booking with its lines, the invoice (vendor, service period), the order and contract behind
it, the payment, the allocation key of the cost item and the previous year on the same account,
plus hints for missing documents. Everything comes from existing records of the positions
themselves; the board sees no IBAN and no record that is not linked to the position. The
previous year is a plain sum of posted lines on the account, information and no statement.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import AuditItem, HoaCostItem
from mhvp.portal.board import _board_user, _own_access, released_document_ids

router = APIRouter(prefix="/portal/board", tags=["Portal Beirat"])
NOTE = (
    "Verweise aus vorhandenen Datensätzen der Position. Der Vorjahreswert ist die Summe der "
    "gebuchten Zeilen des Kontos, keine Abrechnung."
)


def _shift_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:  # 29.02.
        return value.replace(year=value.year - 1, day=28)


async def _account_sum(session: Any, account_id: uuid.UUID, start: date, end: date) -> Decimal:
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine

    value = await session.scalar(
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.booking_date.between(start, end),
        )
    )
    return Decimal(value or 0)


@router.get(
    "/engagements/{engagement_id}/positions/{item_id}/context",
    summary="Kontext einer Prüfposition: Buchung, Auftrag, Zahlung, Schlüssel, Vorjahr (PÜ07)",
)
async def position_context(
    engagement_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    ctx: Any = Depends(_board_user),
) -> dict[str, Any]:
    from mhvp.accounting.models import Invoice, JournalEntry, JournalLine, LedgerAccount
    from mhvp.banking.models import PaymentOrder
    from mhvp.contacts.models import Contact
    from mhvp.contracts.service_contracts import ServiceContract
    from mhvp.properties.models import AllocationKey
    from mhvp.tickets.models import WorkOrder

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        item = await session.get(AuditItem, item_id)
        if item is None or item.engagement_id != eng.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        entry = (
            await session.get(JournalEntry, item.journal_entry_id)
            if item.journal_entry_id is not None
            else None
        )
        lines: list[dict[str, Any]] = []
        if entry is not None:
            rows = await session.execute(
                select(JournalLine, LedgerAccount.number, LedgerAccount.name)
                .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
                .where(JournalLine.journal_entry_id == entry.id)
                .order_by(LedgerAccount.number)
            )
            lines = [
                {
                    "account_id": line.account_id,
                    "account_number": number,
                    "account_name": name,
                    "debit": line.debit,
                    "credit": line.credit,
                }
                for line, number, name in rows.all()
            ]
        conditions = []
        if entry is not None:
            conditions.append(Invoice.journal_entry_id == entry.id)
        if item.document_id is not None:
            conditions.append(Invoice.document_id == item.document_id)
        if entry is not None and entry.document_id is not None:
            conditions.append(Invoice.document_id == entry.document_id)
        invoice = None
        if conditions:
            from sqlalchemy import or_

            invoice = await session.scalar(select(Invoice).where(or_(*conditions)).limit(1))
        invoice_out = order_out = contract_out = payment_out = None
        if invoice is not None:
            vendor = await session.get(Contact, invoice.provider_contact_id)
            invoice_out = {
                "number": invoice.number,
                "invoice_date": invoice.invoice_date,
                "service_from": invoice.service_from,
                "service_to": invoice.service_to,
                "gross": invoice.gross,
                "vendor_name": vendor.display_name if vendor else None,
                "order_reference": invoice.order_reference,
                "e_invoice_format": invoice.e_invoice_format,
            }
            order = await session.scalar(
                select(WorkOrder).where(WorkOrder.invoice_id == invoice.id)
            )
            if order is not None:
                order_out = {
                    "id": order.id,
                    "status": order.status.value,
                    "description": order.description,
                    "quote_amount": order.quote_amount,
                    "scheduled_at": order.scheduled_at,
                }
            if invoice.service_contract_id is not None:
                contract = await session.get(ServiceContract, invoice.service_contract_id)
                if contract is not None:
                    contract_out = {
                        "id": contract.id,
                        "title": contract.title,
                        "starts_at": contract.starts_at,
                        "ends_at": contract.ends_at,
                    }
            pay = await session.scalar(
                select(PaymentOrder)
                .where(PaymentOrder.invoice_id == invoice.id)
                .order_by(PaymentOrder.created_at.desc())
                .limit(1)
            )
            if pay is not None:
                payment_out = {
                    "status": pay.status.value,
                    "execution_date": pay.execution_date,
                    "amount": pay.amount,
                    "executed_amount": pay.executed_amount,
                }
        cost_item = None
        if eng.statement_id is not None and item.journal_entry_id is not None:
            cost_item = await session.scalar(
                select(HoaCostItem).where(
                    HoaCostItem.statement_id == eng.statement_id,
                    HoaCostItem.journal_entry_id == item.journal_entry_id,
                )
            )
        allocation_out = None
        if cost_item is not None:
            key = await session.get(AllocationKey, cost_item.allocation_key_id)
            allocation_out = {
                "label": cost_item.label,
                "amount": cost_item.amount,
                "basis": cost_item.basis,
                "key_code": key.code if key else None,
                "key_name": key.name if key else None,
            }
        previous_year = None
        account_id = cost_item.account_id if cost_item is not None else None
        if account_id is None and lines:
            account_id = next((x["account_id"] for x in lines if x["debit"] > 0), None)
        if account_id is not None:
            name = next(
                (
                    f"{x['account_number']} {x['account_name']}"
                    for x in lines
                    if x["account_id"] == account_id
                ),
                None,
            )
            current = await _account_sum(session, account_id, eng.period_from, eng.period_to)
            previous = await _account_sum(
                session, account_id, _shift_year(eng.period_from), _shift_year(eng.period_to)
            )
            previous_year = {
                "account": name,
                "current": current,
                "previous": previous,
                "difference": current - previous,
            }
        released = await released_document_ids(session, [item])
        missing: list[str] = []
        if item.document_id is None:
            missing.append("Kein Beleg an der Position verknüpft.")
        elif item.document_id not in released:
            missing.append("Der Beleg ist für das Gremium noch nicht freigegeben.")
        if entry is not None and invoice is None:
            missing.append("Zur Buchung liegt keine erfasste Rechnung vor.")
        if invoice is not None and payment_out is None:
            missing.append("Zur Rechnung liegt kein Zahlungsauftrag vor.")
        return {
            "item_id": item.id,
            "booking": None
            if entry is None
            else {
                "id": entry.id,
                "booking_date": entry.booking_date,
                "text": entry.text,
                "reference": entry.reference,
                "lines": lines,
            },
            "invoice": invoice_out,
            "order": order_out,
            "contract": contract_out,
            "payment": payment_out,
            "allocation": allocation_out,
            "previous_year": previous_year,
            "missing": missing,
            "note": NOTE,
        }
