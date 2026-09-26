"""A35 KI-Plausibilität of an operating cost statement (M17) with a fake provider: the run
is queued and executed inline, the answer becomes a ``statement_check`` proposal, nothing on
the statement or its snapshot changes, the provider sees no contract id and no name, rights
and tenant separation hold, and a draft without a snapshot is refused."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.ai.providers import Completion
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m7_ai import PROVIDER, _settings, _upload

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ai"
A = "/api/v1/accounting"
S = "/api/v1/statements"


class FakeProvider:
    def __init__(self) -> None:
        self.queue: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = self.queue.pop(0)
        return Completion(
            data=data, raw_text=json.dumps(data), tokens_in=800, tokens_out=200, model="m"
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
        a, _ = await services.provision_tenant(factory, slug=f"kc-{RUN}", name=f"KI BK {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"kd-{RUN}", name=f"Fremd BK {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ckadmin", a, "tenant_admin"),
            ("cksecond", a, "tenant_admin"),
            ("ckreader", a, "read_only"),
            ("ckother", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _release_provider(c: TestClient, world: World) -> dict[str, str]:
    admin = bearer(login(c, world, "ckadmin"))
    second = bearer(login(c, world, "cksecond"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second))
    return admin


def _calculated_statement(c: TestClient, h: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Property with one let unit, a ledger and one caretaker position (living area key),
    calculated. Returns the statement and the tenant's contact last name (must never reach
    the provider)."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Miethaus KI", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(c, h, "Vermieter", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    keys = {
        k["code"]: k["id"]
        for k in _ok(c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    building = _ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h), 201
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        c.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={"allocation_key_id": keys["WFL"], "value": "60", "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant, contact = _party(c, h, "Mieterin")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    ledger = _ok(c.post(f"{A}/ledgers", json={"legal_entity_id": entity}, headers=h), 201)["id"]
    st = _ok(
        c.post(
            S,
            json={"ledger_id": ledger, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Hausmeister",
                "amount": "1200.00",
                "allocation_key_id": keys["WFL"],
                "basis": "§ 4 Mietvertrag, Anlage Betriebskosten",
            },
            headers=h,
        ),
        201,
    )
    return _ok(c.post(f"{S}/{st['id']}/calculate", headers=h)), str(contact["last_name"])


ANSWER = {
    "findings": [
        {
            "field": "key_without_source",
            "description": "Position P1 nennt den Schlüssel, die Quelle ist zu prüfen.",
            "severity": "medium",
            "position": "P1",
            "unit": None,
        },
        {
            "field": "advances",
            "description": "Einheit 01 hat keine Vorauszahlungen.",
            "severity": "low",
            "position": None,
            "unit": "01",
        },
        {
            "field": "totals_mismatch",
            "description": "Unbekannte Position.",
            "severity": "high",
            "position": "P7",
            "unit": "99",
        },
    ],
    "overall": "pruefen",
    "summary": "Der Entwurf ist im Wesentlichen nachvollziehbar.",
}


def test_ai_check_is_a_proposal_and_changes_nothing(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _release_provider(client, world)
    reader = bearer(login(client, world, "ckreader"))
    other = bearer(login(client, world, "ckother"))
    st, tenant_name = _calculated_statement(client, admin)
    before = _ok(client.get(f"{S}/{st['id']}", headers=admin))
    assert before["snapshot"]["hash"]

    # Rights: reading without accounting:create may not start a run; a foreign tenant sees
    # neither the statement nor the check (RLS).
    assert client.post(f"{S}/{st['id']}/ai-check", headers=reader).status_code == 403
    assert client.post(f"{S}/{st['id']}/ai-check", headers=other).status_code == 404
    assert client.get(f"{S}/{st['id']}/ai-check", headers=other).status_code == 404
    empty = _ok(client.get(f"{S}/{st['id']}/ai-check", headers=reader))
    assert (empty["latest_run"], empty["latest"], empty["proposals"]) == (None, None, [])
    assert fake.calls == []

    fake.queue.append(ANSWER)
    started = _ok(client.post(f"{S}/{st['id']}/ai-check", headers=admin), 202)
    assert started["latest_run"]["status"] == "succeeded", started
    assert started["latest_run"]["snapshot_hash"] == before["snapshot"]["hash"]
    proposal = started["latest"]
    assert proposal["entity_type"] == "statement_check"
    assert proposal["decision"] == "pending"
    proposed = proposal["proposed"]
    # Normalised: high finding with unknown references keeps its severity but loses the
    # references; overall follows the highest severity, not the model's word.
    assert [f["severity"] for f in proposed["findings"]] == ["high", "medium", "low"]
    assert proposed["findings"][0]["position"] is None
    assert proposed["findings"][0]["unit"] is None
    assert proposed["findings"][1]["position"] == "P1"
    assert (proposed["overall"], proposed["model_overall"]) == ("kritisch", "pruefen")
    assert proposed["snapshot_hash"] == before["snapshot"]["hash"]
    assert all("amount" not in f for f in proposed["findings"])

    # The provider saw the masked JSON only: no contract id, no name, positions as P1.
    assert len(fake.calls) == 1
    sent = fake.calls[0]["messages"][0]["content"]
    assert tenant_name not in sent
    assert '"ref": "P1"' in sent
    assert '"unit": "01"' in sent
    assert "contract:" not in sent
    payload = json.loads(sent.split("<daten>", 1)[1].split("</daten>", 1)[0].split("\n\n", 1)[1])
    assert payload["positions"][0]["amount"] == "1200.00"
    assert payload["previous_period"] is None
    assert payload["totals"]["sum_of_unit_costs"] == "1200.00"

    # Nothing changed on the statement: same snapshot hash, same status, same items.
    after = _ok(client.get(f"{S}/{st['id']}", headers=admin))
    assert after["snapshot"]["hash"] == before["snapshot"]["hash"]
    assert after["status"] == before["status"] == "calculated"
    assert after["cost_items"] == before["cost_items"]

    # The reader sees the proposal; the foreign tenant still nothing.
    listed = _ok(client.get(f"{S}/{st['id']}/ai-check", headers=reader))
    assert [p["id"] for p in listed["proposals"]] == [proposal["id"]]
    assert client.get(f"{S}/{st['id']}/ai-check", headers=other).status_code == 404

    # Same snapshot again: deduplicated by input hash (no second provider call), new proposal.
    again = _ok(client.post(f"{S}/{st['id']}/ai-check", headers=admin), 202)
    assert len(fake.calls) == 1
    assert again["latest_run"]["status"] == "succeeded"
    assert len(again["proposals"]) == 2


def test_ai_check_needs_a_snapshot(client: TestClient, world: World, fake: FakeProvider) -> None:
    admin = bearer(login(client, world, "ckadmin"))
    st = _ok(client.get(S, headers=admin))[0]
    draft = _ok(client.post(f"{S}/{st['id']}/new-version", headers=admin), 201)
    assert draft["status"] == "draft"
    refused = client.post(f"{S}/{draft['id']}/ai-check", headers=admin)
    assert refused.status_code == 409, refused.text
    assert "Snapshot" in refused.json()["detail"]
    assert fake.calls == []
