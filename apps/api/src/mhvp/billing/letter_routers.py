"""Tenant letters of an operating cost statement (/api/v1/statements/{id}/letters, A34).

Preview (PDF per tenant or bundled) and filing as draft documents are allowed from the
calculated snapshot on; the dispatch (``/letters/send``) needs G3 and is not implemented,
so it is always refused (0.1.1, API first 0.1.4).
"""

import uuid
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import info_sheet
from mhvp.billing import letters as tenant_letters
from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ReleaseGateResolver, ensure_release_gate_open
from mhvp.documents import text_blocks
from mhvp.workspace.services import local_today

# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class LettersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    letter_date: date | None = None
    # One tenant (single PDF) or all tenants of the statement (bundled PDF, unit order).
    contract_id: uuid.UUID | None = None
    # GA06-02: append the Informationsblatt after each letter of the preview (A07).
    include_info_sheet: bool = False


async def _statement_with_snapshot(
    session: AsyncSession, statement_id: uuid.UUID
) -> tuple[Statement, StatementSnapshot]:
    st = await session.get(Statement, statement_id)
    if st is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
    if snap is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Kein Ergebnis-Snapshot: die Abrechnung ist noch nicht berechnet.",
        )
    return st, snap


async def _build(
    session: AsyncSession, request: Request, statement_id: uuid.UUID, body: LettersIn | None
) -> tuple[Statement, list[tenant_letters.TenantLetter]]:
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    st, snap = await _statement_with_snapshot(session, statement_id)
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    drafts = await tenant_letters.build(
        session,
        st,
        snap,
        head,
        (body.letter_date if body else None) or local_today(),
        contract_id=body.contract_id if body else None,
    )
    tenant_letters.render(head, drafts)
    return st, drafts


@router.post(
    "/{statement_id}/letters/preview",
    summary="Anschreiben Guthaben/Nachzahlung je Mieter als PDF-Entwurf (Vorschau, kein Versand)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def letters_preview(
    statement_id: uuid.UUID,
    request: Request,
    body: LettersIn | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        st, drafts = await _build(session, request, statement_id, body)
        sheet = None
        if body is not None and body.include_info_sheet:
            sheet = await _info_sheet_pdf(session, request, st)
    if sheet is not None:
        for draft in drafts:
            draft.pdf = tenant_letters.bundle_pdfs([draft.pdf, sheet])
    if len(drafts) == 1:
        pdf, filename = drafts[0].pdf, drafts[0].filename
    else:
        pdf = tenant_letters.bundle(drafts)
        filename = f"betriebskosten_{st.period_from.year}_anschreiben_gesamt.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{quote(filename)}"',
        },
    )


async def _info_sheet_pdf(session: AsyncSession, request: Request, st: Statement) -> bytes:
    from mhvp.documents import letters as doc_letters
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.properties.models import Property

    st, snap = await _statement_with_snapshot(session, st.id)
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    prop = await session.get(Property, st.property_id)
    texts = await text_blocks.approved_texts(session, info_sheet.TEXT_CODES)
    sheet = info_sheet.build(
        period_from=st.period_from,
        period_to=st.period_to,
        object_line=f"Objekt {prop.number} {prop.name}" if prop else "das Objekt",
        snapshot_inputs=snap.inputs,
        snapshot_hash=snap.hash,
        version=st.version,
        letter_date=local_today(),
        texts={
            "inspection": texts.get("info_sheet_inspection", ""),
            "objection": texts.get("info_sheet_objection", ""),
        },
    )
    return doc_letters.render_pdf(head, sheet)


@router.post(
    "/{statement_id}/info-sheet/preview",
    summary="Informationsblatt zur Abrechnung als PDF-Entwurf (eigene Ausgabe, kein Versand)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def info_sheet_preview(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        st, _ = await _statement_with_snapshot(session, statement_id)
        pdf = await _info_sheet_pdf(session, request, st)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f'attachment; filename="betriebskosten_{st.period_from.year}_informationsblatt.pdf"'
            ),
        },
    )


@router.post(
    "/{statement_id}/info-sheet",
    status_code=201,
    summary="Informationsblatt als Dokument zum Abrechnungslauf ablegen (GA06-02, G3)",
)
async def info_sheet_file(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Files the info sheet of the current snapshot as a generated document linked to the
    statement run (context ``statement``) and the property. Output of the statement, so G3 is
    required; the legally relevant paragraphs stay marked "Text nicht freigegeben" (AA11-01)."""
    from mhvp.billing import allocation_basis, outputs
    from mhvp.documents.blobs import BlobStore

    await ensure_release_gate_open(
        ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st, snap = await _statement_with_snapshot(session, statement_id)
        await allocation_basis.ensure_complete(session, st)
        pdf = await _info_sheet_pdf(session, request, st)
        released = await text_blocks.approved_texts(session, info_sheet.TEXT_CODES)
        document = await outputs.file_output(
            session,
            BlobStore(request.app.state.settings),
            principal,
            pdf=pdf,
            title=f"Informationsblatt Betriebskostenabrechnung {st.period_from.year} (Entwurf)",
            filename=f"betriebskosten_{st.period_from.year}_informationsblatt.pdf",
            links=[("property", st.property_id), ("statement", st.id)],
            context_type="statement",
            context_id=st.id,
            origin="billing_info_sheet",
        )
        return {
            "statement_id": st.id,
            "document_id": document.id,
            "snapshot_hash": snap.hash,
            "text_status": info_sheet.TEXT_NOT_RELEASED
            if len(released) < len(info_sheet.TEXT_CODES)
            else "freigegeben",
            "texts_status": text_blocks.status_by_code(released, info_sheet.TEXT_CODES),
        }


@router.get("/{statement_id}/outputs", summary="Abgelegte Ausgaben des Abrechnungslaufs")
async def statement_outputs(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.billing import outputs

    async with tenant_tx(request, principal) as session:
        st = await session.get(Statement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {
            "statement_id": st.id,
            "items": await outputs.list_outputs(session, "statement", st.id),
        }


@router.post(
    "/{statement_id}/letters",
    status_code=201,
    summary="Anschreiben je Mieter als PDF-Entwurf ablegen (Dokument je Vertrag, kein Versand)",
)
async def letters_create(
    statement_id: uuid.UUID,
    request: Request,
    body: LettersIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore

    async with tenant_tx(request, principal) as session:
        st, drafts = await _build(session, request, statement_id, body)
        await tenant_letters.store(
            session,
            BlobStore(request.app.state.settings),
            statement=st,
            drafts=drafts,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return {
            "statement_id": st.id,
            "status": st.status.value,
            "hinweis": tenant_letters.DRAFT_LABEL,
            "letters": [tenant_letters.summary(d) for d in drafts],
        }


@router.post(
    "/{statement_id}/letters/send",
    summary="Anschreiben zustellen (gesperrt: G3 geschlossen, Zustellung nicht umgesetzt)",
)
async def letters_send(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Locked on purpose: G3 must be open for the tenant, and even then the dispatch path
    (postal or e-mail evidence of access, A04, M17-04) is not released."""
    resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
    await ensure_release_gate_open(ReleaseGate.G3, principal.tenant_id, resolver)
    raise ProblemError(
        ErrorCodes.CONFLICT,
        detail=(
            "Die Zustellung der Anschreiben ist nicht freigegeben (M17-04, M17-05). Die "
            "Schreiben bleiben Entwürfe; der Zugang wird mit der Ausgabe der Abrechnung "
            "erfasst."
        ),
        extensions={"locked": "statement_letters_send", "statement_id": str(statement_id)},
    )


# Draft editing, results per contract, access, diff, result entries and Belegeinsicht
# (M17-01 to M17-08) share the /statements prefix; included here so the app wiring stays.
from mhvp.billing.result_routers import router as _result_router  # noqa: E402

router.include_router(_result_router)
