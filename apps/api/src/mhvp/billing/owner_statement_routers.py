"""Owner statements (/api/v1/billing/owner-statements, 7.6 A06, M17 task A25).

Create, calculate, read and approve internally are drafts; the PDF output needs release gate
G3 (closed by default: 403 MHVP-GATE-0001). Rights: accounting:read, accounting:create,
accounting:approve; tenant separation by RLS through ``tenant_tx``.
"""

import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import owner_statement as svc
from mhvp.billing import owner_statement_pdf as owner_pdf
from mhvp.billing import statement_lifecycle as lifecycle
from mhvp.billing.owner_statement import (
    OwnerStatement,
    OwnerStatementKind,
    OwnerStatementStatus,
)
from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard, session_allowed_property_ids
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents import letters, text_blocks

# M2-02/S16-02: owner statements outside the membership's property assignment answer 404.
router = APIRouter(
    prefix="/billing/owner-statements",
    tags=["Abrechnung"],
    dependencies=[Depends(property_column_guard({"statement_id": svc.OwnerStatement.property_id}))],
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class OwnerStatementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    period_from: date
    period_to: date
    # GA03-08: append the linked receipts of the posted expenses to the PDF output.
    attach_receipts: bool = False


class OwnerStatementOptionsIn(BaseModel):
    """GA03-08: output options of the statement (no effect on the calculation)."""

    model_config = ConfigDict(extra="forbid")
    attach_receipts: bool


class OwnerStatementTransitionIn(BaseModel):
    """S69-01: status change after the internal approval (6.9.3)."""

    model_config = ConfigDict(extra="forbid")
    target: OwnerStatementStatus
    # Only for ``posted``: the entries posted in the statement's ledger that settle it.
    entry_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


async def _statement(session: AsyncSession, statement_id: uuid.UUID) -> OwnerStatement:
    row = await session.get(OwnerStatement, statement_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


def _out(st: OwnerStatement, *, with_snapshot: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": st.id,
        "kind": st.kind.value,
        "ledger_id": st.ledger_id,
        "legal_entity_id": st.legal_entity_id,
        "property_id": st.property_id,
        "period_from": st.period_from,
        "period_to": st.period_to,
        "status": st.status.value,
        "rule_version": st.rule_version,
        "snapshot_hash": st.snapshot_hash,
        "calculated_at": st.calculated_at,
        "approved_at": st.approved_at,
        "approved_by": st.approved_by,
        "created_by": st.created_by,
        "status_log": list(st.status_log or []),
        "posted_entry_ids": list(st.posted_entry_ids or []),
        "attach_receipts": st.attach_receipts,
    }
    if with_snapshot:
        snap = st.snapshot or {}
        out["results"] = snap.get("results")
        out["findings"] = snap.get("findings", [])
        # M17-05: payout block for the owner output, derived from the snapshot only.
        out["settlement"] = owner_pdf.settlement(snap["results"]) if snap.get("results") else None
    return out


@router.post("", status_code=201, summary="Eigentümerabrechnung anlegen (Entwurf)")
async def create(
    body: OwnerStatementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    if body.period_to < body.period_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
    async with tenant_tx(request, principal) as session:
        ledger = await session.get(Ledger, body.ledger_id)
        entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
        if ledger is None or entity is None or ledger.property_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        kinds = {
            LegalEntityKind.RENTAL_OWNER: OwnerStatementKind.RENTAL_OWNER,
            LegalEntityKind.SEV_OWNER: OwnerStatementKind.SEV_OWNER,
        }
        if entity.kind not in kinds:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Eigentümerabrechnungen nur im Buchungskreis eines Vermieters "
                "(Mietverwaltung oder SEV).",
            )
        st = OwnerStatement(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            legal_entity_id=entity.id,
            property_id=ledger.property_id,
            kind=kinds[entity.kind],
            period_from=body.period_from,
            period_to=body.period_to,
            attach_receipts=body.attach_receipts,
        )
        session.add(st)
        await session.flush()
        return _out(st)


@router.get("", summary="Eigentümerabrechnungen", dependencies=[Depends(strict_query)])
async def list_statements(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(OwnerStatement).order_by(
            OwnerStatement.period_to.desc(), OwnerStatement.created_at.desc()
        )
        if ledger_id is not None:
            query = query.where(OwnerStatement.ledger_id == ledger_id)
        allowed = session_allowed_property_ids(session)  # M2-02/S16-02
        if allowed is not None:
            query = query.where(OwnerStatement.property_id.in_(allowed))
        rows = (await session.scalars(query.limit(200))).all()
        return [_out(r, with_snapshot=False) for r in rows]


@router.get("/{statement_id}", summary="Eigentümerabrechnung mit Blöcken")
async def get(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _statement(session, statement_id))


@router.post("/{statement_id}/calculate", summary="Berechnen (Snapshot aus dem Ledger)")
async def calculate(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if StatementStatus(st.status.value) not in lifecycle.RECALCULABLE:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Nach der internen Freigabe wird nicht neu berechnet; neue Abrechnung "
                "anlegen.",
            )
        await svc.calculate(session, st, principal.user_id)
        await session.flush()
        return _out(st)


@router.post("/{statement_id}/approve", summary="Interne Freigabe (zweite Person)")
async def approve(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.status is not OwnerStatementStatus.CALCULATED:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nur eine berechnete Abrechnung wird freigegeben."
            )
        _approve(st, principal, None)
        await session.flush()
        return _out(st)


def _approve(st: OwnerStatement, principal: TenantPrincipal, note: str | None) -> None:
    if lifecycle.four_eyes_violated(principal.user_id, st.created_by, st.calculated_by):
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die interne Freigabe muss eine andere Person erteilen.",
        )
    if any(f["level"] == "error" for f in (st.snapshot or {}).get("findings", [])):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Summenprüfung mit Fehlern; keine Freigabe.")
    st.status_log = [
        *(st.status_log or []),
        lifecycle.log_entry(
            StatementStatus(st.status.value),
            StatementStatus.INTERNALLY_APPROVED,
            principal.user_id,
            note,
        ),
    ]
    st.status = OwnerStatementStatus.INTERNALLY_APPROVED
    st.approved_at = datetime.now(tz=UTC)
    st.approved_by = principal.user_id


@router.post("/{statement_id}/transition", summary="Statuswechsel (6.9.3, S69-01)")
async def transition(
    statement_id: uuid.UUID,
    body: OwnerStatementTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Uniform status model (6.9.3): internally_approved (four eyes), board_reviewed, issued,
    due, posted, locked. ``resolved`` is refused (WEG only). issued, due and posted make the
    statement relevant towards the owner or the ledger and need release gate G3 (rental
    statements, 18.0); ``posted`` only records entries already posted in the ledger."""
    target = StatementStatus(body.target.value)
    if target in lifecycle.GATED_TARGETS:
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
    if target in (StatementStatus.DRAFT, StatementStatus.CALCULATED):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Berechnung über den Berechnungsendpunkt.")
    if target is not StatementStatus.POSTED and body.entry_ids:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Buchungen nur beim Status gebucht.")
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        current = StatementStatus(st.status.value)
        try:
            check_transition(current, target, is_hoa=False)
        except TransitionError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from None
        if target is StatementStatus.INTERNALLY_APPROVED:
            _approve(st, principal, body.note)
        else:
            if target is StatementStatus.POSTED:
                entries = await lifecycle.posted_entries_of_ledger(
                    session, st.ledger_id, body.entry_ids
                )
                if entries is None:
                    raise ProblemError(
                        ErrorCodes.CONFLICT,
                        detail="Gebucht nur mit gebuchten Buchungen dieses Buchungskreises.",
                    )
                st.posted_entry_ids = entries
            st.status_log = [
                *(st.status_log or []),
                lifecycle.log_entry(current, target, principal.user_id, body.note),
            ]
            st.status = OwnerStatementStatus(target.value)
        st.updated_by = principal.user_id
        lock_info: dict[str, Any] = {}
        if target is StatementStatus.LOCKED:
            from mhvp.accounting import period_lock

            lock_info = await period_lock.lock_for_closed_statement(
                session,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                source="owner_statement",
                statement_id=st.id,
                ledger_id=st.ledger_id,
                property_id=st.property_id,
                period_from=st.period_from,
                period_to=st.period_to,
            )
        await session.flush()
        return {**_out(st), **lock_info}


@router.patch(
    "/{statement_id}/options", summary="Ausgabeoptionen der Eigentümerabrechnung (Belege anfügen)"
)
async def options(
    statement_id: uuid.UUID,
    body: OwnerStatementOptionsIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.status in (OwnerStatementStatus.POSTED, OwnerStatementStatus.LOCKED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Gebuchte oder gesperrte Abrechnung nicht änderbar."
            )
        st.attach_receipts = body.attach_receipts
        st.updated_by = principal.user_id
        await session.flush()
        return _out(st)


async def receipts_bundle(
    session: AsyncSession, request: Request, st: OwnerStatement, statement_pdf: bytes
) -> bytes:
    """GA03-08: statement PDF followed by the linked receipts (PDF documents only) in booking
    order. A missing or non PDF receipt is listed on a closing page, never replaced."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, StorageKind

    blobs: BlobStore | None = None
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(statement_pdf)).pages:
        writer.add_page(page)
    lines = ((st.snapshot or {}).get("results") or {}).get("receipts", {}).get("lines", [])
    seen: set[str] = set()
    gaps: list[str] = []
    for line in lines:
        label = f"{line['booking_date']} {line.get('text') or ''} {_eur(line['amount'])}".strip()
        doc_id = line.get("document_id")
        if doc_id is None:
            gaps.append(f"{label}: kein Beleg verknüpft")
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        document = await session.get(Document, uuid.UUID(doc_id))
        if document is None or document.storage is StorageKind.GOOGLE_DRIVE:
            gaps.append(f"{label}: Beleg nicht lokal verfügbar")
            continue
        if document.mime_type != "application/pdf":
            gaps.append(f"{label}: Beleg {document.filename} ist kein PDF, gesondert beifügen")
            continue
        try:
            blobs = blobs or BlobStore(request.app.state.settings)
            for page in PdfReader(io.BytesIO(blobs.get(document.storage_ref))).pages:
                writer.add_page(page)
        except Exception:  # unreadable receipt is listed, never dropped silently
            gaps.append(f"{label}: Beleg {document.filename} nicht lesbar")
    if gaps:
        buffer = io.BytesIO()
        c = Canvas(buffer, pagesize=A4)
        y = A4[1] - 60
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Belegmappe: nicht beigefügte Belege")
        c.setFont("Helvetica", 9)
        for gap in gaps:
            y -= 14
            if y < 60:
                c.showPage()
                c.setFont("Helvetica", 9)
                y = A4[1] - 60
            c.drawString(50, y, gap[:120])
        c.showPage()
        c.save()
        for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _eur(value: str) -> str:
    amount = Decimal(value)
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


async def render_letter_pdf(
    session: AsyncSession, request: Request, st: OwnerStatement, part: str = "letter"
) -> bytes:
    """PDF on the tenant's letterhead via the letter blocks (M17-05); falls back to the plain
    block list when the tenant's company data is incomplete (draft, never blocked by it)."""
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.properties.models import LegalEntity, Property
    from mhvp.workspace.services import local_today

    try:
        head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    except ProblemError:
        return render_pdf(st)
    prop = await session.get(Property, st.property_id)
    entity = await session.get(LegalEntity, st.legal_entity_id)
    property_line = (
        f"{prop.number} {prop.name}, {prop.street or ''} {prop.house_number or ''}, "
        f"{prop.postal_code or ''} {prop.city or ''}".replace("  ", " ").strip(" ,")
        if prop
        else str(st.property_id)
    )
    texts = await text_blocks.approved_texts(session, owner_pdf.TEXT_CODES)
    build = owner_pdf.build_s35a_sheet if part == "s35a" else owner_pdf.build_letter
    letter = build(
        st,
        texts=texts,
        recipient_lines=[entity.name] if entity else [],
        property_line=property_line,
        letter_date=local_today(),
        signatory=[s for s in (str(head.company.get("name", "")),) if s],
    )
    return letters.render_pdf(head, letter)


def render_pdf(st: OwnerStatement) -> bytes:
    """Plain PDF of the blocks (fallback without letterhead; see ``render_letter_pdf``)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    results = (st.snapshot or {}).get("results") or {}
    lines = [
        f"Eigentümerabrechnung {st.period_from:%d.%m.%Y} bis {st.period_to:%d.%m.%Y}",
        f"Status: {st.status.value}, Regelversion {st.rule_version}",
        "",
        f"Einnahmen Mieten: {_eur(results['income']['rent'])}",
        f"Einnahmen Vorauszahlungen: {_eur(results['income']['advances'])}",
        f"Sonstige Erträge: {_eur(results['income']['other'])}",
        f"Ausgaben: {_eur(results['expenses']['total'])}",
        f"Verwalterhonorar (brutto): {_eur(results['admin_fee']['gross'])}",
        f"Auszahlungen an den Eigentümer: {_eur(results['payouts']['total'])}",
        f"Offene Mietforderungen: {_eur(results['open_receivables']['total'])}",
        f"Kautionen (Fremdgeld): {_eur(results['deposits']['held'])}",
        f"Freie Liquidität: {_eur(results['liquidity']['free'])}",
    ]
    if "sev_reconciliation" in results:
        sev = results["sev_reconciliation"]
        lines += [
            "",
            "Überleitung WEG-Einzelabrechnung zu Mietabrechnung:",
            f"Kostenanteil laut WEG: {_eur(sev['hoa_cost_share'])}",
            f"Hausgeld-Soll: {_eur(sev['hausgeld_resolved'])}",
            f"Abrechnungsspitze: {_eur(sev['hoa_result'])}",
            f"Auf Mieter umgelegt: {_eur(sev['tenant_allocable_costs'])}",
            f"Eigentümerbelastung: {_eur(sev['owner_burden'])}",
        ]
    buffer = io.BytesIO()
    c = Canvas(buffer, pagesize=A4)
    y = A4[1] - 60
    c.setFont("Helvetica", 11)
    for line in lines:
        c.drawString(50, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buffer.getvalue()


@router.get("/{statement_id}/pdf", summary="Ausgabe als PDF (nur mit Freigabestufe G3)")
async def pdf(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    await ensure_release_gate_open(
        ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if StatementStatus(st.status.value) not in lifecycle.APPROVED_OR_LATER:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ausgabe nur nach interner Freigabe.")
        content = await render_letter_pdf(session, request, st)
        if st.attach_receipts:
            content = await receipts_bundle(session, request, st, content)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="eigentuemerabrechnung-{st.id}.pdf"'
            },
        )


OUTPUT_PARTS = {
    "letter": ("Anschreiben Eigentümerabrechnung", "anschreiben", "owner_statement_letter"),
    "s35a": ("Nachweis § 35a EStG", "nachweis-35a", "owner_statement_s35a"),
}


@router.get(
    "/{statement_id}/preview/{part}",
    summary="Vorschau Anschreiben oder § 35a-Nachweis als PDF-Entwurf (GA06-03, kein Versand)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def output_preview(
    statement_id: uuid.UUID,
    part: str,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    """Draft preview from the calculated snapshot; carries the draft marking and the
    placeholders "Text nicht freigegeben" (AA11-02). Issuing and filing need G3."""
    if part not in OUTPUT_PARTS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Teil: letter oder s35a.")
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if not (st.snapshot or {}).get("results"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Erst berechnen.")
        content = await render_letter_pdf(session, request, st, part)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{OUTPUT_PARTS[part][1]}-{st.id}.pdf"',
        },
    )


@router.post(
    "/{statement_id}/outputs",
    status_code=201,
    summary="Anschreiben und § 35a-Nachweis ablegen (GA06-03, nur mit Freigabestufe G3)",
)
async def file_outputs(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Files the letter and the § 35a proof of the approved statement as generated documents
    linked to the statement run (context ``owner_statement``), the legal entity and the
    property. Internal drafts, nothing is sent."""
    from mhvp.billing import outputs
    from mhvp.documents.blobs import BlobStore

    await ensure_release_gate_open(
        ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if StatementStatus(st.status.value) not in lifecycle.APPROVED_OR_LATER:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ablage nur nach interner Freigabe.")
        blobs = BlobStore(request.app.state.settings)
        released = await text_blocks.approved_texts(session, owner_pdf.TEXT_CODES)
        filed = []
        for part, (label, stem, origin) in OUTPUT_PARTS.items():
            pdf = await render_letter_pdf(session, request, st, part)
            document = await outputs.file_output(
                session,
                blobs,
                principal,
                pdf=pdf,
                title=f"{label} {st.period_from:%d.%m.%Y} bis {st.period_to:%d.%m.%Y} (Entwurf)",
                filename=f"{stem}-{st.period_from.isoformat()}-{st.period_to.isoformat()}.pdf",
                links=[("legal_entity", st.legal_entity_id), ("property", st.property_id)],
                context_type="owner_statement",
                context_id=st.id,
                origin=origin,
            )
            filed.append({"part": part, "document_id": document.id})
        return {
            "statement_id": st.id,
            "items": filed,
            "text_status": owner_pdf.TEXT_NOT_RELEASED
            if len(released) < len(owner_pdf.TEXT_CODES)
            else "freigegeben",
            "texts_status": text_blocks.status_by_code(released, owner_pdf.TEXT_CODES),
        }


@router.get("/{statement_id}/outputs", summary="Abgelegte Ausgaben der Eigentümerabrechnung")
async def list_outputs(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.billing import outputs

    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        return {
            "statement_id": st.id,
            "items": await outputs.list_outputs(session, "owner_statement", st.id),
        }
