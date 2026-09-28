"""Unit test: gcal.GCalClient request building against httpx.MockTransport (M23-02)."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from mhvp.communication import gcal


def _token_response(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/token")
    return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})


@pytest.mark.asyncio
async def test_list_events_sends_time_range_and_bearer_token() -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response(request)
        seen["list"] = request
        assert request.headers["Authorization"] == "Bearer t"
        assert request.url.params["singleEvents"] == "true"
        assert request.url.params["orderBy"] == "startTime"
        assert "primary" in request.url.path
        return httpx.Response(200, json={"items": [{"id": "e1", "summary": "Termin"}]})

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        events = await client.list_events(
            "primary",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
        )
    finally:
        await client.aclose()
    assert events == [{"id": "e1", "summary": "Termin"}]
    assert seen["list"].url.params["timeMin"] == "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_list_events_follows_page_token() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response(request)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"items": [{"id": "e1"}], "nextPageToken": "p2"})
        assert request.url.params["pageToken"] == "p2"
        return httpx.Response(200, json={"items": [{"id": "e2"}]})

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        events = await client.list_events(
            "primary", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )
    finally:
        await client.aclose()
    assert [e["id"] for e in events] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_insert_event_posts_body_to_calendar_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response(request)
        assert request.method == "POST"
        assert request.url.path.endswith("/calendars/primary/events")
        assert request.headers["Authorization"] == "Bearer t"
        return httpx.Response(200, json={"id": "new-event"})

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        event = await client.insert_event(
            "primary", {"summary": "Besichtigung", "start": {"date": "2026-10-01"}}
        )
    finally:
        await client.aclose()
    assert event == {"id": "new-event"}


@pytest.mark.asyncio
async def test_patch_and_delete_event_target_the_right_path() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response(request)
        seen.append((request.method, request.url.path))
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "evt-1"})
        return httpx.Response(204)

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        patched = await client.patch_event("primary", "evt-1", {"summary": "Neu"})
        await client.delete_event("primary", "evt-1")
    finally:
        await client.aclose()
    assert patched == {"id": "evt-1"}
    assert ("PATCH", "/calendar/v3/calendars/primary/events/evt-1") in seen
    assert ("DELETE", "/calendar/v3/calendars/primary/events/evt-1") in seen


@pytest.mark.asyncio
async def test_401_triggers_one_token_refresh_retry() -> None:
    state = {"tokens": 0, "calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            state["tokens"] += 1
            return httpx.Response(200, json={"access_token": f"t{state['tokens']}"})
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401)
        assert request.headers["Authorization"] == "Bearer t2"
        return httpx.Response(200, json={"items": []})

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        events = await client.list_events(
            "primary", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )
    finally:
        await client.aclose()
    assert events == []
    assert state["tokens"] == 2


@pytest.mark.asyncio
async def test_list_events_404_raises_gcal_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _token_response(request)
        return httpx.Response(404)

    client = gcal.GCalClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(gcal.GCalError):
            await client.list_events(
                "primary", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
            )
    finally:
        await client.aclose()


def test_make_client_requires_refresh_token() -> None:
    from mhvp.communication.models import Mailbox

    box = Mailbox(address="info@example.com", kind="gmail")
    with pytest.raises(gcal.GCalError):
        gcal.make_client("cid", "secret", box)


async def _list_error(token_status: int, api_status: int, api_body: Any) -> gcal.GCalError:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            if token_status != 200:
                return httpx.Response(
                    token_status, json={"error": "invalid_grant", "refresh": "secret-refresh"}
                )
            return _token_response(request)
        return httpx.Response(api_status, json=api_body)

    client = gcal.GCalClient(
        "cid", "secret", "secret-refresh", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(gcal.GCalError) as info:
            await client.list_events(
                "primary", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
            )
    finally:
        await client.aclose()
    return info.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_status", "api_status", "api_body", "kind"),
    [
        (400, 200, {}, gcal.AUTH),
        (401, 200, {}, gcal.AUTH),
        (503, 200, {}, gcal.UNAVAILABLE),
        (200, 401, {}, gcal.AUTH),
        (200, 403, {"error": {"errors": [{"reason": "insufficientPermissions"}]}}, gcal.AUTH),
        (200, 403, {"error": {"errors": [{"reason": "rateLimitExceeded"}]}}, gcal.UNAVAILABLE),
        (200, 404, {}, gcal.AUTH),
        (200, 429, {}, gcal.UNAVAILABLE),
        (200, 500, {}, gcal.UNAVAILABLE),
        (200, 400, {}, gcal.REJECTED),
    ],
)
async def test_errors_carry_kind_and_status_but_no_secret(
    token_status: int, api_status: int, api_body: Any, kind: str
) -> None:
    error = await _list_error(token_status, api_status, api_body)
    assert error.kind == kind
    assert error.status == (token_status if token_status != 200 else api_status)
    assert error.reconnect_required is (kind == gcal.AUTH)
    assert "secret" not in str(error)
    assert "invalid_grant" not in str(error)


def test_missing_refresh_token_needs_reconnect() -> None:
    from types import SimpleNamespace

    with pytest.raises(gcal.GCalError) as info:
        gcal.make_client("cid", "secret", SimpleNamespace(secret=None))  # type: ignore[arg-type]
    assert info.value.kind == gcal.AUTH
