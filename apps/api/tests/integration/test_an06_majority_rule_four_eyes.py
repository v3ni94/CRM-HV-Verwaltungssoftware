"""AN06 / GAJ-602: four eyes approval of meeting majority rules behind the tenant switch
hoa_majority_rule_four_eyes (default off). Expected: switch off -> rule usable at once
(behaviour before AN06); switch on -> rule is a draft, assignment refused with MHVP-HOA-0040,
the creator cannot approve (MHVP-HOA-0041), a second admin approves, then the rule applies.
The model question AM02-01 is not decided here."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an06a-{RUN}", name=f"AN06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"an06b-{RUN}", name=f"AN06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("an06adm1", a, "tenant_admin"),
            ("an06adm2", a, "tenant_admin"),
            ("an06std", a, "standard"),
            ("an06admb", b, "tenant_admin"),
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


def test_an06_four_eyes_majority_rule(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "an06adm1"))
    h2 = bearer(login(client, world, "an06adm2"))
    hs = bearer(login(client, world, "an06std"))
    hb = bearer(login(client, world, "an06admb"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "606", "name": "WEG Vier Augen", "management_type": "hoa"},
            headers=h1,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    rule = {
        "legal_entity_id": hoa,
        "principle": "head",
        "share_of_votes_cast": "0.5",
        "source": "Teilungserklärung (Testannahme)",
        "valid_from": "2020-01-01",
    }
    # Switch default off: rule usable at once, approval route answers 409 (no approval needed).
    assert _ok(client.get(f"{H}/majority-rule-four-eyes", headers=h1)) == {"enabled": False}
    legacy = _ok(client.post(f"{H}/majority-rules", json=rule | {"label": "Alt"}, headers=h1), 201)
    assert legacy["approval_status"] == "approved"
    assert legacy["requires_approval"] is False
    nope = client.post(f"{H}/majority-rules/{legacy['id']}/approve", headers=h2)
    assert nope.status_code == 409
    assert nope.json()["code"] == "MHVP-HOA-0041"

    # Switch: read only settings 403, validation 422, admin on.
    assert (
        client.put(f"{H}/majority-rule-four-eyes", json={"enabled": True}, headers=hs).status_code
        == 403
    )
    assert client.put(f"{H}/majority-rule-four-eyes", json={}, headers=h1).status_code == 422
    _ok(client.put(f"{H}/majority-rule-four-eyes", json={"enabled": True}, headers=h1))
    draft = _ok(client.post(f"{H}/majority-rules", json=rule | {"label": "Neu"}, headers=h1), 201)
    assert (draft["approval_status"], draft["approved_by"]) == ("draft", None)

    meeting = _ok(
        client.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"},
            headers=h1,
        ),
        201,
    )
    refused = client.post(
        f"{H}/meetings/{meeting['id']}/agenda",
        json={"title": "Dach", "rule_id": draft["id"]},
        headers=h1,
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-HOA-0040"
    # The legacy rule (created before the switch) keeps working.
    _ok(
        client.post(
            f"{H}/meetings/{meeting['id']}/agenda",
            json={"title": "Fassade", "rule_id": legacy["id"]},
            headers=h1,
        ),
        201,
    )

    approve = f"{H}/majority-rules/{draft['id']}/approve"
    assert client.post(approve, headers=hs).status_code == 403  # no hoa:approve
    assert client.post(approve, headers=hb).status_code == 404  # foreign tenant
    assert client.post(f"{H}/majority-rules/{uuid.uuid4()}/approve", headers=h2).status_code == 404
    assert client.post(f"{H}/majority-rules/not-a-uuid/approve", headers=h2).status_code == 422
    own = client.post(approve, headers=h1)
    assert own.status_code == 409
    assert own.json()["code"] == "MHVP-HOA-0041"
    done = _ok(client.post(approve, headers=h2))
    assert done["approval_status"] == "approved"
    assert done["approved_by"] == str(world.users["an06adm2"])
    assert client.post(approve, headers=h2).status_code == 409

    _ok(
        client.post(
            f"{H}/meetings/{meeting['id']}/agenda",
            json={"title": "Dach", "rule_id": draft["id"]},
            headers=h1,
        ),
        201,
    )
    listed = _ok(client.get(f"{H}/majority-rules", params={"legal_entity_id": hoa}, headers=h1))
    assert {r["label"]: r["approval_status"] for r in listed} == {
        "Alt": "approved",
        "Neu": "approved",
    }
    _ok(client.put(f"{H}/majority-rule-four-eyes", json={"enabled": False}, headers=h1))
