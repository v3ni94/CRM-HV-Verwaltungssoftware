"""Operations metrics per job for monitoring and alerts (M9, section 16 Beobachtbarkeit).

Counts only, no personal data. JSON for the admin UI, Prometheus text format for scraping.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import func, select

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus

router = APIRouter(prefix="/platform/ops", tags=["Betrieb"])

# metric name -> alert when value > 0 (failures), informational otherwise
ALERTING = {
    "webhook_deliveries_failed",
    "document_mirrors_failed",
    "ai_runs_failed_24h",
}


async def collect(request: Request) -> dict[str, int]:
    from mhvp.ai.models import AiTaskRun, RunStatus
    from mhvp.core.webhooks import DeliveryStatus, WebhookDelivery
    from mhvp.documents.models import DocumentMirror, MirrorStatus
    from mhvp.workspace.models import Notification

    factory = sessions(request)
    async with platform_transaction(factory) as session:
        tenant_ids: list[uuid.UUID] = list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    since = datetime.now(UTC) - timedelta(hours=24)
    totals = {
        "tenants_active": len(tenant_ids),
        "webhook_deliveries_pending": 0,
        "webhook_deliveries_failed": 0,
        "document_mirrors_pending": 0,
        "document_mirrors_failed": 0,
        "ai_runs_24h": 0,
        "ai_runs_failed_24h": 0,
        "notifications_unread": 0,
    }
    queries: dict[str, Any] = {
        "webhook_deliveries_pending": select(func.count()).where(
            WebhookDelivery.status == DeliveryStatus.PENDING
        ),
        "webhook_deliveries_failed": select(func.count()).where(
            WebhookDelivery.status == DeliveryStatus.FAILED
        ),
        "document_mirrors_pending": select(func.count()).where(
            DocumentMirror.status.in_((MirrorStatus.PENDING, MirrorStatus.SUBMITTED))
        ),
        "document_mirrors_failed": select(func.count()).where(
            DocumentMirror.status == MirrorStatus.FAILED
        ),
        "ai_runs_24h": select(func.count()).where(AiTaskRun.created_at >= since),
        "ai_runs_failed_24h": select(func.count()).where(
            AiTaskRun.created_at >= since, AiTaskRun.status == RunStatus.FAILED
        ),
        "notifications_unread": select(func.count()).where(Notification.read_at.is_(None)),
    }
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            for name, query in queries.items():
                totals[name] += int(await session.scalar(query) or 0)
    return totals


@router.get("/metrics", summary="Betriebskennzahlen je Job (JSON oder Prometheus)")
async def metrics(
    request: Request, format: str = "json", _: Principal = Depends(require_platform_admin)
) -> Response:
    values = await collect(request)
    if format == "prometheus":
        lines = []
        for name, value in values.items():
            lines += [f"# TYPE mhvp_{name} gauge", f"mhvp_{name} {value}"]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
    alerts = sorted(n for n in ALERTING if values.get(n, 0) > 0)
    return JSONResponse({"metrics": values, "alerts": alerts})
