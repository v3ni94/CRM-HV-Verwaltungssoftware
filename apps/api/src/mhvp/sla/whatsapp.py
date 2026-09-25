"""WhatsApp Business Platform (Meta Cloud API) as a second escalation channel (M35, operator
decision 25.09.2026). Only approved message templates are sent, never free text: Meta only
allows a business initiated message outside the 24 hour customer service window as a template
message, and MHVP escalations are always business initiated (docs/rules/M21-05.md). SMS stays
available as a fallback channel per tenant (``WhatsAppConfig.sms_fallback``).

Consent (rule 0.1.13, contacts consent model): a message to a contact (tenant, owner) requires
a recorded, non revoked consent of kind ``whatsapp`` (``mhvp.contacts.models.ConsentKind``).
Staff members (tenant members, ``Membership.mobile_phone``) are treated as an internal channel
and are allowed without contact consent (documented assumption, ``docs/ASSUMPTIONS.md``).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Consent, ConsentKind
from mhvp.core.config import Settings
from mhvp.sla.models import WhatsAppConfig, WhatsAppDelivery

WHATSAPP_TIMEOUT_SECONDS = 10.0
WHATSAPP_TEST_TEMPLATE_KEY = "test"


class DeliveryResult:
    """Result of a channel send: ``None`` error means success."""

    __slots__ = ("error", "provider_message_id")

    def __init__(self, provider_message_id: str | None, error: str | None) -> None:
        self.provider_message_id = provider_message_id
        self.error = error


class MessagingChannel(Protocol):
    """Common shape of an outbound messaging channel (SMS gateway, WhatsApp Cloud API)."""

    async def send(
        self, to: str, template: str, params: list[str]
    ) -> DeliveryResult: ...  # pragma: no cover - protocol


async def get_config(session: AsyncSession, tenant_id: uuid.UUID) -> WhatsAppConfig | None:
    result: WhatsAppConfig | None = await session.scalar(
        select(WhatsAppConfig).where(WhatsAppConfig.tenant_id == tenant_id)
    )
    return result


async def has_whatsapp_consent(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    """True if the contact has a granted, not revoked ``whatsapp`` consent."""
    consent = await session.scalar(
        select(Consent).where(
            Consent.contact_id == contact_id,
            Consent.kind == ConsentKind.WHATSAPP,
            Consent.revoked_at.is_(None),
        )
    )
    return consent is not None


class WhatsAppCloudApi:
    """Sends approved template messages via the Meta Cloud API
    (``POST /{phone_number_id}/messages``, type ``template``). No free text path exists: the
    only public entry point is :meth:`send`, which always builds a template payload."""

    def __init__(
        self,
        config: WhatsAppConfig,
        settings: Settings,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._base_url = settings.whatsapp_api_base_url.rstrip("/")
        self._transport = http_transport

    async def send(self, to: str, template: str, params: list[str]) -> DeliveryResult:
        if not self._config.phone_number_id or not self._config.access_token:
            return DeliveryResult(None, "WhatsApp nicht eingerichtet: Nummer oder Token fehlt.")
        url = f"{self._base_url}/{self._config.phone_number_id}/messages"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": self._config.template_language or "de"},
            },
        }
        if params:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ]
        headers = {"Authorization": f"Bearer {self._config.access_token}"}
        try:
            async with httpx.AsyncClient(
                timeout=WHATSAPP_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            return DeliveryResult(None, "WhatsApp Cloud API antwortet nicht (Zeitüberschreitung).")
        except httpx.HTTPError as exc:
            return DeliveryResult(
                None, f"WhatsApp Cloud API nicht erreichbar ({type(exc).__name__})."
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except ValueError:
                detail = ""
            return DeliveryResult(
                None, f"WhatsApp Cloud API meldet HTTP {response.status_code}: {detail}"[:500]
            )
        try:
            data = response.json()
            message_id = data["messages"][0]["id"]
        except (ValueError, KeyError, IndexError):
            return DeliveryResult(
                None, "WhatsApp Cloud API: unerwartete Antwort ohne Nachrichten-ID."
            )
        return DeliveryResult(message_id, None)


def template_for(config: WhatsAppConfig, alert_type: str) -> str | None:
    return (config.template_names or {}).get(alert_type)


async def send_whatsapp(
    session: AsyncSession,
    settings: Settings,
    config: WhatsAppConfig,
    *,
    alert_id: uuid.UUID | None,
    to: str,
    alert_type: str,
    params: list[str],
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> str | None:
    """Sends a template message and records the delivery row; returns an error text or
    ``None`` on success (mirrors :func:`mhvp.sla.channels.send_sms`)."""
    template = template_for(config, alert_type)
    if not template:
        return f"Keine WhatsApp-Vorlage für Alarmtyp {alert_type!r} hinterlegt."
    if not to.strip():
        return "Keine Mobilnummer hinterlegt."
    api = WhatsAppCloudApi(config, settings, http_transport=http_transport)
    result = await api.send(to.strip(), template, params)
    session.add(
        WhatsAppDelivery(
            tenant_id=config.tenant_id,
            alert_id=alert_id,
            wa_message_id=result.provider_message_id,
            to=to.strip(),
            template_name=template,
            status="sent" if result.error is None else "failed",
            error=result.error,
        )
    )
    return result.error


def verify_webhook_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Checks ``X-Hub-Signature-256: sha256=<hex>`` against the raw request body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


async def apply_status_update(
    session: AsyncSession, wa_message_id: str, status: str
) -> WhatsAppDelivery | None:
    """Updates the delivery row's status from a Cloud API status webhook payload."""
    delivery = await session.scalar(
        select(WhatsAppDelivery).where(WhatsAppDelivery.wa_message_id == wa_message_id)
    )
    if delivery is not None:
        delivery.status = status
        delivery.updated_at = datetime.now(UTC)
    return delivery
