"""AP14: access export complete per source (GAM-402), processing log, change log and
recipients (GAM-403), access log behind a tenant switch (GAM-410)."""

import asyncio
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
EXPORT_SETTINGS = "/api/v1/contact-access-export-settings"
LOG_SETTINGS = "/api/v1/contact-access-log-settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap14a-{RUN}", name=f"AP14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap14b-{RUN}", name=f"AP14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ap14prep", a, "tenant_admin"),
            ("ap14rev", a, "tenant_admin"),
            ("ap14view", a, "read_only"),
            ("ap14other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _seed(database: Database, redis_url: str, tenant_id: uuid.UUID, contact_id: str) -> None:
    """A call log row (further source) and a transfer event to a recipient."""
    from mhvp.communication.telephony import CallLog
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.events import emit

    async def go() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                session.add(
                    CallLog(
                        tenant_id=tenant_id,
                        event="ended",
                        direction="inbound",
                        number="+4930123456",
                        number_normalised=True,
                        started_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
                        contact_id=uuid.UUID(contact_id),
                        match_status="matched",
                        proposal_status="none",
                    )
                )
                await emit(
                    session,
                    tenant_id=tenant_id,
                    type="schadenstool.handover_queued",
                    entity_type="schadenstool_ticket_link",
                    entity_id=uuid.uuid4(),
                    actor_user_id=None,
                    payload={
                        "contact_id": contact_id,
                        "recipient": "schadenstool",
                        "sharing_basis": "data_sharing_consent",
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(go())


def _download(client: TestClient, cid: str, prep: dict[str, str], rev: dict[str, str]) -> Any:
    base = f"/api/v1/contacts/{cid}/access-exports"
    export = _ok(client.post(base, headers=prep), 201)
    url = f"{base}/{export['id']}"
    _ok(client.get(f"{url}/preview", headers=rev))
    _ok(client.post(f"{url}/review", headers=rev))
    _ok(client.post(f"{url}/approve", headers=rev))
    return _ok(client.get(f"{url}/download", headers=prep))


def test_further_sources_protocols_and_access_log(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    prep = bearer(login(client, world, "ap14prep"))
    rev = bearer(login(client, world, "ap14rev"))
    viewer = bearer(login(client, world, "ap14view"))
    other = bearer(login(client, world, "ap14other"))
    cid = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Ina", "last_name": f"Quelle{RUN}"},
            headers=prep,
        ),
        201,
    )["id"]
    _seed(database, redis_url, world.tenant_a, cid)
    time.sleep(1.1)  # generated_at is truncated to the second; rows must lie before it

    # Defaults: further source only counted, recipients and log listed, access log empty.
    data = _download(client, cid, prep, rev)
    content = data.get("content", data)
    assert "further_sources" not in content
    assert content["withheld"]["further_sources_count"]["call_log"] == 1
    assert "+4930123456" not in str(content)
    assert content["recipients"][0]["recipient"] == "schadenstool"
    assert content["recipients"][0]["basis"] == "data_sharing_consent"
    types = [e["type"] for e in content["processing_log"]]
    assert "schadenstool.handover_queued" in types
    assert not any(t.startswith("contact.access_export") for t in types)
    assert content["access_log"] == []
    assert isinstance(content["change_log"], list)

    # Access log switch: default off, permissions, validation, tenant separation.
    assert _ok(client.get(LOG_SETTINGS, headers=prep)) == {"scope": "off", "retention_days": None}
    _ok(client.get(f"/api/v1/contacts/{cid}", headers=prep))
    assert _ok(client.get(f"/api/v1/contacts/{cid}/access-log", headers=prep)) == []
    assert client.put(LOG_SETTINGS, json={"scope": "contact"}, headers=viewer).status_code == 403
    assert client.put(LOG_SETTINGS, json={"scope": "all"}, headers=prep).status_code == 422
    assert (
        client.put(LOG_SETTINGS, json={"scope": "contact", "retention_days": 0}, headers=prep)
    ).status_code == 422
    _ok(client.put(LOG_SETTINGS, json={"scope": "contact", "retention_days": 365}, headers=prep))
    assert client.get(f"/api/v1/contacts/{cid}/access-log", headers=other).status_code == 404
    assert client.get(f"/api/v1/contacts/{cid}/access-log", headers=viewer).status_code == 403
    _ok(client.get(f"/api/v1/contacts/{cid}", headers=prep))
    time.sleep(1.1)
    log = _ok(client.get(f"/api/v1/contacts/{cid}/access-log", headers=prep))
    assert [r["action"] for r in log] == ["contact_read"]
    assert log[0]["user_id"] == str(world.users["ap14prep"])

    # Switch on: the further source is listed with its allowlisted fields; the export lists
    # the read and reproduces its reviewed hash although preview and download are logged.
    _ok(
        client.put(
            EXPORT_SETTINGS,
            json={"third_party_scope": "none", "include_communication": True},
            headers=prep,
        )
    )
    try:
        content = _download(client, cid, prep, rev)
        content = content.get("content", content)
        rows = content["further_sources"]["call_log"]["rows"]
        assert rows[0]["number"] == "+4930123456"
        assert set(rows[0]) == {"event", "direction", "number", "started_at", "duration_seconds"}
        assert [r["action"] for r in content["access_log"]] == ["contact_read"]
        actions = [
            r["action"] for r in _ok(client.get(f"/api/v1/contacts/{cid}/access-log", headers=prep))
        ]
        assert "access_export_download" in actions
        assert "access_export_preview" in actions
    finally:
        _ok(
            client.put(
                EXPORT_SETTINGS,
                json={"third_party_scope": "none", "include_communication": False},
                headers=prep,
            )
        )
        _ok(client.put(LOG_SETTINGS, json={"scope": "off"}, headers=prep))
