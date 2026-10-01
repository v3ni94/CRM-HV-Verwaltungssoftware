"""Verwalterhonorar documents and batch issue (M13-05, M13-06).

* PDF invoice document on the tenant letterhead for an issued fee invoice or credit note
  (``POST /accounting/admin-fee-invoices/{id}/document``). It is built from the same frozen
  data and the same locks as the XRechnung (``xrechnung.load``), so PDF and XML never differ.
* The XML of a credit note is filed like the one of an invoice
  (``POST .../xrechnung-credit-note/document``).
* ``POST /accounting/admin-fees-run`` issues all due fee invoices of a period in one call. Without
  ``confirm`` it only previews. Each invoice gets its own gapless number inside its own
  savepoint, so a failing fee neither blocks the others nor burns a number. Nothing is sent or
  posted (G1, G2 stay closed).
"""

import html
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import admin_fees, numbering, receivables, xrechnung_credit
from mhvp.accounting import xrechnung as xr
from mhvp.accounting.dunning_letters import fmt_eur
from mhvp.accounting.models import AdminFeeInvoice, AdminFeeInvoiceStatus, AdminFeeSetting
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import DocumentSource, LinkRole
from mhvp.platform.models import TenantBillingSettings
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")

TABLE = "positionen"
CREDIT_LABEL = "Gutschrift"
INVOICE_LABEL = "Rechnung"


def _d(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _pct(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",") + " %"


def build_letter(
    data: xr.InvoiceData,
    invoice: AdminFeeInvoice,
    original: AdminFeeInvoice | None = None,
) -> letters.Letter:
    """Invoice letter from the frozen data. Credit notes keep their negative amounts and name
    the corrected invoice. Tax identifiers come from ``data`` (billing settings), not storage."""
    credit = invoice.kind == "credit_note"
    title = CREDIT_LABEL if credit else INVOICE_LABEL
    seller = data.seller
    info: list[tuple[str, str]] = [
        (f"{title}snummer" if not credit else "Gutschriftsnummer", data.number),
        ("Datum", _d(data.issue_date)),
    ]
    if invoice.period_start and invoice.period_end:
        info.append(
            ("Leistungszeitraum", f"{_d(invoice.period_start)} bis {_d(invoice.period_end)}")
        )
    if original is not None:
        info.append(("Bezug", f"Rechnung {original.number} vom {_d(original.invoice_date)}"))
    if seller.vat_id:
        info.append(("USt-IdNr.", seller.vat_id))
    elif seller.tax_number:
        info.append(("Steuernummer", seller.tax_number))
    info.append(("Leitweg-ID", data.buyer_reference))
    rows = [
        [ln.text, f"{ln.quantity.normalize():f}".replace(".", ","), fmt_eur(ln.amount)]
        for ln in data.lines
    ]
    rows.append(["Nettobetrag", "", fmt_eur(data.net)])
    rows.append([f"Umsatzsteuer {_pct(data.vat_percent)}", "", fmt_eur(data.vat)])
    rows.append(["Gesamtbetrag", "", fmt_eur(data.gross)])
    table = letters.LetterTable(
        header=["Leistung", "Menge", "Betrag"],
        rows=rows,
        right_aligned=(1, 2),
        total_row=True,
        widths=(0.6, 0.15, 0.25),
    )
    parts = [
        "für die Verwaltung stellen wir Ihnen folgende Leistungen in Rechnung:"
        if not credit
        else "wir schreiben Ihnen den nachfolgenden Betrag gut:",
        letters.TABLE_MARKER.format(name=TABLE),
    ]
    if data.tax_exemption_reason:
        parts.append(html.escape(data.tax_exemption_reason))
    if credit:
        parts.append(
            "Diese Gutschrift korrigiert die genannte Rechnung. Die Rechnung bleibt in unseren "
            "Unterlagen unverändert erhalten."
        )
    elif seller.payee_iban:
        parts.append(
            f"Bitte überweisen Sie {fmt_eur(data.gross)} auf das Konto "
            f"{html.escape(seller.payee_iban)}."
        )
    return letters.Letter(
        recipient_lines=[
            data.buyer.name,
            data.buyer.address.street,
            f"{data.buyer.address.postal_code} {data.buyer.address.city}",
        ],
        subject=html.escape(f"{title} {data.number}"),
        body="\n\n".join(parts),
        letter_date=data.issue_date,
        info=info,
        signatory=[seller.name],
        tables={TABLE: table},
    )


async def _invoice(
    session: AsyncSession, invoice_id: uuid.UUID, *, lock: bool = False
) -> AdminFeeInvoice:
    query = select(AdminFeeInvoice).where(AdminFeeInvoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status not in (
        AdminFeeInvoiceStatus.ISSUED,
        AdminFeeInvoiceStatus.RELEASED,
        AdminFeeInvoiceStatus.CANCELLED,
    ):
        raise ProblemError(ErrorCodes.XRECHNUNG_NOT_ISSUED)
    return row


def _links(row: AdminFeeInvoice) -> list[tuple[str, uuid.UUID, LinkRole]]:
    links: list[tuple[str, uuid.UUID, LinkRole]] = [
        ("property", row.property_id, LinkRole.GENERATED)
    ]
    if row.debtor_legal_entity_id is not None:
        links.append(("legal_entity", row.debtor_legal_entity_id, LinkRole.GENERATED))
    return links


@router.post(
    "/admin-fee-invoices/{invoice_id}/document",
    status_code=201,
    summary="Honorarrechnung oder Gutschrift als PDF auf dem Briefbogen ablegen",
)
async def store_pdf(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    """Renders the readable document once and files it (source generated); a second call returns
    the existing document. Nothing is sent. The same data locks as the XRechnung apply."""
    async with tenant_tx(request, principal) as session:
        row = await _invoice(session, invoice_id, lock=True)
        if row.pdf_document_id is not None:
            return {"document_id": row.pdf_document_id, "created": False}
        original = (
            await session.get(AdminFeeInvoice, row.corrects_invoice_id)
            if row.corrects_invoice_id
            else None
        )
        blobs = BlobStore(request.app.state.settings)
        head = await docs.letterhead(session, blobs)
        pdf = letters.render_pdf(head, build_letter(await xr.load(session, row), row, original))
        label = CREDIT_LABEL if row.kind == "credit_note" else INVOICE_LABEL
        document = await docs.store_document(
            session,
            blobs,
            tenant_id=principal.tenant_id,
            data=pdf,
            title=f"{label} {row.number}",
            filename=f"{row.number}.pdf",
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=_links(row),
            created_by=principal.user_id,
        )
        row.pdf_document_id = document.id
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.pdf_stored",
            entity_type="admin_fee_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"number": row.number, "document_id": str(document.id)},
        )
        await session.flush()
        return {"document_id": document.id, "created": True}


@router.post(
    "/admin-fee-invoices/{invoice_id}/xrechnung-credit-note/document",
    status_code=201,
    summary="Gutschrift-XRechnung als Dokument ablegen",
)
async def store_credit_note_xml(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row, xml = await xrechnung_credit._render(session, invoice_id)
        if row.xml_document_id is not None:
            return {"document_id": row.xml_document_id, "created": False}
        document = await docs.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=xml,
            title=f"XRechnung Gutschrift {row.number}",
            filename=f"{row.number}.xml",
            mime_type="application/xml",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=_links(row),
            created_by=principal.user_id,
        )
        row.xml_document_id = document.id
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.xrechnung_stored",
            entity_type="admin_fee_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"number": row.number, "document_id": str(document.id)},
        )
        await session.flush()
        return {"document_id": document.id, "created": True}


# Batch issue (M13-06) ---------------------------------------------------------------------


class FeeRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_date: date | None = Field(default=None, description="Tag im abzurechnenden Zeitraum")
    invoice_date: date | None = None
    property_id: uuid.UUID | None = None
    fee_setting_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    confirm: bool = Field(default=False, description="Ohne Bestätigung nur Vorschau")


class FeeRunRowOut(BaseModel):
    fee_setting_id: uuid.UUID
    property_id: uuid.UUID
    period_start: date
    period_end: date
    status: str  # preview, issued, already_issued, skipped, error
    invoice_id: uuid.UUID | None = None
    number: str | None = None
    gross: Decimal | None = None
    detail: str | None = None


class FeeRunOut(BaseModel):
    confirmed: bool
    period_date: date
    invoice_date: date
    issued: int
    rows: list[FeeRunRowOut]


@router.post("/admin-fees-run", summary="Fällige Honorare eines Zeitraums gesammelt ausstellen")
async def fee_run(
    body: FeeRunIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> FeeRunOut:
    day = body.period_date or local_today()
    issue_date = body.invoice_date or local_today()
    async with tenant_tx(request, principal) as session:
        query = select(AdminFeeSetting).order_by(AdminFeeSetting.start_date, AdminFeeSetting.id)
        if body.property_id is not None:
            query = query.where(AdminFeeSetting.property_id == body.property_id)
        if body.fee_setting_ids:
            query = query.where(AdminFeeSetting.id.in_(body.fee_setting_ids))
        billing = await session.scalar(
            select(TenantBillingSettings).where(
                TenantBillingSettings.tenant_id == principal.tenant_id
            )
        )
        if body.confirm:
            numbering.assert_xrechnung_allowed(billing)
        rows: list[FeeRunRowOut] = []
        issued = 0
        for fee in (await session.scalars(query)).all():
            start, end = admin_fees.period_for(fee.interval, day)
            if end < fee.start_date or (fee.end_date is not None and start > fee.end_date):
                continue
            base = {
                "fee_setting_id": fee.id,
                "property_id": fee.property_id,
                "period_start": start,
                "period_end": end,
            }
            existing = await admin_fees.issued_for_period(session, fee.id, start)
            if existing is not None:
                rows.append(
                    FeeRunRowOut(
                        **base,
                        status="already_issued",
                        invoice_id=existing.id,
                        number=existing.number,
                        gross=existing.gross,
                    )
                )
                continue
            counts = await receivables.fee_unit_counts(session, fee, min(end, issue_date))
            draft = await receivables.admin_fee_draft(session, fee, counts)
            gross = Decimal(str(draft["gross"]))
            if gross <= 0 or (
                not draft.get("debtor_legal_entity_id") and fee.invoice_debtor_party_id is None
            ):
                rows.append(
                    FeeRunRowOut(
                        **base,
                        status="skipped",
                        gross=gross,
                        detail="Kein Betrag oder kein Rechnungsempfänger ermittelbar.",
                    )
                )
                continue
            if not body.confirm:
                rows.append(FeeRunRowOut(**base, status="preview", gross=gross))
                continue
            try:
                async with session.begin_nested():
                    locked = await session.get(AdminFeeSetting, fee.id, with_for_update=True)
                    if locked is None:
                        continue
                    # Re-check under the row lock: a parallel run may have issued the period
                    # since the unlocked check above (B08).
                    if await admin_fees.issued_for_period(session, fee.id, start) is not None:
                        raise ProblemError(
                            ErrorCodes.CONFLICT,
                            detail="Für diesen Leistungszeitraum ist bereits eine Rechnung "
                            "ausgestellt.",
                        )
                    number = await numbering.allocate_invoice_number(
                        session, principal.tenant_id, issue_date.year
                    )
                    row = await xr.issue(
                        session,
                        fee=locked,
                        draft=draft,
                        number=number,
                        issue_date=issue_date,
                        billing=billing,
                        tenant_id=principal.tenant_id,
                        user_id=principal.user_id,
                        period=(start, end),
                    )
                    await emit(
                        session,
                        tenant_id=principal.tenant_id,
                        type="invoice.issued",
                        entity_type="admin_fee_invoice",
                        entity_id=row.id,
                        actor_user_id=principal.user_id,
                        payload={
                            "invoice_id": str(row.id),
                            "number": number,
                            "invoice_date": issue_date.isoformat(),
                            "kind": "admin_fee",
                            "fee_setting_id": str(fee.id),
                            "property_id": str(fee.property_id),
                            "net": str(row.net),
                            "vat": str(row.vat),
                            "gross": str(row.gross),
                            "currency": "EUR",
                        },
                    )
            except ProblemError as exc:
                rows.append(
                    FeeRunRowOut(
                        **base, status="error", gross=gross, detail=exc.detail or exc.error.code
                    )
                )
                continue
            issued += 1
            rows.append(
                FeeRunRowOut(
                    **base, status="issued", invoice_id=row.id, number=number, gross=row.gross
                )
            )
    return FeeRunOut(
        confirmed=body.confirm, period_date=day, invoice_date=issue_date, issued=issued, rows=rows
    )
