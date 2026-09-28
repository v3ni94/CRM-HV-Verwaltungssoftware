"""HMAC signature of the claims adjuster contract (sections 3.1 and 3.2 of the draft).

``X-Timestamp: <unix seconds>`` and ``X-Signature: sha256=<hex>`` where the MAC is
HMAC-SHA256 over ``f"{timestamp}.{raw_body}"``. The receiver accepts a timestamp at most
``REPLAY_WINDOW_SECONDS`` away from its own clock (contract: "z. B. 5 Minuten").
"""

from __future__ import annotations

import hashlib
import hmac

REPLAY_WINDOW_SECONDS = 300
TIMESTAMP_HEADER = "X-Timestamp"
SIGNATURE_HEADER = "X-Signature"
PREFIX = "sha256="


def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return PREFIX + mac.hexdigest()


def signed_headers(secret: str, body: bytes, timestamp: int) -> dict[str, str]:
    return {TIMESTAMP_HEADER: str(timestamp), SIGNATURE_HEADER: sign(secret, body, timestamp)}


def verify(
    secret: str,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    *,
    now: int,
    window: int = REPLAY_WINDOW_SECONDS,
) -> str | None:
    """``None`` when valid, otherwise a short reason (``missing``, ``stale``, ``bad``)."""
    if not timestamp_header or not signature_header:
        return "missing"
    try:
        timestamp = int(timestamp_header.strip())
    except ValueError:
        return "bad"
    if abs(now - timestamp) > window:
        return "stale"
    if not hmac.compare_digest(sign(secret, body, timestamp), signature_header.strip()):
        return "bad"
    return None
