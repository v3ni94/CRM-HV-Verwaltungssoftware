"""Unit test: gcal.GCalClient request building against httpx.MockTransport (M23-02)."""

from datetime import UTC, datetime

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
