"""AE26 / M11-01: manual FinTS address per connection (PATCH /banking/fints/connections/{id}),
German check steps for a locked access (MHVP-BANK-0010) and an unreachable bank
(MHVP-BANK-0013) in the session, the connection and the stored last error. Fake python-fints
client (`tests.fints_fake`), no network; own test world with the prefix ae26."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.banking import fints as fints_mod
from mhvp.banking import tasks as banking_tasks
from mhvp.main import create_app
from mhvp.platform import services
from tests import fints_fake as fake
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking/fints"
PRODUCT_ID = "TESTPRODUCTID000000000026"
BLZ = "38250110"  # Kreissparkasse Euskirchen, with FinTS URL in the list
MANUAL = "https://fints.fusionsbank.example.de/hbci/pintan"


def _settings(database: Database, redis_url: str, **overrides: Any) -> Any:
    return base_settings(database, redis_url, **{"fints_product_id": PRODUCT_ID, **overrides})


@pytest.fixture(autouse=True)
def _fake_fints(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, database: Database, redis_url: str
) -> None:
    # `client` first: the API lifespan binds the configured Celery app as current; the
    # `.delay` patch below must land on that app's task object.
    del client
    fake.install(monkeypatch)
    test_settings = _settings(database, redis_url)
    monkeypatch.setattr(banking_tasks, "get_settings", lambda: test_settings)

    def run_now(*args: str) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(banking_tasks.fints_step.run, *args).result()

    monkeypatch.setattr(banking_tasks.fints_step, "delay", run_now)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ae26-fints-{RUN}", name=f"AE26 FinTS {RUN}"
        )
        b, _ = await services.provision_tenant(
            factory, slug=f"ae26-fints-sep-{RUN}", name=f"AE26 FinTS Sep {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant_id in [
            ("ae26-admin", "tenant_admin", a),
            ("ae26-noaccounting", "accountant_no_banking", a),
            ("ae26-b-admin", "tenant_admin", b),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _connect(client: TestClient, h: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body = {"institute": BLZ, "login": "kunde-26", "pin": fake.GOOD_PIN, **overrides}
    created: dict[str, Any] = _ok(client.post(f"{B}/connections", json=body, headers=h), 201)
    return created


def _session(client: TestClient, h: dict[str, str], session_id: str) -> dict[str, Any]:
    out: dict[str, Any] = _ok(client.get(f"{B}/sessions/{session_id}", headers=h))
    return out


def _connection(client: TestClient, h: dict[str, str], fints_id: str) -> dict[str, Any]:
    rows = _ok(client.get(f"{B}/connections", headers=h))
    row: dict[str, Any] = next(r for r in rows if r["id"] == fints_id)
    return row


def _connect_done(client: TestClient, h: dict[str, str]) -> str:
    created = _connect(client, h)
    _ok(client.post(f"{B}/sessions/{created['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))
    assert _session(client, h, created["id"])["status"] == "done"
    fints_id: str = created["fints_connection_id"]
    return fints_id


def test_connection_lists_effective_manual_and_list_address(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae26-admin"))
    fints_id = _connect_done(client, h)
    conn = _connection(client, h, fints_id)
    assert conn["fints_url_manual"] is None
    assert conn["fints_url_list"] == fints_mod.list_fints_url(BLZ)
    assert conn["fints_url"] == conn["fints_url_list"]
    assert fake.Scenario.constructed[-1]["url"] == conn["fints_url_list"]


def test_manual_address_needs_the_pin_and_a_valid_https_host(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae26-admin"))
    fints_id = _connect_done(client, h)
    path = f"{B}/connections/{fints_id}"
    # PIN is required together with an address
    r = client.patch(path, json={"fints_url": MANUAL}, headers=h)
    assert r.status_code == 422
    assert r.json()["code"] == "MHVP-CORE-0004"
    assert "PIN erneut eingegeben" in r.json()["detail"]
    for bad, reason in (
        ("http://fints.example.de/x", "https://"),
        ("https://127.0.0.1/x", "IP-Adresse"),
        ("https://intern.local/x", "öffentlichen Rechnernamen"),
        ("https://user:pw@fints.example.de/x", "Zugangsdaten"),
    ):
        r = client.patch(path, json={"fints_url": bad, "pin": fake.GOOD_PIN}, headers=h)
        assert r.status_code == 422, bad
        assert reason in r.json()["detail"], bad
    # the field is required: an empty body must not reset anything silently
    assert client.patch(path, json={}, headers=h).status_code == 422
    assert (
        client.patch(
            path, json={"fints_url": MANUAL, "pin": "x", "extra": 1}, headers=h
        ).status_code
        == 422
    )
    assert _connection(client, h, fints_id)["fints_url_manual"] is None


def test_manual_address_is_used_by_the_next_dialog_and_can_be_reset(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae26-admin"))
    fints_id = _connect_done(client, h)
    path = f"{B}/connections/{fints_id}"
    out = _ok(client.patch(path, json={"fints_url": MANUAL, "pin": fake.GOOD_PIN}, headers=h))
    assert out["fints_url_manual"] == MANUAL
    assert out["fints_url"] == MANUAL
    assert out["fints_url_list"] == fints_mod.list_fints_url(BLZ)
    assert out["pin_blocked"] is False
    # no dialog was started by the change
    assert out["open_session_id"] is None
    restarted = _ok(client.post(f"{path}/restart", json={}, headers=h), 201)
    assert fake.Scenario.constructed[-1]["url"] == MANUAL
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"
    # cannot change the address while a TAN session is open
    r = client.patch(path, json={"fints_url": None}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-BANK-0015"
    _ok(client.post(f"{B}/sessions/{restarted['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))
    # back to the institute list: no PIN needed
    out = _ok(client.patch(path, json={"fints_url": None}, headers=h))
    assert out["fints_url_manual"] is None
    assert out["fints_url"] == out["fints_url_list"]
    restarted = _ok(client.post(f"{path}/restart", json={}, headers=h), 201)
    assert fake.Scenario.constructed[-1]["url"] == out["fints_url_list"]
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"


def test_permissions_tenant_separation_and_disconnected(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae26-admin"))
    fints_id = _connect_done(client, h)
    path = f"{B}/connections/{fints_id}"
    body = {"fints_url": MANUAL, "pin": fake.GOOD_PIN}
    no_banking = bearer(login(client, world, "ae26-noaccounting"))
    assert client.patch(path, json=body, headers=no_banking).status_code == 403
    assert client.patch(path, json=body).status_code == 401
    other_tenant = bearer(login(client, world, "ae26-b-admin"))
    assert client.patch(path, json=body, headers=other_tenant).status_code == 404
    assert _connection(client, h, fints_id)["fints_url_manual"] is None
    assert client.delete(path, headers=h).status_code == 204
    r = client.patch(path, json=body, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-BANK-0015"


def test_locked_access_shows_german_check_steps_and_url_change_clears_the_block(
    client: TestClient, world: World
) -> None:
    """Operator finding 01.10.2026: the locked access came back as the English python-fints
    sentence. Now session, connection and API detail carry the German check steps; changing the
    address with a fresh PIN clears the block and the old error."""
    h = bearer(login(client, world, "ae26-admin"))
    fake.Scenario.lock_account = True
    created = _connect(client, h)
    session = _session(client, h, created["id"])
    assert session["status"] == "failed"
    assert session["error_code"] == "MHVP-BANK-0010"
    message = session["error_message"]
    assert "temporarily" not in message
    assert "Rückmeldecode 3938" in message
    assert "Online-Banking" in message
    assert "Anmeldename" in message
    assert "\n5. " in message
    fints_id = created["fints_connection_id"]
    conn = _connection(client, h, fints_id)
    assert conn["pin_blocked"] is True
    assert conn["last_error_code"] == "MHVP-BANK-0010"
    assert conn["last_error"] == message
    fake.Scenario.lock_account = False
    out = _ok(
        client.patch(
            f"{B}/connections/{fints_id}",
            json={"fints_url": MANUAL, "pin": fake.GOOD_PIN},
            headers=h,
        )
    )
    assert out["pin_blocked"] is False
    assert out["last_error"] is None
    assert out["last_error_code"] is None
    restarted = _ok(client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=h), 201)
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"


def test_unreachable_bank_names_the_host_and_keeps_the_pin(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae26-admin"))
    fake.Scenario.unreachable = True
    created = _connect(client, h)
    session = _session(client, h, created["id"])
    assert session["status"] == "failed"
    assert session["error_code"] == "MHVP-BANK-0013"
    host = fints_mod.fints_host(fints_mod.list_fints_url(BLZ))
    assert f"unter {host}" in session["error_message"]
    assert "Bankfusion" in session["error_message"]
    assert "FinTS-Adresse der Bank" in session["error_message"]
    conn = _connection(client, h, created["fints_connection_id"])
    assert conn["last_error_code"] == "MHVP-BANK-0013"
    # an unreachable server is no wrong PIN: the stored PIN stays usable
    assert conn["pin_blocked"] is False
    fake.Scenario.unreachable = False
    restarted = _ok(
        client.post(
            f"{B}/connections/{created['fints_connection_id']}/restart", json={}, headers=h
        ),
        201,
    )
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"
