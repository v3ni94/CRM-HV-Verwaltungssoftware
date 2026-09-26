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

from mhvp.billing import letters as tenant_letters
from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ReleaseGateResolver, ensure_release_gate_open
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/statements", tags=["Abrechnung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class LettersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    letter_date: date | None = None
    # One tenant (single PDF) or all tenants of the statement (bundled PDF, unit order).
    contract_id: uuid.UUID | None = None


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
