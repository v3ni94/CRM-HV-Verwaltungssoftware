"""R03 (Q07 rest): tickets from open takeover points, takeover checklist in the owner portal,
bank accounts, allocation keys of every kind, debtor accounts and document links in the
property onboarding (one transaction, undo)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m7_ai import (
    BUCKET,
    FakeProvider,
    _chat,
    _ok,
    _party,
    _settings,
    _setup_provider,
    _unit,
    _upload,
)

pytestmark = pytest.mark.integration
IBAN = "DE02120300000000202051"


class _R03World(World):
    """Own e-mail namespace: the helpers of test_m7_ai log in as ``m7admin`` and ``m7second``,
    whose addresses must not collide with the world of test_m7_ai in the same process."""

    def email(self, name: str) -> str:
        return f"r03-{super().email(name)}"


async def _world_with_reader(settings: Any) -> World:
    # Own tenants and users: ``_world`` of test_m7_ai is not reusable in the same process
    # (slugs and e-mail addresses are derived from the module constant RUN).
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services
    from tests.integration.test_m2_platform import PASSWORD, RUN

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        a, _ = await services.provision_tenant(factory, slug=f"r03-{RUN}", name=f"R03 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r03b-{RUN}", name=f"R03 B {RUN}")
        world = _R03World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("r03admin", a, "tenant_admin"),
            ("r03other", b, "tenant_admin"),
            ("m7admin", a, "tenant_admin"),
            ("m7second", a, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        uid = await services.create_user(
            factory, email=world.email("r03reader"), display_name="Lesend", password=PASSWORD
        )
        world.users["r03reader"] = uid
        await services.add_member(
            factory,
            tenant_id=world.tenant_a,
            user_id=uid,
            role_codes=["caretaker"],
            actor_user_id=None,
        )
    finally:
        await engine.dispose()
    return world


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world_with_reader(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _property_proposal(
    c: TestClient, world: World, fake: FakeProvider
) -> tuple[dict[str, str], dict[str, Any], str]:
    admin = _setup_provider(c, world)
    doc = _upload(c, admin, "eigentuemerliste.txt", b"Eigentuemerliste WEG Test", "text/plain")
    fake.queue.append(
        {
            "property": {
                "number": None,
                "name": "WEG Testweg 1",
                "management_type": "hoa",
                "street": "Testweg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            "buildings": ["Haus A"],
            "units": [
                _unit(number="01", building="Haus A", living_area_sqm="70.5", mea="100"),
                _unit(number="02", building="Haus A", living_area_sqm="55", mea="80"),
            ],
            "parties": [
                _party(unit_number="01", last_name="Eigner", start_date="2020-01-01"),
            ],
            "questions": [],
        }
    )
    run = _chat(c, admin, "extract_property", "Objekt anlegen", [doc])
    assert run["status"] == "succeeded", run
    return admin, run, doc


def test_onboarding_extras_and_undo(client: TestClient, world: World, fake: FakeProvider) -> None:
    admin, run, doc = _property_proposal(client, world, fake)
    extra_doc = _upload(client, admin, "grundbuch.txt", b"Grundbuchauszug", "text/plain")
    body: dict[str, Any] = {
        "number": "731",
        "as_of": "2020-01-01",
        "bank_accounts": [
            {
                "kind": "hoa",
                "iban": IBAN,
                "holder": "WEG Testweg 1",
                "bank_name": "Testbank",
                "is_default": True,
            },
            {"kind": "rent", "iban": "DE89370400440532013000", "holder": "Ohne Rechtsträger"},
        ],
        "allocation_keys": [
            {"code": "WFL", "values": {"01": "70.5", "02": "55", "99": "1"}},
            {"code": "FEST", "values": {"01": "12.50"}},
            {"code": "V_KW"},
            {
                "code": "SOND_A",
                "name": "Sonderschlüssel A",
                "unit_of_measure": "%",
                "kind": "fixed_share",
                "expected_total": "100",
                "values": {"01": "60", "02": "40"},
            },
        ],
        "create_debtor_accounts": True,
        "document_ids": [extra_doc],
    }
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
            json={"property": body},
            headers=admin,
        )
    )
    notes = applied["summary"]["notes"]
    assert any("Einheit 99 unbekannt" in n for n in notes)
    assert any("kein passender Rechtsträger" in n for n in notes)
    assert any("Buchungskreis" in n and "angelegt" in n for n in notes)
    prop_id = applied["summary"]["property_id"]
    accounts = _ok(client.get(f"/api/v1/properties/{prop_id}/bank-accounts", headers=admin), 200)
    assert len(accounts) == 1
    assert accounts[0]["kind"] == "hoa"
    assert accounts[0]["iban_masked"].endswith("2051")
    ledgers = _ok(
        client.get("/api/v1/accounting/ledgers", params={"property_id": prop_id}, headers=admin),
        200,
    )
    assert len(ledgers) == 1
    ledger_accounts = _ok(
        client.get(f"/api/v1/accounting/ledgers/{ledgers[0]['id']}/accounts", headers=admin), 200
    )
    assert any(a["category"] == "debtor" for a in ledger_accounts)
    keys = {
        k["code"]: k
        for k in _ok(
            client.get(f"/api/v1/properties/{prop_id}/allocation-keys", headers=admin), 200
        )
    }
    assert keys["SOND_A"]["kind"] == "fixed_share"
    assert keys["SOND_A"]["is_template_derived"] is False
    assert keys["FEST"]["kind"] == "fixed_amount"
    assert keys["V_KW"]["kind"] == "consumption"
    docs = _ok(client.get(f"/api/v1/documents/{extra_doc}", headers=admin), 200)
    assert any(link["entity_id"] == prop_id for link in docs["links"])
    source = _ok(client.get(f"/api/v1/documents/{doc}", headers=admin), 200)
    assert any(
        link["entity_id"] == prop_id and link["role"] == "original" for link in source["links"]
    )

    undone = _ok(client.post(f"/api/v1/imports/{applied['id']}/undo", headers=admin), 200)
    assert undone["status"] == "partially_undone" or undone["status"] == "undone"
    kinds = {i["entity_type"] for i in undone["items"]}
    assert {"property_bank_account", "document_link"} <= kinds
    assert all(i["undone"] for i in undone["items"] if i["entity_type"] != "document"), undone
    assert client.get(f"/api/v1/properties/{prop_id}", headers=admin).status_code == 404
    after = _ok(client.get(f"/api/v1/documents/{extra_doc}", headers=admin), 200)
    assert not any(link["entity_id"] == prop_id for link in after["links"])


def test_onboarding_extras_validation(client: TestClient, world: World, fake: FakeProvider) -> None:
    admin, run, _ = _property_proposal(client, world, fake)
    url = f"/api/v1/ai/proposals/{run['proposal_id']}/apply"
    base = {"number": "732", "as_of": "2020-01-01"}

    def post(extra: dict[str, Any]) -> Any:
        return client.post(url, json={"property": {**base, **extra}}, headers=admin)

    assert post({"allocation_keys": [{"code": "V_KW", "values": {"01": "5"}}]}).status_code == 422
    assert post({"allocation_keys": [{"code": "NEU_X"}]}).status_code == 422
    assert post({"allocation_keys": [{"code": "WFL", "values": {"01": "-1"}}]}).status_code == 422
    assert (
        post(
            {"bank_accounts": [{"kind": "hoa", "iban": "DE00123", "holder": "WEG Test"}]}
        ).status_code
        == 422
    )
    assert (
        post(
            {
                "bank_accounts": [
                    {"kind": "deposit", "iban": IBAN, "holder": "WEG Test", "is_default": True}
                ]
            }
        ).status_code
        == 422
    )
    missing = post({"document_ids": ["00000000-0000-4000-8000-000000000000"]})
    assert missing.status_code == 404
    # Nothing of the refused attempts exists: the proposal is still open and number 732 is free.
    again = post({})
    assert again.status_code == 201, again.text


def test_takeover_tickets_from_open_points(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "r03admin"))
    clerk = bearer(login(client, world, "r03reader"))
    other = bearer(login(client, world, "r03other"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "741",
                "name": "Objekt 741",
                "management_type": "hoa",
                "street": "Testweg",
                "house_number": "2",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=admin,
        )
    )
    url = f"/api/v1/properties/{prop['id']}/takeover-checklist"
    _ok(client.post(url, headers=admin), 200)
    _ok(client.patch(f"{url}/insurance", json={"status": "received"}, headers=admin), 200)
    _ok(
        client.patch(
            f"{url}/meters",
            json={"status": "requested", "note": "Zählerliste fehlt", "due_date": "2026-11-15"},
            headers=admin,
        ),
        200,
    )
    assert client.post(f"{url}/tickets", json={}, headers=clerk).status_code == 403
    assert (
        client.post(f"{url}/tickets", json={"categories": ["x"]}, headers=admin).status_code == 422
    )
    assert client.post(f"{url}/tickets", json={}, headers=other).status_code == 404
    first = _ok(
        client.post(f"{url}/tickets", json={"categories": ["meters", "insurance"]}, headers=admin)
    )
    assert [c["category"] for c in first["created"]] == ["meters"]
    assert first["skipped"] == ["insurance"]
    ticket = _ok(
        client.get(f"/api/v1/tickets/{first['created'][0]['ticket_id']}", headers=admin), 200
    )
    assert ticket["property_id"] == prop["id"]
    assert ticket["title"] == "Objektübernahme 741: Zähler"
    assert ticket["due_on"] == "2026-11-15"
    items = {i["category"]: i for i in first["checklist"]["items"]}
    assert items["meters"]["ticket_id"] == first["created"][0]["ticket_id"]
    second = _ok(client.post(f"{url}/tickets", json={}, headers=admin))
    assert len(second["created"]) == 5  # all other open points, meters already has one
    assert "meters" in second["skipped"]
    third = _ok(client.post(f"{url}/tickets", json={}, headers=admin))
    assert third["created"] == []


def test_person_match_batch_preview(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "r03admin"))
    other = bearer(login(client, world, "r03reader"))
    foreign = bearer(login(client, world, "r03other"))
    name = f"Batchtest{IBAN[-4:]}"
    _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Berta", "last_name": name},
            headers=admin,
        )
    )
    url = "/api/v1/onboarding/person-match-batch"
    persons = [
        {"first_name": "Berta", "last_name": name},
        {"last_name": "Niemandsname"},
    ]
    result = _ok(client.post(url, json={"persons": persons}, headers=admin), 200)
    assert len(result["results"]) == 2
    assert result["results"][0]["candidates"]
    assert result["results"][0]["candidates"][0]["name"].startswith(name)
    assert result["results"][1] == {"decision": "none", "candidates": []}
    assert float(result["link_threshold"]) >= float(result["suggest_threshold"])
    # nothing is written by the preview
    assert client.post(url, json={"persons": []}, headers=admin).status_code == 422
    assert client.post(url, json={"persons": persons}, headers=other).status_code == 403
    separated = _ok(client.post(url, json={"persons": persons[:1]}, headers=foreign), 200)
    assert separated["results"][0]["candidates"] == []


def test_multiple_owners_account_needs_entity_choice(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    """R03-02: with several matching legal entities nothing is created automatically; the
    decision point carries the candidates and the apply after the choice creates the account."""
    admin = _setup_provider(client, world)
    doc = _upload(client, admin, "eigentuemer.txt", b"Mietobjekt zwei Eigentuemer", "text/plain")
    fake.queue.append(
        {
            "property": {
                "number": None,
                "name": "Mietobjekt Zwei",
                "management_type": "rental",
                "street": "Testweg",
                "house_number": "2",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            "buildings": ["Haus A"],
            "units": [_unit(number="01", building="Haus A"), _unit(number="02", building="Haus A")],
            "parties": [
                _party(unit_number="01", last_name="Eigner", start_date="2020-01-01"),
                _party(unit_number="02", last_name="Besitzer", start_date="2020-01-01"),
            ],
            "questions": [],
        }
    )
    run = _chat(client, admin, "extract_property", "Objekt anlegen", [doc])
    assert run["status"] == "succeeded", run
    number = str(100 + int(uuid.uuid4().hex[:6], 16) % 900)
    rent = {"kind": "rent", "iban": IBAN, "holder": "Eigner und Besitzer"}
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
            json={"property": {"number": number, "as_of": "2020-01-01", "bank_accounts": [rent]}},
            headers=admin,
        )
    )
    summary = applied["summary"]
    assert any("Auswahl nötig" in n for n in summary["notes"])
    decisions = summary["entity_decisions"]
    assert len(decisions) == 1
    assert decisions[0]["kind"] == "bank_account"
    assert "iban" not in str(decisions).lower()
    candidates = decisions[0]["candidates"]
    assert len(candidates) == 2
    prop_id = summary["property_id"]
    assert _ok(client.get(f"/api/v1/properties/{prop_id}/bank-accounts", headers=admin), 200) == []

    url = f"/api/v1/ai/import-runs/{applied['id']}/resolve-entities"
    body = {"bank_accounts": [{**rent, "legal_entity_id": candidates[0]["id"]}]}
    body["resolved_indexes"] = [0]
    body["as_of"] = "2020-01-01"
    clerk = bearer(login(client, world, "r03reader"))
    other = bearer(login(client, world, "r03other"))
    assert client.post(url, json=body, headers=clerk).status_code == 403
    assert client.post(url, json=body, headers=other).status_code == 404
    bad = {
        **body,
        "bank_accounts": [{**rent, "legal_entity_id": "00000000-0000-4000-8000-000000000000"}],
    }
    assert client.post(url, json=bad, headers=admin).status_code == 422
    assert client.post(url, json={**body, "resolved_indexes": []}, headers=admin).status_code == 422
    done = _ok(client.post(url, json=body, headers=admin), 200)
    assert done["created_bank_accounts"] == 1
    accounts = _ok(client.get(f"/api/v1/properties/{prop_id}/bank-accounts", headers=admin), 200)
    assert len(accounts) == 1
    assert accounts[0]["legal_entity_id"] == candidates[0]["id"]
    after = _ok(client.get(f"/api/v1/imports/{applied['id']}", headers=admin), 200)
    assert after["summary"]["entity_decisions"] == []
    assert client.post(url, json=body, headers=admin).status_code == 409


def test_takeover_ticket_defaults(client: TestClient, world: World) -> None:
    """V06-01: default team and assignee of the takeover tickets (empty means no assignment)."""
    admin = bearer(login(client, world, "r03admin"))
    clerk = bearer(login(client, world, "r03reader"))
    other = bearer(login(client, world, "r03other"))
    url = "/api/v1/onboarding/takeover-ticket-defaults"
    assert _ok(client.get(url, headers=admin), 200) == {"team_id": None, "assignee_user_id": None}
    assert client.put(url, json={}, headers=clerk).status_code == 403
    team = _ok(
        client.post(
            "/api/v1/teams", json={"name": "Übernahme", "member_user_ids": []}, headers=admin
        ),
        201,
    )
    foreign_team = _ok(
        client.post("/api/v1/teams", json={"name": "Fremd", "member_user_ids": []}, headers=other),
        201,
    )
    assert client.put(url, json={"team_id": foreign_team["id"]}, headers=admin).status_code == 422
    stranger = str(world.users["r03other"])
    assert client.put(url, json={"assignee_user_id": stranger}, headers=admin).status_code == 422
    assert client.put(url, json={"assignee_user_id": "x"}, headers=admin).status_code == 422
    assignee = str(world.users["r03admin"])
    saved = _ok(
        client.put(url, json={"team_id": team["id"], "assignee_user_id": assignee}, headers=admin),
        200,
    )
    assert saved == {"team_id": team["id"], "assignee_user_id": assignee}
    assert _ok(client.get(url, headers=other), 200) == {"team_id": None, "assignee_user_id": None}

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "742",
                "name": "Objekt 742",
                "management_type": "hoa",
                "street": "Testweg",
                "house_number": "3",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=admin,
        )
    )
    check = f"/api/v1/properties/{prop['id']}/takeover-checklist"
    _ok(client.post(check, headers=admin), 200)
    made = _ok(client.post(f"{check}/tickets", json={"categories": ["meters"]}, headers=admin))
    ticket = _ok(
        client.get(f"/api/v1/tickets/{made['created'][0]['ticket_id']}", headers=admin), 200
    )
    assert ticket["team_id"] == team["id"]
    assert ticket["assignee_user_id"] == assignee
    # Empty again: later tickets carry no assignment.
    _ok(client.put(url, json={}, headers=admin), 200)
    later = _ok(client.post(f"{check}/tickets", json={"categories": ["insurance"]}, headers=admin))
    ticket = _ok(
        client.get(f"/api/v1/tickets/{later['created'][0]['ticket_id']}", headers=admin), 200
    )
    assert ticket["team_id"] is None
    assert ticket["assignee_user_id"] is None
