"""D51: an unknown legal or allocation rule entered as configuration never becomes productive
by itself (E04, 6.9.4, 7.4). Covered here for the two rule kinds the platform evaluates:
a bank posting rule (proposed, released by a second person, activated only with amount limit
and test evidence, ignored by the automatic run until then) and a community majority rule
(refused without the source it was taken from). Allocation keys (Umlageschlüssel) carry no
source or release state yet; that gap is an operator decision (docs/OPEN_QUESTIONS.md)."""

import asyncio
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
from tests.integration.test_m11_banking import _upload

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"d51-{RUN}", name=f"Regel {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("d51admin", "tenant_admin"), ("d51acc", "accountant_no_banking")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def test_d51_configured_rule_is_never_productive_without_decision_and_tests(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "d51admin"))
    second = bearer(login(client, world, "d51acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "751", "name": "Regelhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")

    # A posting rule typed in by one person is only a proposal (6.9.4).
    _ok(client.put(f"{B}/automation", json={"enabled": True, "reason": "Test D51"}, headers=h))
    rule = _ok(
        client.post(
            f"{B}/rules",
            json={"name": "Unbekannte Regel", "legal_entity_id": hoa, "purpose_regex": "Sonder"},
            headers=h,
        ),
        201,
    )
    assert rule["approval_state"] == "proposed"
    assert rule["max_amount"] is None
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # proposal has no effect
    assert client.post(f"{B}/rules/{rule['id']}/approve", headers=h).status_code == 403  # own
    evidence = _upload(client, h, "testlauf.xml", b"<nachweis>Testlauf D51</nachweis>")
    activation = {"max_amount": "250.00", "test_evidence_document_id": evidence}
    early = client.post(f"{B}/rules/{rule['id']}/activate", json=activation, headers=second)
    assert early.status_code == 409  # decision (release by a second person) missing
    _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=second))
    assert _ok(client.get(f"{B}/rules", headers=h))[0]["approval_state"] == "approved"
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # approved is not active
    no_evidence = client.post(
        f"{B}/rules/{rule['id']}/activate",
        json={"max_amount": "250.00", "test_evidence_document_id": str(world.tenant_a)},
        headers=second,
    )
    assert no_evidence.status_code == 404  # tests are required, a made up reference is not
    assert (
        client.post(
            f"{B}/rules/{rule['id']}/activate",
            json={"test_evidence_document_id": evidence},
            headers=second,
        ).status_code
        == 422
    )  # amount limit is mandatory
    active = _ok(client.post(f"{B}/rules/{rule['id']}/activate", json=activation, headers=second))
    assert active["approval_state"] == "active"
    assert active["max_amount"] == "250.00"
    assert active["test_evidence_document_id"] == evidence

    # A majority rule of a community needs the source it was taken from and a validity date.
    body = {
        "legal_entity_id": hoa,
        "label": "Qualifizierte Mehrheit",
        "principle": "head",
        "share_of_votes_cast": "0.66666667",
        "valid_from": "2026-01-01",
    }
    assert client.post(f"{H}/majority-rules", json=body, headers=h).status_code == 422
    assert (
        client.post(f"{H}/majority-rules", json={**body, "source": "?"}, headers=h).status_code
        == 422
    )  # no meaningful source
    assert (
        client.post(
            f"{H}/majority-rules",
            json={**body, "source": "Teilungserklärung § 12 (Testannahme)", "principle": "mea"},
            headers=h,
        ).status_code
        == 201
    )
    rules = _ok(client.get(f"{H}/majority-rules", params={"legal_entity_id": hoa}, headers=h))
    assert [r["source"] for r in rules] == ["Teilungserklärung § 12 (Testannahme)"]
