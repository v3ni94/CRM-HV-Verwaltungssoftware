"""Paperless-Suche (M31, Hub 7.2): Objekt-/Ticketsuche, Gesellschaftsfilter und Datei-Proxy
gegen einen MockTransport."""

import json
from collections.abc import Callable, Coroutine

import httpx
import pytest

from mhvp.documents.paperless_search import (
    PaperlessSearch,
    PaperlessSearchError,
    format_company_options,
    object_number_matches,
    parse_company_options,
    parse_field_id,
)


def _client(
    handler: Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_list_by_object_number_uses_custom_field_query() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [
                    {
                        "id": 42,
                        "title": "Nebenkostenabrechnung",
                        "created": "2026-01-01",
                        "added": "2026-01-02",
                        "correspondent": {"name": "Stadtwerke"},
                        "document_type": {"name": "Abrechnung"},
                        "tags": [{"name": "objekt:602"}],
                        "page_count": 3,
                        "original_file_name": "nk.pdf",
                    }
                ],
            },
        )

    search = PaperlessSearch(
        "https://paperless.example", "sek-ret", client=_client(handler), object_field_id=7
    )
    page = await search.list_by_object_number("602", page=1, page_size=25)
    await search.aclose()

    assert page.total == 1
    assert page.items[0].id == 42
    assert page.items[0].correspondent == "Stadtwerke"
    assert "custom_field_query" in str(seen["url"])
    assert seen["auth"] == "Token sek-ret"
    assert "sek-ret" not in str(seen["url"])


@pytest.mark.asyncio
async def test_list_by_object_number_without_field_id_is_empty() -> None:
    async def unreachable(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected without a configured field id")

    search = PaperlessSearch("https://paperless.example", "t", client=_client(unreachable))
    page = await search.list_by_object_number("602")
    await search.aclose()

    assert page.items == []
    assert page.total == 0


@pytest.mark.asyncio
async def test_list_by_ticket_uses_fulltext_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query"] == "1234"
        return httpx.Response(200, json={"count": 0, "results": []})

    search = PaperlessSearch("https://paperless.example", "t", client=_client(handler))
    page = await search.list_by_ticket(1234)
    await search.aclose()

    assert page.total == 0


@pytest.mark.asyncio
async def test_fetch_file_streams_bytes_and_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/documents/42/preview/")
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    search = PaperlessSearch("https://paperless.example", "t", client=_client(handler))
    file = await search.fetch_file(42, "preview")
    await search.aclose()

    assert file.content == b"%PDF-1.4"
    assert file.content_type == "application/pdf"


@pytest.mark.asyncio
async def test_unreachable_paperless_raises_clean_error_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    search = PaperlessSearch("https://paperless.example", "geheimes-token", client=_client(handler))
    with pytest.raises(PaperlessSearchError) as exc:
        await search.list_by_ticket("1234")
    await search.aclose()

    assert "geheimes-token" not in str(exc.value)


@pytest.mark.asyncio
async def test_error_status_is_wrapped_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    search = PaperlessSearch("https://paperless.example", "geheimes-token", client=_client(handler))
    with pytest.raises(PaperlessSearchError) as exc:
        await search.fetch_file(1, "download")
    await search.aclose()

    assert "geheimes-token" not in str(exc.value)


# Hub 7.2: Objektsuche und Gesellschaftsfilter ---------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("523", True),  # exakt die Nummer
        ("5230", False),  # längere Nummer mit gleichem Anfang
        ("523, Musterstr", True),  # Nummer, Komma, Leerzeichen, Anschrift
        ("1523", False),  # Nummer als Endung einer anderen Nummer
    ],
)
def test_object_number_matches_hub_edge_cases(value: str, expected: bool) -> None:
    assert object_number_matches(value, "523") is expected


@pytest.mark.parametrize("value", ["523,Musterstr", "523 Musterstr", " 523", "", None, 523])
def test_object_number_matches_rejects_other_forms(value: object) -> None:
    assert object_number_matches(value, "523") is False


def test_object_number_matches_requires_a_number() -> None:
    assert object_number_matches("523", "") is False


def _doc(doc_id: int, fields: list[dict[str, object]] | None) -> dict[str, object]:
    raw: dict[str, object] = {"id": doc_id, "title": f"Dokument {doc_id}", "created": None}
    if fields is not None:
        raw["custom_fields"] = fields
    return raw


@pytest.mark.asyncio
async def test_object_query_is_exact_or_number_comma_and_rechecked_locally() -> None:
    """Auch wenn Paperless den Filter ignoriert und alles liefert, bleiben nur 523 und
    "523, Musterstr" übrig; 5230 und 1523 fallen heraus, total wird entsprechend gekürzt."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["custom_field_query"]
        docs = [
            _doc(1, [{"field": 7, "value": "523"}]),
            _doc(2, [{"field": 7, "value": "5230"}]),
            _doc(3, [{"field": 7, "value": "523, Musterstr"}]),
            _doc(4, [{"field": 7, "value": "1523"}]),
            _doc(5, [{"field": 9, "value": "523"}]),  # anderes Feld, kein Objektbezug
        ]
        return httpx.Response(200, json={"count": 5, "results": docs})

    search = PaperlessSearch(
        "https://paperless.example", "t", client=_client(handler), object_field_id=7
    )
    page = await search.list_by_object_number("523")
    await search.aclose()

    assert json.loads(seen["query"]) == [
        "OR",
        [[7, "exact", "523"], [7, "istartswith", "523, "]],
    ]
    assert [d.id for d in page.items] == [1, 3]
    assert page.total == 2


@pytest.mark.asyncio
async def test_results_without_custom_fields_are_trusted_to_the_server_filter() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"count": 1, "results": [_doc(1, None)]})

    search = PaperlessSearch(
        "https://paperless.example", "t", client=_client(handler), object_field_id=7
    )
    page = await search.list_by_object_number("523")
    await search.aclose()
    assert [d.id for d in page.items] == [1]


@pytest.mark.asyncio
async def test_company_filter_combines_object_and_option_id_with_and() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = request.url.params["custom_field_query"]
        docs = [
            _doc(1, [{"field": 7, "value": "523"}, {"field": 5, "value": "opt-a"}]),
            _doc(2, [{"field": 7, "value": "523"}, {"field": 5, "value": "opt-b"}]),
            _doc(3, [{"field": 7, "value": "523"}]),
        ]
        return httpx.Response(200, json={"count": 3, "results": docs})

    search = PaperlessSearch(
        "https://paperless.example",
        "t",
        client=_client(handler),
        object_field_id=7,
        company_field_id=5,
        company_options={"opt-a": "Gesellschaft A", "opt-b": "Gesellschaft B"},
    )
    page = await search.list_by_object_number("523", company_option_id="opt-a")
    await search.aclose()

    assert json.loads(seen["query"]) == [
        "AND",
        [["OR", [[7, "exact", "523"], [7, "istartswith", "523, "]]], [5, "exact", "opt-a"]],
    ]
    assert [d.id for d in page.items] == [1]
    assert page.items[0].company == "Gesellschaft A"
    assert page.total == 1


@pytest.mark.asyncio
async def test_company_label_is_mapped_without_filter() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        docs = [
            _doc(1, [{"field": 7, "value": "523"}, {"field": 5, "value": "opt-b"}]),
            _doc(2, [{"field": 7, "value": "523"}, {"field": 5, "value": "unbekannt"}]),
        ]
        return httpx.Response(200, json={"count": 2, "results": docs})

    search = PaperlessSearch(
        "https://paperless.example",
        "t",
        client=_client(handler),
        object_field_id=7,
        company_field_id=5,
        company_options={"opt-b": "Gesellschaft B"},
    )
    page = await search.list_by_object_number("523")
    await search.aclose()
    assert [(d.id, d.company) for d in page.items] == [(1, "Gesellschaft B"), (2, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("company_field_id", "company_options", "option"),
    [
        (None, {"opt-a": "A"}, "opt-a"),  # Feld nicht eingerichtet
        (5, {}, "opt-a"),  # Zuordnung leer
        (5, {"opt-a": "A"}, "opt-x"),  # Option nicht zugeordnet
    ],
)
async def test_company_filter_without_configuration_is_empty_and_sends_nothing(
    company_field_id: int | None, company_options: dict[str, str], option: str
) -> None:
    async def unreachable(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected without a usable company configuration")

    search = PaperlessSearch(
        "https://paperless.example",
        "t",
        client=_client(unreachable),
        object_field_id=7,
        company_field_id=company_field_id,
        company_options=company_options,
    )
    page = await search.list_by_object_number("523", company_option_id=option)
    await search.aclose()
    assert (page.items, page.total) == ([], 0)


@pytest.mark.asyncio
async def test_search_with_company_and_full_text_only() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json={"count": 0, "results": []})

    search = PaperlessSearch(
        "https://paperless.example",
        "t",
        client=_client(handler),
        company_field_id=5,
        company_options={"opt-a": "A"},
    )
    await search.search(company_option_id="opt-a", query="Heizung")
    await search.aclose()
    assert json.loads(seen["custom_field_query"]) == [5, "exact", "opt-a"]
    assert seen["query"] == "Heizung"


def test_parse_company_options_lines_and_semicolons() -> None:
    parsed = parse_company_options(" opt-a = Gesellschaft A \n\nopt-b=Gesellschaft B;3=Sonstige")
    assert parsed == {"opt-a": "Gesellschaft A", "opt-b": "Gesellschaft B", "3": "Sonstige"}
    assert format_company_options(parsed) == (
        "opt-a=Gesellschaft A\nopt-b=Gesellschaft B\n3=Sonstige"
    )
    assert parse_company_options(None) == {}
    assert parse_company_options("  ") == {}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("opt-a", "Form Options-ID=Gesellschaft"),
        ("=A", "Form Options-ID=Gesellschaft"),
        ("opt-a=", "Form Options-ID=Gesellschaft"),
        ("opt-a=A\nopt-a=B", "mehrfach"),
        ("x" * 65 + "=A", "zu lang"),
    ],
)
def test_parse_company_options_rejects_invalid_input(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_company_options(raw)


def test_parse_field_id() -> None:
    assert parse_field_id(None, "Feld") is None
    assert parse_field_id(" ", "Feld") is None
    assert parse_field_id(" 7 ", "Feld") == 7
    for bad in ("0", "-1", "sieben", "7.0"):
        with pytest.raises(ValueError, match="positive ganze Zahl"):
            parse_field_id(bad, "Feld")
