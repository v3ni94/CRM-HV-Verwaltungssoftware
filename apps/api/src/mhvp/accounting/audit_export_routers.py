"""Audit export endpoints (/api/v1/accounting/audit-exports, A26, 7.7, D55).

Create needs ``accounting:export``; list and status need ``accounting:read``; the download of
the ZIP needs ``accounting:export`` again because it hands out the complete bookkeeping of a
legal entity. Small periods are built inside the request, larger ones on the worker.
"""

import logging
import uuid
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import audit_export
from mhvp.accounting.models import ExportRun, Ledger
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_legal_entity_allowed,
    legal_entity_allowed,
    session_allowed_legal_entity_ids,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document

log = logging.getLogger(__name__)
router = APIRouter(prefix="/accounting/audit-exports", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
EXPORT = require_permission("accounting:export")


class AuditExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    period_from: date
    period_to: date
    # Above this total size the receipts are listed with hash only (belege.csv), not packed.
    receipts_max_bytes: int = Field(
        default=audit_export.DEFAULT_RECEIPTS_MAX_BYTES, ge=0, le=2 * 1024**3
    )
    # Force the worker even for a small period (default: inline up to SYNC_MAX_ENTRIES).
    run_in_background: bool = False

    @model_validator(mode="after")
    def _period(self) -> "AuditExportIn":
        if self.period_to < self.period_from:
            raise ValueError("period_to must not lie before period_from")
        return self


async def _run(session: AsyncSession, run_id: uuid.UUID) -> ExportRun:
    run = await session.scalar(
        select(ExportRun).where(ExportRun.id == run_id, ExportRun.format == audit_export.FORMAT)
    )
    if run is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    # A37: a scoped membership (tax advisor) only sees exports of its legal entities.
    allowed = session_allowed_legal_entity_ids(session)
    if allowed is not None:
        legal_entity_id = await session.scalar(
            select(Ledger.legal_entity_id).where(Ledger.id == run.ledger_id)
        )
        if legal_entity_id is None or not legal_entity_allowed(
            session.info.get("mhvp.principal"), legal_entity_id
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return run


@router.post("", status_code=201, summary="Prüfexport je Rechtsträger und Zeitraum erstellen")
async def create_audit_export(
    body: AuditExportIn, request: Request, principal: TenantPrincipal = Depends(EXPORT)
) -> dict[str, Any]:
    queued = False
    async with tenant_tx(request, principal) as session:
        ledger = await session.scalar(select(Ledger).where(Ledger.id == body.ledger_id))
        if ledger is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ensure_legal_entity_allowed(principal, ledger.legal_entity_id)  # A37: 404 for foreign
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format=audit_export.FORMAT,
            period_from=body.period_from,
            period_to=body.period_to,
            rows=0,
            sha256="",
            status=audit_export.ExportStatus.QUEUED.value,
            params={
                "receipts_max_bytes": body.receipts_max_bytes,
                "legal_entity_id": str(ledger.legal_entity_id),
            },
        )
        session.add(run)
        await session.flush()
        count = await audit_export.count_entries(session, ledger, body.period_from, body.period_to)
        if body.run_in_background or count > audit_export.SYNC_MAX_ENTRIES:
            queued = True
        else:
            blobs = BlobStore(request.app.state.settings)
            await audit_export.execute(session, blobs, run, ledger)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.created",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "status": run.status, "entries": count},
        )
        out = audit_export.run_out(run)
    if queued:
        dispatch_audit_export(str(out["id"]), str(principal.tenant_id))
    return out


def dispatch_audit_export(run_id: str, tenant_id: str) -> None:
    """Hands a queued run to the worker (``mhvp.accounting.audit_export_run``), after the
    creating transaction has committed. Module level on purpose: ``shared_task`` returns a
    proxy that resolves the task on the *current* Celery app per thread, so a test cannot
    patch ``.delay`` reliably once another test has created its own app; tests replace this
    function instead (see ``tests/integration/test_m18_audit_export.py``)."""
    from mhvp.accounting.tasks import audit_export_run

    audit_export_run.delay(run_id, tenant_id)


@router.get("", summary="Prüfexporte auflisten")
async def list_audit_exports(
    request: Request,
    ledger_id: uuid.UUID | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(ExportRun).where(ExportRun.format == audit_export.FORMAT)
        if ledger_id is not None:
            query = query.where(ExportRun.ledger_id == ledger_id)
        allowed = session_allowed_legal_entity_ids(session)  # A37: scoped membership
        if allowed is not None:
            query = query.where(
                ExportRun.ledger_id.in_(
                    select(Ledger.id).where(Ledger.legal_entity_id.in_(list(allowed)))
                )
            )
        runs = await session.scalars(query.order_by(ExportRun.created_at.desc()).limit(200))
        return [audit_export.run_out(r) for r in runs]


@router.get("/{run_id}", summary="Status eines Prüfexports")
async def get_audit_export(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return audit_export.run_out(await _run(session, run_id))


@router.get(
    "/{run_id}/download",
    summary="Prüfexport (ZIP) herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def download_audit_export(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(EXPORT)
) -> Response:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        if run.status != audit_export.ExportStatus.DONE.value or run.document_id is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Prüfexport ist noch nicht fertiggestellt."
            )
        document = await session.get(Document, run.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.downloaded",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "sha256": run.sha256},
        )
        filename = document.filename
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
