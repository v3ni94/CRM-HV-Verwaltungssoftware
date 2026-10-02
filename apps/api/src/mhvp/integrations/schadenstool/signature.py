"""HMAC signature of the claims adjuster contract (sections 3.1 and 3.2 of the draft).

``X-Timestamp: <unix seconds>`` and ``X-Signature: sha256=<hex>`` where the MAC is
HMAC-SHA256 over ``f"{timestamp}.{raw_body}"``. The receiver accepts a timestamp at most
``REPLAY_WINDOW_SECONDS`` away from its own clock (contract: "z. B. 5 Minuten").
"""

from __future__ import annotations

from mhvp.core import hmac_signature

REPLAY_WINDOW_SECONDS = 300
TIMESTAMP_HEADER = "X-Timestamp"
SIGNATURE_HEADER = "X-Signature"
PREFIX = "sha256="


def sign(secret: str, body: bytes, timestamp: int) -> str:
    return PREFIX + hmac_signature.mac_hex(secret, timestamp, body)


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
    return hmac_signature.check(
        secret, body, timestamp_header, signature_header, now=now, window=window, prefix=PREFIX
    )
