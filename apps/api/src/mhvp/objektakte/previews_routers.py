"""M35 technical preparation, preview images (open question M35-02): `/api/v1/objektakte/
previews`. Start a takeover run (worker, resumable), read the latest run, and serve one
preview page of a taken over document from the object store.

Permissions: `objektakte:read` for the run state and the image (a preview is document
content, so the document itself must be visible to the caller in this tenant),
`objektakte:approve` to start a run (a configuration level action like the rules, docs/rules/
M35-03.md). No run changes financial or legal content; a preview is a derived picture.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.objektakte import previews
from mhvp.objektakte.models import ObjektaktePreviewImportRun, PreviewImportStatus

router = APIRouter(prefix="/objektakte/previews", tags=["objektakte"])
READ = require_permission("objektakte:read")
MANAGE = require_permission("objektakte:approve")


class StartPreviewImport(BaseModel):
    # Whether a missing objektakte file is rendered from the original in the CRM (images
    # only, PDF stays pending until a renderer is decided, M35-02).
    render_missing: bool = False
    # Continue the latest interrupted or failed run instead of starting over.
    resume: bool = True
    # Run inside this request (small tenants, tests) instead of the worker.
    inline_limit: int | None = Field(default=None, ge=1, le=500)


async def _latest_run(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ObjektaktePreviewImportRun | None:
    run: ObjektaktePreviewImportRun | None = await session.scalar(
        select(ObjektaktePreviewImportRun)
        .where(ObjektaktePreviewImportRun.tenant_id == tenant_id)
        .order_by(ObjektaktePreviewImportRun.started_at.desc())
        .limit(1)
    )
    return run


@router.get("/import", summary="Stand der Vorschaubild-Übernahme aus objektakte")
async def get_preview_import(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await _latest_run(session, principal.tenant_id)
        return {
            "previews_dir": request.app.state.settings.objektakte_previews_dir,
            "run": previews.run_dict(run) if run is not None else None,
        }


@router.post("/import", summary="Vorschaubilder aus objektakte übernehmen (Lauf starten)")
async def start_preview_import(
    request: Request, body: StartPreviewImport, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        latest = await _latest_run(session, principal.tenant_id)
        if latest is not None and latest.status == PreviewImportStatus.RUNNING:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Es läuft bereits eine Vorschaubild-Übernahme für diesen Mandanten.",
            )
        resume = (
            latest
            if (body.resume and latest is not None and latest.status == PreviewImportStatus.FAILED)
            else None
        )
        if body.inline_limit is not None:
            store = BlobStore(settings)
            run = await previews.import_previews(
                session,
                store,
                principal.tenant_id,
                previews_dir=settings.objektakte_previews_dir,
                render_missing=body.render_missing,
                resume=resume,
                trigger="manual",
                max_documents=body.inline_limit,
            )
            return {"mode": "inline", "run": previews.run_dict(run)}
        tenant_id = principal.tenant_id
        resume_id = str(resume.id) if resume is not None else None
    from mhvp.objektakte.tasks import import_previews_tenant

    import_previews_tenant.delay(str(tenant_id), body.render_missing, resume_id)
    return {"mode": "queued", "tenant_id": tenant_id}


@router.get(
    "/documents/{document_id}",
    summary="Vorschaubild (Seite) eines übernommenen Dokuments",
    response_class=Response,
)
async def get_preview_page(
    request: Request,
    document_id: uuid.UUID,
    page: int = Query(1, ge=1, le=previews.MAX_PAGES_PER_DOCUMENT),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        meta = (document.source_meta or {}).get("preview") or {}
        pages = int(meta.get("pages") or 0)
        if meta.get("status") not in ("imported", "rendered") or page > pages:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND,
                detail="Für dieses Dokument liegt keine Vorschau vor.",
            )
        tenant_id = principal.tenant_id
    store = BlobStore(request.app.state.settings)
    data = store.get(previews.preview_key(tenant_id, document_id, page))
    return Response(
        content=data,
        media_type=previews.PREVIEW_MIME,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
