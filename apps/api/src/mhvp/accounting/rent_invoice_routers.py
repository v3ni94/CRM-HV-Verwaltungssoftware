"""Rent invoice endpoints (Mietrechnung, Dauermietrechnung with VAT; rule M13-04 section
"Mietrechnung", M13-03 follow up, V21).

- ``POST /contracts/{id}/rent-invoices``: freeze the receivable items of a period into an
  invoice with a gapless number per legal entity, render the PDF on the tenant letterhead and
  file it as a document (contract and contact linked). Draft watermark while G1 is closed.
- ``GET /contracts/{id}/rent-invoices``: list; ``GET .../{invoice_id}/pdf``: the PDF.
- ``POST .../{invoice_id}/credit-note``: cancel by credit note (no deletion, rule 0.1.7).
- ``GET /accounting/rent-invoices/fields``: the mandatory field list (documentation).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.accounting import rent_invoice as ri
from mhvp.accounting.rent_invoice_models import RentInvoice, RentInvoiceKind, RentInvoiceStatus
from mhvp.contracts.models import Contract
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate
from mhvp.documents import letters
from mhvp.documents import services as docs
from mhvp.documents.blobs import BlobStore
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Verträge"])
READ = require_permission("contracts:read")
UPDATE = require_permission("contracts:update")


class RentInvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_start: date
    period_end: date
    # Dauermietrechnung: several periods (usually a year) on one invoice, one line each.
    standing: bool = False
    invoice_date: date | None = None


class RentInvoiceLineOut(BaseModel):
    receivable_item_id: uuid.UUID
    payment_type_code: str
    period_start: date
    period_end: date
    net: Decimal
    vat_percent: Decimal
    vat: Decimal
    gross: Decimal


class RentInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    contract_id: uuid.UUID
    legal_entity_id: uuid.UUID
    contact_id: uuid.UUID | None
    kind: RentInvoiceKind
    status: RentInvoiceStatus
    number: str
    invoice_date: date
    period_start: date
    period_end: date
    net_total: Decimal
    vat_total: Decimal
    gross_total: Decimal
    lines: list[RentInvoiceLineOut]
    tax_identifier_kind: str
    draft: bool
    cancels_invoice_id: uuid.UUID | None
    cancelled_by_invoice_id: uuid.UUID | None
    document_id: uuid.UUID | None
    hinweis: str = Field(default="")


class MandatoryFieldOut(BaseModel):
    field: str
    description: str


def _out(row: RentInvoice) -> RentInvoiceOut:
    out = RentInvoiceOut.model_validate(row)
    out.hinweis = ri.DRAFT_LABEL if row.draft else "Ausgestellt, kein Versand durch die Plattform"
    return out


async def _contract(session: Any, contract_id: uuid.UUID) -> Contract:
    contract: Contract | None = await session.get(Contract, contract_id)
    if contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return contract


async def _invoice(session: Any, contract_id: uuid.UUID, invoice_id: uuid.UUID) -> RentInvoice:
    row: RentInvoice | None = await session.get(RentInvoice, invoice_id)
    if row is None or row.contract_id != contract_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _g1_open(request: Request, tenant_id: uuid.UUID) -> bool:
    """True only when the resolver says so; any error counts as closed (draft)."""
    try:
        result = await request.app.state.release_gate_resolver.is_open(tenant_id, ReleaseGate.G1)
    except Exception:
        return False
    return result is True


async def _render_and_store(
    request: Request, session: Any, principal: TenantPrincipal, row: RentInvoice, contract: Contract
) -> None:
    blobs = BlobStore(request.app.state.settings)
    head = await docs.letterhead(session, blobs)
    letter = await ri.build_letter(session, invoice=row, contract=contract, head=head)
    pdf = letters.render_pdf(head, letter)
    await ri.store(
        session,
        blobs,
        invoice=row,
        contract=contract,
        pdf=pdf,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
    )


@router.get(
    "/accounting/rent-invoices/fields",
    summary="Pflichtangaben einer Mietrechnung (Feldliste, zu prüfen durch Steuerberater)",
)
async def mandatory_fields(principal: TenantPrincipal = Depends(READ)) -> list[MandatoryFieldOut]:
    return [MandatoryFieldOut(field=f, description=d) for f, d in ri.MANDATORY_FIELDS]


@router.get("/contracts/{contract_id}/rent-invoices", summary="Mietrechnungen des Vertrags")
async def list_rent_invoices(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[RentInvoiceOut]:
    async with tenant_tx(request, principal) as session:
        await _contract(session, contract_id)
        rows = (
            await session.execute(
                select(RentInvoice)
                .where(RentInvoice.contract_id == contract_id)
                .order_by(RentInvoice.invoice_date.desc(), RentInvoice.number.desc())
            )
        ).scalars()
        return [_out(r) for r in rows]


@router.post(
    "/contracts/{contract_id}/rent-invoices",
    status_code=201,
    summary="Mietrechnung oder Dauermietrechnung mit Umsatzsteuerausweis erzeugen (PDF, Ablage)",
)
async def create_rent_invoice(
    contract_id: uuid.UUID,
    body: RentInvoiceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> RentInvoiceOut:
    """Uses the receivable items of the period (net, tax rate, tax, gross) as they are; nothing
    is posted or sent. Locked without VAT option, VAT split or tax identifier."""
    async with tenant_tx(request, principal) as session:
        contract = await _contract(session, contract_id)
        draft = not await _g1_open(request, principal.tenant_id)
        row = await ri.issue(
            session,
            contract=contract,
            period_start=body.period_start,
            period_end=body.period_end,
            standing=body.standing,
            invoice_date=body.invoice_date or local_today(),
            draft=draft,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        await _render_and_store(request, session, principal, row, contract)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rent_invoice.issued",
            entity_type="rent_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"number": row.number, "contract_id": str(contract.id), "draft": draft},
        )
        return _out(row)


@router.post(
    "/contracts/{contract_id}/rent-invoices/{invoice_id}/credit-note",
    status_code=201,
    summary="Mietrechnung durch Gutschrift stornieren (keine Löschung)",
)
async def create_credit_note(
    contract_id: uuid.UUID,
    invoice_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> RentInvoiceOut:
    async with tenant_tx(request, principal) as session:
        contract = await _contract(session, contract_id)
        original = await _invoice(session, contract_id, invoice_id)
        draft = not await _g1_open(request, principal.tenant_id)
        row = await ri.credit_note(
            session,
            invoice=original,
            invoice_date=local_today(),
            draft=draft,
            user_id=principal.user_id,
        )
        await _render_and_store(request, session, principal, row, contract)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rent_invoice.credit_note",
            entity_type="rent_invoice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"number": row.number, "cancels": original.number},
        )
        return _out(row)


@router.get(
    "/contracts/{contract_id}/rent-invoices/{invoice_id}/pdf",
    summary="Mietrechnung als PDF (Entwurf mit Wasserzeichen, solange G1 geschlossen)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def rent_invoice_pdf(
    contract_id: uuid.UUID,
    invoice_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        contract = await _contract(session, contract_id)
        row = await _invoice(session, contract_id, invoice_id)
        blobs = BlobStore(request.app.state.settings)
        pdf: bytes | None = None
        if row.document_id is not None:
            from mhvp.documents.models import Document

            document = await session.get(Document, row.document_id)
            if document is not None:
                pdf = blobs.get(document.storage_ref)
        if pdf is None:
            head = await docs.letterhead(session, blobs)
            letter = await ri.build_letter(session, invoice=row, contract=contract, head=head)
            pdf = letters.render_pdf(head, letter)
        number = row.number
    filename = quote(f"{ri.title_of(row).split(' ')[0].lower()}_{number}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
