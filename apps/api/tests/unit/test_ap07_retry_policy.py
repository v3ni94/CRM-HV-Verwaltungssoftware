"""AP07 (GAL-206): shared delivery retry policy, only transient errors, Retry-After honoured.

Expected values by hand: base 30 s, cap 600 s, full jitter between half and the ceiling, so
attempt 0 lies in [15, 30], attempt 3 in [120, 240]; ``Retry-After: 900`` wins over 240."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from mhvp.core import task_policy as tp


def _http_error(status: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    request = httpx.Request("POST", "https://example.org/x")
    response = httpx.Response(status, headers=headers, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ConnectionError("down"), True),
        (TimeoutError(), True),
        (httpx.ConnectError("x"), True),
        (OperationalError("select 1", {}, Exception("gone")), True),
        (_http_error(429), True),
        (_http_error(503), True),
        (_http_error(400), False),
        (_http_error(401), False),
        (ValueError("bad input"), False),
        (KeyError("x"), False),
    ],
)
def test_is_transient(exc: BaseException, expected: bool) -> None:
    assert tp.is_transient(exc) is expected


def test_countdown_backoff_grows_and_is_capped() -> None:
    for _ in range(50):
        first = tp.transient_retry_countdown(ConnectionError(), 0)
        third = tp.transient_retry_countdown(ConnectionError(), 3)
        late = tp.transient_retry_countdown(ConnectionError(), 20)
        assert first is not None
        assert 15 <= first <= 30
        assert third is not None
        assert 120 <= third <= 240
        assert late is not None
        assert 300 <= late <= 600


def test_countdown_none_for_permanent_error() -> None:
    assert tp.transient_retry_countdown(ValueError(), 0) is None
    assert tp.transient_retry_countdown(_http_error(404), 0) is None


def test_retry_after_seconds_and_cap() -> None:
    assert tp.transient_retry_countdown(_http_error(429, "900"), 3) == 900
    assert tp.transient_retry_countdown(_http_error(429, "99999"), 0) == tp.RETRY_AFTER_CAP_SECONDS
    small = tp.transient_retry_countdown(_http_error(503, "1"), 3)
    assert small is not None
    assert small >= 120
    garbage = tp.transient_retry_countdown(_http_error(503, "soon"), 0)
    assert garbage is not None
    assert 15 <= garbage <= 30


class _Task:
    name = "mhvp.communication.postal_status_poll"

    def __init__(self, retries: int) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.calls: list[dict[str, Any]] = []

    def retry(self, **kwargs: Any) -> BaseException:
        self.calls.append(kwargs)
        return RuntimeError("retry")


def test_retry_transient_retries_only_transient() -> None:
    task = _Task(retries=1)
    exc = ValueError("permanent")
    assert tp.retry_transient(task, exc) is exc
    assert task.calls == []
    out = tp.retry_transient(task, ConnectionError())
    assert str(out) == "retry"
    assert task.calls[0]["max_retries"] == tp.RETRY_MAX
    assert 30 <= task.calls[0]["countdown"] <= 60
