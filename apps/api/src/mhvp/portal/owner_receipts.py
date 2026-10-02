"""Owner portal: receipt search per statement period (GAF-36, section 14, phase 4), read only.

``GET /portal/owner/receipts`` lists the receipts behind the cost positions of the issued
hoa statements of the own community, optionally filtered by year and search text. Switch
``portal_owner_receipts_enabled`` (default off) and release gate G4 are required, otherwise the
list is empty with a note. The list never opens a document: the retrieval runs over the existing
``/portal/documents/{id}/download``, which checks the document authorisation of the account and
writes the read receipt (indication only, no delivery). A receipt the account may not see is
listed without retrieval (``available`` false) and its title is not disclosed."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.release_gates import ReleaseGate, ReleaseGateClosedError, ensure_release_gate_open
from mhvp.portal import access
from mhvp.portal import features as portal_features
from mhvp.portal.owner import _owner_scope
from mhvp.portal.owner_statements import _provided
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
MAX_ITEMS = 500
NOTE = (
    "Belege zu den Kostenpositionen der freigegebenen Abrechnungen Ihrer Gemeinschaft. Der "
    "Abruf wird als Indiz vermerkt, er ersetzt keine Zustellung."
)
NOTE_OFF = "Die Belegeinsicht ist für Ihre Verwaltung nicht freigeschaltet."
NOTE_GATE = "Die Belegeinsicht steht erst nach Freigabe (G4) zur Verfügung."


@router.get(
    "/receipts",
    summary="Belegsuche je Abrechnungsperiode (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def owner_receipts(
    request: Request,
    ctx: Portal = Depends(portal_user),
    year: int | None = Query(default=None, ge=2000, le=2100),
    q: str | None = Query(default=None, max_length=100, description="Suche in der Bezeichnung"),
) -> dict[str, Any]:
    from mhvp.hoa.models import HoaCostItem

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ownership = await _owner_scope(session, account, local_today())
        if not (await portal_features.get_or_default(session)).portal_owner_receipts_enabled:
            return {"items": [], "years": [], "enabled": False, "note": NOTE_OFF}
        try:
            await ensure_release_gate_open(
                ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
            )
        except ReleaseGateClosedError:
            return {"items": [], "years": [], "enabled": False, "note": NOTE_GATE}
        latest: dict[int, Any] = {}
        for st in await _provided(session, hoa_ids):  # ordered by year, version descending
            latest.setdefault(st.year, st)
        years = sorted(latest, reverse=True)
        chosen = [latest[y] for y in years if year is None or y == year]
        visible = {d.id: d for d in await access.visible_documents(session, account, local_today())}
        items: list[dict[str, Any]] = []
        needle = q.strip().lower() if q else ""
        for st in chosen:
            rows = (
                await session.scalars(
                    select(HoaCostItem)
                    .where(
                        HoaCostItem.statement_id == st.id,
                        HoaCostItem.document_id.is_not(None),
                    )
                    .order_by(HoaCostItem.label)
                )
            ).all()
            for row in rows:
                if needle and needle not in row.label.lower():
                    continue
                doc = visible.get(row.document_id) if row.document_id else None
                items.append(
                    {
                        "statement_id": st.id,
                        "year": st.year,
                        "version": st.version,
                        "item_id": row.id,
                        "label": row.label,
                        "amount": str(row.amount),
                        "document_id": row.document_id if doc is not None else None,
                        "document_title": doc.title if doc is not None else None,
                        "available": doc is not None,
                    }
                )
        return {
            "items": items[:MAX_ITEMS],
            "years": years,
            "enabled": True,
            "truncated": len(items) > MAX_ITEMS,
            "note": NOTE,
        }
