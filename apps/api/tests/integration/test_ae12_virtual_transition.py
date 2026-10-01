"""AE12 (GA07-01, AA06-02, AD06-01): transition date of the enabling resolution as a tenant
setting entered by the operator (no legal text, no lock effect), orientation values of the
deadline notice and the online meeting switch (default off). Own world (prefix ae12)."""

import asyncio
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from mhvp.hoa import meeting_rules
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings) -> World:  # type: ignore[no-untyped-def]
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae12a-{RUN}", name=f"AE12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae12b-{RUN}", name=f"AE12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae12admin", a, "tenant_admin"),
            ("ae12other", b, "tenant_admin"),
            ("ae12care", a, "caretaker"),
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as c:
        yield c


def test_transition_notice_unit() -> None:
    assert meeting_rules.transition_notice(date(2024, 1, 1), None) is None
    before = meeting_rules.transition_notice(date(2024, 1, 1), date(2025, 6, 30))
    assert before
    assert "30.06.2025" in before
    assert "vor dem Stichtag" in before
    after = meeting_rules.transition_notice(date(2025, 6, 30), date(2025, 6, 30))
    assert after
    assert "am oder nach dem Stichtag" in after
    d = meeting_rules.basis_deadlines(
        date(2024, 2, 29), date(2026, 1, 11), None, today=date(2026, 1, 1)
    )
    assert d["term_limit"] == date(2027, 2, 28)
    assert d["days_until_valid_until"] == 10
    assert d["to_verify"] is True
    assert d["transition_notice"] is None


def test_transition_date_setting(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae12admin", world.tenant_a))
    hb = bearer(login(client, world, "ae12other", world.tenant_b))
    hc = bearer(login(client, world, "ae12care", world.tenant_a))
    body = {"invitation_weeks": 3, "virtual_meetings_enabled": False}

    got = client.get(f"{H}/meeting-settings", headers=ha).json()
    assert got["virtual_basis_transition_date"] is None
    assert got["virtual_basis_term_lock_enabled"] is False

    # set, omit keeps, null clears
    put = client.put(
        f"{H}/meeting-settings",
        json=body | {"virtual_basis_transition_date": "2025-06-30"},
        headers=ha,
    )
    assert put.status_code == 200
    assert put.json()["virtual_basis_transition_date"] == "2025-06-30"
    assert client.put(f"{H}/meeting-settings", json=body, headers=ha).status_code == 200
    got = client.get(f"{H}/meeting-settings", headers=ha).json()
    assert got["virtual_basis_transition_date"] == "2025-06-30"

    # other tenant does not see it (RLS)
    other = client.get(f"{H}/meeting-settings", headers=hb).json()
    assert other["virtual_basis_transition_date"] is None

    # validation and permission
    bad = client.put(
        f"{H}/meeting-settings", json=body | {"virtual_basis_transition_date": "kein"}, headers=ha
    )
    assert bad.status_code == 422
    assert (
        client.put(
            f"{H}/meeting-settings",
            json=body | {"virtual_basis_transition_date": "2025-01-01"},
            headers=hc,
        ).status_code
        == 403
    )

    cleared = client.put(
        f"{H}/meeting-settings", json=body | {"virtual_basis_transition_date": None}, headers=ha
    )
    assert cleared.json()["virtual_basis_transition_date"] is None


def test_online_switch_default_off(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae12admin", world.tenant_a))
    hb = bearer(login(client, world, "ae12other", world.tenant_b))
    hc = bearer(login(client, world, "ae12care", world.tenant_a))
    assert client.get(f"{H}/online-meeting-settings", headers=ha).json()["enabled"] is False
    assert (
        client.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=hc).status_code
        == 403
    )
    assert (
        client.put(f"{H}/online-meeting-settings", json={"enabled": "x"}, headers=ha).status_code
        == 422
    )
    assert (
        client.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=ha).json()[
            "enabled"
        ]
        is True
    )
    assert client.get(f"{H}/online-meeting-settings", headers=hb).json()["enabled"] is False
    client.put(f"{H}/online-meeting-settings", json={"enabled": False}, headers=ha)
