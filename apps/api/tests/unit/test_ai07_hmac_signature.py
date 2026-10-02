"""AI07 (GAH-215, GAH-212): shared signature helper and WhatsApp status order.

The four callers keep their wire formats; the shared helper decides window and comparison.
"""

import time

import pytest

from mhvp.communication import telephony
from mhvp.core import hmac_signature, webhooks
from mhvp.documents import paperless_webhook
from mhvp.integrations.schadenstool import signature as schadenstool
from mhvp.objektakte import webhook as objektakte
from mhvp.sla.whatsapp import status_timestamp_ok, status_transition_allowed

SECRET = "ai07-secret"
BODY = b'{"a":1}'


def test_mac_is_hmac_over_timestamp_dot_body() -> None:
    import hashlib
    import hmac

    expected = hmac.new(SECRET.encode(), b"100." + BODY, hashlib.sha256).hexdigest()
    assert hmac_signature.mac_hex(SECRET, 100, BODY) == expected
    assert hmac_signature.mac_hex(SECRET, "100", BODY) == expected


@pytest.mark.parametrize(
    ("ts", "sig", "reason"),
    [
        (None, "sha256=x", "missing"),
        ("1", None, "missing"),
        ("abc", "sha256=x", "bad"),
        ("STALE", "OK", "stale"),
        ("NOW", "sha256=00", "bad"),
        ("NOW", "OK", None),
    ],
)
def test_check_reasons(ts: str | None, sig: str | None, reason: str | None) -> None:
    now = 1_000_000
    stamp = {"NOW": str(now), "STALE": str(now - 301)}.get(ts or "", ts)
    value = sig
    if sig == "OK":
        value = "sha256=" + hmac_signature.mac_hex(SECRET, int(stamp or 0), BODY)
    assert hmac_signature.check(SECRET, BODY, stamp, value, now=now) == reason


def test_window_boundary_is_inclusive() -> None:
    assert hmac_signature.within_window(700, now=1000, window=300)
    assert not hmac_signature.within_window(699, now=1000, window=300)
    assert hmac_signature.within_window(1300, now=1000, window=300)


def test_callers_keep_their_formats() -> None:
    now = int(time.time())
    # Paperless and telephony: separate timestamp header, sha256=<hex>.
    for module in (paperless_webhook, telephony):
        sig = module.sign(SECRET, now, BODY)
        assert sig == "sha256=" + hmac_signature.mac_hex(SECRET, now, BODY)
        assert module.verify(SECRET, str(now), sig, BODY)
        assert not module.verify(
            SECRET, str(now - 3600), module.sign(SECRET, now - 3600, BODY), BODY
        )
        assert not module.verify(SECRET, str(now), "v1=" + sig[7:], BODY)
    # Outgoing webhooks: t=<ts>,v1=<hex> in one header.
    header = webhooks.sign(SECRET, BODY, now)
    assert header == f"t={now},v1={hmac_signature.mac_hex(SECRET, now, BODY)}"
    assert webhooks.verify(SECRET, BODY, header, now=now)
    assert not webhooks.verify(SECRET, BODY, header, now=now + 301)
    assert not webhooks.verify(SECRET, BODY, "v1=abc", now=now)
    # Schadenstool: X-Timestamp plus reason strings.
    headers = schadenstool.signed_headers(SECRET, BODY, now)
    ok = schadenstool.verify(SECRET, BODY, headers["X-Timestamp"], headers["X-Signature"], now=now)
    assert ok is None
    assert schadenstool.verify(SECRET, BODY, None, "x", now=now) == "missing"
    assert schadenstool.verify(SECRET, BODY, str(now - 400), headers["X-Signature"], now=now) == (
        "stale"
    )
    # Objektakte: body only (legacy) and timestamped variant.
    assert objektakte.verify(SECRET, objektakte.sign(SECRET, BODY), BODY)
    assert not objektakte.verify("", objektakte.sign(SECRET, BODY), BODY)
    stamped = objektakte.sign_timestamped(SECRET, now, BODY)
    assert objektakte.verify_timestamped(SECRET, str(now), stamped, BODY, now=now) is None
    assert objektakte.verify_timestamped(SECRET, str(now - 301), stamped, BODY, now=now) in (
        "stale",
        "bad",
    )
    assert objektakte.verify_timestamped("", str(now), stamped, BODY, now=now) == "missing"


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        ("sent", "delivered", True),
        ("sent", "read", True),
        ("delivered", "read", True),
        ("read", "delivered", False),
        ("read", "read", False),
        ("delivered", "sent", False),
        ("sent", "failed", True),
        ("delivered", "failed", False),
        ("failed", "delivered", False),
        ("sent", "bogus", False),
        (None, "sent", True),
    ],
)
def test_whatsapp_status_order(current: str | None, new: str, allowed: bool) -> None:
    assert status_transition_allowed(current, new) is allowed


def test_whatsapp_replay_window() -> None:
    now = 2_000_000_000.0
    assert status_timestamp_ok(None, now=now)
    assert status_timestamp_ok(str(int(now) - 3600), now=now)
    assert not status_timestamp_ok(str(int(now) - 8 * 24 * 3600), now=now)
    assert not status_timestamp_ok(str(int(now) + 3600), now=now)
    assert not status_timestamp_ok("x", now=now)
