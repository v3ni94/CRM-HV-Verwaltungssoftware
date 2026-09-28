"""Rule M20-08: ``history.list`` with every history type and no label filter, parsing of all
event kinds, dropped labels, dedupe across pages, order by history id and the client calls
``archive`` (history id, 404), ``restore_inbox``, ``message_labels`` and ``thread_message_ids``.
No network, no database (httpx MockTransport)."""

import json
from typing import Any

import httpx
import pytest

from mhvp.communication.gmail import (
    ArchiveResult,
    GmailClient,
    GmailError,
    HistoryEvent,
    parse_history,
    state_from_labels,
)


def _client(handler: Any) -> GmailClient:
    return GmailClient(
        "client-id", "client-secret", "refresh-token", transport=httpx.MockTransport(handler)
    )


def _token(request: httpx.Request) -> httpx.Response | None:
    if "token" in str(request.url):
        return httpx.Response(200, json={"access_token": "token-1"})
    return None


def test_parse_history_kinds_and_dropped_labels() -> None:
    history = [
        {"id": "10", "messagesAdded": [{"message": {"id": "a", "labelIds": ["INBOX", "UNREAD"]}}]},
        {"id": "11", "messagesAdded": [{"message": {"id": "b", "labelIds": ["Ablage"]}}]},
        {"id": "12", "messagesAdded": [{"message": {"id": "c"}}]},
        {
            "id": "13",
            "labelsRemoved": [{"message": {"id": "a"}, "labelIds": ["INBOX", "UNREAD"]}],
            "labelsAdded": [{"message": {"id": "a"}, "labelIds": ["TRASH", "STARRED", "Warten"]}],
        },
        {"id": "14", "labelsRemoved": [{"message": {"id": "a"}, "labelIds": ["UNREAD"]}]},
        {
            "id": "15",
            "labelsAdded": [
                {"message": {"id": "a"}, "labelIds": ["CATEGORY_UPDATES", "IMPORTANT"]}
            ],
        },
        {"id": "16", "messagesDeleted": [{"message": {"id": "a"}}]},
        {"id": "17", "labelsAdded": [{"message": {"id": "d"}, "labelIds": ["SPAM"]}]},
        {"id": "18", "labelsRemoved": [{"message": {"id": "d"}, "labelIds": ["SPAM"]}]},
    ]
    events = parse_history(history, "9")
    assert events == [
        HistoryEvent(10, "a", "added", label_ids=("INBOX", "UNREAD")),
        HistoryEvent(12, "c", "added"),
        HistoryEvent(13, "a", "inbox_removed"),
        HistoryEvent(13, "a", "trash_added"),
        HistoryEvent(13, "a", "label_added_other", added_labels=("Warten",)),
        HistoryEvent(16, "a", "deleted"),
        HistoryEvent(17, "d", "spam_added"),
        HistoryEvent(18, "d", "spam_removed"),
    ]
    assert state_from_labels(None) == "inbox"
    assert state_from_labels(["INBOX"]) == "inbox"
    assert state_from_labels(["TRASH", "INBOX"]) == "trashed"
    assert state_from_labels(["SPAM"]) == "spam"
    assert state_from_labels(["Ablage"]) == "archived"


async def test_history_since_requests_all_types_dedupes_pages_and_sorts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        requests.append(request)
        if request.url.params.get("pageToken") == "p2":
            return httpx.Response(
                200,
                json={
                    "history": [
                        {
                            "id": "22",
                            "labelsRemoved": [{"message": {"id": "x"}, "labelIds": ["INBOX"]}],
                        },
                        {"id": "21", "messagesAdded": [{"message": {"id": "y"}}]},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "history": [
                    {
                        "id": "22",
                        "labelsRemoved": [{"message": {"id": "x"}, "labelIds": ["INBOX"]}],
                    },
                    {
                        "id": "23",
                        "messagesAdded": [{"message": {"id": "z", "labelIds": ["INBOX"]}}],
                    },
                ],
                "nextPageToken": "p2",
            },
        )

    client = _client(handler)
    try:
        events = await client.history_since("20")
    finally:
        await client.aclose()
    params = requests[0].url.params
    assert set(params.get_list("historyTypes")) == {
        "messageAdded",
        "labelRemoved",
        "labelAdded",
        "messageDeleted",
    }
    assert "labelId" not in params
    assert params["maxResults"] == "500"
    assert events == [
        HistoryEvent(21, "y", "added"),
        HistoryEvent(22, "x", "inbox_removed"),
        HistoryEvent(23, "z", "added", label_ids=("INBOX",)),
    ]


async def test_history_since_expired_returns_none_and_errors_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        return httpx.Response(404)

    client = _client(handler)
    try:
        assert await client.history_since("1") is None
    finally:
        await client.aclose()

    def failing(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        return httpx.Response(500)

    client = _client(failing)
    try:
        with pytest.raises(GmailError):
            await client.history_since("1")
    finally:
        await client.aclose()


async def test_archive_returns_history_id_and_gone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        if request.url.path.endswith("/msg-1/modify"):
            assert json.loads(request.content) == {"removeLabelIds": ["INBOX", "UNREAD"]}
            return httpx.Response(200, json={"id": "msg-1", "labelIds": [], "historyId": "12345"})
        return httpx.Response(404)

    client = _client(handler)
    try:
        assert await client.archive("msg-1") == ArchiveResult("archived", 12345)
        assert await client.archive("msg-gone") == ArchiveResult("gone", None)
    finally:
        await client.aclose()


async def test_restore_inbox_untrashes_then_adds_inbox() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        calls.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content or b"{}")))
        return httpx.Response(200, json={"id": "m", "historyId": str(100 + len(calls))})

    client = _client(handler)
    try:
        assert await client.restore_inbox("m", untrash=True) == 102
        assert calls == [("untrash", {}), ("modify", {"addLabelIds": ["INBOX"]})]
        calls.clear()
        assert await client.restore_inbox("m", untrash=False) == 101
        assert calls == [("modify", {"addLabelIds": ["INBOX"]})]
    finally:
        await client.aclose()


async def test_message_labels_and_thread_message_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (r := _token(request)) is not None:
            return r
        assert request.url.params.get("format") == "minimal"
        if request.url.path.endswith("/messages/m1"):
            return httpx.Response(200, json={"id": "m1", "historyId": "77", "labelIds": ["TRASH"]})
        if request.url.path.endswith("/threads/t1"):
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {"id": "m1", "labelIds": ["INBOX"]},
                        {"id": "m2", "labelIds": ["SENT"]},
                    ]
                },
            )
        return httpx.Response(404)

    client = _client(handler)
    try:
        assert await client.message_labels("m1") == (77, ["TRASH"])
        assert await client.message_labels("m9") is None
        assert await client.thread_message_ids("t1") == [("m1", ["INBOX"]), ("m2", ["SENT"])]
        assert await client.thread_message_ids("t9") is None
    finally:
        await client.aclose()
