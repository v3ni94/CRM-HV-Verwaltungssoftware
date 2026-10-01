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
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import owner_statement as svc
from mhvp.billing import owner_statement_pdf as owner_pdf
from mhvp.billing.owner_statement import (
    OwnerStatement,
    OwnerStatementKind,
    OwnerStatementStatus,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard, session_allowed_property_ids
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents import letters

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
        )
        session.add(st)
        await session.flush()
        return _out(st)


@router.get("", summary="Eigentümerabrechnungen")
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
        if st.status is OwnerStatementStatus.INTERNALLY_APPROVED:
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
        if principal.user_id in (st.created_by, st.calculated_by):
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die interne Freigabe muss eine andere Person erteilen.",
            )
        if any(f["level"] == "error" for f in (st.snapshot or {}).get("findings", [])):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Summenprüfung mit Fehlern; keine Freigabe."
            )
        st.status = OwnerStatementStatus.INTERNALLY_APPROVED
        st.approved_at = datetime.now(tz=UTC)
        st.approved_by = principal.user_id
        await session.flush()
        return _out(st)


def _eur(value: str) -> str:
    amount = Decimal(value)
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


async def render_letter_pdf(session: AsyncSession, request: Request, st: OwnerStatement) -> bytes:
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
    letter = owner_pdf.build_letter(
        st,
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
        if st.status is not OwnerStatementStatus.INTERNALLY_APPROVED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ausgabe nur nach interner Freigabe.")
        return Response(
            content=await render_letter_pdf(session, request, st),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="eigentuemerabrechnung-{st.id}.pdf"'
            },
        )
