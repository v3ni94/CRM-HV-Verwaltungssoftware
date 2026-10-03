"""AN05 (GAJ-610): address history behind the tenant switch contacts.address_history."""

import asyncio
import importlib.util
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.contacts.address_history import closing_date
from mhvp.core.clock import local_today
from mhvp.main import create_app
from mhvp.platform import services as platform
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
C = "/api/v1/contacts"
S = "/api/v1/contact-address-history"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform.provision_tenant(factory, slug=f"an05a-{RUN}", name=f"AN05 A {RUN}")
        b, _ = await platform.provision_tenant(factory, slug=f"an05b-{RUN}", name=f"AN05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("admin", a, "tenant_admin"),
            ("reader", a, "read_only"),
            ("other", b, "tenant_admin"),
        ]:
            uid = await platform.create_user(
                factory, email=world.email(f"an05{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"an05{name}"] = uid
            await platform.add_member(
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


def _body(last: str, *cities: str) -> dict[str, Any]:
    return {
        "kind": "person",
        "first_name": "Max",
        "last_name": last,
        "addresses": [
            {"street": "Weg", "house_number": "1", "city": c, "is_primary": i == 0}
            for i, c in enumerate(cities)
        ],
    }


def _switch(c: TestClient, h: dict[str, str], on: bool) -> None:
    r = c.put(S, json={"enabled": on}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is on


def test_closing_date_never_before_start() -> None:
    today = local_today()
    assert closing_date(None, today) == today - timedelta(days=1)
    assert closing_date(today, today) == today


def test_switch_off_replace_unchanged(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "an05admin"))
    _switch(client, admin, False)
    created = client.post(C, json=_body(f"Aus{RUN}", "Hilden"), headers=admin)
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    r = client.put(f"{C}/{cid}", json=_body(f"Aus{RUN}", "Erkrath"), headers=admin)
    assert r.status_code == 200, r.text
    listed = client.get(f"{C}/{cid}/addresses", headers=admin).json()
    assert listed["history_available"] is False
    assert [a["city"] for a in listed["items"]] == ["Erkrath"]
    assert listed["items"][0]["valid_from"] is None
    for query in ("as_of=2025-01-01", "include_history=true"):
        refused = client.get(f"{C}/{cid}/addresses?{query}", headers=admin)
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "MHVP-CONT-0034"


def test_switch_on_closes_and_queries_by_date(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "an05admin"))
    reader = bearer(login(client, world, "an05reader"))
    other = bearer(login(client, world, "an05other"))
    created = client.post(C, json=_body(f"An{RUN}", "Hilden", "Mettmann"), headers=admin)
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    _switch(client, admin, True)
    try:
        r = client.put(f"{C}/{cid}", json=_body(f"An{RUN}", "Erkrath", "Mettmann"), headers=admin)
        assert r.status_code == 200, r.text
        # The contact itself shows only the current addresses.
        assert sorted(a["city"] for a in r.json()["addresses"]) == ["Erkrath", "Mettmann"]
        today = local_today()
        current = client.get(f"{C}/{cid}/addresses", headers=admin).json()
        assert current["history_available"] is True
        assert sorted(a["city"] for a in current["items"]) == ["Erkrath", "Mettmann"]
        erkrath = next(a for a in current["items"] if a["city"] == "Erkrath")
        assert erkrath["valid_from"] == today.isoformat()
        assert erkrath["is_primary"] is True
        mettmann = next(a for a in current["items"] if a["city"] == "Mettmann")
        assert mettmann["valid_from"] is None  # unchanged row kept, not rewritten
        history = client.get(f"{C}/{cid}/addresses?include_history=true", headers=admin).json()
        hilden = next(a for a in history["items"] if a["city"] == "Hilden")
        # AO09: no valid_from before, so it is the creation date (today) and valid_to is not
        # before it (CHECK), although yesterday would be the closing day otherwise.
        assert hilden["valid_from"] == today.isoformat()
        assert hilden["valid_to"] == today.isoformat()
        assert hilden["superseded_at"] is not None
        assert hilden["is_primary"] is False
        past = (today - timedelta(days=1)).isoformat()
        before = client.get(f"{C}/{cid}/addresses?as_of={past}", headers=reader)
        assert before.status_code == 200, before.text
        assert sorted(a["city"] for a in before.json()["items"]) == ["Mettmann"]
        assert before.json()["as_of"] == past
        now = client.get(f"{C}/{cid}/addresses?as_of={today.isoformat()}", headers=admin).json()
        assert sorted(a["city"] for a in now["items"]) == ["Erkrath", "Hilden", "Mettmann"]
        bad = client.get(f"{C}/{cid}/addresses?as_of=gestern", headers=admin)
        assert bad.status_code == 422
        assert client.get(f"{C}/{cid}/addresses?as_of={past}", headers=other).status_code == 404
        assert client.get(f"{C}/{uuid.uuid4()}/addresses", headers=admin).status_code == 404
        # Switch: reader may read, not write; other tenant keeps its own (default off).
        assert client.get(S, headers=reader).json()["enabled"] is True
        assert client.put(S, json={"enabled": False}, headers=reader).status_code == 403
        assert client.get(S, headers=other).json()["enabled"] is False
        assert client.put(S, json={"enabled": "ja"}, headers=admin).status_code == 422
        assert client.put(S, json={"enabled": True, "x": 1}, headers=admin).status_code == 422
        assert client.get(S).status_code == 401
    finally:
        _switch(client, admin, False)
    # Switching off deletes nothing: the history stays readable in the database only.
    after = client.get(f"{C}/{cid}/addresses", headers=admin).json()
    assert sorted(a["city"] for a in after["items"]) == ["Erkrath", "Mettmann"]


def _migration() -> Any:
    path = Path(__file__).parents[2] / "alembic/versions/0452_an05_contact_address_history.py"
    spec = importlib.util.spec_from_file_location("an05_migration_0452", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0452_round_trip(migrator_engine: Engine) -> None:
    """Downgrade and upgrade of 0452 itself, inside one rolled back transaction, so later
    migrations of other packages do not take part."""
    migration = _migration()
    columns = text(
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'contact_address' "
        "AND column_name IN ('valid_to', 'superseded_at')"
    )
    constraint = text(
        "SELECT count(*) FROM pg_constraint WHERE conrelid = 'contact_address'::regclass "
        "AND conname = 'ck_contact_address_valid_range'"
    )
    with migrator_engine.connect() as conn:
        tx = conn.begin()
        try:
            assert conn.execute(columns).scalar_one() == 2
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
                assert conn.execute(columns).scalar_one() == 0
                assert conn.execute(constraint).scalar_one() == 0
                migration.upgrade()
            assert conn.execute(columns).scalar_one() == 2
            assert conn.execute(constraint).scalar_one() == 1
        finally:
            tx.rollback()
