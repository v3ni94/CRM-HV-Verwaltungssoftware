"""IMAP search and fetch (M20-01) against a fake connection, no network."""

from datetime import UTC, datetime

import pytest

from mhvp.communication.imap import ImapError, collect


class FakeConn:
    def __init__(self, uids: list[int], fail_search: bool = False) -> None:
        self.uids = uids
        self.fail_search = fail_search
        self.calls: list[tuple[str, ...]] = []

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        self.calls.append((command, *(str(a) for a in args)))
        if command == "SEARCH":
            if self.fail_search:
                return "NO", [b""]
            return "OK", [b" ".join(str(u).encode() for u in self.uids)]
        uid = int(str(args[0]))
        return "OK", [(f"{uid} (BODY[] {{10}}".encode(), f"raw-{uid}".encode()), b")"]


def test_after_uid_filters_star_quirk_and_uses_peek() -> None:
    conn = FakeConn([7])  # "8:*" returns the highest UID 7 although it is below 8
    result = collect(conn, 5, after_uid=7, since=None, limit=10)
    assert result.messages == []
    assert conn.calls[0] == ("SEARCH", "None", "UID 8:*")


def test_fetch_batch_limit_and_more_flag() -> None:
    conn = FakeConn([3, 1, 2])
    result = collect(conn, 9, after_uid=None, since=datetime(2026, 9, 1, tzinfo=UTC), limit=2)
    assert conn.calls[0] == ("SEARCH", "None", "SINCE 01-Sep-2026")
    assert [u for u, _ in result.messages] == [1, 2]
    assert result.messages[0][1] == b"raw-1"
    assert result.more is True
    assert all(c[2] == "(BODY.PEEK[])" for c in conn.calls[1:])


def test_search_failure_raises() -> None:
    with pytest.raises(ImapError):
        collect(FakeConn([], fail_search=True), None, after_uid=1, since=None, limit=5)
