"""AO09 (AN05 rest): portal address proposal and contact merge close addresses as history."""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.clock import local_today
from mhvp.main import create_app
from mhvp.platform import services as platform
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
C = "/api/v1/contacts"
S = "/api/v1/contact-address-history"
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
M = "/api/v1/contact-merges"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform.provision_tenant(factory, slug=f"ao9a-{RUN}", name=f"AO09 {RUN}")
        b, _ = await platform.provision_tenant(factory, slug=f"ao9b-{RUN}", name=f"AO09B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name in ("one", "two"):
            uid = await platform.create_user(
                factory, email=world.email(f"ao9{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"ao9{name}"] = uid
            await platform.add_member(
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _contact(c: TestClient, h: dict[str, str], last: str, *cities: str) -> dict[str, Any]:
    body = {
        "kind": "person",
        "first_name": "Max",
        "last_name": last,
        "addresses": [
            {"street": "Weg", "house_number": "1", "city": x, "is_primary": i == 0}
            for i, x in enumerate(cities)
        ],
    }
    return dict(_ok(c.post(C, json=body, headers=h), 201))


def _history(c: TestClient, h: dict[str, str], cid: str) -> list[dict[str, Any]]:
    return list(_ok(c.get(f"{C}/{cid}/addresses?include_history=true", headers=h))["items"])


def _portal_change(c: TestClient, h: dict[str, str], world: World, last: str) -> str:
    contact = _contact(c, h, last, "Hilden")
    invite = _ok(
        c.post(
            f"{PA}/accounts",
            json={
                "contact_id": contact["id"],
                "email": world.email(f"ao9p{last}"),
                "display_name": last,
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{P}/invitations/accept",
            json={"token": invite["invitation_token"], "password": PASSWORD},
        )
    )
    portal = bearer(login(c, world, f"ao9p{last}"))
    payload = {
        "street": "Neue Straße",
        "house_number": "5",
        "postal_code": "40213",
        "city": "Düsseldorf",
        "valid_from": local_today().isoformat(),
    }
    proposal = _ok(
        c.post(
            f"{P}/change-requests", json={"kind": "address", "payload": payload}, headers=portal
        ),
        201,
    )
    _ok(c.post(f"{PA}/change-requests/{proposal['id']}/decide", json={"accept": True}, headers=h))
    return str(contact["id"])


def test_portal_proposal_switch_on_closes_old_address(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao9one"))
    _ok(client.put(S, json={"enabled": True}, headers=h))
    try:
        cid = _portal_change(client, h, world, f"On{RUN}")
        rows = {a["city"]: a for a in _history(client, h, cid)}
        current = _ok(client.get(f"{C}/{cid}/addresses", headers=h))["items"]
    finally:
        _ok(client.put(S, json={"enabled": False}, headers=h))
    assert rows["Düsseldorf"]["is_primary"] is True
    assert rows["Düsseldorf"]["valid_to"] is None
    old = rows["Hilden"]
    assert old["is_primary"] is False
    assert old["superseded_at"] is not None
    # No valid_from before: it is the creation date, valid_to is the day before the new start.
    assert old["valid_from"] == local_today().isoformat()
    assert old["valid_to"] == local_today().isoformat()  # never before valid_from (CHECK)
    assert [a["city"] for a in current] == ["Düsseldorf"]


def test_portal_proposal_switch_off_keeps_old_row_current(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao9one"))
    _ok(client.put(S, json={"enabled": False}, headers=h))
    cid = _portal_change(client, h, world, f"Off{RUN}")
    rows = _ok(client.get(f"{C}/{cid}", headers=h))["addresses"]
    old = next(a for a in rows if a["city"] == "Hilden")
    assert old["is_primary"] is False
    assert old["valid_to"] is None
    assert old["superseded_at"] is None


def _merge(c: TestClient, world: World, src: str, dst: str) -> dict[str, Any]:
    one = bearer(login(c, world, "ao9one"))
    two = bearer(login(c, world, "ao9two"))
    proposal = _ok(c.post(M, json={"source_id": src, "target_id": dst}, headers=one), 201)
    return dict(_ok(c.post(f"{M}/{proposal['id']}/execute", json={}, headers=two)))


def test_merge_switch_on_closes_demoted_primary(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao9one"))
    src = _contact(client, h, f"MQ{RUN}", "Hilden")
    dst = _contact(client, h, f"MZ{RUN}", "Mettmann")
    _ok(client.put(S, json={"enabled": True}, headers=h))
    try:
        done = _merge(client, world, src["id"], dst["id"])
        rows = {a["city"]: a for a in _history(client, h, dst["id"])}
    finally:
        _ok(client.put(S, json={"enabled": False}, headers=h))
    assert len(done["result"]["closed_address_ids"]) == 1
    assert len(done["result"]["valid_from_backfilled_ids"]) == 1
    assert rows["Mettmann"]["is_primary"] is True
    assert rows["Mettmann"]["superseded_at"] is None
    assert rows["Hilden"]["superseded_at"] is not None
    assert rows["Hilden"]["valid_to"] == (local_today() - timedelta(days=1)).isoformat() or (
        rows["Hilden"]["valid_to"] == rows["Hilden"]["valid_from"]
    )


def test_merge_switch_off_unchanged(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao9one"))
    src = _contact(client, h, f"NQ{RUN}", "Hilden")
    dst = _contact(client, h, f"NZ{RUN}", "Mettmann")
    done = _merge(client, world, src["id"], dst["id"])
    assert "closed_address_ids" not in done["result"]
    rows = _ok(client.get(f"{C}/{dst['id']}", headers=h))["addresses"]
    assert sorted(a["city"] for a in rows) == ["Hilden", "Mettmann"]
    assert all(a["superseded_at"] is None for a in rows)
