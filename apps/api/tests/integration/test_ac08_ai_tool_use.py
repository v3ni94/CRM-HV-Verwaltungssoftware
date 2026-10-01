"""Model planned lookups (tool use, GA10-06, rule AI-TOOL-01). No network: the fake provider
returns ``tool_calls`` like a model would.

Fixed expected values: tenant A holds contact "Tilo Werkzeug<RUN>" (phone +49 30 777001, e-mail
tilo.<RUN>@example.org); tenant B holds nothing with that name. Limits: 3 rounds, 6 calls.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import tool_use
from mhvp.ai.providers import ToolCall
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake

pytestmark = pytest.mark.integration
__all__ = ["fake"]

SURNAME = f"Werkzeug{RUN}"
EMAIL = f"tilo.{RUN}@example.org"
PHONE = "+49 30 777001"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ac08a-{RUN}", name=f"AC08 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ac08b-{RUN}", name=f"AC08B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("ac08admin", a), ("ac08second", a), ("ac08other", b)]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


def _provider(c: TestClient, world: World, *, tool_use_on: bool) -> dict[str, str]:
    admin = bearer(login(c, world, "ac08admin"))
    second = bearer(login(c, world, "ac08second"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    models = {k: dict(v) for k, v in PROVIDER["models"].items()}
    for entry in models.values():
        entry["tool_use"] = tool_use_on
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "models": models, "dpa_document_id": dpa},
            headers=admin,
        ),
        200,
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second), 200)
    return admin


@pytest.fixture(scope="module")
def contact(database: Database, redis_url: str, world: World) -> str:
    with mock_aws(), TestClient(create_app(_settings(database, redis_url))) as c:
        h = bearer(login(c, world, "ac08admin"))
        body = {
            "kind": "person",
            "first_name": "Tilo",
            "last_name": SURNAME,
            "phones": [{"number": PHONE, "is_primary": True}],
            "emails": [{"email": EMAIL, "is_primary": True}],
        }
        return str(_ok(c.post("/api/v1/contacts", json=body, headers=h))["id"])


def _ask(c: TestClient, h: dict[str, str], question: str) -> dict[str, Any]:
    conversation = _ok(c.post("/api/v1/ai/conversations", json={}, headers=h))["id"]
    body = {"content": question, "task": "answer_question", "document_ids": []}
    run = _ok(
        c.post(f"/api/v1/ai/conversations/{conversation}/messages", json=body, headers=h), 202
    )
    return dict(_ok(c.get(f"/api/v1/ai/runs/{run['id']}", headers=h), 200))


ANSWER = {"answer": "Erledigt.", "sources": [], "answerable": True}


def _tool_answer(name: str, **arguments: str) -> dict[str, Any]:
    return {
        "answer": "",
        "sources": [],
        "answerable": False,
        "tool_calls": [{"name": name, "arguments": arguments}],
    }


def _all_sent(fake: FakeProvider) -> str:
    return "\n".join(str(m["content"]) for call in fake.calls for m in call["messages"])


def test_off_by_default_no_tools_offered(
    client: TestClient, world: World, contact: str, fake: FakeProvider
) -> None:
    admin = _provider(client, world, tool_use_on=False)
    fake.queue.append(ANSWER)
    run = _ask(client, admin, "Wer ist Tilo?")
    assert run["status"] == "succeeded", run["error"]
    assert run["tools_used"] == []
    assert len(fake.calls) == 1
    assert "tool_calls" not in str(fake.calls[0]["schema"])
    assert "tool_calls" not in str(fake.calls[0]["messages"])


def test_tool_loop_runs_masks_and_logs(
    client: TestClient, world: World, contact: str, fake: FakeProvider
) -> None:
    admin = _provider(client, world, tool_use_on=True)
    fake.queue += [
        _tool_answer("kontakte", suche=f"{SURNAME} {EMAIL}"),
        {**ANSWER, "tool_calls": []},
    ]
    run = _ask(client, admin, "Wie erreiche ich den Kontakt?")
    assert run["status"] == "succeeded", run["error"]
    assert len(fake.calls) == 2
    assert "tool_calls" in str(fake.calls[0]["schema"])
    used = run["tools_used"]
    assert [u["tool"] for u in used] == ["kontakte"]
    assert used[0]["permitted"] is True
    assert used[0]["count"] == 1
    # Masking: neither the arguments in the protocol nor anything sent carries e-mail or phone.
    assert EMAIL not in str(used[0]["arguments"])
    sent = _all_sent(fake)
    assert "<werkzeugdaten>" in sent
    assert "[contact " in sent  # the id itself may be hit by the phone masker
    assert EMAIL not in sent
    assert "777001" not in sent
    # Hits come back as chat links (no phone or e-mail in the detail) and the reloaded
    # conversation carries tools_used and the link on the answer message.
    link = next(x for x in used[0]["links"] if x["type"] == "contact")
    assert link["id"] == contact
    assert link["href"] == f"/kontakte/{contact}"
    assert link["detail"] == ""
    assert contact in [x["id"] for x in run["links"]]
    listing = _ok(client.get("/api/v1/ai/conversations", headers=admin), 200)
    items = listing["items"] if isinstance(listing, dict) else listing
    conv = next(
        c
        for c in (
            _ok(client.get(f"/api/v1/ai/conversations/{i['id']}", headers=admin), 200)
            for i in items
        )
        if any(m["task_run_id"] == run["id"] for m in c["messages"])
    )
    answer = next(
        m for m in conv["messages"] if m["task_run_id"] == run["id"] and m["role"] == "assistant"
    )
    assert [u["tool"] for u in answer["tools_used"]] == ["kontakte"]
    assert contact in [x["id"] for x in answer["links"]]
    user_msg = next(m for m in conv["messages"] if m["role"] == "user")
    assert user_msg["tools_used"] is None


def test_tool_loop_ends_at_limits(
    client: TestClient, world: World, contact: str, fake: FakeProvider
) -> None:
    admin = _provider(client, world, tool_use_on=True)
    endless = {
        "answer": "",
        "sources": [],
        "answerable": False,
        "tool_calls": [{"name": "kontakte", "arguments": {"suche": SURNAME}}] * 4,
    }
    fake.queue += [endless, endless, endless]
    run = _ask(client, admin, "Bitte immer weiter suchen")
    assert run["status"] == "succeeded", run["error"]
    # 6 calls are spent after two rounds (4 + 2), then one final call without tools.
    assert len(run["tools_used"]) == tool_use.MAX_CALLS
    assert len(fake.calls) == 3
    assert "tool_calls" not in str(fake.calls[-1]["schema"])
    assert tool_use.FINAL_NOTICE in str(fake.calls[-1]["messages"][-1]["content"])
    assert fake.queue == []  # a further tool request after the limits is not executed


def test_tool_respects_permission_and_tenant(
    database: Database, redis_url: str, world: World, contact: str
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    call = ToolCall("kontakte", {"suche": SURNAME})

    async def _run(tenant: uuid.UUID, user: str, permissions: frozenset[str]) -> dict[str, Any]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), tenant) as session:
                principal = tool_use.principal_of(
                    {"user_id": str(world.users[user]), "permissions": sorted(permissions)},
                    tenant,
                )
                tool_use.attach(session, principal)
                return await tool_use.run_call(session, permissions, call)
        finally:
            await engine.dispose()

    own = asyncio.run(_run(world.tenant_a, "ac08admin", frozenset({"contacts:read"})))
    assert own["count"] == 1
    assert own["links"][0]["id"] == contact
    denied = asyncio.run(_run(world.tenant_a, "ac08admin", frozenset()))
    assert denied["permitted"] is False
    assert denied["links"] == []
    foreign = asyncio.run(_run(world.tenant_b, "ac08other", frozenset({"contacts:read"})))
    assert foreign["count"] == 0
