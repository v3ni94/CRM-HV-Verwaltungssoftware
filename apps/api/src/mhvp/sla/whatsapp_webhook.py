"""Meta Cloud API webhook for WhatsApp status updates (M35). This endpoint is outside tenant
authentication by design (Meta calls it directly): the GET verification uses the platform wide
``MHVP_WHATSAPP_VERIFY_TOKEN``, and POST deliveries are checked with an HMAC-SHA256 signature
over the raw body using ``MHVP_WHATSAPP_APP_SECRET`` (``X-Hub-Signature-256``). See
``docs/integrations/whatsapp.md`` for the setup at Meta."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.sla.models import WhatsAppConfig
from mhvp.sla.whatsapp import apply_status_update, verify_webhook_signature

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Webhook"])


@router.get("/webhook", summary="Webhook-Verifizierung (Meta Cloud API)")
async def verify(
    request: Request,
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> Response:
    settings: Settings = request.app.state.settings
    expected = (
        settings.whatsapp_verify_token.get_secret_value()
        if settings.whatsapp_verify_token
        else None
    )
    if hub_mode == "subscribe" and expected and hub_verify_token == expected:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook", summary="Statuswebhook (Meta Cloud API)")
async def receive(request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    raw = await request.body()
    secret = (
        settings.whatsapp_app_secret.get_secret_value() if settings.whatsapp_app_secret else None
    )
    signature = request.headers.get("X-Hub-Signature-256")
    if not secret or not verify_webhook_signature(secret, raw, signature):
        log.warning("whatsapp webhook: invalid or missing signature")
        return {"status": "ignored"}
    import json

    try:
        payload = json.loads(raw)
    except ValueError:
        return {"status": "ignored"}
    updates: list[tuple[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for status in change.get("value", {}).get("statuses", []):
                message_id = status.get("id")
                new_status = status.get("status")
                if message_id and new_status:
                    updates.append((message_id, new_status))
    if updates:
        await _apply_updates(settings, updates)
    return {"status": "ok"}


async def _apply_updates(settings: Settings, updates: list[tuple[str, str]]) -> None:
    """Looks up the delivery row of each status update across tenants (the webhook carries no
    tenant id, only a WhatsApp phone number id): one tenant transaction per active tenant, first
    match wins. Acceptable at the current low message volume; revisit if this becomes a
    bottleneck (docs/OPEN_QUESTIONS.md)."""
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        remaining = dict(updates)
        for tenant_id in tenant_ids:
            if not remaining:
                break
            async with tenant_transaction(factory, tenant_id) as session:
                config = await session.scalar(
                    select(WhatsAppConfig).where(WhatsAppConfig.tenant_id == tenant_id)
                )
                if config is None:
                    continue
                for message_id, new_status in list(remaining.items()):
                    delivery = await apply_status_update(session, message_id, new_status)
                    if delivery is not None:
                        del remaining[message_id]
    finally:
        await engine.dispose()
