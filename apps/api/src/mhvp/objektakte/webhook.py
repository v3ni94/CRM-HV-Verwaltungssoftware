"""M29 Stufe 4: webhook receiver ``POST /api/v1/integrations/objektakte/webhook``.

objektakte sends ``document.filed`` and ``object.taken_over`` (contract in
docs/integrations/objektakte.md) with

* ``X-Objektakte-Signature: sha256=<hex HMAC-SHA256 of the raw body with the secret>``,
* ``X-Objektakte-Event: <event>`` (must equal ``event`` in the body),
* optional ``X-MHVP-Timestamp: <unix seconds>`` (GAH-202): when sent, the signature is the
  HMAC over ``"{timestamp}." + body`` and the timestamp must lie within
  ``WINDOW_SECONDS``; without the header the body-only signature still applies unless the
  tenant switch ``objektakte_webhook_require_timestamp`` is on (default off, AI07-01).

The secret comes from ``OBJEKTAKTE_WEBHOOK_SECRET`` (environment, never the database); without
it every delivery is refused (401). Deliveries belong to the tenant named in
``OBJEKTAKTE_TENANT``. Idempotency over (event, object number, document id): the first delivery
is processed and recorded in ``objektakte_webhook_receipt``, every repetition answers 200 with
``"status": "duplicate"`` and changes nothing, so the retries of objektakte never create a second
document. ``document.filed`` becomes a CRM document linked to the property
(``mhvp.objektakte.dms_service.link_filed_document``); ``object.taken_over`` is recorded as a
domain event only. Unknown events are recorded as ``ignored``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mhvp.core import hmac_signature
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_body_limited
from mhvp.objektakte import dms_service as svc
from mhvp.objektakte.dms_models import ObjektakteWebhookReceipt
from mhvp.objektakte.dms_routers import configured_tenant_id

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/objektakte", tags=["objektakte-dms"])

SIGNATURE_HEADER = "X-Objektakte-Signature"
TIMESTAMP_HEADER = "X-MHVP-Timestamp"
WINDOW_SECONDS = 300
EVENT_HEADER = "X-Objektakte-Event"
MAX_BODY_BYTES = 256 * 1024
EVENT_DOCUMENT_FILED = "document.filed"
EVENT_OBJECT_TAKEN_OVER = "object.taken_over"


def sign(secret: str, body: bytes) -> str:
    """Header value objektakte sends (used by tests and the handbook)."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def sign_timestamped(secret: str, timestamp: int | str, body: bytes) -> str:
    """Header value with ``X-MHVP-Timestamp`` (GAH-202)."""
    return "sha256=" + hmac_signature.mac_hex(secret, timestamp, body)


def verify(secret: str, signature: str | None, body: bytes) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    return hmac_signature.equal(sign(secret, body), signature.strip())


def verify_timestamped(
    secret: str, timestamp: str | None, signature: str | None, body: bytes, *, now: float
) -> str | None:
    """``None`` when valid, otherwise ``missing``, ``stale`` or ``bad``."""
    if not secret:
        return "missing"
    return hmac_signature.check(secret, body, timestamp, signature, now=now, window=WINDOW_SECONDS)


async def _require_timestamp(request: Request, tenant_id: uuid.UUID) -> bool:
    from mhvp.platform.models import TenantSettings

    factory = request.app.state.resources.session_factory
    async with tenant_transaction(factory, tenant_id) as session:
        value = await session.scalar(select(TenantSettings.objektakte_webhook_require_timestamp))
    return bool(value)


def _occurred_at(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


@router.post("/webhook", summary="Webhook objektakte (HMAC, idempotent)")
async def receive(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    # Size check before reading (GAH-202): a declared oversized body is refused unread.
    raw = await read_body_limited(
        request,
        MAX_BODY_BYTES,
        error=ErrorCodes.WEBHOOK_TOO_LARGE,
        detail="Webhook-Inhalt zu groß.",
    )
    secret = (
        settings.objektakte_webhook_secret.get_secret_value()
        if settings.objektakte_webhook_secret
        else ""
    )
    signature = request.headers.get(SIGNATURE_HEADER)
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    if timestamp is not None:
        reason = verify_timestamped(secret, timestamp, signature, raw, now=time.time())
        if reason is not None:
            log.warning("objektakte webhook: timestamped signature refused (%s)", reason)
            raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)
    elif not verify(secret, signature, raw):
        log.warning("objektakte webhook: invalid or missing signature")
        raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)
    tenant_id = await configured_tenant_id(request)
    if tenant_id is None:
        raise ProblemError(ErrorCodes.OBJEKTAKTE_NOT_CONFIGURED)
    if timestamp is None and await _require_timestamp(request, tenant_id):
        log.warning("objektakte webhook: timestamp header required by tenant switch")
        raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)

    try:
        payload = json.loads(raw)
    except ValueError:
        raise _invalid("Webhook-Inhalt ist kein JSON.") from None
    if not isinstance(payload, dict):
        raise _invalid("Webhook-Inhalt ist kein Objekt.")
    event = payload.get("event")
    if not isinstance(event, str) or not event or len(event) > 64:
        raise _invalid("event fehlt.")
    header_event = request.headers.get(EVENT_HEADER)
    if header_event is not None and header_event != event:
        raise _invalid("X-Objektakte-Event passt nicht zum Inhalt.")
    object_number = payload.get("object_number")
    if not isinstance(object_number, str) or not object_number.strip() or len(object_number) > 16:
        raise _invalid("object_number fehlt.")
    object_number = object_number.strip()

    raw_document = payload.get("document")
    document_ref = raw_document.get("id") if isinstance(raw_document, dict) else None
    doc: svc.FiledDocument | None = None
    if event == EVENT_DOCUMENT_FILED:
        try:
            doc = svc.parse_document(raw_document)
        except ValueError as exc:
            raise _invalid(str(exc)) from None
    valid_ref = isinstance(document_ref, int) and not isinstance(document_ref, bool)
    source_document_id = str(document_ref) if valid_ref else ""
    body_hash = hashlib.sha256(raw).hexdigest()

    factory = request.app.state.resources.session_factory
    key = (
        ObjektakteWebhookReceipt.event == event,
        ObjektakteWebhookReceipt.object_number == object_number,
        ObjektakteWebhookReceipt.source_document_id == source_document_id,
    )
    async with tenant_transaction(factory, tenant_id) as session:
        seen = await session.scalar(select(ObjektakteWebhookReceipt).where(*key))
        if seen is not None:
            return _duplicate(seen)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            outcome = "ignored"
            document_id: uuid.UUID | None = None
            property_id: uuid.UUID | None = None
            if doc is not None:
                result = await svc.link_filed_document(
                    session, tenant_id, object_number=object_number, doc=doc, actor_user_id=None
                )
                outcome, document_id, property_id = (
                    result.outcome,
                    result.document_id,
                    result.property_id,
                )
            elif event == EVENT_OBJECT_TAKEN_OVER:
                prop = await svc.property_by_number(session, tenant_id, object_number)
                property_id = prop.id if prop is not None else None
                outcome = "recorded"
                await emit(
                    session,
                    tenant_id=tenant_id,
                    type="objektakte.object_taken_over",
                    entity_type="property",
                    entity_id=property_id,
                    actor_user_id=None,
                    payload={
                        "object_number": object_number,
                        "occurred_at": payload.get("occurred_at")
                        if isinstance(payload.get("occurred_at"), str)
                        else None,
                    },
                )
            receipt = ObjektakteWebhookReceipt(
                tenant_id=tenant_id,
                event=event,
                object_number=object_number,
                source_document_id=source_document_id,
                occurred_at=_occurred_at(payload.get("occurred_at")),
                body_sha256=body_hash,
                outcome=outcome,
                document_id=document_id,
                property_id=property_id,
            )
            session.add(receipt)
            await session.flush()
            return {
                "status": "processed" if outcome != "ignored" else "ignored",
                "event": event,
                "outcome": outcome,
                "document_id": str(document_id) if document_id else None,
                "property_id": str(property_id) if property_id else None,
            }
    except IntegrityError:
        # A concurrent delivery of the same key won the race; its result stands.
        async with tenant_transaction(factory, tenant_id) as session:
            seen = await session.scalar(select(ObjektakteWebhookReceipt).where(*key))
        if seen is None:
            raise
        return _duplicate(seen)


def _duplicate(seen: ObjektakteWebhookReceipt) -> dict[str, Any]:
    return {
        "status": "duplicate",
        "event": seen.event,
        "outcome": seen.outcome,
        "document_id": str(seen.document_id) if seen.document_id else None,
        "property_id": str(seen.property_id) if seen.property_id else None,
    }
