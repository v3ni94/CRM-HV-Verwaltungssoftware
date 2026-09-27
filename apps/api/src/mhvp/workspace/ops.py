"""Operations metrics per job for monitoring and alerts (M9, section 16 Beobachtbarkeit).

Counts only, no personal data. JSON for the admin UI, Prometheus text format for scraping.
Job results with a protocol (A67 ``ops.backup_verify``: status, duration, checked file,
error) are read from Redis and returned under ``jobs``; they are gauges in Prometheus.

Monitoring access (M9-04a, operator decision 26.09.2026): a platform administrator issues an
API key that carries only ``platform:metrics:read`` (``/platform/ops/metrics-keys``). The key
reuses the ``api_key`` table and is stored under a tenant chosen by the administrator (the
key format and RLS need a tenant); that tenant is a storage location only, the key holds no
tenant permission and ``require_permission`` rejects it everywhere else.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from mhvp.core.auth import tokens
from mhvp.core.auth.permissions import PLATFORM_METRICS_READ
from mhvp.core.auth.principal import (
    Principal,
    format_api_key,
    require_platform_admin,
    require_platform_metrics_read,
    sessions,
)
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import ApiKey, Tenant, TenantStatus
from mhvp.platform.schemas import ApiKeyOut
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
    request: Request,
    format: str = "json",
    _: Principal = Depends(require_platform_metrics_read),
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


# Monitoring keys (M9-04a) ------------------------------------------------------------------


class MetricsKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    tenant_id: uuid.UUID | None = Field(
        default=None,
        description="Speicherort des Schlüssels (Mandant). Fehlt die Angabe, gilt der Mandant "
        "des aktuellen Mandantenwechsels. Der Schlüssel erhält keine Mandantenrechte.",
    )
    expires_at: datetime | None = None


class MetricsKeyOut(ApiKeyOut):
    tenant_id: uuid.UUID


class MetricsKeyCreated(MetricsKeyOut):
    key: str = Field(description="Wird nur einmal angezeigt")


def _metrics_key_out(key: ApiKey) -> MetricsKeyOut:
    return MetricsKeyOut(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scopes=key.scopes,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        tenant_id=key.tenant_id,
    )


async def _active_tenant_ids(request: Request) -> list[uuid.UUID]:
    async with platform_transaction(sessions(request)) as session:
        return list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )


@router.get("/metrics-keys", summary="API-Schlüssel der Überwachung")
async def list_metrics_keys(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> list[MetricsKeyOut]:
    factory = sessions(request)
    out: list[MetricsKeyOut] = []
    for tenant_id in await _active_tenant_ids(request):
        async with tenant_transaction(factory, tenant_id) as session:
            keys = await session.scalars(
                select(ApiKey)
                .where(ApiKey.scopes == [PLATFORM_METRICS_READ])
                .order_by(ApiKey.created_at)
            )
            out.extend(_metrics_key_out(k) for k in keys.all())
    return out


@router.post("/metrics-keys", status_code=201, summary="API-Schlüssel der Überwachung erzeugen")
async def create_metrics_key(
    body: MetricsKeyCreate,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> MetricsKeyCreated:
    """Issues a key with exactly ``platform:metrics:read`` (M9-04a). Only platform
    administrators with a session token; the secret is returned once."""
    tenant_id = body.tenant_id or principal.tenant_id
    if tenant_id is None:
        raise ProblemError(ErrorCodes.TENANT_SELECTION)
    if tenant_id not in await _active_tenant_ids(request):
        raise ProblemError(ErrorCodes.NOT_FOUND, developer_message="Unknown or inactive tenant.")
    prefix, secret = secrets.token_hex(6), tokens.new_opaque_secret()
    async with tenant_transaction(sessions(request), tenant_id) as session:
        key = ApiKey(
            tenant_id=tenant_id,
            name=body.name,
            prefix=prefix,
            secret_hash=tokens.sha256_hex(secret),
            scopes=[PLATFORM_METRICS_READ],
            expires_at=body.expires_at,
            created_by=principal.user_id,
        )
        session.add(key)
        await session.flush()
        await emit(
            session,
            tenant_id=tenant_id,
            type="api_key.created",
            entity_type="api_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
            payload={"name": key.name, "scopes": key.scopes, "platform": True},
        )
        return MetricsKeyCreated(
            **_metrics_key_out(key).model_dump(), key=format_api_key(tenant_id, prefix, secret)
        )


@router.delete(
    "/metrics-keys/{key_id}", status_code=204, summary="API-Schlüssel der Überwachung widerrufen"
)
async def revoke_metrics_key(
    key_id: uuid.UUID, request: Request, principal: Principal = Depends(require_platform_admin)
) -> Response:
    factory = sessions(request)
    for tenant_id in await _active_tenant_ids(request):
        async with tenant_transaction(factory, tenant_id) as session:
            key = await session.get(ApiKey, key_id)
            if key is None or key.scopes != [PLATFORM_METRICS_READ]:
                continue
            if key.revoked_at is not None:
                raise ProblemError(ErrorCodes.NOT_FOUND)
            key.revoked_at = datetime.now(UTC)
            await emit(
                session,
                tenant_id=tenant_id,
                type="api_key.revoked",
                entity_type="api_key",
                entity_id=key.id,
                actor_user_id=principal.user_id,
                payload={"platform": True},
            )
            return Response(status_code=204)
    raise ProblemError(ErrorCodes.NOT_FOUND)
