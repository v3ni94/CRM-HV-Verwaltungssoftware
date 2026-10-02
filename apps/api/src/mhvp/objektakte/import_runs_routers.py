"""GAG-12 (GAF-14): `/api/v1/objektakte/import-runs`. List of the objektakte import runs
(status, date, counts) and clearing of the OCR text that was taken over from the objektakte
OCR cache (`POST /objektakte/imports/{id}/ocr-cache`).

Permissions: `documents:read` for the list (same level as `GET /objektakte/imports/{id}`),
`objektakte:update` for clearing the cache. The objektakte permission set has no `write`
action (see `core/auth/permissions.py`); `update` is the review level of M35-03. Clearing
removes derived text only (`ocr_text`), the documents, their files and all financial content
stay untouched; affected documents go back to `text_status=pending` so the later OCR
pipeline can read them again.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select, update

from mhvp.ai.models import ImportRun
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import ListParams, ListSpec, sparse
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, TextStatus

router = APIRouter(prefix="/objektakte/import-runs", tags=["objektakte"])
READ = require_permission("documents:read")
WRITE = require_permission("objektakte:update")

_RUN_LIST = ListSpec(
    filters={"status": ImportRun.status},
    sort={"created_at": ImportRun.created_at, "status": ImportRun.status},
)


def _sum_counts(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(v for v in value.values() if isinstance(v, int) and not isinstance(v, bool))


def run_out(run: ImportRun) -> dict[str, Any]:
    summary = run.summary or {}
    return {
        "id": run.id,
        "status": run.status,
        "created_at": run.created_at,
        "created_by": run.created_by,
        "created_total": _sum_counts(summary.get("created")),
        "updated_total": _sum_counts(summary.get("updated")),
        "skipped_duplicates_total": _sum_counts(summary.get("skipped_duplicates")),
        "considered_total": _sum_counts(summary.get("considered")),
        "deleted_marked": _sum_counts(summary.get("deleted_marked")),
        "undone_at": run.undone_at,
    }


def _cache_filter(tenant_id: uuid.UUID) -> list[Any]:
    return [
        Document.tenant_id == tenant_id,
        Document.source_system == "objektakte",
        Document.source_meta["ocr_cache_key"].as_string().is_not(None),
        Document.ocr_text.is_not(None),
    ]


@router.get("", summary="Importläufe der objektakte-Übernahme (Verlauf)")
async def list_import_runs(
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    params: ListParams = Depends(_RUN_LIST.dependency),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    """Newest first; total, page and page size in `X-Total-Count`, `X-Page`, `X-Page-Size`.
    `cache_documents` is the number of documents that currently hold OCR text from the
    cache (the same for every run, since a cache upload is matched per tenant)."""
    async with tenant_tx(request, principal) as session:
        base = select(ImportRun).where(
            ImportRun.tenant_id == principal.tenant_id, ImportRun.source == "objektakte"
        )
        query = _RUN_LIST.apply(base, params, (ImportRun.created_at.desc(), ImportRun.id.desc()))
        total = (
            await session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
            or 0
        )
        rows = list(
            (await session.scalars(query.offset((page - 1) * page_size).limit(page_size))).all()
        )
        cache_documents = (
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(*_cache_filter(principal.tenant_id))
            )
            or 0
        )
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        items = [{**run_out(r), "cache_documents": cache_documents} for r in rows]
        return sparse(items, params, None, response=response)


@router.delete(
    "/{import_run_id}/ocr-cache", summary="Aus dem OCR-Cache übernommene Texte entfernen"
)
async def clear_ocr_cache(
    request: Request,
    import_run_id: uuid.UUID,
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ImportRun, import_run_id)
        if run is None or run.tenant_id != principal.tenant_id or run.source != "objektakte":
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        result = await session.execute(
            update(Document)
            .where(*_cache_filter(principal.tenant_id))
            .values(ocr_text=None, text_status=TextStatus.PENDING)
        )
        cleared = int(result.rowcount or 0)  # type: ignore[attr-defined]
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="objektakte.ocr_cache_cleared",
            entity_type="import_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"cleared": cleared},
        )
        return {"import_run_id": run.id, "cleared": cleared}
