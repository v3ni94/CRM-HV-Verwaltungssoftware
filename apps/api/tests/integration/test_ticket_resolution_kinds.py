"""Erledigungsarten je Mandant (Regel M19-07, Entscheidung M19-04 vom 26.09.2026):
``GET /tickets/resolution-kinds`` liefert die eingebauten Arten (mit den vier neuen) und die
eigenen Arten des Mandanten; ``PATCH /tenant/settings`` pflegt ``resolution_kinds``; ein
Abschluss mit deaktivierter oder fremder Art wird mit 422 abgewiesen; Mandanten sehen nur
ihre eigenen Arten."""

import asyncio
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
S = "/api/v1/tenant/settings"
K = "/api/v1/tickets/resolution-kinds"
NEW_KINDS = ("zahlung_geklaert", "termin_vereinbart", "mangel_behoben", "vertrag_geaendert")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rk-a-{RUN}", name=f"Arten A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rk-b-{RUN}", name=f"Arten B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("rkadmin", a), ("rkother", b)):
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
    return asyncio.run(_world(_settings(database, redis_url, ai_inline=True)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url, ai_inline=True)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ticket(c: TestClient, h: dict[str, str], title: str) -> dict[str, Any]:
    return cast(dict[str, Any], _ok(c.post(T, json={"title": title}, headers=h), 201))


def _close(c: TestClient, h: dict[str, str], ticket_id: str, kind: str) -> Any:
    return c.patch(
        f"{T}/{ticket_id}",
        json={"status": "done", "resolution": {"kind": kind, "note": "Test"}},
        headers=h,
    )


def _kinds(c: TestClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {k["code"]: k for k in _ok(c.get(K, headers=h))["kinds"]}


def test_default_list_contains_the_extended_builtin_kinds(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rkadmin"))
    kinds = _kinds(client, h)
    for code in NEW_KINDS:
        assert kinds[code]["builtin"] is True
        assert kinds[code]["active"] is True
    assert kinds["zahlung_geklaert"]["label"] == "Zahlung geklärt"
    assert kinds["sonstiges"]["active"] is True
    assert all(k["builtin"] for k in kinds.values())
    assert _ok(client.get(S, headers=h))["resolution_kinds"] == {"disabled": [], "custom": []}
    ticket = _ticket(client, h, f"Neue Art {RUN}")
    assert _ok(_close(client, h, ticket["id"], "termin_vereinbart"))["resolution_kind"] == (
        "termin_vereinbart"
    )


def test_tenant_configures_kinds_and_closing_validates_against_them(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "rkadmin"))
    config = {
        "disabled": ["weitergeleitet"],
        "custom": [{"code": "schluessel_uebergeben", "label": "Schlüssel übergeben"}],
    }
    saved = _ok(client.patch(S, json={"resolution_kinds": config}, headers=h))
    assert saved["resolution_kinds"] == config
    kinds = _kinds(client, h)
    assert kinds["weitergeleitet"]["active"] is False
    assert kinds["schluessel_uebergeben"] == {
        "code": "schluessel_uebergeben",
        "label": "Schlüssel übergeben",
        "builtin": False,
        "active": True,
    }

    own = _ticket(client, h, f"Eigene Art {RUN}")
    done = _ok(_close(client, h, own["id"], "schluessel_uebergeben"))
    assert done["resolution_kind"] == "schluessel_uebergeben"
    history = _ok(client.get(f"{T}/{own['id']}", headers=h))
    status_events = [e for e in history["events"] if e["kind"] == "status"]
    assert status_events[-1]["data"]["resolution"]["kind"] == "schluessel_uebergeben"

    disabled = _ticket(client, h, f"Deaktivierte Art {RUN}")
    refused = _close(client, h, disabled["id"], "weitergeleitet")
    assert refused.status_code == 422, refused.text
    assert "weitergeleitet" in refused.json()["detail"]
    assert _ok(client.get(f"{T}/{disabled['id']}", headers=h))["status"] == "new"

    unknown = _close(client, h, disabled["id"], "erfunden")
    assert unknown.status_code == 422, unknown.text
    assert _close(client, h, disabled["id"], "Keine Art!").status_code == 422

    # Bulk and merge validate the same way.
    bulk = _ok(
        client.post(
            f"{T}/bulk-status",
            json={
                "ticket_ids": [disabled["id"]],
                "status": "done",
                "resolution": {"kind": "weitergeleitet", "note": None},
            },
            headers=h,
        )
    )
    assert bulk["changed"] == []
    assert len(bulk["failed"]) == 1
    other = _ticket(client, h, f"Zusammenführen {RUN}")
    merge = client.post(
        f"{T}/merge",
        json={
            "ticket_ids": [disabled["id"], other["id"]],
            "resolution": {"kind": "weitergeleitet", "note": None},
        },
        headers=h,
    )
    assert merge.status_code == 422, merge.text


def test_protected_kinds_and_limits_are_enforced(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "rkadmin"))
    for bad in (
        {"disabled": ["sonstiges"]},
        {"disabled": ["zusammengefuehrt"]},
        {"disabled": ["erfunden"]},
        {"custom": [{"code": "sonstiges", "label": "Doppelt"}]},
        {"custom": [{"code": "a", "label": "Zu kurz"}]},
        {"custom": [{"code": "Nicht Slug", "label": "Falsch"}]},
        {"custom": [{"code": "x_1", "label": "Eins"}, {"code": "x_1", "label": "Zwei"}]},
        {"custom": [{"code": f"art_{i}", "label": f"Art {i}"} for i in range(31)]},
    ):
        response = client.patch(S, json={"resolution_kinds": bad}, headers=h)
        assert response.status_code == 422, (bad, response.text)
    many = {"custom": [{"code": f"art_{i}", "label": f"Art {i}"} for i in range(30)]}
    assert (
        len(
            _ok(client.patch(S, json={"resolution_kinds": many}, headers=h))["resolution_kinds"][
                "custom"
            ]
        )
        == 30
    )
    _ok(client.patch(S, json={"resolution_kinds": {"disabled": [], "custom": []}}, headers=h))


def test_kinds_are_separated_per_tenant(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "rkadmin"))
    hb = bearer(login(client, world, "rkother"))
    _ok(
        client.patch(
            S,
            json={
                "resolution_kinds": {
                    "disabled": ["abgelehnt"],
                    "custom": [{"code": "nur_a", "label": "Nur A"}],
                }
            },
            headers=ha,
        )
    )
    kinds_b = _kinds(client, hb)
    assert "nur_a" not in kinds_b
    assert kinds_b["abgelehnt"]["active"] is True
    ticket_b = _ticket(client, hb, f"Mandant B {RUN}")
    assert _close(client, hb, ticket_b["id"], "nur_a").status_code == 422
    assert _ok(_close(client, hb, ticket_b["id"], "abgelehnt"))["resolution_kind"] == "abgelehnt"
    ticket_a = _ticket(client, ha, f"Mandant A {RUN}")
    assert _ok(_close(client, ha, ticket_a["id"], "nur_a"))["resolution_kind"] == "nur_a"
    _ok(client.patch(S, json={"resolution_kinds": {"disabled": [], "custom": []}}, headers=ha))


def test_kinds_endpoint_requires_tickets_read(client: TestClient) -> None:
    assert client.get(K).status_code == 401
