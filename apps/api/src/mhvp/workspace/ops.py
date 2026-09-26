"""Operations metrics per job for monitoring and alerts (M9, section 16 Beobachtbarkeit).

Counts only, no personal data. JSON for the admin UI, Prometheus text format for scraping.
Job results with a protocol (A67 ``ops.backup_verify``: status, duration, checked file,
error) are read from Redis and returned under ``jobs``; they are gauges in Prometheus.
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
from mhvp.workspace import backup_verify

router = APIRouter(prefix="/platform/ops", tags=["Betrieb"])

# metric name -> alert when value > 0 (failures), informational otherwise
ALERTING = {
    "webhook_deliveries_failed",
    "document_mirrors_failed",
    "ai_runs_failed_24h",
    "backup_verify_failed",
    "backup_verify_stale",
}


async def job_results(request: Request) -> dict[str, dict[str, Any]]:
    """Protocol of the last run per job (A67). Redis errors yield the ``missing`` view."""
    resources = getattr(request.app.state, "resources", None)
    record = None
    if resources is not None:
        try:
            record = await backup_verify.load_result(resources.redis)
        except Exception:  # metrics must not fail on a Redis error
            record = None
    return {"backup_verify": backup_verify.summarize(record)}


def job_gauges(jobs: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Numeric view of the job protocol for alerts and Prometheus."""
    result = jobs["backup_verify"]
    return {
        "backup_verify_ok": int(result["status"] == backup_verify.STATUS_OK),
        "backup_verify_failed": int(result["status"] == backup_verify.STATUS_FAILED),
        "backup_verify_not_configured": int(
            result["status"] == backup_verify.STATUS_NOT_CONFIGURED
        ),
        "backup_verify_stale": int(bool(result["stale"])),
        "backup_verify_duration_seconds": int(result["duration_seconds"] or 0),
        "backup_verify_age_seconds": int(result["age_seconds"] or 0),
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
    jobs = await job_results(request)
    values.update(job_gauges(jobs))
    if format == "prometheus":
        lines = []
        for name, value in values.items():
            lines += [f"# TYPE mhvp_{name} gauge", f"mhvp_{name} {value}"]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
    alerts = sorted(n for n in ALERTING if values.get(n, 0) > 0)
    return JSONResponse({"metrics": values, "alerts": alerts, "jobs": jobs})
