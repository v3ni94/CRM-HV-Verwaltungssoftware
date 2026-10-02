"""Gmail push notifications via Google Cloud Pub/Sub (operator decision 26.09.2026: new mails
appear immediately; the 5 minute beat sync stays as the safety net).

``POST /integrations/gmail/push`` is outside the tenant login by design: the Pub/Sub push
subscription of the operator's Google Cloud project calls it. Protection, in this order:

* size limit (``MAX_BODY_BYTES``) checked before anything is read or parsed;
* shared secret ``MHVP_GMAIL_PUSH_TOKEN`` in the query (``?token=``) or the header
  ``X-MHVP-Push-Token``; without a configured secret every delivery is refused (401);
* optionally the Pub/Sub OIDC token (``Authorization: Bearer``) when
  ``MHVP_GMAIL_PUSH_AUDIENCE`` is set: issuer accounts.google.com, audience, signature against
  Google's JWKS (fetched once per hour, so this needs outbound access to googleapis.com; the
  shared secret alone works offline).

The Pub/Sub envelope carries base64 ``message.data`` with ``{"emailAddress", "historyId"}``.
The endpoint never fetches mail inline: it sets a "sync requested" flag per address in Redis
(so a burst of notifications enqueues one job) and hands the address to the ``mail`` queue.
The job maps the address to mailboxes across tenants (platform listing of active tenants, then
one RLS bound transaction per tenant) and runs the existing history based sync per mailbox.
An unknown address is acknowledged (204) without effect; a non 2xx answer would only make
Pub/Sub retry forever.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_body_limited
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/gmail", tags=["Gmail Push"])

# A Pub/Sub push envelope is a few hundred bytes; 64 KiB leaves room for attributes.
MAX_BODY_BYTES = 64 * 1024
TOKEN_HEADER = "X-MHVP-Push-Token"  # noqa: S105 - header name, not a secret
TOKEN_QUERY = "token"  # noqa: S105
# "sync requested" flag per address: a second notification within this window is dropped, the
# queued job reads the whole history since the cursor anyway. The job clears the flag when it
# starts so a notification arriving during the run enqueues a fresh job.
PENDING_TTL_SECONDS = 120
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
JWKS_TTL_SECONDS = 3600


def pending_key(address: str) -> str:
    return f"gmail-push:pending:{address.strip().lower()}"


def parse_envelope(raw: bytes) -> tuple[str, str]:
    """``(emailAddress, historyId)`` from a Pub/Sub push envelope. Raises ``ValueError`` with
    a German reason when the envelope, the base64 data or the Gmail payload is malformed."""
    try:
        envelope = json.loads(raw) if raw else None
    except ValueError:
        raise ValueError("Pub/Sub-Umschlag ist kein JSON.") from None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("message"), dict):
        raise ValueError("Pub/Sub-Umschlag ohne message.")
    data = envelope["message"].get("data")
    if not isinstance(data, str) or not data:
        raise ValueError("Pub/Sub-Nachricht ohne data.")
    try:
        decoded = base64.b64decode(data + "=" * (-len(data) % 4), validate=False)
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Pub/Sub-Daten sind nicht lesbar.") from None
    if not isinstance(payload, dict):
        raise ValueError("Gmail-Nachricht ist kein Objekt.")
    address = payload.get("emailAddress")
    history_id = payload.get("historyId")
    if not isinstance(address, str) or "@" not in address or len(address) > 320:
        raise ValueError("emailAddress fehlt.")
    if isinstance(history_id, bool) or not isinstance(history_id, int | str):
        raise ValueError("historyId fehlt.")
    history = str(history_id).strip()
    if not history.isdigit():
        raise ValueError("historyId ist keine Zahl.")
    return address.strip().lower(), history


def secret_ok(settings: Settings, request: Request) -> bool:
    expected = settings.gmail_push_token.get_secret_value() if settings.gmail_push_token else ""
    if not expected:
        return False
    given = request.headers.get(TOKEN_HEADER) or request.query_params.get(TOKEN_QUERY) or ""
    return hmac.compare_digest(given.encode(), expected.encode())


# Optional OIDC verification of the Pub/Sub push token ------------------------------------

_jwks_cache: dict[str, Any] = {"fetched": 0.0, "keys": None}


async def google_jwks() -> Any:
    """Google's JWK set (``PyJWKSet``), cached for ``JWKS_TTL_SECONDS``."""
    import jwt

    now = time.monotonic()
    if _jwks_cache["keys"] is not None and now - _jwks_cache["fetched"] < JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.get(GOOGLE_JWKS_URL)
    r.raise_for_status()
    keys = jwt.PyJWKSet.from_dict(r.json())
    _jwks_cache.update(fetched=now, keys=keys)
    return keys


def verify_oidc(token: str, audience: str, jwks: Any) -> dict[str, Any]:
    """Decodes and verifies the Pub/Sub OIDC token: RS256 signature against ``jwks``
    (``PyJWKSet``), issuer accounts.google.com, the configured audience and expiry. Raises
    ``ValueError`` when invalid. The service account e-mail is returned in the claims for the
    log; which account may publish is decided in the Google Cloud project, not here."""
    import jwt

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = jwks[kid].key if kid else None
        if key is None:
            raise ValueError("kid fehlt")
        claims: dict[str, Any] = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iss", "aud"]},
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise ValueError(f"OIDC-Token ungültig: {exc}") from None
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("OIDC-Token: falscher Aussteller.")
    return claims


async def _check_oidc(settings: Settings, request: Request) -> None:
    audience = settings.gmail_push_audience
    if not audience:
        return
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE, detail="OIDC-Token fehlt.")
    try:
        verify_oidc(header[7:].strip(), audience, await google_jwks())
    except (ValueError, httpx.HTTPError) as exc:
        log.warning("gmail push: oidc verification failed", extra={"reason": str(exc)[:200]})
        raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE, detail="OIDC-Token ungültig.") from None


# Endpoint --------------------------------------------------------------------------------


def enqueue(settings: Settings, address: str, history_id: str) -> None:
    """Hands the notification to the ``mail`` queue (task ``mhvp.communication.gmail_push_sync``).
    Never runs the sync inline: the endpoint must answer within Pub/Sub's ack deadline."""
    from mhvp.worker import get_celery

    get_celery().send_task(
        "mhvp.communication.gmail_push_sync", args=[address, history_id], queue="mail"
    )


@router.post(
    "/push",
    status_code=204,
    summary="Gmail-Push (Pub/Sub) entgegennehmen",
    response_class=Response,
)
async def receive_push(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    raw = await read_body_limited(
        request, MAX_BODY_BYTES, error=ErrorCodes.WEBHOOK_TOO_LARGE, detail="Push-Inhalt zu groß."
    )
    if not secret_ok(settings, request):
        log.warning("gmail push: missing or wrong token")
        raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE, detail="Push-Token fehlt oder falsch.")
    await _check_oidc(settings, request)
    try:
        address, history_id = parse_envelope(raw)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    redis = request.app.state.resources.redis
    fresh = await redis.set(pending_key(address), history_id, nx=True, ex=PENDING_TTL_SECONDS)
    if not fresh:
        return Response(status_code=204)
    try:
        enqueue(settings, address, history_id)
    except Exception:
        # The flag must not block the next notification when the broker was unavailable; the
        # 5 minute beat sync remains the safety net.
        log.exception("gmail push: could not enqueue", extra={"address": address})
        await redis.delete(pending_key(address))
    return Response(status_code=204)


# Mapping and job -------------------------------------------------------------------------


async def mailboxes_for_address(
    factory: async_sessionmaker[AsyncSession], address: str
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """``(tenant_id, mailbox_id)`` of every enabled Gmail mailbox with this address across all
    active tenants. Platform level lists the tenants; the mailbox lookup runs per tenant under
    its RLS context, so no query ever spans tenants."""
    wanted = address.strip().lower()
    async with platform_transaction(factory) as session:
        tenant_ids: list[uuid.UUID] = list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    found: list[tuple[uuid.UUID, uuid.UUID]] = []
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            ids = await session.scalars(
                select(Mailbox.id).where(
                    Mailbox.address == wanted,
                    Mailbox.kind == "gmail",
                    Mailbox.enabled.is_(True),
                    Mailbox.deleted_at.is_(None),
                )
            )
            found.extend((tenant_id, mailbox_id) for mailbox_id in ids)
    return found


async def mark_push_received(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, mailbox_id: uuid.UUID
) -> None:
    async with tenant_transaction(factory, tenant_id) as session:
        box = await session.get(Mailbox, mailbox_id)
        if box is not None:
            box.gmail_last_push_at = datetime.now(UTC)
