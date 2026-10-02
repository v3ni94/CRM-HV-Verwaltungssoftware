"""Owner portal: individual hoa fee statement after release (M24-03, 7.8 W12), read only.

``GET /portal/owner/statements`` lists the statements of the own community that were already
issued to owners (status issued, due, posted or locked) with the units the account owns; the
PDF of exactly such an own unit is served by ``.../statements/{id}/units/{unit_id}/pdf``. A
statement before release, a foreign unit or a foreign community answers 404 without a hint.
The release gate G4 applies as for the CRM PDF; the PDF is the same filed document as the
manager's output (GAB-06, ``hoa.statement_archive``).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
PROVIDED = (
    StatementStatus.ISSUED,
    StatementStatus.DUE,
    StatementStatus.POSTED,
    StatementStatus.LOCKED,
)
NOTE = (
    "Einzelabrechnung Ihrer Einheit nach Freigabe durch die Verwaltung. Maßgeblich sind der "
    "Beschluss der Eigentümerversammlung und die Rechtsfolgen nach Gesetz und Gemeinschaftsordnung."
)


async def _own_units(session: Any, ownership: set[uuid.UUID]) -> set[str]:
    from mhvp.contracts.models import Contract

    if not ownership:
        return set()
    rows = await session.scalars(select(Contract.unit_id).where(Contract.id.in_(ownership)))
    return {str(u) for u in rows if u is not None}


async def _provided(session: Any, hoa_ids: set[uuid.UUID]) -> list[Any]:
    from mhvp.accounting.models import Ledger
    from mhvp.hoa.models import HoaStatement

    return list(
        (
            await session.scalars(
                select(HoaStatement)
                .join(Ledger, Ledger.id == HoaStatement.ledger_id)
                .where(Ledger.legal_entity_id.in_(hoa_ids), HoaStatement.status.in_(PROVIDED))
                .order_by(HoaStatement.year.desc(), HoaStatement.version.desc())
            )
        ).all()
    )


@router.get("/statements", summary="Freigegebene Einzelabrechnungen (Eigentümer)")
async def owner_statements(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, local_today())
        own = await _own_units(session, ownership)
        items: list[dict[str, Any]] = []
        for st in await _provided(session, hoa_ids):
            for unit in (st.snapshot or {}).get("units", []):
                if unit["unit_id"] in own:
                    items.append(
                        {
                            "statement_id": st.id,
                            "year": st.year,
                            "version": st.version,
                            "status": st.status.value,
                            "unit_id": uuid.UUID(unit["unit_id"]),
                            "unit_number": unit["unit_number"],
                        }
                    )
        return {"items": items, "note": NOTE}


@router.get(
    "/statements/{statement_id}/units/{unit_id}/pdf",
    summary="Einzelabrechnung als PDF (Eigentümer, nach Freigabe)",
)
async def owner_statement_pdf(
    statement_id: uuid.UUID,
    unit_id: uuid.UUID,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> Response:
    from mhvp.hoa import statement_pdf

    principal, account = ctx
    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, local_today())
        if str(unit_id) not in await _own_units(session, ownership):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        st = next((s for s in await _provided(session, hoa_ids) if s.id == statement_id), None)
        unit = None
        if st is not None and st.snapshot is not None:
            unit = next(
                (u for u in st.snapshot.get("units", []) if u["unit_id"] == str(unit_id)), None
            )
        if st is None or unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        from mhvp.accounting.models import Ledger
        from mhvp.documents.blobs import BlobStore
        from mhvp.hoa import statement_archive

        ledger = await session.get(Ledger, st.ledger_id)
        snapshot, snap_hash = st.snapshot, st.snapshot_hash or ""
        # GAB-06: the same filed document as in the CRM; filed on first output if missing.
        content, _doc = await statement_archive.archived_pdf(
            session,
            BlobStore(request.app.state.settings),
            st=st,
            property_id=ledger.property_id if ledger else None,
            legal_entity_id=ledger.legal_entity_id if ledger else None,
            unit=unit,
            render=lambda: statement_pdf.render(st.year, snapshot, unit, snap_hash),
            created_by=None,
        )
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", f"Hausgeldabrechnung-{st.year}-{unit['unit_number']}.pdf"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
