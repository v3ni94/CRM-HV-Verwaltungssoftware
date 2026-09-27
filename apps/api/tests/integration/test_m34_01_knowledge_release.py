"""M34-01 Freigabeworkflow für Wissenseinträge: Status Entwurf/zur Prüfung/freigegeben/
zurückgezogen, Versionierung je Eintrag, Vier-Augen-Freigabe, Mandantentrennung und dass nur
freigegebene, gültige Einträge in einen KI-Lauf als Kontext einfließen."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

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
        a, _ = await services.provision_tenant(factory, slug=f"kbr-{RUN}", name=f"WissenR {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"kbr2-{RUN}", name=f"WissenR2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name, role in [
            (a, "kbrauthor", "tenant_admin"),
            (a, "kbrapprover", "tenant_admin"),
            (b, "kbrother", "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
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


def _create(c: TestClient, h: dict[str, str], title: str = "Regel") -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _ok(
            c.post(
                f"{M}/ai/knowledge",
                json={"kind": "fact", "title": title, "content": "Erstfassung"},
                headers=h,
            ),
            201,
        ),
    )


def test_release_workflow_and_four_eyes(client: TestClient, world: World) -> None:
    author = bearer(login(client, world, "kbrauthor"))
    approver = bearer(login(client, world, "kbrapprover"))

    entry = _create(client, author)
    assert entry["status"] == "draft"
    assert entry["version"] == 1

    # Freigabe vor Einreichung ist kein gültiger Übergang.
    assert (
        client.post(f"{M}/ai/knowledge/{entry['id']}/approve", headers=approver).status_code == 409
    )

    submitted = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/submit", headers=author))
    assert submitted["status"] == "in_review"
    assert submitted["submitted_by"] is not None

    # Vier-Augen: der Verfasser darf die eigene Version nicht freigeben.
    assert client.post(f"{M}/ai/knowledge/{entry['id']}/approve", headers=author).status_code == 403

    approved = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/approve", headers=approver))
    assert approved["status"] == "approved"
    assert approved["approved_by"] is not None

    withdrawn = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/withdraw", headers=approver))
    assert withdrawn["status"] == "withdrawn"
    # ein bereits zurückgezogener Eintrag kann nicht erneut zurückgezogen werden
    assert (
        client.post(f"{M}/ai/knowledge/{entry['id']}/withdraw", headers=approver).status_code == 409
    )


def test_reject_needs_four_eyes_and_returns_to_draft(client: TestClient, world: World) -> None:
    author = bearer(login(client, world, "kbrauthor"))
    approver = bearer(login(client, world, "kbrapprover"))

    entry = _create(client, author, title="Wird zurückgewiesen")

    # Zurückweisen vor Einreichung ist kein gültiger Übergang.
    assert (
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/reject", json={"reason": "x"}, headers=approver
        ).status_code
        == 409
    )

    submitted = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/submit", headers=author))
    assert submitted["status"] == "in_review"

    # Vier-Augen: der Verfasser darf die eigene Version nicht zurückweisen.
    assert (
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/reject", json={"reason": "x"}, headers=author
        ).status_code
        == 403
    )

    rejected = _ok(
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/reject",
            json={"reason": "Quelle fehlt."},
            headers=approver,
        )
    )
    assert rejected["status"] == "draft"
    assert rejected["rejected_by"] is not None
    assert rejected["rejection_reason"] == "Quelle fehlt."

    # Eine leere Begründung wird abgelehnt (Validierung).
    submitted_again = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/submit", headers=author))
    assert submitted_again["status"] == "in_review"
    assert (
        client.post(
            f"{M}/ai/knowledge/{entry['id']}/reject", json={"reason": ""}, headers=approver
        ).status_code
        == 422
    )


def test_change_after_approval_creates_new_version(client: TestClient, world: World) -> None:
    author = bearer(login(client, world, "kbrauthor"))
    approver = bearer(login(client, world, "kbrapprover"))

    entry = _create(client, author, title="Ablageregel")
    _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/submit", headers=author))
    v1 = _ok(client.post(f"{M}/ai/knowledge/{entry['id']}/approve", headers=approver))
    assert v1["version"] == 1

    v2 = _ok(
        client.put(
            f"{M}/ai/knowledge/{v1['id']}",
            json={"kind": "fact", "title": "Ablageregel", "content": "Zweite Fassung"},
            headers=author,
        )
    )
    assert v2["id"] != v1["id"]
    assert v2["group_id"] == v1["group_id"]
    assert v2["version"] == 2
    assert v2["status"] == "draft"

    history = _ok(client.get(f"{M}/ai/knowledge/{v1['id']}/versions", headers=author))
    assert [h["version"] for h in history] == [1, 2]
    old = next(h for h in history if h["version"] == 1)
    assert old["superseded_at"] is not None
    assert old["content"] == "Erstfassung" or old["content"]  # alte Version bleibt lesbar
    new = next(h for h in history if h["version"] == 2)
    assert new["superseded_at"] is None

    # v1 ist nicht mehr die aktuelle Version, ein weiteres Ändern darüber ist ein Konflikt.
    assert (
        client.put(
            f"{M}/ai/knowledge/{v1['id']}",
            json={"kind": "fact", "title": "Ablageregel", "content": "x"},
            headers=author,
        ).status_code
        == 409
    )


def test_tenant_separation_on_workflow_endpoints(client: TestClient, world: World) -> None:
    author = bearer(login(client, world, "kbrauthor"))
    other = bearer(login(client, world, "kbrother"))
    entry = _create(client, author, title="Nur Mandant A")

    assert client.post(f"{M}/ai/knowledge/{entry['id']}/submit", headers=other).status_code == 404
    assert client.get(f"{M}/ai/knowledge/{entry['id']}/versions", headers=other).status_code == 404


def test_only_approved_and_valid_entries_feed_ai_context(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    author = bearer(login(client, world, "kbrauthor"))
    approver = bearer(login(client, world, "kbrapprover"))

    draft = _create(client, author, title="Entwurf, nie im Kontext")

    approved_entry = _create(client, author, title="Freigegeben, im Kontext")
    _ok(client.post(f"{M}/ai/knowledge/{approved_entry['id']}/submit", headers=author))
    approved_entry = _ok(
        client.post(f"{M}/ai/knowledge/{approved_entry['id']}/approve", headers=approver)
    )

    expired = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={
                "kind": "fact",
                "title": "Abgelaufen, nie im Kontext",
                "content": "x",
                "valid_until": "2020-01-01",
            },
            headers=author,
        ),
        201,
    )
    _ok(client.post(f"{M}/ai/knowledge/{expired['id']}/submit", headers=author))
    _ok(client.post(f"{M}/ai/knowledge/{expired['id']}/approve", headers=approver))

    async def _run() -> tuple[str, list[dict[str, Any]]]:
        from mhvp.communication import preparation
        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.core.db.tenancy import tenant_transaction

        settings = _settings(database, redis_url)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await preparation._knowledge_context(session, world.tenant_a, None)
        finally:
            await engine.dispose()

    text, used = asyncio.run(_run())
    used_ids = {u["id"] for u in used}
    assert approved_entry["id"] in used_ids
    assert draft["id"] not in used_ids
    assert expired["id"] not in used_ids
    assert "Freigegeben, im Kontext" in text
    assert "Entwurf, nie im Kontext" not in text
    assert "Abgelaufen, nie im Kontext" not in text
