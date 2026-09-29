"""Audit 29.09.2026 (Wissensdatenbank und Playbooks): freigegebene Wissenseinträge fließen in
den Chat ein (``gateway.knowledge_context``), die Nutzung wird je Eintrag gezählt, Rückmeldung
"hilfreich / nicht hilfreich" je Antwort, Eintrag und Playbook, Hinweis "lange nicht geprüft",
Mandantentrennung der neuen Endpunkte."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mhvp.ai import gateway, knowledge
from mhvp.ai.models import AiKnowledgeEntry, AiTask, AiTaskRun, RunStatus
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
M = "/api/v1"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"kbf-{RUN}", name=f"WissenF {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"kbf2-{RUN}", name=f"WissenF2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name in [(a, "kbfauthor"), (a, "kbfapprover"), (b, "kbfother")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant_id,
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
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _approved(
    c: TestClient, author: dict[str, str], approver: dict[str, str], title: str
) -> dict[str, Any]:
    row = _ok(
        c.post(
            f"{M}/ai/knowledge",
            json={"kind": "fact", "title": title, "content": f"Inhalt {title}"},
            headers=author,
        ),
        201,
    )
    _ok(c.post(f"{M}/ai/knowledge/{row['id']}/submit", headers=author))
    return cast(
        dict[str, Any], _ok(c.post(f"{M}/ai/knowledge/{row['id']}/approve", headers=approver))
    )


def _in_tenant(database: Database, redis_url: str, tenant_id: uuid.UUID, work: Any) -> Any:
    async def _run() -> Any:
        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.core.db.tenancy import tenant_transaction

        settings = _settings(database, redis_url)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_chat_run_gets_approved_knowledge_and_counts_usage(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    author = bearer(login(client, world, "kbfauthor"))
    approver = bearer(login(client, world, "kbfapprover"))
    entry = _approved(client, author, approver, f"Hausordnung Ruhezeiten {RUN}")
    draft = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={"kind": "fact", "title": f"Entwurf {RUN}", "content": "nie im Chat"},
            headers=author,
        ),
        201,
    )

    async def _work(session: Any) -> tuple[str, dict[str, Any]]:
        run = AiTaskRun(
            tenant_id=world.tenant_a,
            created_by=world.users["kbfauthor"],
            task=AiTask.ANSWER_QUESTION,
            prompt_version="test",
            input_hash="x",
            input_ref={"instruction": "Wann sind die Ruhezeiten?", "document_ids": []},
            status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.flush()
        text = await gateway.knowledge_context(session, run, "Wann sind die Ruhezeiten?")
        return text, dict(run.input_ref)

    text, ref = _in_tenant(database, redis_url, world.tenant_a, _work)
    assert "Vorrang vor Dokumenttext" in text
    assert f"Hausordnung Ruhezeiten {RUN}" in text
    assert "nie im Chat" not in text
    assert entry["id"] in ref["knowledge_ids"]
    assert draft["id"] not in ref["knowledge_ids"]

    listed = _ok(client.get(f"{M}/ai/knowledge", headers=author))
    row = next(r for r in listed if r["id"] == entry["id"])
    assert row["usage_count"] == 1
    assert row["last_used_at"] is not None
    assert row["stale"] is False


def test_feedback_on_entry_run_and_playbook(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    author = bearer(login(client, world, "kbfauthor"))
    approver = bearer(login(client, world, "kbfapprover"))
    other = bearer(login(client, world, "kbfother"))
    entry = _approved(client, author, approver, f"Bewertet {RUN}")

    rated = _ok(
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/feedback", json={"helpful": True}, headers=author
        )
    )
    assert (rated["helpful_count"], rated["unhelpful_count"]) == (1, 0)
    # Feedback never touches the status or the version (approval flow unchanged).
    assert rated["status"] == "approved"
    assert rated["version"] == entry["version"]
    # Tenant separation: the other tenant sees no such entry.
    assert (
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/feedback", json={"helpful": True}, headers=other
        ).status_code
        == 404
    )

    async def _make_run(session: Any) -> uuid.UUID:
        run = AiTaskRun(
            tenant_id=world.tenant_a,
            created_by=world.users["kbfauthor"],
            task=AiTask.ANSWER_QUESTION,
            prompt_version="test",
            input_hash="y",
            input_ref={"instruction": "?", "document_ids": [], "knowledge_ids": [entry["id"]]},
            status=RunStatus.SUCCEEDED,
            output={"answer": "Antwort"},
        )
        session.add(run)
        await session.flush()
        return run.id

    run_id = _in_tenant(database, redis_url, world.tenant_a, _make_run)
    out = _ok(
        client.post(f"{M}/ai/runs/{run_id}/feedback", json={"helpful": False}, headers=author)
    )
    assert out["feedback"] == "unhelpful"
    assert out["knowledge_ids"] == [entry["id"]]
    # A second vote replaces the first: helpful moves back, unhelpful moves on.
    out = _ok(client.post(f"{M}/ai/runs/{run_id}/feedback", json={"helpful": True}, headers=author))
    assert out["feedback"] == "helpful"
    row = _ok(client.get(f"{M}/ai/knowledge/{entry['id']}/versions", headers=author))[-1]
    assert (row["helpful_count"], row["unhelpful_count"]) == (2, 0)
    # Not the run's author: forbidden; other tenant: not found.
    assert (
        client.post(
            f"{M}/ai/runs/{run_id}/feedback", json={"helpful": True}, headers=approver
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{M}/ai/runs/{run_id}/feedback", json={"helpful": True}, headers=other
        ).status_code
        == 404
    )

    playbook = _ok(
        client.post(
            f"{M}/mail/playbooks",
            json={"title": f"Playbook {RUN}", "keywords": ["heizung"], "status": "active"},
            headers=author,
        ),
        201,
    )
    rated = _ok(
        client.post(
            f"{M}/mail/playbooks/{playbook['id']}/feedback", json={"helpful": False}, headers=author
        )
    )
    assert (rated["helpful_count"], rated["unhelpful_count"]) == (0, 1)
    assert rated["status"] == "active"
    assert rated["usage_count"] == 0
    assert (
        client.post(
            f"{M}/mail/playbooks/{playbook['id']}/feedback", json={"helpful": True}, headers=other
        ).status_code
        == 404
    )
    # Use outside apply-playbook (ticket reply insert, operator 29.09.2026): counter and
    # last_used_at only; other tenant: not found.
    used = _ok(client.post(f"{M}/mail/playbooks/{playbook['id']}/use", headers=author))
    assert used["usage_count"] == 1
    assert used["last_used_at"] is not None
    assert (used["helpful_count"], used["unhelpful_count"]) == (0, 1)
    assert (
        _ok(client.post(f"{M}/mail/playbooks/{playbook['id']}/use", headers=author))["usage_count"]
        == 2
    )
    assert client.post(f"{M}/mail/playbooks/{playbook['id']}/use", headers=other).status_code == 404


def test_stale_hint_for_old_approved_entries(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    author = bearer(login(client, world, "kbfauthor"))
    approver = bearer(login(client, world, "kbfapprover"))
    entry = _approved(client, author, approver, f"Alt {RUN}")
    old = datetime.now(UTC) - timedelta(days=knowledge.STALE_AFTER_DAYS + 5)

    async def _age(session: Any) -> None:
        await session.execute(
            update(AiKnowledgeEntry)
            .where(AiKnowledgeEntry.id == uuid.UUID(entry["id"]))
            .values(updated_at=old)
        )

    _in_tenant(database, redis_url, world.tenant_a, _age)
    listed = _ok(client.get(f"{M}/ai/knowledge?status=approved", headers=author))
    row = next(r for r in listed if r["id"] == entry["id"])
    assert row["stale"] is True
    # The hint changes nothing: still approved, still fed to runs.
    assert row["status"] == "approved"
