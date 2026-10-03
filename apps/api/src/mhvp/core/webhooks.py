"""Webhooks (section 12): subscriptions, signed delivery, retries, SSRF guard.

Signature header ``X-MHVP-Signature: t=<unix>,v1=<hex>`` with
``v1 = HMAC-SHA256(secret, "<t>.<raw body>")``. Receivers should reject timestamps older
than five minutes. Retry schedule: 1 min, 5 min, 30 min, 2 h, 6 h, 24 h, then failed.

Dispatch (GAM-501 to GAM-503): the minute job never holds a database transaction open during
an HTTP call. Each delivery is claimed in its own short transaction (``claim_delivery``:
row lock, ``attempts + 1``, ``next_attempt_at`` moved to the retry moment of this attempt as
a lease, commit), sent without a session (``send_claimed``) and its outcome written in a new
short transaction (``apply_outcome``). A worker lost between claim and outcome counts as a
failed attempt, so a delivery always reaches ``failed`` after the schedule and is never stuck.
New events are found through a watermark per subscription (``watermark_occurred_at``,
migration 0463) with an overlap window, no longer by scanning all events since creation.
Delivery order is not guaranteed (docs/integrations/webhooks.md); receivers order by
``occurred_at`` of the payload and deduplicate by ``Idempotency-Key``.
"""

import asyncio
import ipaddress
import json
import logging
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core import hmac_signature
from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import DomainEvent
from mhvp.core.ids import uuid7

log = logging.getLogger(__name__)

RETRY_SCHEDULE_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200, 21600, 86400)
# GAM-503: events are looked up from the subscription watermark minus this overlap, so an
# event whose transaction committed late (``occurred_at`` is the transaction start) is still
# found; the unique constraint (subscription, event) keeps the lookup idempotent.
ENQUEUE_OVERLAP = timedelta(minutes=15)
ENQUEUE_BATCH_LIMIT = 1000

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
    # Produced by the domains today (S12-02).
    "contact.merged": "Kontakte zusammengeführt (Ziel-Kontakt-ID, Quell-Kontakt-ID)",
    "contract.created": "Vertrag angelegt (Vertrags-ID)",
    "contract.updated": "Vertrag geändert (Vertrags-ID, Namen der geänderten Felder)",
    "contract.terminated": "Vertrag beendet (Vertrags-ID, Beendigungsdatum)",
    "contract.changed": "Vertrag fachlich geändert (Vertrags-ID, auslösender Ereignistyp)",
    "contract_payment.changed": "Zahlungsvereinbarung geändert (Vertrags-ID, auslösender "
    "Ereignistyp)",
    "journal_entry.posted": "Buchung festgeschrieben (Buchungs-ID, Datum, Betrag)",
    "journal_entry.reversed": "Buchung storniert (Buchungs-ID, Stornobuchungs-ID)",
    "bank_transaction.imported": "Bankumsätze importiert (Konto-ID, Importlauf-ID, Anzahl neuer "
    "Umsätze)",
    "bank_transaction.booked": "Bankumsatz gebucht, manuell, automatisch oder per Zahllauf "
    "(Umsatz-ID, Buchungs-ID, Herkunft)",
    "invoice.received": "Eingangsrechnung erfasst (Rechnungs-ID)",
    "invoice.approved": "Eingangsrechnung freigegeben (Rechnungs-ID)",
    "invoice.paid": "Eingangsrechnung bezahlt (Rechnungs-ID)",
    "invoice.posted": "Eingangsrechnung gebucht (Rechnungs-ID)",
    "dunning_case.created": "Mahnvorgang angelegt (Vorgangs-ID)",
    "dunning_case.sent": "Mahnung versendet (Vorgangs-ID, Mahnstufe)",
    "ticket.created": "Ticket angelegt (Ticket-ID)",
    "ticket.status_changed": "Ticketstatus geändert (Ticket-ID, alter und neuer Status)",
    "ticket.commented": "Ticket kommentiert (Ticket-ID, Kommentar-ID)",
    "work_order.created": "Auftrag angelegt (Auftrags-ID)",
    "work_order.quoted": "Angebot zum Auftrag erfasst (Auftrags-ID)",
    "work_order.approved": "Auftrag freigegeben (Auftrags-ID)",
    "work_order.completed": "Auftrag abgeschlossen (Auftrags-ID)",
    "document.created": "Dokument angelegt (Dokument-ID)",
    "document.shared": "Dokument im Portal freigegeben (Dokument-ID)",
    "meeting.invited": "Versammlung einberufen (Versammlungs-ID)",
    "meeting.closed": "Versammlung geschlossen (Versammlungs-ID)",
    "statement.confirmed": "Abrechnung bestätigt (Abrechnungs-ID)",
    "ai_proposal.decided": "KI-Vorschlag entschieden (Vorschlags-ID, Entscheidung)",
    "portal_account.invited": "Portalzugang eingeladen (Zugangs-ID)",
    "portal_account.activated": "Portalzugang aktiviert (Zugangs-ID)",
    "property.created": "Objekt angelegt (Objekt-ID)",
    "property.updated": "Objekt geändert (Objekt-ID)",
    "unit.updated": "Einheit geändert (Einheiten-ID)",
}
SIGNATURE_HEADER = "X-MHVP-Signature"
DELIVERY_TIMEOUT_SECONDS = 10.0
# Hard ceiling of one HTTP call (httpx timeouts apply per network operation, a target that
# trickles bytes could otherwise hold the call much longer).
DELIVERY_DEADLINE_SECONDS = 15.0
CLAIM_MARKER = "sending"


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
    # GAH-206 (migration 0441): consecutive final failures (status failed) since the last
    # successful delivery; reset on success. ``disabled_reason`` is set when the tenant switch
    # ``tenant_settings.webhook_auto_disable_after`` deactivated the subscription.
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(32))
    # GAM-503 (migration 0463): newest ``domain_event.occurred_at`` already turned into
    # deliveries; ``None`` until the first run (lookup then starts at ``created_at``).
    watermark_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    return f"t={timestamp},v1={hmac_signature.mac_hex(secret, timestamp, body)}"


def verify(secret: str, body: bytes, header: str, *, now: int, tolerance: int = 300) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    timestamp = hmac_signature.parse_timestamp(parts.get("t"))
    if timestamp is None:
        return False
    if not hmac_signature.within_window(timestamp, now=now, window=tolerance):
        return False
    return hmac_signature.equal(sign(secret, body, timestamp), header)


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


def is_known_event_type(value: str) -> bool:
    """``*``, a catalogue type or an entity wildcard ``<entity>.*`` over a catalogue entity."""
    if value == "*" or value in EVENT_TYPES:
        return True
    entity, _, action = value.partition(".")
    return action == "*" and any(t.startswith(f"{entity}.") for t in EVENT_TYPES)


def matches(subscription: WebhookSubscription, event_type: str) -> bool:
    return any(
        t == "*" or t == event_type or (t.endswith(".*") and event_type.startswith(t[:-1]))
        for t in subscription.event_types
    )


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
    """Create pending deliveries for new events (idempotent per subscription/event).

    GAM-503: per subscription only events since its watermark minus ``ENQUEUE_OVERLAP`` are
    read (index ``tenant_id, occurred_at``), at most ``ENQUEUE_BATCH_LIMIT`` per run in
    ``occurred_at, id`` order; the watermark then moves to the newest event read. Existing
    pairs are skipped by ``ON CONFLICT DO NOTHING`` (also against a parallel run).
    """
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
        since = subscription.created_at
        if subscription.watermark_occurred_at is not None:
            since = max(since, subscription.watermark_occurred_at - ENQUEUE_OVERLAP)
        known = select(WebhookDelivery.event_id).where(
            WebhookDelivery.subscription_id == subscription.id,
            WebhookDelivery.created_at >= since - ENQUEUE_OVERLAP,
        )
        events = (
            await session.scalars(
                select(DomainEvent)
                .where(
                    DomainEvent.tenant_id == tenant_id,
                    DomainEvent.occurred_at >= since,
                    DomainEvent.id.not_in(known),
                )
                .order_by(DomainEvent.occurred_at, DomainEvent.id)
                .limit(ENQUEUE_BATCH_LIMIT)
            )
        ).all()
        for event in events:
            if not matches(subscription, event.type):
                continue
            inserted = await session.scalar(
                pg_insert(WebhookDelivery)
                .values(
                    id=uuid7(),
                    tenant_id=tenant_id,
                    subscription_id=subscription.id,
                    event_id=event.id,
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                    next_attempt_at=now,
                )
                .on_conflict_do_nothing(index_elements=["subscription_id", "event_id"])
                .returning(WebhookDelivery.id)
            )
            if inserted is not None:
                created += 1
        if events:
            newest = events[-1].occurred_at
            current = subscription.watermark_occurred_at
            if current is None or newest > current:
                subscription.watermark_occurred_at = newest
    await session.flush()
    return created


@dataclass(frozen=True)
class ClaimedDelivery:
    """Everything needed to send one claimed delivery without a database session."""

    delivery_id: uuid.UUID
    tenant_id: uuid.UUID
    attempt: int
    url: str
    body: bytes
    secret: str
    headers: dict[str, str]


@dataclass(frozen=True)
class DeliveryOutcome:
    ok: bool
    status_code: int | None
    error: str | None


def _retry_delay(attempt: int) -> int:
    return RETRY_SCHEDULE_SECONDS[min(attempt, len(RETRY_SCHEDULE_SECONDS)) - 1]


async def _fail_final(
    session: AsyncSession,
    delivery: WebhookDelivery,
    subscription: WebhookSubscription | None,
    *,
    now: datetime,
) -> None:
    delivery.status = DeliveryStatus.FAILED
    delivery.next_attempt_at = None
    if subscription is not None:
        await record_final_failure(session, subscription, now=now)
    log.warning(
        "webhook delivery failed finally",
        extra={"tenant_id": str(delivery.tenant_id), "delivery_id": str(delivery.id)},
    )


async def _claim_row(
    session: AsyncSession, delivery: WebhookDelivery, *, now: datetime
) -> ClaimedDelivery | None:
    subscription = await session.get(WebhookSubscription, delivery.subscription_id)
    event = await session.get(DomainEvent, delivery.event_id)
    if subscription is None or event is None or not subscription.active:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error = "subscription inactive"
        delivery.next_attempt_at = None
        return None
    if delivery.last_error == CLAIM_MARKER and delivery.attempts > len(RETRY_SCHEDULE_SECONDS):
        # The last claim ended without an outcome (worker lost) and the schedule is used up.
        # A manual redelivery of a failed row (``redeliver``) keeps its error text and still
        # gets one attempt.
        delivery.last_error = "outcome unknown"
        await _fail_final(session, delivery, subscription, now=now)
        return None
    delivery.attempts += 1
    # Lease: until the outcome is written the row is not due again; a lost worker therefore
    # behaves like a failed attempt and the regular retry moment applies.
    delivery.next_attempt_at = now + timedelta(seconds=_retry_delay(delivery.attempts))
    delivery.last_error = CLAIM_MARKER
    return ClaimedDelivery(
        delivery_id=delivery.id,
        tenant_id=delivery.tenant_id,
        attempt=delivery.attempts,
        url=subscription.url,
        body=event_body(event),
        secret=subscription.secret,
        headers={
            "Content-Type": "application/json",
            "X-MHVP-Event": event.type,
            "X-MHVP-Delivery": str(delivery.id),
            "X-MHVP-Event-Id": str(event.id),
            # Stable per delivery: identical on every retry, so receivers can deduplicate.
            "Idempotency-Key": str(delivery.id),
        },
    )


async def claim_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime | None = None
) -> tuple[bool, ClaimedDelivery | None]:
    """Claim the oldest due delivery of the tenant (GAM-501). Returns ``(found, claim)``:
    ``found`` is False when nothing is due; ``claim`` is None when the row was closed
    instead (inactive subscription, schedule used up). The caller commits right away."""
    now = now or datetime.now(UTC)
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.tenant_id == tenant_id,
            WebhookDelivery.status == DeliveryStatus.PENDING,
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if delivery is None:
        return False, None
    claim = await _claim_row(session, delivery, now=now)
    await session.flush()
    return True, claim


async def send_claimed(
    claim: ClaimedDelivery, *, client: httpx.AsyncClient, allow_private: bool
) -> DeliveryOutcome:
    """The HTTP call of one claimed delivery; runs without any database session."""
    headers = claim.headers | {
        SIGNATURE_HEADER: sign(claim.secret, claim.body, int(time.time())),
    }
    try:
        target = pin_target(claim.url, allow_private=allow_private)
        async with asyncio.timeout(DELIVERY_DEADLINE_SECONDS):
            response = await client.post(
                target.url,
                content=claim.body,
                headers=headers | target.headers,
                extensions=target.extensions,
                follow_redirects=False,
            )
    except UnsafeWebhookTargetError as exc:
        return DeliveryOutcome(False, None, str(exc)[:200])
    except TimeoutError:
        return DeliveryOutcome(False, None, "Timeout")
    except httpx.HTTPError as exc:
        return DeliveryOutcome(False, None, type(exc).__name__)
    ok = 200 <= response.status_code < 300
    return DeliveryOutcome(ok, response.status_code, None if ok else f"HTTP {response.status_code}")


async def _apply(
    session: AsyncSession,
    delivery: WebhookDelivery,
    outcome: DeliveryOutcome,
    *,
    now: datetime,
) -> None:
    subscription = await session.get(WebhookSubscription, delivery.subscription_id)
    delivery.last_status_code = outcome.status_code
    delivery.last_error = outcome.error
    if outcome.ok:
        delivery.status = DeliveryStatus.SUCCEEDED
        delivery.delivered_at = now
        delivery.next_attempt_at = None
        if subscription is not None:
            subscription.consecutive_failures = 0
    elif delivery.attempts > len(RETRY_SCHEDULE_SECONDS):
        await _fail_final(session, delivery, subscription, now=now)
    else:
        delivery.next_attempt_at = now + timedelta(seconds=_retry_delay(delivery.attempts))


async def apply_outcome(
    session: AsyncSession,
    claim: ClaimedDelivery,
    outcome: DeliveryOutcome,
    *,
    now: datetime | None = None,
) -> bool:
    """Write the outcome of a claimed attempt in a new short transaction. Skipped (False) when
    the row changed meanwhile (manual redelivery or a newer claim)."""
    delivery = await session.scalar(
        select(WebhookDelivery).where(WebhookDelivery.id == claim.delivery_id).with_for_update()
    )
    if (
        delivery is None
        or delivery.status != DeliveryStatus.PENDING
        or delivery.attempts != claim.attempt
    ):
        return False
    await _apply(session, delivery, outcome, now=now or datetime.now(UTC))
    await session.flush()
    return True


async def attempt_delivery(
    session: AsyncSession,
    delivery: WebhookDelivery,
    *,
    client: httpx.AsyncClient,
    allow_private: bool,
    now: datetime | None = None,
) -> None:
    """One attempt inside the caller's session (tests and single manual use). The minute job
    does not use it: there claim, call and outcome run in separate transactions (GAM-501)."""
    now = now or datetime.now(UTC)
    claim = await _claim_row(session, delivery, now=now)
    if claim is None:
        return
    outcome = await send_claimed(claim, client=client, allow_private=allow_private)
    await _apply(session, delivery, outcome, now=now)


FAILURE_NOTIFICATION_KIND = "webhook.delivery_failed"
FAILURE_NOTIFICATION_PERMISSION = "webhooks:update"
AUTO_DISABLED_REASON = "consecutive_failures"


async def record_final_failure(
    session: AsyncSession, subscription: WebhookSubscription, *, now: datetime
) -> bool:
    """GAH-206: count the final failure, notify, deactivate only when the tenant switch says so.

    Every member allowed to change webhooks gets one unread notification per subscription
    (``workspace.services.notify`` is idempotent on the unread entry). Automatic deactivation
    happens only when ``tenant_settings.webhook_auto_disable_after`` is set (default off,
    question AI07-02) and the counter reached it. Returns True when deactivated.
    """
    from mhvp.banking.tasks import users_with_permission
    from mhvp.platform.models import TenantSettings
    from mhvp.workspace.services import notify

    subscription.consecutive_failures = (subscription.consecutive_failures or 0) + 1
    subscription.last_failure_at = now
    threshold = await session.scalar(
        select(TenantSettings.webhook_auto_disable_after).where(
            TenantSettings.tenant_id == subscription.tenant_id
        )
    )
    disabled = threshold is not None and subscription.consecutive_failures >= threshold
    if disabled:
        subscription.active = False
        subscription.disabled_reason = AUTO_DISABLED_REASON
    title = "Webhook automatisch deaktiviert" if disabled else "Webhook-Zustellung fehlgeschlagen"
    body = (
        f"{subscription.url[:300]}: {subscription.consecutive_failures} Zustellungen "
        "in Folge endgültig fehlgeschlagen."
    )
    for user_id in await users_with_permission(
        session, subscription.tenant_id, FAILURE_NOTIFICATION_PERMISSION
    ):
        await notify(
            session,
            tenant_id=subscription.tenant_id,
            user_id=user_id,
            kind=FAILURE_NOTIFICATION_KIND,
            title=title,
            body=body,
            target_type="webhook_subscription",
            target_id=subscription.id,
        )
    return disabled


def redeliver(delivery: WebhookDelivery, *, now: datetime | None = None) -> None:
    """Manual redelivery from the UI/API: reset to pending, keep the attempt history."""
    delivery.status = DeliveryStatus.PENDING
    delivery.next_attempt_at = now or datetime.now(UTC)
