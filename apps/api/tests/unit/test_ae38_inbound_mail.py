"""AE38 / M20-04: pure parts of the inbound mail webhook (signature, hash, mapping, schema).

Expected values by hand: the window is 300 seconds in both directions (299 passes, 301 does
not); a changed body, a changed secret, a missing or non ASCII header never pass and never raise;
the canonical hash ignores key order and whitespace but not content; the recipient list holds To
and Cc like the parser of an .eml; NUL bytes never reach the stored text.
"""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mhvp.communication import inbound_webhook as hook
from mhvp.core import webhooks
from mhvp.core.auth.permissions import ALL_PERMISSIONS, MAIL_INBOUND_INGEST, SYSTEM_ROLES
from mhvp.core.problems import ErrorCodes

SECRET = "ae38-test-secret-with-enough-length"
BODY = b'{"event_id":"e1"}'
NOW = 1_790_000_000


def test_signature_window_is_300_seconds_both_ways() -> None:
    for delta, expected in [(0, True), (299, True), (-299, True), (301, False), (-301, False)]:
        header = hook.sign_delivery(SECRET, BODY, timestamp=NOW - delta)
        assert hook.verify_signature(SECRET, BODY, header, now=NOW) is expected, delta


def test_signature_rejects_everything_else_without_raising() -> None:
    good = hook.sign_delivery(SECRET, BODY, timestamp=NOW)
    assert hook.verify_signature(SECRET, BODY, good, now=NOW)
    assert not hook.verify_signature(SECRET, BODY + b" ", good, now=NOW)
    assert not hook.verify_signature("other-secret-value", BODY, good, now=NOW)
    for bad in [None, "", "t=abc,v1=00", good.split(",", 1)[1], "t=1,v1=äöü", "x" * 500, "t=1"]:
        assert not hook.verify_signature(SECRET, BODY, bad, now=NOW), bad
    # absurd timestamp is a rejection, not an error
    assert not hook.verify_signature(SECRET, BODY, f"t={10**30},v1=00", now=NOW)


def test_signature_is_the_platform_format() -> None:
    header = hook.sign_delivery(SECRET, BODY, timestamp=NOW)
    assert header == webhooks.sign(SECRET, BODY, NOW)
    assert header.startswith(f"t={NOW},v1=")
    assert hook.SIGNATURE_HEADER == "X-MHVP-Signature"
    assert hook.TOLERANCE_SECONDS == 300
    assert hook.MAX_BODY_BYTES == 1024 * 1024


def test_canonical_hash_ignores_order_and_whitespace_but_not_content() -> None:
    first = json.loads('{"b": 1, "a": {"y": [1, 2], "x": "ä"}}')
    second = json.loads('{\n  "a": {"x": "ä", "y": [1, 2]},\n  "b": 1\n}')
    assert hook.canonical_hash(first) == hook.canonical_hash(second)
    assert hook.canonical_hash(first) != hook.canonical_hash({**first, "b": 2})
    assert len(hook.canonical_hash(first)) == 64


def _payload(**mail: object) -> hook.InboundMailEventIn:
    base: dict[str, object] = {"from_address": " Mieter@Example.ORG ", "subject": "Betreff"}
    base.update(mail)
    return hook.InboundMailEventIn.model_validate({"event_id": "evt-1", "mail": base})


def test_mapping_to_the_parsed_mail_shape() -> None:
    payload = _payload(
        to=["Info@Example.com", "b@example.com"],
        cc=["B@example.com", "c@example.com"],
        subject="Heizung\x00 defekt",
        body_text="  Text\x00 mit NUL  ",
        message_id="<a@b>",
        references="<x@y>\n <z@y>",
        received_at="2026-09-30T08:15:00+02:00",
        auto_submitted=True,
    )
    parsed = hook.to_parsed(payload)
    assert parsed["from"] == "mieter@example.org"
    assert parsed["to"] == ["info@example.com", "b@example.com", "c@example.com"]
    assert parsed["cc"] == ["b@example.com", "c@example.com"]
    assert parsed["subject"] == "Heizung defekt"
    assert parsed["body"] == "Text mit NUL"
    assert parsed["references"] == "<x@y> <z@y>"
    assert parsed["attachments"] == []
    assert parsed["auto_submitted"] is True
    received = parsed["received_at"]
    assert isinstance(received, datetime)
    assert received.astimezone(UTC) == datetime(2026, 9, 30, 6, 15, tzinfo=UTC)
    empty = hook.to_parsed(_payload())
    assert empty["subject"] == "Betreff"
    assert empty["body"] == ""
    assert empty["message_id"] is None
    assert empty["received_at"] is None


@pytest.mark.parametrize(
    "document",
    [
        {"event_id": "", "mail": {"from_address": "a@b.de"}},
        {"event_id": "has space", "mail": {"from_address": "a@b.de"}},
        {"event_id": "x" * 201, "mail": {"from_address": "a@b.de"}},
        {"event_id": "e", "mail": {"from_address": "no-at"}},
        {"event_id": "e", "mail": {"from_address": "a@b.de", "to": ["x"]}},
        {"event_id": "e", "mail": {"from_address": "a@b.de", "received_at": "2026-09-30T08:00:00"}},
        {"event_id": "e", "mail": {"from_address": "a@b.de"}, "extra": 1},
        {"event_id": "e", "mail": {"from_address": "a@b.de", "unknown": 1}},
        {"event_id": "e", "mail": {"from_address": "a@b.de"}, "classification": {"urgency": "x"}},
        {"event_id": "e", "mail": {"from_address": "a@b.de"}, "classification": {"confidence": 2}},
        {
            "event_id": "e",
            "mail": {"from_address": "a@b.de"},
            "classification": {"labels": ["x" * 65]},
        },
        {"event_id": "e", "mail": {"from_address": "a@b.de", "body_text": "x" * 100001}},
        {"event_id": "e"},
    ],
)
def test_schema_rejects_invalid_deliveries(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        hook.InboundMailEventIn.model_validate(document)


def test_right_and_problem_codes_are_registered() -> None:
    assert MAIL_INBOUND_INGEST == "mail_inbound:ingest"
    assert MAIL_INBOUND_INGEST in ALL_PERMISSIONS
    holders = {role.code for role in SYSTEM_ROLES if MAIL_INBOUND_INGEST in role.permissions}
    assert holders == {"tenant_admin", "administrator"}
    assert ErrorCodes.INBOUND_MAIL_EVENT_CONFLICT.status == 409
    assert ErrorCodes.INBOUND_MAIL_SOURCE_INACTIVE.status == 409
    assert ErrorCodes.WEBHOOK_SIGNATURE.status == 401
    assert ErrorCodes.WEBHOOK_TOO_LARGE.status == 413
