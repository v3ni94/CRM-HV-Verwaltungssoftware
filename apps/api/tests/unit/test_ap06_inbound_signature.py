"""AP06 / GAL-204: inbound ``X-MHVP-Signature`` accepts the platform standard
``t=<unix>,v1=<hex>`` (same as outgoing webhooks) and still the legacy ``sha256=<hex>``.

Attack paths covered: forged MAC, stale timestamp, mismatching separate timestamp header and a
replay with a reformatted header (the replay marker is the MAC, not the header text).
"""

import time

import pytest

from mhvp.communication import telephony
from mhvp.core import hmac_signature, webhooks
from mhvp.documents import paperless_webhook

SECRET = "ap06-secret"
BODY = b'{"document_id":7}'


@pytest.mark.parametrize("module", [telephony, paperless_webhook])
def test_standard_format_accepted_like_outgoing(module: object) -> None:
    now = int(time.time())
    header = webhooks.sign(SECRET, BODY, now)
    assert module.verify(SECRET, None, header, BODY)  # type: ignore[attr-defined]
    assert module.verify(SECRET, str(now), header, BODY)  # type: ignore[attr-defined]


@pytest.mark.parametrize("module", [telephony, paperless_webhook])
def test_legacy_format_still_accepted(module: object) -> None:
    now = int(time.time())
    legacy = module.sign(SECRET, now, BODY)  # type: ignore[attr-defined]
    assert legacy.startswith("sha256=")
    assert module.verify(SECRET, str(now), legacy, BODY)  # type: ignore[attr-defined]
    assert not module.verify(SECRET, None, legacy, BODY)  # type: ignore[attr-defined]


@pytest.mark.parametrize("module", [telephony, paperless_webhook])
def test_forged_stale_or_mismatching_refused(module: object) -> None:
    now = int(time.time())
    verify = module.verify  # type: ignore[attr-defined]
    assert not verify(SECRET, None, webhooks.sign("other", BODY, now), BODY)
    assert not verify(SECRET, None, webhooks.sign(SECRET, BODY, now - 3600), BODY)
    assert not verify(SECRET, str(now + 1), webhooks.sign(SECRET, BODY, now), BODY)
    assert not verify(SECRET, None, webhooks.sign(SECRET, BODY, now), BODY + b" ")
    assert not verify(SECRET, None, f"t={now}", BODY)
    assert not verify(SECRET, None, "garbage", BODY)
    assert not verify(SECRET, None, None, BODY)


def test_replay_token_ignores_header_layout() -> None:
    now = int(time.time())
    header = webhooks.sign(SECRET, BODY, now)
    mac = header.split("v1=")[1]
    variants = [header, f" t={now}, v1={mac} ", f"v1={mac},t={now},x=1"]
    assert all(telephony.verify(SECRET, None, v, BODY) for v in variants)
    assert {hmac_signature.replay_token(v) for v in variants} == {mac}
    assert hmac_signature.replay_token(f"sha256={mac}") == mac
