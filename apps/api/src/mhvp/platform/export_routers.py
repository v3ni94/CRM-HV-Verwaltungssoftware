"""Full tenant export for the tenant administrator (``/api/v1/tenant/export-jobs``, M2-01, 5.3).

Only the tenant administrator (role ``tenant_admin``) starts, lists and downloads; every start
and every download is a domain event with the user (audit). The archive is built by the Celery
job ``mhvp.platform.export_job`` and kept in the object store. The synchronous export of the
platform operator (``mhvp.platform.market_readiness``) stays unchanged."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform import export_job
from mhvp.platform.models import TenantExportJob

router = APIRouter(prefix="/tenant/export-jobs", tags=["Mandant"])
ADMIN = require_permission("tenant_settings:update")
ADMIN_ROLES = {"tenant_admin"}


def _require_tenant_admin(principal: TenantPrincipal) -> None:
    # U15: a platform administrator only after a recorded tenant switch (access reason).
    platform = principal.is_platform_admin and bool(principal.platform_access_reason)
    if not (ADMIN_ROLES & set(principal.roles)) and not platform:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Only the tenant administrator may export."
        )


def _out(row: TenantExportJob) -> dict[str, Any]:
    manifest = row.manifest or {}
    documents = manifest.get("documents") or {}
    return {
        "id": row.id,
        "status": row.status,
        "requested_by": row.requested_by,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "size": row.size,
        "sha256": row.sha256,
        "error": row.error,
        "downloads": row.downloads,
        "last_downloaded_at": row.last_downloaded_at,
        "entities": manifest.get("entities"),
        "documents_written": documents.get("written"),
        "documents_failed": len(documents.get("errors") or []) if documents else None,
    }


@router.post("", status_code=202, summary="Vollständigen Mandantenexport starten")
async def create_export_job(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> dict[str, Any]:
    _require_tenant_admin(principal)
    async with tenant_tx(request, principal) as session:
        active = await session.scalar(
            select(TenantExportJob.id).where(
                TenantExportJob.status.in_([export_job.JOB_QUEUED, export_job.JOB_RUNNING])
            )
        )
        if active is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ein Export läuft bereits.")
        row = TenantExportJob(
            tenant_id=principal.tenant_id,
            status=export_job.JOB_QUEUED,
            requested_by=principal.user_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="tenant_export.started",
            entity_type="tenant_export_job",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        out = _out(row)
        job_id = row.id
    export_job.dispatch_tenant_export_job(str(job_id), str(principal.tenant_id))
    return out


@router.get("", summary="Mandantenexporte auflisten")
async def list_export_jobs(
    request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> list[dict[str, Any]]:
    _require_tenant_admin(principal)
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(TenantExportJob).order_by(TenantExportJob.created_at.desc()).limit(50)
        )
        return [_out(r) for r in rows.all()]


@router.get(
    "/{job_id}/download",
    summary="Mandantenexport herunterladen (Ereignis je Abruf)",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def download_export_job(
    job_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ADMIN)
) -> Response:
    from mhvp.core.storage import create_s3_client

    _require_tenant_admin(principal)
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        row = await session.get(TenantExportJob, job_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != export_job.JOB_READY or not row.object_key:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"Der Export ist nicht fertig ({row.status})."
            )
        try:
            client = create_s3_client(settings)
            data = client.get_object(Bucket=settings.s3_bucket, Key=row.object_key)["Body"].read()
        except Exception as exc:
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE) from exc
        row.downloads += 1
        row.last_downloaded_at = datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="tenant_export.downloaded",
            entity_type="tenant_export_job",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"sha256": row.sha256},
        )
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(
                "attachment", f"mandantenexport-{job_id}.zip"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
