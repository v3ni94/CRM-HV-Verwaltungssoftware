"""M35 Stufe 4 (docs/plans/M35-objektakte-uebernahme.md section 4, docs/rules/M35-03.md):
read-only view of the objektakte AI call protocol taken over by the importer
(`objektakte_ai_call`), per document: `GET /api/v1/objektakte/documents/{id}/ai-calls`.

There is deliberately no write endpoint: the rows are history of the old application (cost
evaluation, masking evidence); new AI calls run through `mhvp.ai` and are recorded as
`AiTaskRun`. Permission `objektakte:read`.
"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.objektakte.models import ObjektakteAiCall

router = APIRouter(prefix="/objektakte", tags=["objektakte-ai-calls"])
READ = require_permission("objektakte:read")


def _call_out(row: ObjektakteAiCall) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "document_id": str(row.document_id) if row.document_id else None,
        "property_id": str(row.property_id) if row.property_id else None,
        "purpose": row.purpose,
        "provider": row.provider,
        "model": row.model,
        "endpoint": row.endpoint,
        "region": row.region,
        "page_from": row.page_from,
        "page_to": row.page_to,
        "prompt_hash": row.prompt_hash,
        "prompt_chars": row.prompt_chars,
        "masked_entities_count": row.masked_entities_count,
        "tokens_in": row.tokens_in,
        "tokens_out": row.tokens_out,
        "cost_eur": str(row.cost_eur) if row.cost_eur is not None else None,
        "price_list_version": row.price_list_version,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "http_status": row.http_status,
        "error_message": row.error_message,
        "fallback_used": row.fallback_used,
        "response_summary": row.response_summary,
        "requested_at": row.requested_at.isoformat(),
        "source_system": row.source_system,
        "source_id": row.source_id,
    }


@router.get(
    "/documents/{document_id}/ai-calls",
    summary="KI-Aufrufprotokoll der Altanwendung objektakte zu einem Dokument (nur lesend)",
)
async def list_document_ai_calls(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        rows = (
            (
                await session.execute(
                    select(ObjektakteAiCall)
                    .where(ObjektakteAiCall.document_id == document_id)
                    .order_by(ObjektakteAiCall.requested_at.desc())
                )
            )
            .scalars()
            .all()
        )
        total_cost = sum((row.cost_eur for row in rows if row.cost_eur is not None), Decimal("0"))
        return {
            "document_id": str(document_id),
            "items": [_call_out(r) for r in rows],
            "count": len(rows),
            "total_cost_eur": str(total_cost),
            "total_tokens_in": sum(r.tokens_in or 0 for r in rows),
            "total_tokens_out": sum(r.tokens_out or 0 for r in rows),
        }
