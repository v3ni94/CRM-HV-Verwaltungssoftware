"""Shared HMAC-SHA256 helper for timestamped webhook signatures (GAH-215).

All inbound and outbound webhooks of the platform sign ``f"{timestamp}." + raw_body``
with HMAC-SHA256. The callers differ only in header layout (``sha256=<hex>`` with a separate
timestamp header, or ``t=<ts>,v1=<hex>`` in one header); they keep their own wire formats and
use these primitives so window check and constant time comparison exist exactly once.
"""

from __future__ import annotations

import hashlib
import hmac

DEFAULT_WINDOW_SECONDS = 300


def mac_hex(secret: str, timestamp: int | str, body: bytes) -> str:
    """Hex HMAC-SHA256 over ``"{timestamp}." + body``."""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def parse_timestamp(value: str | None) -> int | None:
    """Unix seconds from a header value, ``None`` when missing or not an integer."""
    if not value:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def within_window(timestamp: int, *, now: float, window: int = DEFAULT_WINDOW_SECONDS) -> bool:
    return abs(now - timestamp) <= window


def equal(expected: str, received: str) -> bool:
    """Constant time comparison of two signature strings."""
    return hmac.compare_digest(expected.encode(), received.encode())


def check(
    secret: str,
    body: bytes,
    timestamp_value: str | None,
    signature_value: str | None,
    *,
    now: float,
    window: int = DEFAULT_WINDOW_SECONDS,
    prefix: str = "sha256=",
) -> str | None:
    """``None`` when valid, otherwise ``missing``, ``stale`` or ``bad``.

    For the format ``<prefix><hex>`` with the timestamp in its own header.
    """
    if not timestamp_value or not signature_value:
        return "missing"
    ts = parse_timestamp(timestamp_value)
    if ts is None:
        return "bad"
    if not within_window(ts, now=now, window=window):
        return "stale"
    if not equal(prefix + mac_hex(secret, ts, body), signature_value.strip()):
        return "bad"
    return None
