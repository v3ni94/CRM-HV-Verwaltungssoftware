"""M35 Stufe 4 (docs/plans/M35-objektakte-uebernahme.md section 4, docs/rules/M35-03.md):
read-only view of the objektakte AI call protocol taken over by the importer
(`objektakte_ai_call`), per document: `GET /api/v1/objektakte/documents/{id}/ai-calls`, and
the cost evaluation per property and month: `GET /api/v1/objektakte/ai-calls/summary`.

There is deliberately no write endpoint: the rows are history of the old application (cost
evaluation, masking evidence); new AI calls run through `mhvp.ai` and are recorded as
`AiTaskRun`. Permission `objektakte:read`.
"""

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.objektakte.models import ObjektakteAiCall
from mhvp.properties.models import Property

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


def _money(value: Any) -> str:
    """Decimal sum as string with the six decimals of the source (objektakte priced fractions
    of a cent); the UI rounds to `1.234,56 EUR` without float (rule 6.9.8)."""
    return str(
        (Decimal(value) if value is not None else Decimal("0")).quantize(Decimal("0.000001"))
    )


@router.get(
    "/ai-calls/summary",
    summary="KI-Kosten der Altanwendung objektakte je Objekt und je Monat (nur lesend)",
)
async def ai_call_summary(
    request: Request,
    property_id: uuid.UUID | None = Query(default=None),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Aggregates `objektakte_ai_call` of the tenant: cost in EUR, tokens and number of calls
    per property (`by_property`, calls without a resolved property in one row with
    `property_id=null`) and per calendar month of `requested_at` (`by_month`, `YYYY-MM`, UTC).
    `from`/`to` are inclusive calendar days; `property_id` narrows both groupings. Cost sums
    keep six decimals as decimal strings (the UI formats `1.234,56 EUR`), tokens are integers."""
    if from_ is not None and to is not None and from_ > to:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Zeitraum ist ungültig (von > bis).")
    async with tenant_tx(request, principal) as session:
        filters = [ObjektakteAiCall.tenant_id == principal.tenant_id]
        if property_id is not None:
            filters.append(ObjektakteAiCall.property_id == property_id)
        if from_ is not None:
            filters.append(
                ObjektakteAiCall.requested_at >= datetime.combine(from_, time.min, tzinfo=UTC)
            )
        if to is not None:
            filters.append(
                ObjektakteAiCall.requested_at <= datetime.combine(to, time.max, tzinfo=UTC)
            )
        calls = func.count(ObjektakteAiCall.id)
        tokens_in = func.coalesce(func.sum(ObjektakteAiCall.tokens_in), 0)
        tokens_out = func.coalesce(func.sum(ObjektakteAiCall.tokens_out), 0)
        cost = func.coalesce(func.sum(ObjektakteAiCall.cost_eur), 0)

        by_property_rows = (
            await session.execute(
                select(
                    ObjektakteAiCall.property_id,
                    Property.number,
                    Property.name,
                    calls,
                    tokens_in,
                    tokens_out,
                    cost,
                )
                .outerjoin(Property, Property.id == ObjektakteAiCall.property_id)
                .where(*filters)
                .group_by(ObjektakteAiCall.property_id, Property.number, Property.name)
                .order_by(Property.number.nulls_last(), Property.name)
            )
        ).all()
        month = func.to_char(func.timezone("UTC", ObjektakteAiCall.requested_at), "YYYY-MM").label(
            "month"
        )
        by_month_rows = (
            await session.execute(
                select(month, calls, tokens_in, tokens_out, cost)
                .where(*filters)
                .group_by(month)
                .order_by(month)
            )
        ).all()
        total = (
            await session.execute(select(calls, tokens_in, tokens_out, cost).where(*filters))
        ).one()
        return {
            "property_id": str(property_id) if property_id else None,
            "from": from_.isoformat() if from_ else None,
            "to": to.isoformat() if to else None,
            "by_property": [
                {
                    "property_id": str(pid) if pid else None,
                    "property_number": number,
                    "property_name": name,
                    "calls": int(n),
                    "tokens_in": int(t_in),
                    "tokens_out": int(t_out),
                    "cost_eur": _money(c),
                }
                for pid, number, name, n, t_in, t_out, c in by_property_rows
            ],
            "by_month": [
                {
                    "month": m,
                    "calls": int(n),
                    "tokens_in": int(t_in),
                    "tokens_out": int(t_out),
                    "cost_eur": _money(c),
                }
                for m, n, t_in, t_out, c in by_month_rows
            ],
            "total": {
                "calls": int(total[0]),
                "tokens_in": int(total[1]),
                "tokens_out": int(total[2]),
                "cost_eur": _money(total[3]),
            },
        }
