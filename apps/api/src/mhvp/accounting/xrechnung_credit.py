"""XRechnung credit note with reference to the original invoice (7.11 S02, S711-02).

A cancelled Verwalterhonorar invoice keeps its number and content; the correction is the
credit note with its own gapless number (``POST /accounting/admin-fee-invoices/{id}/cancel``).
This module renders that credit note as UBL 2.1 ``CreditNote`` with type code 381 (UNTDID
1001) and the reference to the original (BG-3 BillingReference: BT-25 number, BT-26 date).
The stored credit note carries negative amounts; the UBL credit note states them positive,
the document type expresses the correction.

The XML is derived from the invoice XML of ``mhvp.accounting.xrechnung`` so that every lock
of ``load`` applies. Only the own structural check runs; the official KoSIT validation of the
credit note profile is open (P05, docs/OPEN_QUESTIONS.md S711-02) and reported as not run.
"""

import copy
import uuid
import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Any

from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Request, Response

from mhvp.accounting import xrechnung as xr
from mhvp.accounting.models import AdminFeeInvoice, AdminFeeInvoiceStatus
from mhvp.accounting.response_models import AccountingEInvoiceCheckOut
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError

NS_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CREDIT_NOTE_TYPE_CODE = "381"
_CBC = f"{{{xr.NS_CBC}}}"
_CAC = f"{{{xr.NS_CAC}}}"

router = APIRouter(tags=["Buchhaltung"])


def _positive(data: xr.InvoiceData) -> xr.InvoiceData:
    lines = [replace(ln, amount=abs(ln.amount), unit_price=abs(ln.unit_price)) for ln in data.lines]
    return replace(data, lines=lines, net=abs(data.net), vat=abs(data.vat), gross=abs(data.gross))


def build_credit_note_xml(data: xr.InvoiceData, original_number: str, original_date: Any) -> bytes:
    """UBL CreditNote (381) with BillingReference to the corrected invoice."""
    invoice_root = SafeET.fromstring(xr.build_xml(_positive(data)))
    for prefix, uri in xr.NS.items():
        ET.register_namespace("" if prefix == "ubl" else prefix, uri)
    ET.register_namespace("", NS_CREDIT_NOTE)
    root = ET.Element(f"{{{NS_CREDIT_NOTE}}}CreditNote")
    for child in list(invoice_root):
        node = copy.deepcopy(child)
        if node.tag == f"{_CBC}InvoiceTypeCode":
            node.tag, node.text = f"{_CBC}CreditNoteTypeCode", CREDIT_NOTE_TYPE_CODE
        elif node.tag == f"{_CAC}InvoiceLine":
            node.tag = f"{_CAC}CreditNoteLine"
            for sub in node:
                if sub.tag == f"{_CBC}InvoicedQuantity":
                    sub.tag = f"{_CBC}CreditedQuantity"
        if node.tag == f"{_CAC}AccountingSupplierParty":
            # BG-3 precedes the parties in the UBL element order.
            ref = ET.SubElement(root, f"{_CAC}BillingReference")
            doc = ET.SubElement(ref, f"{_CAC}InvoiceDocumentReference")
            ET.SubElement(doc, f"{_CBC}ID").text = original_number  # BT-25
            ET.SubElement(doc, f"{_CBC}IssueDate").text = original_date.isoformat()  # BT-26
        root.append(node)
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def check_credit_note(xml: bytes) -> list[xr.Finding]:
    """Own check: type code, BillingReference, then the invoice checks on the mirrored XML."""
    try:
        root = SafeET.fromstring(xml)
    except (ET.ParseError, ValueError) as exc:
        return [xr.Finding("XML", f"Kein wohlgeformtes XML: {exc}")]
    if root.tag != f"{{{NS_CREDIT_NOTE}}}CreditNote":
        return [xr.Finding("UBL", "Wurzelelement ist keine UBL-CreditNote.")]
    findings: list[xr.Finding] = []
    if root.findtext(f"{_CBC}CreditNoteTypeCode") != CREDIT_NOTE_TYPE_CODE:
        findings.append(xr.Finding("BT-3", "Rechnungstyp ist nicht 381 (Gutschrift)."))
    ref = root.find(f"{_CAC}BillingReference/{_CAC}InvoiceDocumentReference")
    if ref is None or not (ref.findtext(f"{_CBC}ID") or "").strip():
        findings.append(xr.Finding("BT-25", "Bezug auf die Ursprungsrechnung fehlt."))
    mirror = ET.Element(f"{{{xr.NS_INVOICE}}}Invoice")
    for child in list(root):
        node = copy.deepcopy(child)
        if node.tag == f"{_CBC}CreditNoteTypeCode":
            node.tag = f"{_CBC}InvoiceTypeCode"
        elif node.tag == f"{_CAC}CreditNoteLine":
            node.tag = f"{_CAC}InvoiceLine"
            for sub in node:
                if sub.tag == f"{_CBC}CreditedQuantity":
                    sub.tag = f"{_CBC}InvoicedQuantity"
        elif node.tag == f"{_CAC}BillingReference":
            continue
        mirror.append(node)
    findings.extend(xr.check_structure(ET.tostring(mirror)))
    return findings


async def _credit_note(
    session: Any, invoice_id: uuid.UUID
) -> tuple[AdminFeeInvoice, AdminFeeInvoice]:
    row = await session.get(AdminFeeInvoice, invoice_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.kind != "credit_note" or row.corrects_invoice_id is None:
        raise ProblemError(
            ErrorCodes.XRECHNUNG_NOT_ISSUED, detail="Nur Gutschriften mit Ursprungsbezug."
        )
    if row.status not in (
        AdminFeeInvoiceStatus.ISSUED,
        AdminFeeInvoiceStatus.RELEASED,
        AdminFeeInvoiceStatus.CANCELLED,
    ):
        raise ProblemError(ErrorCodes.XRECHNUNG_NOT_ISSUED)
    original = await session.get(AdminFeeInvoice, row.corrects_invoice_id)
    if original is None:  # pragma: no cover - FK
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row, original


async def _render(session: Any, invoice_id: uuid.UUID) -> tuple[AdminFeeInvoice, bytes]:
    row, original = await _credit_note(session, invoice_id)
    data = await xr.load(session, row)
    return row, build_credit_note_xml(data, original.number, original.invoice_date)


@router.get(
    "/admin-fee-invoices/{invoice_id}/xrechnung-credit-note.xml",
    summary="Gutschrift als XRechnung (UBL CreditNote 381 mit Ursprungsbezug)",
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}}},
)
async def credit_note_xml(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(xr.READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row, xml = await _render(session, invoice_id)
    findings = check_credit_note(xml)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{row.number}.xml"',
            "X-MHVP-XRechnung-Findings": str(len(findings)),
        },
    )


@router.get(
    "/admin-fee-invoices/{invoice_id}/xrechnung-credit-note/check",
    summary="Strukturprüfung der Gutschrift-XRechnung",
    response_model=AccountingEInvoiceCheckOut,
)
async def credit_note_check(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(xr.READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row, xml = await _render(session, invoice_id)
    findings = check_credit_note(xml)
    return {
        "invoice_id": row.id,
        "number": row.number,
        "type_code": CREDIT_NOTE_TYPE_CODE,
        "corrects_invoice_id": row.corrects_invoice_id,
        "structure_ok": not findings,
        "findings": [f.as_dict() for f in findings],
        "official_validation": "not_run",
    }
