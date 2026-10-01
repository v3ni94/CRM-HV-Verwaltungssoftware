"""Q10: portal document search and sort (M25-06), ticket external policies (M19-03)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mhvp.portal.routers import _filter_sort_documents
from mhvp.tickets.models import Ticket


def _doc(title: str, filename: str, day: int) -> SimpleNamespace:
    created = datetime(2026, 1, day, tzinfo=UTC)
    return SimpleNamespace(title=title, filename=filename, created_at=created)


DOCS = [
    _doc("Rechnung Dach", "a.pdf", 1),
    _doc("Abrechnung", "z.pdf", 3),
    _doc("vertrag", "m.pdf", 2),
]


def test_search_is_case_insensitive_on_title_and_filename() -> None:
    assert [d.title for d in _filter_sort_documents(DOCS, "RECHNUNG", "title_asc")] == [
        "Abrechnung",
        "Rechnung Dach",
    ]
    assert [d.filename for d in _filter_sort_documents(DOCS, "m.pdf", "created_desc")] == ["m.pdf"]
    assert _filter_sort_documents(DOCS, "nichts", "title_asc") == []


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("created_desc", ["z.pdf", "m.pdf", "a.pdf"]),
        ("created_asc", ["a.pdf", "m.pdf", "z.pdf"]),
        ("title_asc", ["z.pdf", "a.pdf", "m.pdf"]),
        ("filename_desc", ["z.pdf", "m.pdf", "a.pdf"]),
    ],
)
def test_sort(sort: str, expected: list[str]) -> None:
    assert [d.filename for d in _filter_sort_documents(DOCS, None, sort)] == expected


def test_ticket_policy_defaults_open() -> None:
    for name in ("external_comments", "external_attachments"):
        column = Ticket.__table__.c[name]
        assert column.default.arg == "open"
        assert "open" in str(column.server_default.arg)
