"""Ticket merge into an existing target (M36): the target keeps number, status, priority and
assignment; comments, mails and history move to it; every source leaves a merged_from origin
entry on the target, its SLA clock is resolved and its assignees are carried over (append
only). Merged sources refuse edits, comments, assignees and bulk status changes with 409 or a
failed entry. GET /tickets filters with include_merged, merged_into and q; GET /tickets/{id}
reports message_count."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import Engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_ticket_merge import _eml, _ok, _upload
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tz-{RUN}", name=f"Ziel {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("tzadmin", "tzhelper", "tzother"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _create(c: TestClient, h: dict[str, str], title: str, priority: str = "normal") -> Any:
    return _ok(
        c.post(T, json={"title": title, "priority": priority, "source": "manual"}, headers=h),
        201,
    )


def _clock_state(engine: Engine, world: World, ticket_id: str) -> tuple[str, Any] | None:
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        row = conn.execute(
            text("SELECT state, resolved_at FROM sla_clock WHERE ticket_id = :t"),
            {"t": ticket_id},
        ).one_or_none()
    return None if row is None else (str(row[0]), row[1])


def test_merge_into_existing_target(client: TestClient, world: World, app_engine: Engine) -> None:
    h = bearer(login(client, world, "tzadmin"))
    helper = str(world.users["tzhelper"])
    other = str(world.users["tzother"])
    admin = str(world.users["tzadmin"])

    target = _create(client, h, f"Heizung Sammelvorgang {RUN}", priority="high")
    _ok(
        client.patch(
            f"{T}/{target['id']}",
            json={"status": "in_progress", "assignee_user_id": admin},
            headers=h,
        )
    )
    source_a = _create(client, h, f"Heizung kalt Wohnung 3 {RUN}", priority="urgent")
    _ok(client.patch(f"{T}/{source_a['id']}", json={"assignee_user_id": helper}, headers=h))
    _ok(
        client.post(
            f"{T}/{source_a['id']}/assignees",
            json={"user_id": other, "reason": "Vertretung"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{T}/{source_a['id']}/comments",
            json={"body": "Monteur bestellt.", "internal": True},
            headers=h,
        ),
        201,
    )

    doc = _upload(
        client,
        h,
        "z1.eml",
        _eml(f"zmieter{RUN}@example.com", f"Heizung ausgefallen {RUN}", f"<z1-{RUN}@x>"),
    )
    ingested = _ok(
        client.post(
            "/api/v1/mail/ingest", json={"document_id": doc, "auto_ticket": True}, headers=h
        ),
        201,
    )
    source_b_id = ingested["ticket_id"]
    assert source_b_id
    source_b = _ok(client.get(f"{T}/{source_b_id}", headers=h))
    assert source_b["message_count"] == 1

    before = _clock_state(app_engine, world, source_a["id"])
    assert before is not None
    assert before[1] is None

    # Target among the sources is a validation error.
    assert (
        client.post(
            f"{T}/merge",
            json={"ticket_ids": [target["id"]], "target_ticket_id": target["id"]},
            headers=h,
        ).status_code
        == 422
    )

    merged = _ok(
        client.post(
            f"{T}/merge",
            json={"ticket_ids": [source_a["id"], source_b_id], "target_ticket_id": target["id"]},
            headers=h,
        ),
        201,
    )
    assert merged["id"] == target["id"]
    assert merged["number"] == target["number"]
    assert merged["status"] == "in_progress"
    assert merged["priority"] == "high"
    assert merged["assignee_user_id"] == admin
    assert set(merged["merged_ticket_ids"]) == {source_a["id"], source_b_id}

    detail = _ok(client.get(f"{T}/{target['id']}", headers=h))
    assert detail["number"] == target["number"]
    assert detail["message_count"] == 1
    assert {c["body"] for c in detail["comments"]} == {"Monteur bestellt."}
    origins = [e["data"] for e in detail["events"] if e["kind"] == "merged_from"]
    assert {o["ticket_id"] for o in origins} == {source_a["id"], source_b_id}
    origin_a = next(o for o in origins if o["ticket_id"] == source_a["id"])
    assert origin_a["number"] == source_a["number"]
    assert origin_a["moved"]["comments"] == 1
    assert origin_a["moved"]["events"] >= 1
    origin_b = next(o for o in origins if o["ticket_id"] == source_b_id)
    assert origin_b["moved"]["messages"] == 1
    # History of the sources moved to the target, only merged_into stays at the source.
    assert any(e["kind"] != "merged_from" for e in detail["events"])

    carried = {a["user_id"]: a["reason"] for a in detail["assignees"]}
    assert carried.get(helper) == "Zusammenführung"
    assert other in carried
    assert admin not in carried or carried[admin] != "Zusammenführung"

    messages = _ok(client.get("/api/v1/mail/messages", headers=h))
    assert next(m for m in messages if m["id"] == ingested["id"])["ticket_id"] == target["id"]

    for sid in (source_a["id"], source_b_id):
        src = _ok(client.get(f"{T}/{sid}", headers=h))
        assert src["status"] == "closed"
        assert src["merged_into_ticket_id"] == target["id"]
        assert [e["kind"] for e in src["events"]] == ["merged_into"]
        assert src["comments"] == []
        assert src["message_count"] == 0
        clock = _clock_state(app_engine, world, sid)
        if sid == source_a["id"]:
            assert clock is not None
        if clock is not None:
            assert clock[0] == "done"
            assert clock[1] is not None

    # Target clock keeps running.
    target_clock = _clock_state(app_engine, world, target["id"])
    assert target_clock is not None
    assert target_clock[1] is None

    # Merged sources are read only.
    sa = source_a["id"]
    assert client.patch(f"{T}/{sa}", json={"priority": "low"}, headers=h).status_code == 409
    assert (
        client.post(
            f"{T}/{sa}/comments", json={"body": "Nachtrag", "internal": True}, headers=h
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{T}/{sa}/assignees", json={"user_id": admin, "reason": "Test"}, headers=h
        ).status_code
        == 409
    )
    bulk = _ok(
        client.post(f"{T}/bulk-status", json={"ticket_ids": [sa], "status": "new"}, headers=h)
    )
    assert bulk["changed"] == []
    assert bulk["failed"][0]["id"] == sa

    # A merged source cannot be merged again, neither as source nor as target.
    fresh = _create(client, h, f"Neues Ticket {RUN}")
    assert (
        client.post(
            f"{T}/merge", json={"ticket_ids": [fresh["id"]], "target_ticket_id": sa}, headers=h
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{T}/merge", json={"ticket_ids": [sa], "target_ticket_id": fresh["id"]}, headers=h
        ).status_code
        == 409
    )

    # List filters.
    def ids(params: dict[str, Any]) -> set[str]:
        return {t["id"] for t in _ok(client.get(T, params=params, headers=h))}

    everything = ids({"q": RUN})
    assert {target["id"], sa, source_b_id, fresh["id"]} <= everything
    visible = ids({"q": RUN, "include_merged": "false"})
    assert target["id"] in visible
    assert sa not in visible
    assert source_b_id not in visible
    assert ids({"merged_into": target["id"]}) == {sa, source_b_id}
    assert ids({"q": str(target["number"])}) >= {target["id"]}
    assert ids({"q": f"#{target['number']}", "include_merged": "false"}) >= {target["id"]}
    assert ids({"q": f"Wohnung 3 {RUN}"}) == {sa}
    assert ids({"q": "9" * 30}) == set()
    assert ids({"q": f"kein Treffer {RUN}"}) == set()
