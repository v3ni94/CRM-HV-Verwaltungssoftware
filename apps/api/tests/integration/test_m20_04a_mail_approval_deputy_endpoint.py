"""M20-04a (docs/OPEN_QUESTIONS.md): Pflege der Mail-Vertretungen (``MailApprovalDeputy``)
über GET/POST/DELETE /api/v1/mail/mail-approval/deputies. Recht ``tenant_settings:update``
verwaltet beliebige Vertretungen, ohne dieses Recht darf ein Nutzer nur seine eigene
Abwesenheit vertreten lassen. Validierung: kein Selbstbezug, Zeitraum, Mandantenzugehörigkeit;
Audit-Ereignis je Anlage/Widerruf."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
D = "/api/v1/mail/mail-approval/deputies"


async def _world(redis_url: str, database: Database) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(_settings(database, redis_url))
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"md-{RUN}", name=f"MailDeputy {RUN}")
        world = World(
            tenant_a=a,
            tenant_b=a,
            app_url=_settings(database, redis_url).database_url.get_secret_value(),
        )
        for name, role in [
            ("mdadmin", "tenant_admin"),
            ("mdabsent", "standard"),
            ("mddeputy", "standard"),
            ("mdother", "standard"),
        ]:
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
    return asyncio.run(_world(redis_url, database))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _period() -> tuple[str, str]:
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).isoformat(), (now + timedelta(days=8)).isoformat()


def test_own_deputy_self_service(client: TestClient, world: World) -> None:
    """Ohne ``tenant_settings:update`` darf ``mdabsent`` seine eigene Abwesenheit vertreten
    lassen, aber keine fremde Vertretung anlegen."""
    absent = bearer(login(client, world, "mdabsent"))
    starts, ends = _period()
    ok = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdabsent"]),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": starts,
            "ends_at": ends,
            "note": "Urlaub",
        },
        headers=absent,
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["absent_user_id"] == str(world.users["mdabsent"])
    assert body["deputy_user_id"] == str(world.users["mddeputy"])

    forbidden = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdother"]),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=absent,
    )
    assert forbidden.status_code == 403, forbidden.text


def test_admin_manages_any_deputy(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "mdadmin"))
    starts, ends = _period()
    created = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdother"]),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    listed = client.get(D, headers=admin)
    assert listed.status_code == 200
    assert any(r["id"] == created.json()["id"] for r in listed.json())

    deleted = client.delete(f"{D}/{created.json()['id']}", headers=admin)
    assert deleted.status_code == 204
    listed_after = client.get(D, headers=admin)
    assert all(r["id"] != created.json()["id"] for r in listed_after.json())


def test_validation_self_reference_and_period(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "mdadmin"))
    starts, ends = _period()
    self_ref = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdother"]),
            "deputy_user_id": str(world.users["mdother"]),
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=admin,
    )
    assert self_ref.status_code == 422, self_ref.text

    bad_period = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdother"]),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": ends,
            "ends_at": starts,
        },
        headers=admin,
    )
    assert bad_period.status_code == 422, bad_period.text

    unknown_user = client.post(
        D,
        json={
            "absent_user_id": str(uuid.uuid4()),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=admin,
    )
    assert unknown_user.status_code == 422, unknown_user.text


def test_delete_needs_admin_or_own_absence(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "mdadmin"))
    other = bearer(login(client, world, "mdother"))
    starts, ends = _period()
    created = client.post(
        D,
        json={
            "absent_user_id": str(world.users["mdother"]),
            "deputy_user_id": str(world.users["mddeputy"]),
            "starts_at": starts,
            "ends_at": ends,
        },
        headers=admin,
    ).json()

    third = bearer(login(client, world, "mddeputy"))
    refused = client.delete(f"{D}/{created['id']}", headers=third)
    assert refused.status_code == 403, refused.text

    allowed = client.delete(f"{D}/{created['id']}", headers=other)
    assert allowed.status_code == 204, allowed.text
