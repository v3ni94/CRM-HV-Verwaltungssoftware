"""Owner portal: asset report of the community (GA07-02, 7.8 W11 sentence 1), read only.

``GET /portal/owner/asset-reports`` lists the issued asset reports (status issued) of the own
community; ``.../asset-reports/{id}/pdf`` serves the PDF and logs the retrieval per ownership
contract of the owner in ``hoa_asset_report_provision`` (indication, no delivery, no legally
assessed receipt). Drafts, calculated reports and reports of foreign communities answer 404.
Gate G4 applies as for the CRM PDF."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
NOTE = (
    "Vermögensbericht der Gemeinschaft nach Freigabe durch die Verwaltung. Der Abruf wird als "
    "Indiz vermerkt, er ersetzt keine Zustellung."
)


async def _issued(session: Any, hoa_ids: set[uuid.UUID]) -> list[Any]:
    from mhvp.hoa.models import HoaAssetReport

    return list(
        (
            await session.scalars(
                select(HoaAssetReport)
                .where(
                    HoaAssetReport.legal_entity_id.in_(hoa_ids),
                    HoaAssetReport.status == "issued",
                )
                .order_by(HoaAssetReport.as_of.desc())
            )
        ).all()
    )


@router.get("/asset-reports", summary="Vermögensberichte der Gemeinschaft (Eigentümer)")
async def owner_asset_reports(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ownership = await _owner_scope(session, account, local_today())
        items = [
            {"report_id": r.id, "as_of": r.as_of, "issued_at": r.issued_at}
            for r in await _issued(session, hoa_ids)
        ]
        return {"items": items, "note": NOTE}


@router.get("/asset-reports/{report_id}/pdf", summary="Vermögensbericht als PDF (Eigentümer)")
async def owner_asset_report_pdf(
    report_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    from mhvp.contracts.models import Contract
    from mhvp.hoa.assets import render_report_pdf
    from mhvp.hoa.models import HoaAssetReportProvision

    principal, account = ctx
    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, local_today())
        row = next((r for r in await _issued(session, hoa_ids) if r.id == report_id), None)
        if row is None or row.snapshot is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        pdf = await render_report_pdf(session, request.app.state.settings, row)
        own = await session.scalars(
            select(Contract.id).where(
                Contract.id.in_(ownership), Contract.legal_entity_id == row.legal_entity_id
            )
        )
        now = datetime.now(UTC)
        for contract_id in own.all():
            session.add(
                HoaAssetReportProvision(
                    tenant_id=account.tenant_id,
                    report_id=row.id,
                    contract_id=contract_id,
                    account_id=account.id,
                    kind="downloaded",
                    snapshot_hash=row.snapshot_hash,
                    occurred_at=now,
                    created_by=account.user_id,
                    updated_by=account.user_id,
                )
            )
        await session.flush()
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", f"Vermoegensbericht-{row.as_of.isoformat()}.pdf"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
