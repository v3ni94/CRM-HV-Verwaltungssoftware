"""Meta Cloud API webhook for WhatsApp status updates (M35). This endpoint is outside tenant
authentication by design (Meta calls it directly): the GET verification uses the platform wide
``MHVP_WHATSAPP_VERIFY_TOKEN``, and POST deliveries are checked with an HMAC-SHA256 signature
over the raw body using ``MHVP_WHATSAPP_APP_SECRET`` (``X-Hub-Signature-256``). See
``docs/integrations/whatsapp.md`` for the setup at Meta."""

from __future__ import annotations

import hmac
import logging
import time
import uuid

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ErrorCodes
from mhvp.core.uploads import read_body_limited
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.sla.models import WhatsAppConfig
from mhvp.sla.whatsapp import (
    KNOWN_STATUSES,
    apply_status_update,
    status_timestamp_ok,
    verify_webhook_signature,
)

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 256 * 1024

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
    if (
        hub_mode == "subscribe"
        and expected
        and hmac.compare_digest(hub_verify_token.encode(), expected.encode())
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook", summary="Statuswebhook (Meta Cloud API)")
async def receive(request: Request) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    # Size limit before the HMAC check and before any parsing (GAI-315).
    raw = await read_body_limited(
        request,
        MAX_BODY_BYTES,
        error=ErrorCodes.WEBHOOK_TOO_LARGE,
        detail="Webhook-Inhalt zu groß.",
    )
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
    now = time.time()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for status in change.get("value", {}).get("statuses", []):
                message_id = status.get("id")
                new_status = status.get("status")
                if not message_id or new_status not in KNOWN_STATUSES:
                    continue
                if not status_timestamp_ok(status.get("timestamp"), now=now):
                    log.warning("whatsapp webhook: status outside the replay window ignored")
                    continue
                updates.append((message_id, new_status))
    if updates:
        await _apply_updates(request, updates)
    return {"status": "ok"}


async def _apply_updates(request: Request, updates: list[tuple[str, str]]) -> None:
    """Looks up the delivery row of each status update across tenants (the webhook carries no
    tenant id, only a WhatsApp phone number id): one tenant transaction per active tenant, first
    match wins. Acceptable at the current low message volume; revisit if this becomes a
    bottleneck (docs/OPEN_QUESTIONS.md)."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.resources.session_factory
    async with platform_transaction(factory) as session:
        tenant_ids: list[uuid.UUID] = list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    # Kept in payload order so "delivered" then "read" in one delivery both apply (GAH-212).
    remaining = list(updates)
    for tenant_id in tenant_ids:
        if not remaining:
            break
        async with tenant_transaction(factory, tenant_id) as session:
            config = await session.scalar(
                select(WhatsAppConfig).where(WhatsAppConfig.tenant_id == tenant_id)
            )
            if config is None:
                continue
            found: set[str] = set()
            for message_id, new_status in remaining:
                delivery = await apply_status_update(session, message_id, new_status)
                if delivery is not None:
                    found.add(message_id)
            remaining = [u for u in remaining if u[0] not in found]
