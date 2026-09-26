"""Webhooks (section 12): subscriptions, signed delivery, retries, SSRF guard.

Signature header ``X-MHVP-Signature: t=<unix>,v1=<hex>`` with
``v1 = HMAC-SHA256(secret, "<t>.<raw body>")``. Receivers should reject timestamps older
than five minutes. Retry schedule: 1 min, 5 min, 30 min, 2 h, 6 h, 24 h, then failed.
"""

import hashlib
import hmac
import ipaddress
import json
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import DomainEvent

RETRY_SCHEDULE_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200, 21600, 86400)

# Event types offered to subscribers (section 12, ``<entity>.<action>``; A69). The catalogue
# documents the contract of the payloads (docs/integrations/webhooks.md): identifiers, field
# names and amounts only, never IBAN, names, addresses or document contents. A subscription
# may name any ``domain_event.type``; the catalogue is the documented, stable subset.
EVENT_TYPES: dict[str, str] = {
    "contact.created": "Kontakt angelegt (Kontakt-ID)",
    "contact.updated": "Kontaktstammdaten geändert (Kontakt-ID, Namen der geänderten Felder)",
    "contact.deleted": "Kontakt gelöscht (Kontakt-ID)",
    "contact.mandate_iban_changed": "IBAN einer Bankverbindung mit SEPA-Mandat geändert "
    "(Kontakt-ID, Mandatsreferenz)",
    "tenant_settings.updated": "Mandanteneinstellungen geändert",
    "invoice.issued": "Verwalterhonorar-Rechnung ausgestellt (Rechnungs-ID, Nummer, Datum, "
    "Objekt, Beträge, XRechnung-URL)",
    "admin_fee_invoice.xrechnung_stored": "XRechnung-XML zur Honorarrechnung abgelegt",
    "webhook_subscription.created": "Webhook-Abonnement angelegt",
}
SIGNATURE_HEADER = "X-MHVP-Signature"
DELIVERY_TIMEOUT_SECONDS = 10.0


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WebhookSubscription(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "webhook_subscription"

    url: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    secret: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(200))


class WebhookDelivery(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "webhook_delivery"
    __table_args__ = (UniqueConstraint("subscription_id", "event_id"),)

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_subscription.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_event.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            name="webhook_delivery_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(200))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UnsafeWebhookTargetError(ValueError):
    pass


def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, body: bytes, header: str, *, now: int, tolerance: int = 300) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    try:
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(now - timestamp) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, body, timestamp), header)


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


@dataclass(frozen=True)
class PinnedTarget:
    """A checked webhook target: ``url`` is what the HTTP client connects to, ``headers`` and
    ``extensions`` restore the original host for the ``Host`` header and the TLS name check.
    When the target is pinned, ``url`` carries the checked IP address instead of the host name,
    so the client cannot resolve the name a second time (DNS rebinding between check and
    call, Review 1.22 Nr. 12). Unpinned (private targets allowed) all three are pass-through."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)


def _syntax(url: str, *, allow_private: bool) -> Any:
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise UnsafeWebhookTargetError("URL must be http(s) with a host")
    if parts.username or parts.password:
        raise UnsafeWebhookTargetError("credentials in the URL are not allowed")
    if not allow_private and parts.scheme != "https":
        raise UnsafeWebhookTargetError("only https targets are allowed")
    return parts


def _resolve_public(hostname: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeWebhookTargetError("host cannot be resolved") from exc
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeWebhookTargetError("target resolves to a non-public address")
    return addresses


def check_target(url: str, *, allow_private: bool, resolve: bool = True) -> None:
    """Reject non-HTTP(S) URLs and, unless allowed, targets resolving to non-public addresses.
    ``resolve=False`` keeps the check to the URL itself (no DNS query, e.g. for a dry run whose
    host name is chosen freely by the caller, Review 1.22 Nr. 13)."""
    parts = _syntax(url, allow_private=allow_private)
    if allow_private or not resolve:
        return
    _resolve_public(parts.hostname, parts.port or 443)


def pin_target(url: str, *, allow_private: bool) -> PinnedTarget:
    """``check_target`` plus pinning: the call goes to the first checked address with the
    original host in ``Host`` and as TLS server name (``sni_hostname`` extension of httpx)."""
    parts = _syntax(url, allow_private=allow_private)
    if allow_private:
        return PinnedTarget(url=url)
    hostname = parts.hostname
    port = parts.port or 443
    address = _resolve_public(hostname, port)[0]
    literal = f"[{address}]" if ":" in address else address
    netloc = f"{literal}:{port}" if parts.port else literal
    pinned = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    host_header = f"{hostname}:{parts.port}" if parts.port else hostname
    return PinnedTarget(
        url=pinned, headers={"Host": host_header}, extensions={"sni_hostname": hostname}
    )


def matches(subscription: WebhookSubscription, event_type: str) -> bool:
    return "*" in subscription.event_types or event_type in subscription.event_types


def event_body(event: DomainEvent) -> bytes:
    document = {
        "id": str(event.id),
        "type": event.type,
        "tenant_id": str(event.tenant_id),
        "entity_type": event.entity_type,
        "entity_id": str(event.entity_id) if event.entity_id else None,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": event.correlation_id,
        "payload": event.payload,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


async def enqueue_deliveries(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Create pending deliveries for events without one (idempotent per subscription/event)."""
    subscriptions = (
        await session.scalars(
            select(WebhookSubscription).where(
                WebhookSubscription.tenant_id == tenant_id, WebhookSubscription.active.is_(True)
            )
        )
    ).all()
    created = 0
    now = datetime.now(UTC)
    for subscription in subscriptions:
        delivered = select(WebhookDelivery.event_id).where(
            WebhookDelivery.subscription_id == subscription.id
        )
        events = (
            await session.scalars(
                select(DomainEvent).where(
                    DomainEvent.tenant_id == tenant_id,
                    DomainEvent.occurred_at >= subscription.created_at,
                    DomainEvent.id.not_in(delivered),
                )
            )
        ).all()
        for event in events:
            if matches(subscription, event.type):
                session.add(
                    WebhookDelivery(
                        tenant_id=tenant_id,
                        subscription_id=subscription.id,
                        event_id=event.id,
                        next_attempt_at=now,
                    )
                )
                created += 1
    await session.flush()
    return created


async def attempt_delivery(
    session: AsyncSession,
    delivery: WebhookDelivery,
    *,
    client: httpx.AsyncClient,
    allow_private: bool,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    subscription = await session.get(WebhookSubscription, delivery.subscription_id)
    event = await session.get(DomainEvent, delivery.event_id)
    if subscription is None or event is None or not subscription.active:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error = "subscription inactive"
        delivery.next_attempt_at = None
        return
    body = event_body(event)
    headers = {
        "Content-Type": "application/json",
        "X-MHVP-Event": event.type,
        "X-MHVP-Delivery": str(delivery.id),
        SIGNATURE_HEADER: sign(subscription.secret, body, int(time.time())),
    }
    delivery.attempts += 1
    try:
        target = pin_target(subscription.url, allow_private=allow_private)
        response = await client.post(
            target.url,
            content=body,
            headers=headers | target.headers,
            extensions=target.extensions,
            follow_redirects=False,
        )
        delivery.last_status_code = response.status_code
        ok = 200 <= response.status_code < 300
        delivery.last_error = None if ok else f"HTTP {response.status_code}"
    except UnsafeWebhookTargetError as exc:
        ok, delivery.last_error = False, str(exc)[:200]
    except httpx.HTTPError as exc:
        ok, delivery.last_error = False, type(exc).__name__
    if ok:
        delivery.status = DeliveryStatus.SUCCEEDED
        delivery.delivered_at = now
        delivery.next_attempt_at = None
    elif delivery.attempts > len(RETRY_SCHEDULE_SECONDS):
        delivery.status = DeliveryStatus.FAILED
        delivery.next_attempt_at = None
    else:
        delay = RETRY_SCHEDULE_SECONDS[delivery.attempts - 1]
        delivery.next_attempt_at = now + timedelta(seconds=delay)


async def deliver_due(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    client: httpx.AsyncClient,
    allow_private: bool,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    now = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.tenant_id == tenant_id,
                WebhookDelivery.status == DeliveryStatus.PENDING,
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for delivery in due:
        await attempt_delivery(
            session, delivery, client=client, allow_private=allow_private, now=now
        )
    return len(due)


def redeliver(delivery: WebhookDelivery, *, now: datetime | None = None) -> None:
    """Manual redelivery from the UI/API: reset to pending, keep the attempt history."""
    delivery.status = DeliveryStatus.PENDING
    delivery.next_attempt_at = now or datetime.now(UTC)
