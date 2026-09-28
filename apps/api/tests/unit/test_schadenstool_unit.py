"""Unit tests of the claims adjuster link: signature, status mapping, retry plan."""

import hashlib
import hmac
from datetime import UTC, datetime

from mhvp.core.webhooks import RETRY_SCHEDULE_SECONDS
from mhvp.integrations.schadenstool.client import ErrorKind, SchadenstoolError
from mhvp.integrations.schadenstool.models import OutboxStatus, SchadenstoolOutbox
from mhvp.integrations.schadenstool.services import _schedule_retry
from mhvp.integrations.schadenstool.signature import sign, verify
from mhvp.integrations.schadenstool.status_map import remote_status_for, remote_status_label
from mhvp.tickets.models import TicketStatus

SECRET = "s" * 32


def test_sign_matches_contract_format() -> None:
    body = b'{"eventId":"1"}'
    expected = hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert sign(SECRET, body, 1_700_000_000) == f"sha256={expected}"


def test_verify_valid_invalid_stale_missing() -> None:
    body = b"{}"
    now = 1_700_000_000
    good = sign(SECRET, body, now)
    assert verify(SECRET, body, str(now), good, now=now + 299) is None
    assert verify(SECRET, body, str(now), good, now=now + 301) == "stale"
    assert verify(SECRET, body, str(now), good, now=now - 301) == "stale"
    assert verify(SECRET, b"{ }", str(now), good, now=now) == "bad"
    assert verify("x" * 32, body, str(now), good, now=now) == "bad"
    assert verify(SECRET, body, None, good, now=now) == "missing"
    assert verify(SECRET, body, "abc", good, now=now) == "bad"


def test_status_mapping() -> None:
    assert remote_status_for(TicketStatus.NEW) == "open"
    assert remote_status_for(TicketStatus.DONE) == "resolved"
    assert remote_status_for(TicketStatus.REJECTED) is None
    assert remote_status_for("unknown") is None
    assert remote_status_label("in_progress") == "In Bearbeitung"
    assert remote_status_label("gutachten_angefordert") == "gutachten_angefordert"
    assert remote_status_label(None) is None


def _row() -> SchadenstoolOutbox:
    return SchadenstoolOutbox(
        kind="comment",
        idempotency_key="k",
        payload={},
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )


def test_retry_plan_and_retry_after() -> None:
    now = datetime.now(UTC)
    row = _row()
    _schedule_retry(row, SchadenstoolError(ErrorKind.UNAVAILABLE, "x", status_code=503), now)
    assert (row.next_attempt_at - now).total_seconds() == RETRY_SCHEDULE_SECONDS[0]
    row = _row()
    error = SchadenstoolError(ErrorKind.RATE_LIMITED, "x", status_code=429, retry_after=900)
    _schedule_retry(row, error, now)
    assert (row.next_attempt_at - now).total_seconds() == 900
    row = _row()
    _schedule_retry(row, SchadenstoolError(ErrorKind.REJECTED, "x", status_code=422), now)
    assert row.status == OutboxStatus.FAILED.value
    row = _row()
    row.attempts = len(RETRY_SCHEDULE_SECONDS)
    _schedule_retry(row, SchadenstoolError(ErrorKind.UNAVAILABLE, "x"), now)
    assert row.status == OutboxStatus.FAILED.value
