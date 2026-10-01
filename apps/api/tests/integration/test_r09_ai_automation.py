"""R09 (Q14-02, M7-07): tenant switches of the automatic AI runs, automatic rent increase
proposal behind the provider release, nightly mail classification as caller of the collective
run, reply draft schema in the compact view. Fake provider, no network.

Expected values by hand: the switches default to off; with the switch on and a released
provider exactly one run is queued per distinct case input (a second identical input queues no
second run); the nightly run classifies at most the mails with ``suggestion_status = none``."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake
from tests.integration.test_q06_ai_w3 import _rent_case

pytestmark = pytest.mark.integration
__all__ = ["fake"]
L = "/api/v1/letting"
A = "/api/v1/ai/automation"
FINDINGS = {
    "findings": [{"field": "source_missing", "description": "Quelle fehlt.", "severity": "low"}],
    "overall": "unauffaellig",
    "summary": "Ein Hinweis.",
}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r9a-{RUN}", name=f"R09 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r9b-{RUN}", name=f"R09 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("r9admin", a, "tenant_admin"),
            ("r9second", a, "tenant_admin"),
            ("r9reader", a, "read_only"),
            ("r9other", b, "tenant_admin"),
        ):
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


def _release(c: TestClient, world: World) -> dict[str, str]:
    admin = bearer(login(c, world, "r9admin"))
    if _ok(c.get(A, headers=admin))["provider_released"]:
        return admin  # module scoped tenant: an earlier test already released the provider
    second = bearer(login(c, world, "r9second"))
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


def test_switches_default_off_permission_validation_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "r9admin"))
    reader = bearer(login(client, world, "r9reader"))
    other = bearer(login(client, world, "r9other"))
    first = _ok(client.get(A, headers=admin))
    assert first["rent_increase_check"] is False
    assert first["batch_mail_classification"] is False
    assert first["provider_released"] is False
    assert client.get(A, headers=reader).status_code == 403
    assert client.put(A, json={"rent_increase_check": True}, headers=reader).status_code == 403
    assert client.put(A, json={"unknown": True}, headers=admin).status_code == 422
    after = _ok(client.put(A, json={"rent_increase_check": True}, headers=admin))
    assert after["rent_increase_check"] is True
    assert after["batch_mail_classification"] is False  # missing key stays unchanged
    assert _ok(client.get(A, headers=other))["rent_increase_check"] is False
    _ok(client.put(A, json={"rent_increase_check": False}, headers=admin))


def test_rent_increase_auto_check_only_with_switch_and_released_provider(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "r9admin"))
    # Switch off: a new case queues nothing.
    case_id = _rent_case(client, admin)
    assert (
        _ok(client.get(f"{L}/rent-increases/{case_id}/ai-check", headers=admin))["latest_run"]
        is None
    )
    _ok(client.put(A, json={"rent_increase_check": True}, headers=admin))
    # Provider released: the next case gets exactly one proposal, linked as ai_check_id.
    _release(client, world)
    fake.queue.append(FINDINGS)
    calls = len(fake.calls)
    second_case = _rent_case_again(client, admin)
    state = _ok(client.get(f"{L}/rent-increases/{second_case}/ai-check", headers=admin))
    assert state["latest_run"]["status"] == "succeeded"
    assert state["ai_check_id"] == state["latest"]["id"]
    assert len(fake.calls) == calls + 1
    case = _ok(client.get(f"{L}/rent-increases/{second_case}", headers=admin))
    assert case["status"] == "draft"  # the proposal never changes the case
    assert case["ai_check_id"] == state["latest"]["id"]
    sent = fake.calls[-1]["messages"][-1]["content"]
    assert "MieterQ06" not in sent
    _ok(client.put(A, json={"rent_increase_check": False}, headers=admin))


def _rent_case_again(c: TestClient, h: dict[str, str]) -> str:
    """A second case on the first contract of the tenant (same property, same contract)."""
    contracts = _ok(c.get("/api/v1/contracts", headers=h))
    contracts = contracts["items"] if isinstance(contracts, dict) else contracts
    contract = contracts[0]["id"]
    case = _ok(
        c.post(
            f"{L}/rent-increases",
            json={
                "contract_id": contract,
                "basis": "index",
                "effective_date": "2026-12-01",
                "target_rent": "620.00",
                "source_note": "Testwerte, keine Rechtsquelle",
                "basis_data": {"index_base": "100", "index_current": "104"},
            },
            headers=h,
        ),
        201,
    )
    return str(case["id"])


def test_nightly_mail_classification_caller(
    client: TestClient, world: World, fake: FakeProvider, database: Database, redis_url: str
) -> None:
    from mhvp.ai import batch
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    admin = bearer(login(client, world, "r9admin"))
    from tests.integration.test_m20_suggest import _eml

    raw = _eml(f"alt{RUN}@example.com", f"Heizung alt {RUN}", f"<r9-{RUN}@x>", "Heizung kalt.")
    doc = _upload(client, admin, "alt.eml", raw, "message/rfc822")
    msg = _ok(client.post("/api/v1/mail/ingest", json={"document_id": doc}, headers=admin), 201)
    settings = _settings(database, redis_url)
    tenant_id = world.tenant_a
    calls_before = len(fake.calls)

    async def _run(set_none: bool) -> dict[str, Any]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            if set_none:
                async with tenant_transaction(factory, tenant_id) as session:
                    await session.execute(
                        text(
                            "UPDATE message SET suggestion_status = 'none', suggestion = '{}', "
                            "created_at = now() - interval '2 days' WHERE id = :id"
                        ),
                        {"id": msg["id"]},
                    )
            return await batch.run_callers(factory, tenant_id, settings)
        finally:
            await engine.dispose()

    # Switch off: nothing is classified.
    off = asyncio.run(_run(True))
    assert off["mail_classification"]["skipped"] == "switch_off"
    assert len(fake.calls) == calls_before
    # Switch on and provider released: the mail without suggestion is classified once.
    _release(client, world)
    _ok(client.put(A, json={"batch_mail_classification": True}, headers=admin))
    fake.queue.append(
        {
            "category": "Heizung",
            "urgency": "low",
            "summary": "Heizung kalt.",
            "property_number": "042",
            "contact_name": "Max Muster",
            "reply_draft": "Guten Tag",
        }
    )
    on = asyncio.run(_run(False))
    assert on["mail_classification"]["mails"] == 1
    assert on["mail_classification"]["ready"] == 1
    again = asyncio.run(_run(False))
    assert again["mail_classification"]["mails"] == 0  # no suggestion status none left
    detail = _ok(client.get(f"/api/v1/mail/messages/{msg['id']}", headers=admin))
    assert detail["suggestion_status"] == "ready"
    _ok(client.put(A, json={"batch_mail_classification": False}, headers=admin))
