"""M7 acceptance: provider release with DPA evidence (four eyes), budget lock, contact list via
chat into contacts, owner/tenant list into property, units and contracts, undo, schema retry,
deduplication, question answering over documents (9, 10). No live model calls."""

import asyncio
import io
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from openpyxl import Workbook
from pydantic import SecretStr

from mhvp.ai import gateway, providers
from mhvp.ai.providers import Completion, ProviderError
from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ai"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


class FakeProvider:
    """Returns queued outputs in order and records every request."""

    def __init__(self) -> None:
        self.queue: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = self.queue.pop(0) if self.queue else {"summary": "x", "open_points": []}
        return Completion(
            data=data,
            raw_text=json.dumps(data),
            tokens_in=1000,
            tokens_out=500,
            model=kwargs["model"],
        )


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"k-{RUN}", name=f"KI {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"l-{RUN}", name=f"Fremd KI {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m7admin", a, "tenant_admin"),
            ("m7second", a, "tenant_admin"),
            ("m7clerk", a, "standard"),
            ("m7other", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str) -> str:
    doc = _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h))
    return str(doc["id"])


def _xlsx(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "small": {
            "model": "claude-haiku-4-5",
            "input_eur_per_mtok": "1",
            "output_eur_per_mtok": "5",
        },
        "large": {"model": "claude-opus-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


def _setup_provider(c: TestClient, world: World, **overrides: Any) -> dict[str, str]:
    admin = bearer(login(c, world, "m7admin"))
    second = bearer(login(c, world, "m7second"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    body = {**PROVIDER, "dpa_document_id": dpa, **overrides}
    _ok(c.put("/api/v1/ai/providers/anthropic", json=body, headers=admin), 200)
    released = c.post("/api/v1/ai/providers/anthropic/release", headers=second)
    assert released.status_code == 200, released.text
    return admin


def _contact(**values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_row": None,
        "kind": "person",
        "salutation": None,
        "title": None,
        "first_name": None,
        "last_name": None,
        "company_name": None,
        "street": None,
        "house_number": None,
        "postal_code": None,
        "city": None,
        "phones": [],
        "emails": [],
        "iban": None,
        "role": None,
        "unit_number": None,
        "co_members": [],
        "confidence": 0.9,
    }
    return {**base, **values}


def _chat(
    c: TestClient,
    h: dict[str, str],
    task: str,
    content: str,
    docs: list[str],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversation = _ok(c.post("/api/v1/ai/conversations", json=context or {}, headers=h))
    return _ok(  # type: ignore[no-any-return]
        c.post(
            f"/api/v1/ai/conversations/{conversation['id']}/messages",
            json={"content": content, "task": task, "document_ids": docs},
            headers=h,
        ),
        202,
    )


def test_release_needs_second_person_and_evidence(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "m7admin"))
    second = bearer(login(client, world, "m7second"))
    doc = _upload(client, admin, "liste.txt", b"Max Muster, Hauptstr. 1", "text/plain")
    blocked = _chat(client, admin, "extract_contacts", "Kontakte anlegen", [doc])
    assert blocked["status"] == "blocked"
    assert "Kein freigegebener KI-Anbieter" in blocked["error"]
    assert fake.calls == []  # nothing left the platform
    no_dpa = {**PROVIDER, "data_processing_agreement_signed": False}
    _ok(client.put("/api/v1/ai/providers/anthropic", json=no_dpa, headers=admin), 200)
    own = client.post("/api/v1/ai/providers/anthropic/release", headers=admin)
    assert own.status_code == 403
    missing = client.post("/api/v1/ai/providers/anthropic/release", headers=second)
    assert missing.status_code == 422
    assert "Auftragsverarbeitungsvertrag" in missing.json()["detail"]
    unreleased = _chat(client, admin, "extract_contacts", "Kontakte anlegen", [doc])
    assert unreleased["status"] == "blocked"
    assert "Freigabe" in unreleased["error"]
    listed = _ok(client.get("/api/v1/ai/providers", headers=admin), 200)
    assert listed[0]["has_api_key"] is True
    assert "api_key" not in listed[0]
    second = _ok(client.put("/api/v1/ai/providers/openai", json=PROVIDER, headers=admin), 200)
    assert (second["provider"], second["has_api_key"]) == ("openai", True)
    clerk = bearer(login(client, world, "m7clerk"))
    assert client.get("/api/v1/ai/providers", headers=clerk).status_code == 403


def test_contact_list_to_contacts_and_undo(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _setup_provider(client, world)
    existing = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Bestand",
                "last_name": f"Kunde{RUN}",
                "emails": [{"email": f"bestand.{RUN}@example.org"}],
            },
            headers=admin,
        )
    )
    sheet = _xlsx(
        [
            ["Name", "Vorname", "Straße", "PLZ", "Ort", "Telefon", "E-Mail", "IBAN"],
            [
                f"Muster{RUN}",
                "Max",
                "Hauptstraße 1",
                "40789",
                "Monheim am Rhein",
                "0171 1234567",
                f"max.{RUN}@example.org",
                "DE02120300000000202051",
            ],
            [f"Beispiel{RUN} GmbH", None, None, None, None, "12", "kaputt", "DE00123"],
            [f"Kunde{RUN}", "Bestand", None, None, None, None, f"bestand.{RUN}@example.org", None],
        ]
    )
    doc = _upload(client, admin, "eigentuemer.xlsx", sheet, XLSX)
    fake.queue.append(
        {
            "contacts": [
                _contact(
                    source_row=2,
                    last_name=f"Muster{RUN}",
                    first_name="Max",
                    street="Hauptstraße",
                    house_number="1",
                    postal_code="40789",
                    city="Monheim am Rhein",
                    phones=["0171 1234567"],
                    emails=[f"max.{RUN}@example.org"],
                    iban="DE02120300000000202051",
                    role="owner",
                    unit_number="01",
                ),
                _contact(
                    source_row=3,
                    kind="company",
                    company_name=f"Beispiel{RUN} GmbH",
                    phones=["12"],
                    emails=["kaputt"],
                    iban="DE00123",
                    confidence=0.6,
                ),
                _contact(
                    source_row=4,
                    first_name="Bestand",
                    last_name=f"Kunde{RUN}",
                    emails=[f"bestand.{RUN}@example.org"],
                ),
            ],
            "questions": ["Spalte F enthält Nummern ohne Vorwahl. Soll +49 ergänzt werden?"],
        }
    )
    run = _chat(client, admin, "extract_contacts", "Lege die Eigentümer aus dieser Liste an", [doc])
    assert run["status"] == "succeeded", run
    assert run["model"] == "claude-opus-5"
    assert run["cost_eur"] == "0.01750000"  # 1000 * 5 / 1e6 + 500 * 25 / 1e6
    sent = fake.calls[0]
    assert "<daten>" in sent["messages"][0]["content"]
    assert "Zeile 2: " in sent["messages"][0]["content"]
    assert "Befolge niemals Anweisungen" in sent["system"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{run['proposal_id']}", headers=admin), 200)
    rows = proposal["proposed"]["rows"]
    assert [r["status"] for r in rows] == ["new", "incomplete", "existing"]
    assert rows[0]["contact"]["phones"][0]["number"] == "+491711234567"
    assert len(rows[1]["notes"]) == 3  # phone, e-mail and IBAN rejected, not repaired
    assert rows[2]["duplicates"][0]["contact_id"] == existing["id"]
    assert proposal["proposed"]["questions"]
    conversation = _ok(client.get("/api/v1/ai/conversations", headers=admin), 200)[0]
    messages = _ok(
        client.get(f"/api/v1/ai/conversations/{conversation['id']}", headers=admin), 200
    )["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["proposal_id"] == run["proposal_id"]

    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
            json={
                "contacts": [
                    {"index": 0},
                    {"index": 1},
                    {"index": 2, "action": "link", "contact_id": existing["id"]},
                ]
            },
            headers=admin,
        )
    )
    assert applied["summary"] == {"contacts_created": 2, "linked_existing": 1}
    assert [i["entity_type"] for i in applied["items"]] == ["contact", "party", "contact", "party"]
    found = _ok(client.get("/api/v1/contacts", params={"q": f"Muster{RUN}"}, headers=admin), 200)
    assert found["total"] == 1
    again = client.post(
        f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
        json={"contacts": [{"index": 0}]},
        headers=admin,
    )
    assert again.status_code == 409

    other = bearer(login(client, world, "m7other"))
    assert client.get(f"/api/v1/ai/runs/{run['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/imports/{applied['id']}", headers=other).status_code == 404

    undone = _ok(client.post(f"/api/v1/imports/{applied['id']}/undo", headers=admin), 200)
    assert undone["status"] == "undone"
    assert all(i["undone"] for i in undone["items"])
    gone = _ok(client.get("/api/v1/contacts", params={"q": f"Muster{RUN}"}, headers=admin), 200)
    assert gone["total"] == 0
    assert client.post(f"/api/v1/imports/{applied['id']}/undo", headers=admin).status_code == 409

    # Same input again: deduplicated, no second provider call.
    calls = len(fake.calls)
    repeat = _chat(
        client, admin, "extract_contacts", "Lege die Eigentümer aus dieser Liste an", [doc]
    )
    assert repeat["status"] == "succeeded"
    assert len(fake.calls) == calls
    usage = _ok(client.get("/api/v1/ai/usage", headers=admin), 200)
    assert usage["spent_eur"] == "0.02"
    assert usage["blocked"] is False


def test_large_spreadsheet_is_chunked_not_blocked(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    """A synthetic (never real tenant data) contact list large enough to raise ~700k characters
    of table text used to be blocked outright ("zu umfangreich"); it must now be split into row
    chunks and processed with one provider call per chunk instead."""
    admin = _setup_provider(client, world)
    header = ["Name", "Vorname", "Straße", "PLZ", "Ort", "Telefon", "E-Mail", "IBAN"]

    def _row(n: int) -> list[Any]:
        return [
            f"Nachname{n}",
            f"Vorname{n}",
            f"Musterstraße {n}",
            "40789",
            "Monheim am Rhein",
            "0171 0000000",
            f"kontakt{n}@example.org",
            None,
        ]

    # One row rendered ("Zeile n: ...") is about 90 characters; 8_500 rows comfortably clears
    # 700_000 characters of table text without rebuilding the workbook on every row.
    rows = [header, *[_row(n) for n in range(1, 8_501)]]
    sheet = _xlsx(rows)
    raw_text = gateway.spreadsheet_text(sheet)
    assert len(raw_text) > 700_000
    expected_chunks = len(gateway._chunk_table_body(raw_text))
    assert expected_chunks > 1

    doc = _upload(client, admin, "kontakte.xlsx", sheet, XLSX)
    fake.queue.extend([{"contacts": [], "questions": []}] * expected_chunks)
    run = _chat(client, admin, "extract_contacts", "Kontakte anlegen", [doc])
    assert run["status"] == "succeeded", run
    assert len(fake.calls) == expected_chunks
    assert run["input_stats"]["kontakte.xlsx"] == len(raw_text)
    assert run["progress"] == {
        "stage": "Fertig",
        "current": expected_chunks,
        "total": expected_chunks,
    }


def _unit(**values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": "01",
        "label": None,
        "building": None,
        "location": None,
        "unit_type": "apartment",
        "living_area_sqm": None,
        "mea": None,
        "source": None,
        "confidence": 0.9,
    }
    return {**base, **values}


def _party(**values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "role": "owner",
        "unit_number": "01",
        "kind": "person",
        "salutation": None,
        "first_name": None,
        "last_name": None,
        "company_name": None,
        "start_date": None,
        "payments": [],
        "source": None,
        "confidence": 0.9,
    }
    return {**base, **values}


def test_owner_list_to_property_and_partial_undo(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _setup_provider(client, world)
    doc = _upload(
        client,
        admin,
        "eigentuemerliste.txt",
        "Eigentümerliste WEG Rheinpromenade 13\nWE 01 Anna Beispiel seit 01.01.2020".encode(),
        "text/plain",
    )
    output = {
        "property": {
            "number": None,
            "name": "WEG Rheinpromenade 13",
            "management_type": "hoa",
            "street": "Rheinpromenade",
            "house_number": "13",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        },
        "buildings": ["Haus A"],
        "units": [
            _unit(number="01", building="Haus A", living_area_sqm="71.35", mea="125.5"),
            _unit(number="02", building="Haus A", living_area_sqm="1.234,5", mea="98"),
        ],
        "parties": [
            _party(
                unit_number="01",
                first_name="Anna",
                last_name=f"Beispiel{RUN}",
                start_date="2020-01-01",
                payments=[{"payment_type_code": "hoa_fee", "gross": "300.00", "valid_from": None}],
            ),
            _party(unit_number="02", first_name="Bernd", last_name=f"Offen{RUN}", start_date=None),
            _party(
                unit_number="09", first_name="Ohne", last_name="Einheit", start_date="2020-01-01"
            ),
        ],
        "questions": [],
    }
    # First answer violates the schema (missing "questions"); the gateway retries once.
    fake.queue += [{k: v for k, v in output.items() if k != "questions"}, output]
    run = _chat(
        client, admin, "extract_property", "Lege dieses Objekt mit allen Einheiten an", [doc]
    )
    assert run["status"] == "succeeded", run
    assert len(fake.calls) == 2
    assert run["tokens_in"] == 2000
    assert "verletzt das Schema" in fake.calls[1]["messages"][-1]["content"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{run['proposal_id']}", headers=admin), 200)
    assert any("1.234,5" in n for n in proposal["proposed"]["notes"])
    missing_number = client.post(
        f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
        json={"property": {"as_of": "2020-01-01"}},
        headers=admin,
    )
    assert missing_number.status_code == 422
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
            json={
                "property": {
                    "number": "701",
                    "as_of": "2020-01-01",
                    "vat_percent_by_payment_type": {"hoa_fee": "0"},
                }
            },
            headers=admin,
        )
    )
    notes = applied["summary"]["notes"]
    assert any("Beginn fehlt" in n for n in notes)
    assert any("Einheit 09 fehlt" in n for n in notes)
    prop_id = applied["summary"]["property_id"]
    prop = _ok(client.get(f"/api/v1/properties/{prop_id}", headers=admin), 200)
    assert prop["status"] == "onboarding"
    units = _ok(
        client.get(
            f"/api/v1/properties/{prop_id}/units", params={"as_of": "2021-01-01"}, headers=admin
        ),
        200,
    )
    assert [u["number"] for u in units] == ["01", "02"]
    assert units[1]["living_area_sqm"] is None
    contracts = _ok(
        client.get("/api/v1/contracts", params={"property_id": prop_id}, headers=admin), 200
    )
    assert len(contracts) == 1
    assert contracts[0]["kind"] == "ownership"
    assert contracts[0]["title_transfer_date"] == "2020-01-01"
    assert contracts[0]["payments"][0]["gross"] == "300.00"

    # A document is linked to the contract afterwards: that part must stay on undo.
    letter = _upload(client, admin, "brief.txt", b"Schreiben", "text/plain")
    _ok(
        client.post(
            f"/api/v1/documents/{letter}/links",
            json={"entity_type": "contract", "entity_id": contracts[0]["id"]},
            headers=admin,
        )
    )
    undone = _ok(client.post(f"/api/v1/imports/{applied['id']}/undo", headers=admin), 200)
    assert undone["status"] == "partially_undone"
    kept = {i["entity_type"]: i["kept_reason"] for i in undone["items"] if not i["undone"]}
    assert kept["contract"] == "mit Dokumenten verknüpft"
    assert kept["property"] in ("weitere Verträge vorhanden", "Einheiten vorhanden")
    assert _ok(client.get("/api/v1/contracts", params={"property_id": prop_id}, headers=admin), 200)


def test_answer_question_budget_lock_and_failures(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "m7admin"))
    spent = Decimal(_ok(client.get("/api/v1/ai/usage", headers=admin), 200)["spent_eur"])
    admin = _setup_provider(client, world, monthly_budget_eur=str(spent + Decimal("0.02")))
    _upload(
        client,
        admin,
        "hausordnung.txt",
        f"Hausordnung {RUN}: Die Mülltonnen werden dienstags geleert.".encode(),
        "text/plain",
    )
    fake.queue.append(
        {
            "answer": "Dienstags.",
            "sources": [{"document_id": "x", "excerpt": "dienstags"}],
            "answerable": True,
        }
    )
    run = _chat(client, admin, "answer_question", f"Wann wird der Müll in {RUN} geleert?", [])
    assert run["status"] == "succeeded"
    assert run["model"] == "claude-haiku-4-5"  # small tier for questions (9.3)
    assert f"Hausordnung {RUN}" in fake.calls[-1]["messages"][0]["content"]
    fake.queue += [{"summary": 1}, {"summary": 2}]
    failed = _chat(client, admin, "summarize", "Fasse zusammen", [])
    assert failed["status"] == "failed"
    assert failed["error"].startswith("Schemafehler")
    # Spent so far exceeds the tiny budget: the next run is blocked before any call.
    for _ in range(8):
        last = _chat(client, admin, "summarize", f"Fasse zusammen {_}", [])
        if last["status"] == "blocked":
            break
    assert last["status"] == "blocked"
    assert "Monatsbudget" in last["error"]


class RecordingFactory:
    """One fake client per provider; records which provider answered; can fail one provider."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failing: set[str] = set()

    def __call__(self, provider: Any, _key: str) -> Any:
        factory = self

        class Client:
            async def complete(self, **kwargs: Any) -> Completion:
                factory.calls.append(provider.value)
                if provider.value in factory.failing:
                    raise ProviderError("HTTP 503", retryable=True)
                data = {"summary": f"von {provider.value}", "open_points": []}
                return Completion(
                    data=data,
                    raw_text=json.dumps(data),
                    tokens_in=100,
                    tokens_out=50,
                    model=kwargs["model"],
                )

        return Client()


def test_routing_strategy_and_fallback(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expected by hand: anthropic_first with an exhausted Anthropic budget -> OpenAI answers
    and the run records the fallback; anthropic_only -> blocked; openai_first -> OpenAI;
    alternate -> the provider not used last; an OpenAI outage under openai_first -> Anthropic."""
    monkeypatch.setattr(gateway, "RETRY_DELAYS_S", ())
    factory = RecordingFactory()
    providers.set_factory(factory)
    try:
        admin = _setup_provider(client, world, monthly_budget_eur="500.00")
        second = bearer(login(client, world, "m7second"))
        dpa = _upload(client, admin, "avv-openai.txt", b"AVV OpenAI Muster", "text/plain")
        openai_body = {
            **PROVIDER,
            "dpa_document_id": dpa,
            "monthly_budget_eur": "500.00",
            "models": {
                "small": {
                    "model": "gpt-5-mini",
                    "input_eur_per_mtok": "1",
                    "output_eur_per_mtok": "5",
                },
                "large": {"model": "gpt-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
            },
        }
        _ok(client.put("/api/v1/ai/providers/openai", json=openai_body, headers=admin), 200)
        _ok(client.post("/api/v1/ai/providers/openai/release", headers=second), 200)

        assert (
            _ok(client.get("/api/v1/ai/routing", headers=admin), 200)["strategy"]
            == "anthropic_first"
        )
        run = _chat(client, admin, "summarize", f"Strategie A {RUN}", [])
        assert (run["status"], run["provider"], run["model"]) == (
            "succeeded",
            "anthropic",
            "claude-haiku-4-5",
        )

        _ok(client.put("/api/v1/ai/routing", json={"strategy": "openai_first"}, headers=admin), 200)
        run = _chat(client, admin, "summarize", f"Strategie B {RUN}", [])
        assert (run["provider"], run["model"]) == ("openai", "gpt-5-mini")

        _ok(client.put("/api/v1/ai/routing", json={"strategy": "alternate"}, headers=admin), 200)
        first = _chat(client, admin, "summarize", f"Strategie C1 {RUN}", [])["provider"]
        second_run = _chat(client, admin, "summarize", f"Strategie C2 {RUN}", [])["provider"]
        assert {first, second_run} == {"anthropic", "openai"}

        # Anthropic budget exhausted: anthropic_first falls back to OpenAI ...
        spent = Decimal(_ok(client.get("/api/v1/ai/usage", headers=admin), 200)["spent_eur"])
        _setup_provider(client, world, monthly_budget_eur="0.01")
        _ok(
            client.put("/api/v1/ai/routing", json={"strategy": "anthropic_first"}, headers=admin),
            200,
        )
        run = _chat(client, admin, "summarize", f"Strategie D {RUN} {spent}", [])
        assert (run["status"], run["provider"]) == ("succeeded", "openai")
        assert any("anthropic: Monatsbudget" in x for x in run["fallback"])
        # ... anthropic_only does not.
        _ok(
            client.put("/api/v1/ai/routing", json={"strategy": "anthropic_only"}, headers=admin),
            200,
        )
        run = _chat(client, admin, "summarize", f"Strategie E {RUN}", [])
        assert run["status"] == "blocked"
        assert "Monatsbudget" in run["error"]
        assert "openai" not in run["error"]

        # OpenAI outage under openai_first: Anthropic (budget restored) takes over.
        _setup_provider(client, world, monthly_budget_eur="500.00")
        _ok(client.put("/api/v1/ai/routing", json={"strategy": "openai_first"}, headers=admin), 200)
        factory.failing.add("openai")
        run = _chat(client, admin, "summarize", f"Strategie F {RUN}", [])
        assert (run["status"], run["provider"]) == ("succeeded", "anthropic")
        assert any("openai: Anbieterfehler" in x for x in run["fallback"])
        _ok(client.put("/api/v1/ai/routing", json={"strategy": "openai_only"}, headers=admin), 200)
        run = _chat(client, admin, "summarize", f"Strategie G {RUN}", [])
        assert (run["status"], run["provider"]) == ("failed", "openai")
    finally:
        providers.set_factory(providers.default_factory)
        _ok(
            client.put("/api/v1/ai/routing", json={"strategy": "anthropic_first"}, headers=admin),
            200,
        )


def test_audit_view_lists_all_chats_for_admins_only(client: TestClient, world: World) -> None:
    """Expected by hand: a clerk sees only own chats and gets 403 for scope=all; the admin sees
    the chats of every user newest first with user name and message count, can filter by user,
    date and text, can read a foreign chat but cannot write into it."""
    admin = bearer(login(client, world, "m7admin"))
    clerk = bearer(login(client, world, "m7clerk"))
    mine = _ok(
        client.post("/api/v1/ai/conversations", json={"title": f"Clerk {RUN}"}, headers=clerk)
    )
    theirs = _ok(
        client.post("/api/v1/ai/conversations", json={"title": f"Admin {RUN}"}, headers=admin)
    )
    own = _ok(client.get("/api/v1/ai/conversations", headers=clerk), 200)
    assert {c["id"] for c in own} >= {mine["id"]}
    assert theirs["id"] not in {c["id"] for c in own}
    assert (
        client.get("/api/v1/ai/conversations", params={"scope": "all"}, headers=clerk).status_code
        == 403
    )
    assert client.get(f"/api/v1/ai/conversations/{theirs['id']}", headers=clerk).status_code == 404

    everything = _ok(
        client.get("/api/v1/ai/conversations", params={"scope": "all"}, headers=admin), 200
    )
    by_id = {c["id"]: c for c in everything}
    assert mine["id"] in by_id
    assert theirs["id"] in by_id
    assert by_id[mine["id"]]["created_by_name"] == "m7clerk"
    assert by_id[mine["id"]]["message_count"] == 0
    stamps = [c["created_at"] for c in everything]
    assert stamps == sorted(stamps, reverse=True)
    filtered = _ok(
        client.get(
            "/api/v1/ai/conversations",
            params={"scope": "all", "user_id": world.users["m7clerk"], "q": f"Clerk {RUN}"},
            headers=admin,
        ),
        200,
    )
    assert [c["id"] for c in filtered] == [mine["id"]]
    assert (
        _ok(
            client.get(
                "/api/v1/ai/conversations",
                params={"scope": "all", "date_to": "2000-01-01"},
                headers=admin,
            ),
            200,
        )
        == []
    )
    # Read access for the audit trail, no write access into another person's chat.
    detail = _ok(client.get(f"/api/v1/ai/conversations/{mine['id']}", headers=admin), 200)
    assert detail["created_by_name"] == "m7clerk"
    assert (
        client.post(
            f"/api/v1/ai/conversations/{mine['id']}/messages",
            json={"content": "x", "task": "summarize", "document_ids": []},
            headers=admin,
        ).status_code
        == 404
    )
