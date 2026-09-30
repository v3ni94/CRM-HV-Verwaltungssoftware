"""M31: Paperless-Dokumente in Ticket- und Objektansicht, gegen einen gefakten Paperless-Server
(httpx.MockTransport statt eines echten Paperless). Erwartete Werte von Hand:

* Objektsuche liefert genau die zwei Fake-Dokumente, die im Custom-Field ``object_field_id``
  (hier 7) mit "761" oder "761, ..." beginnen (``PaperlessSearch._object_query``), sortiert
  ``-created`` -> Dokument 102 (2026-01-02) vor Dokument 101 (2026-01-01).
* Tickersuche ist Volltext auf die Ticketnummer und liefert zusätzlich Dokument 103; Dedupliziert
  nach Paperless-ID ergibt Objekt+Ticket zusammen 3 verschiedene Dokumente für das Ticket
  (101, 102, 103), da 101 und 102 auch über das Objekt gefunden werden.
* Ohne gepflegte ``object_field_id`` liefert die Objektsuche laut Plan (M31) eine leere Liste
  statt zu raten: 0 Treffer, 0 total.
* Gesellschaftsfilter (Hub 7.2): Feld 5, Option ``opt-hvm`` an Dokument 101, ``opt-mhag`` an
  Dokument 102, Dokument 103 ohne Gesellschaft. Filter ``opt-hvm`` auf das Objekt ergibt nur 101
  mit Gesellschaft "Hausverwaltung", ohne Filter tragen 101 und 102 ihre Bezeichnung.
* Grenzfall der Objektnummer: Dokument 104 trägt ``<Nummer>0`` (etwa 7670 zu 767) und wird nie
  dem Objekt zugeordnet.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from mhvp.documents import routers as documents_routers
from mhvp.documents.paperless_search import PaperlessSearch
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration


class FakePaperless:
    """Minimaler Paperless-ngx-Server: ``/api/documents/`` Suche und Datei-Endpunkte.

    ``object_number`` ist je Test frei wählbar (jeder Test legt sein eigenes Objekt mit dieser
    Nummer an; ``Property.number`` ist je Tenant eindeutig, die Tenants werden über das ganze
    Testmodul wiederverwendet, daher keine feste Nummer)."""

    def __init__(self, object_number: str = "761") -> None:
        self.token = "ppl-token-secret"
        self.object_number = object_number
        self.requests: list[httpx.Request] = []
        self.docs: list[dict[str, Any]] = [
            {
                "id": 101,
                "title": "Rechnung Heizung",
                "created": "2026-01-01T09:00:00Z",
                "added": "2026-01-01T09:05:00Z",
                "correspondent": {"name": "Heizungsbau Muster"},
                "document_type": {"name": "Rechnung"},
                "tags": [{"name": "hausgeld"}],
                "page_count": 2,
                "original_file_name": "rechnung-101.pdf",
                "custom_fields": [
                    {"field": 7, "value": object_number},
                    {"field": 5, "value": "opt-hvm"},
                ],
            },
            {
                "id": 102,
                "title": "Protokoll Eigentümerversammlung",
                "created": "2026-01-02T09:00:00Z",
                "added": "2026-01-02T09:05:00Z",
                "correspondent": None,
                "document_type": None,
                "tags": [],
                "page_count": 5,
                "original_file_name": "protokoll-102.pdf",
                "custom_fields": [
                    {"field": 7, "value": f"{object_number}, Musterstraße 1"},
                    {"field": 5, "value": "opt-mhag"},
                ],
            },
            {
                "id": 103,
                "title": "Foto Schaden Ticket",
                "created": "2026-01-03T09:00:00Z",
                "added": "2026-01-03T09:05:00Z",
                "correspondent": None,
                "document_type": None,
                "tags": [],
                "page_count": 1,
                "original_file_name": "foto-103.jpg",
                # anderes Objekt, nur über die Ticket-Volltextsuche zu finden.
                "custom_fields": [{"field": 7, "value": "999"}],
            },
            {
                "id": 104,
                "title": "Anderes Objekt mit längerer Nummer",
                "created": "2025-12-31T09:00:00Z",
                "added": "2025-12-31T09:05:00Z",
                "correspondent": None,
                "document_type": None,
                "tags": [],
                "page_count": 1,
                "original_file_name": "fremd-104.pdf",
                # Grenzfall der Hub-Regel: "<Nummer>0" gehört nicht zum Objekt <Nummer>.
                "custom_fields": [
                    {"field": 7, "value": f"{object_number}0"},
                    {"field": 5, "value": "opt-hvm"},
                ],
            },
        ]

    def _auth_ok(self, request: httpx.Request) -> bool:
        return bool(request.headers.get("Authorization") == f"Token {self.token}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._auth_ok(request):
            return httpx.Response(401, json={"detail": "invalid token"})
        path = request.url.path
        if path == "/api/documents/":
            query = request.url.params.get("custom_field_query")
            full_text = request.url.params.get("query")
            results = list(self.docs)
            if query:
                # e.g. ["AND", [["OR", [[7, "exact", "761"], [7, "istartswith", "761, "]]],
                # [5, "exact", "opt-hvm"]]], evaluated like Paperless' custom_field_query.
                condition = json.loads(query)
                results = [d for d in results if _matches(condition, d)]
            if full_text:
                hits = [d for d in results if full_text in d["title"]]
                # Ticketnummer landet nicht im Titel; die Fake-Suche hängt für den Test
                # Dokument 103 an jede Ticketnummer-Suche, wie eine echte Volltextsuche es für
                # ein im Dokument erwähntes Aktenzeichen täte.
                doc_103 = self.docs[2]
                if full_text.isdigit() and doc_103 in results and doc_103 not in hits:
                    hits.append(doc_103)
                results = hits
            results = sorted(results, key=lambda d: d["created"] or "", reverse=True)
            # Paperless liefert die Zusatzfelder in der Liste mit (custom_fields).
            return httpx.Response(200, json={"count": len(results), "results": results})
        if path.startswith("/api/documents/") and path.endswith("/download/"):
            doc_id = int(path.split("/")[3])
            if doc_id not in {d["id"] for d in self.docs}:
                return httpx.Response(404)
            return httpx.Response(
                200,
                content=b"%PDF-1.4 fake",
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": f'attachment; filename="doc-{doc_id}.pdf"',
                },
            )
        return httpx.Response(404)


def _matches(condition: list[Any], doc: dict[str, Any]) -> bool:
    if condition[0] in ("AND", "OR"):
        op, parts = condition
        checks = [_matches(part, doc) for part in parts]
        return all(checks) if op == "AND" else any(checks)
    field, op, expected = condition
    values = [cf["value"] for cf in doc["custom_fields"] if cf["field"] == field]
    if op == "exact":
        return any(str(v) == str(expected) for v in values)
    if op == "istartswith":
        return any(str(v).lower().startswith(str(expected).lower()) for v in values)
    raise AssertionError(f"unexpected operator {op}")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m31a-{RUN}", name=f"M31 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"m31b-{RUN}", name=f"M31 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name, role in [
            (a, "m31admin", "tenant_admin"),
            (a, "m31caretaker", "caretaker"),  # ohne documents:read
            (b, "m31badmin", "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake(request: pytest.FixtureRequest) -> FakePaperless:
    return FakePaperless(object_number=getattr(request, "param", "761"))


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakePaperless, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Wraps ``PaperlessSearch`` so it talks to ``fake`` via ``httpx.MockTransport`` instead of a
    real Paperless server; the token, base_url and field IDs still flow through the normal
    ``DmsConnection`` row and ``_paperless_client()`` in ``documents/routers.py``."""
    import boto3
    from moto import mock_aws

    original = PaperlessSearch

    class Patched(PaperlessSearch):
        def __init__(self, base_url: str, token: str, **kwargs: Any) -> None:
            super().__init__(
                base_url,
                token,
                client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
                **kwargs,
            )

    monkeypatch.setattr(documents_routers, "PaperlessSearch", Patched)
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client
    assert original is PaperlessSearch  # patched only on the router's imported name, not globally


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(client: TestClient, h: dict[str, str], number: str) -> str:
    created = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Objekt {number}",
                "management_type": "hoa",
                "city": f"Teststadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    return str(created["id"])


COMPANY_OPTIONS = "opt-hvm=Hausverwaltung\nopt-mhag=Holding"


def _configure_paperless(
    client: TestClient,
    h: dict[str, str],
    fake: FakePaperless,
    *,
    object_field_id: str | None = "7",
    company: bool = False,
) -> Any:
    options = {"object_field_id": object_field_id} if object_field_id else {}
    if company:
        options |= {"company_field_id": "5", "company_options": COMPANY_OPTIONS}
    return _ok(
        client.put(
            "/api/v1/dms-connections/paperless",
            json={
                "enabled": True,
                "base_url": "https://paperless.example.internal",
                "secret": fake.token,
                "options": options,
            },
            headers=h,
        )
    )


def test_property_documents_happy_path_and_ordering(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake)
    prop_id = _property(client, h, "761")

    page = _ok(client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=h))
    assert page["meta"]["total"] == 2
    ids = [d["id"] for d in page["data"]]
    assert ids == [102, 101]  # newest first (-created)
    first = page["data"][0]
    assert first["title"] == "Protokoll Eigentümerversammlung"
    assert first["download_url"].endswith(f"/api/v1/dms-documents/{102}/file?kind=download")
    assert first["preview_url"].endswith(f"/api/v1/dms-documents/{102}/file?kind=preview")

    # Detail: the file proxy streams bytes with the server-side token, the token itself never
    # appears in the response.
    file_response = client.get("/api/v1/dms-documents/102/file", headers=h)
    assert file_response.status_code == 200
    assert file_response.content == b"%PDF-1.4 fake"
    assert file_response.headers["content-type"] == "application/pdf"
    assert fake.token not in file_response.text
    # A missing document in Paperless surfaces as MHVP-DOC-0006 (Paperless unavailable), 503.
    missing = client.get("/api/v1/dms-documents/9999/file", headers=h)
    assert missing.status_code == 503
    assert "MHVP-DOC-0006" in missing.text


@pytest.mark.parametrize("fake", ["762"], indirect=True)
def test_ticket_documents_combine_object_and_fulltext_search(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake)
    prop_id = _property(client, h, "762")
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Wasserschaden", "property_id": prop_id},
            headers=h,
        ),
        201,
    )

    page = _ok(client.get(f"/api/v1/tickets/{ticket['id']}/dms-documents", headers=h))
    # 101 and 102 via the property's object number; 103 mentions no ticket reference and
    # belongs to another object, so it is not listed (regression Ticket #34).
    ids = sorted(d["id"] for d in page["data"])
    assert ids == [101, 102]
    assert page["meta"]["total"] == 2


def test_object_field_not_configured_returns_empty_instead_of_guessing(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake, object_field_id=None)
    prop_id = _property(client, h, "763")

    page = _ok(client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=h))
    assert page == {"data": [], "meta": {"page": 1, "per_page": 25, "total": 0}}


def test_dms_not_configured_returns_502(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m31admin"))
    # Reset: an earlier test in this module may already have configured Paperless for this
    # tenant (the tenant persists across tests). Disable it so "not configured" is exercised.
    _ok(client.put("/api/v1/dms-connections/paperless", json={"enabled": False}, headers=h))
    prop_id = _property(client, h, "764")
    response = client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=h)
    assert response.status_code == 502
    assert "MHVP-DOC-0005" in response.text


def test_authorization_role_without_documents_read_gets_403(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake)
    prop_id = _property(client, h, "765")

    # "caretaker" has properties:read + tickets:* but not documents:read (permissions.py).
    caretaker = bearer(login(client, world, "m31caretaker"))
    assert (
        client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=caretaker).status_code
        == 403
    )
    assert client.get("/api/v1/dms-documents/101/file", headers=caretaker).status_code == 403


def test_tenant_separation_other_tenant_sees_nothing(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake)
    prop_id = _property(client, h, "766")

    hb = bearer(login(client, world, "m31badmin"))
    # Tenant B cannot even resolve tenant A's property id (RLS: not found, not 200 with data).
    assert client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=hb).status_code == 404
    # Tenant B has its own (unconfigured) Paperless connection -> 502, never tenant A's documents.
    prop_b = _property(client, hb, "761")
    response = client.get(f"/api/v1/properties/{prop_b}/dms-documents", headers=hb)
    assert response.status_code == 502


def test_validation_bad_file_kind_is_422(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake)
    assert client.get("/api/v1/dms-documents/101/file?kind=upload", headers=h).status_code == 422


def test_validation_bad_property_id_is_422(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m31admin"))
    assert client.get("/api/v1/properties/not-a-uuid/dms-documents", headers=h).status_code == 422


# Hub 7.2: Objektsuche und Gesellschaftsfilter ---------------------------------------------


@pytest.mark.parametrize("fake", ["767"], indirect=True)
def test_company_filter_on_property_documents_and_company_list(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    connection = _configure_paperless(client, h, fake, company=True)
    assert connection["options"]["company_options"] == COMPANY_OPTIONS
    prop_id = _property(client, h, "767")

    companies = _ok(client.get("/api/v1/dms-documents/companies", headers=h))
    assert companies == [
        {"option_id": "opt-hvm", "label": "Hausverwaltung"},
        {"option_id": "opt-mhag", "label": "Holding"},
    ]

    # Ohne Filter: 101 und 102, nicht 104 ("7670"), jeweils mit Gesellschaft.
    page = _ok(client.get(f"/api/v1/properties/{prop_id}/dms-documents", headers=h))
    assert [(d["id"], d["company"]) for d in page["data"]] == [
        (102, "Holding"),
        (101, "Hausverwaltung"),
    ]

    filtered = _ok(
        client.get(f"/api/v1/properties/{prop_id}/dms-documents?company=opt-hvm", headers=h)
    )
    assert [d["id"] for d in filtered["data"]] == [101]
    assert filtered["meta"]["total"] == 1
    sent = json.loads(fake.requests[-1].url.params["custom_field_query"])
    assert sent == [
        "AND",
        [["OR", [[7, "exact", "767"], [7, "istartswith", "767, "]]], [5, "exact", "opt-hvm"]],
    ]

    unknown = client.get(f"/api/v1/properties/{prop_id}/dms-documents?company=opt-x", headers=h)
    assert unknown.status_code == 422
    assert "MHVP-CORE-0004" in unknown.text


@pytest.mark.parametrize("fake", ["768"], indirect=True)
def test_ticket_documents_with_company_filter(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake, company=True)
    prop_id = _property(client, h, "768")
    ticket = _ok(
        client.post(
            "/api/v1/tickets", json={"title": "Heizung", "property_id": prop_id}, headers=h
        ),
        201,
    )
    page = _ok(
        client.get(f"/api/v1/tickets/{ticket['id']}/dms-documents?company=opt-mhag", headers=h)
    )
    # Objekt und Gesellschaft: nur 102; die Volltexttreffer (103 ohne Gesellschaft) fallen weg.
    assert [d["id"] for d in page["data"]] == [102]


@pytest.mark.parametrize("fake", ["769"], indirect=True)
def test_search_endpoint_object_company_and_validation(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake, company=True)

    page = _ok(client.get("/api/v1/dms-documents?object_number=769", headers=h))
    assert [d["id"] for d in page["data"]] == [102, 101]

    by_company = _ok(client.get("/api/v1/dms-documents?company=opt-hvm", headers=h))
    # Nur Gesellschaft: 101 (769) und 104 (7690), beide mit opt-hvm.
    assert [d["id"] for d in by_company["data"]] == [101, 104]

    combined = _ok(client.get("/api/v1/dms-documents?object_number=769&company=opt-hvm", headers=h))
    assert [d["id"] for d in combined["data"]] == [101]

    # Ohne Kriterium, mit unzulässiger Nummer oder unbekannter Gesellschaft: 422.
    for query in ("", "?object_number=76", "?object_number=7690", "?company=opt-x"):
        response = client.get(f"/api/v1/dms-documents{query}", headers=h)
        assert response.status_code == 422, query

    caretaker = bearer(login(client, world, "m31caretaker"))
    assert (
        client.get("/api/v1/dms-documents?object_number=769", headers=caretaker).status_code == 403
    )
    assert client.get("/api/v1/dms-documents/companies", headers=caretaker).status_code == 403


def test_search_endpoint_needs_object_field_for_object_number(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    _configure_paperless(client, h, fake, object_field_id=None)
    response = client.get("/api/v1/dms-documents?object_number=761", headers=h)
    assert response.status_code == 422
    assert _ok(client.get("/api/v1/dms-documents/companies", headers=h)) == []


def test_put_connection_validates_paperless_field_ids_and_company_options(
    client: TestClient, world: World, fake: FakePaperless
) -> None:
    h = bearer(login(client, world, "m31admin"))
    base = {"enabled": True, "base_url": "https://paperless.example.internal", "secret": "x"}
    for options in (
        {"object_field_id": "sieben"},
        {"company_field_id": "0"},
        {"company_options": "opt-hvm"},
        {"company_options": "opt-hvm=A\nopt-hvm=B"},
    ):
        response = client.put(
            "/api/v1/dms-connections/paperless", json={**base, "options": options}, headers=h
        )
        assert response.status_code == 422, options

    saved = _ok(
        client.put(
            "/api/v1/dms-connections/paperless",
            json={
                **base,
                "options": {
                    "object_field_id": " 7 ",
                    "company_field_id": "",
                    "company_options": " opt-hvm = Hausverwaltung ; ",
                },
            },
            headers=h,
        )
    )
    # Normalisiert gespeichert, leere Feld-ID entfällt statt eines geratenen Werts.
    assert saved["options"] == {
        "object_field_id": "7",
        "company_options": "opt-hvm=Hausverwaltung",
    }
    # Ohne Feld-ID Gesellschaft ist der Filter nicht verfügbar, auch mit Zuordnung.
    assert _ok(client.get("/api/v1/dms-documents/companies", headers=h)) == []
