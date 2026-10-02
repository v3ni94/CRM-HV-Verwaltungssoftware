"""AG07 / GAF-32: circular resolution in the owner portal (switch off by default, G4 for the
vote).

Expected values by hand: community with units 01 (owner 1) and 02 (owner 2). Circular
procedure with one item "Fassadenanstrich" / proposal "Anstrich 2027". Switch off: list shows
enabled false, vote 403 MHVP-HOA-0037, nothing stored. Switch on but G4 closed: 403, nothing
stored. G4 open: owner 1 votes yes for 01 (201, hash = sha256("Fassadenanstrich\\nAnstrich
2027")), second vote for 01 is 409, vote for 02 by owner 1 is 403, foreign tenant owner sees
nothing and gets 404. CRM reads one portal vote. Own world (prefix 7-ag07, RUN)."""

import asyncio
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal_owner import (
    _contact_of,
    _ok,
    _ownership,
    _portal_user,
    _weg,
)

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"
HASH = hashlib.sha256(b"Fassadenanstrich\nAnstrich 2027").hexdigest()


class OpenG4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G4


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"7-ag07a-{RUN}", name=f"AG07A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"7-ag07b-{RUN}", name=f"AG07B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ag07_admin", a, "tenant_admin"),
            ("ag07_reader", a, "read_only"),
            ("ag07_admin_b", b, "tenant_admin"),
        ):
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
        ):
            yield closed, open_


@dataclass
class W:
    admin: dict[str, str]
    reader: dict[str, str]
    o1: dict[str, str]
    ob: dict[str, str]
    hoa: str
    u1: str
    u2: str


@pytest.fixture(scope="module")
def w(clients: tuple[TestClient, TestClient], world: World) -> W:
    c, _ = clients
    h = bearer(login(c, world, "ag07_admin"))
    weg, hoa = _weg(c, h, "971", "AG07 WEG Umlauf")
    parties = [_party(c, h, f"AG07Eig0{n}")[0] for n in (1, 2)]
    units = [
        _ownership(c, h, _unit(c, h, weg["id"], f"0{n}"), p)["id"]
        for n, p in zip((1, 2), parties, strict=True)
    ]
    hb = bearer(login(c, world, "ag07_admin_b"))
    weg_b, _ = _weg(c, hb, "972", "AG07 Fremd")
    pb, _ = _party(c, hb, "AG07FremdEig")
    _ownership(c, hb, _unit(c, hb, weg_b["id"], "01"), pb)
    return W(
        admin=h,
        reader=bearer(login(c, world, "ag07_reader")),
        o1=_portal_user(c, h, world, "ag07_o1", _contact_of(c, h, parties[0])),
        ob=_portal_user(c, hb, world, "ag07_ob", _contact_of(c, hb, pb)),
        hoa=hoa,
        u1=units[0],
        u2=units[1],
    )


def test_portal_circular_flow(clients: tuple[TestClient, TestClient], w: W) -> None:
    closed, c = clients
    h = w.admin
    m = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": w.hoa,
                "kind": "circular_resolution",
                "scheduled_at": "2026-12-10T18:00:00+01:00",
            },
            headers=h,
        ),
        201,
    )
    mid = m["id"]
    item = _ok(
        c.post(
            f"{H}/meetings/{mid}/agenda",
            json={"title": "Fassadenanstrich", "proposal": "Anstrich 2027"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(c.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-11-01"}, headers=h))
    vote = {"agenda_item_id": item, "contract_id": w.u1, "choice": "yes"}

    # Switch default off.
    assert _ok(c.get(f"{H}/portal-circular-settings", headers=h))["enabled"] is False
    listing = _ok(c.get(f"{P}/circular-resolutions", headers=w.o1))
    assert listing == listing | {"enabled": False, "circulars": []}
    off = c.post(f"{P}/circular-resolutions/{mid}/vote", json=vote, headers=w.o1)
    assert off.status_code == 403, off.text
    assert off.json()["code"] == "MHVP-HOA-0037"
    # Reader may not switch, body 422, unknown query 422.
    put = f"{H}/portal-circular-settings"
    assert c.put(put, json={"enabled": True}, headers=w.reader).status_code == 403
    assert c.put(put, json={}, headers=h).status_code == 422
    assert c.get(f"{P}/circular-resolutions?x=1", headers=w.o1).status_code == 422
    _ok(c.put(put, json={"enabled": True}, headers=h))

    # G4 closed: 403, nothing stored.
    shut = closed.post(f"{P}/circular-resolutions/{mid}/vote", json=vote, headers=w.o1)
    assert shut.status_code == 403, shut.text
    assert _ok(c.get(f"{H}/meetings/{mid}/portal-circular-votes", headers=h)) == []

    listing = _ok(c.get(f"{P}/circular-resolutions", headers=w.o1))
    [circ] = listing["circulars"]
    assert circ["own_contract_ids"] == [w.u1]
    assert circ["items"][0]["wording_sha256"] == HASH
    assert circ["items"][0]["open"] is True

    bad = c.post(f"{P}/circular-resolutions/{mid}/vote", json=vote | {"choice": "x"}, headers=w.o1)
    assert bad.status_code == 422
    done = _ok(c.post(f"{P}/circular-resolutions/{mid}/vote", json=vote, headers=w.o1), 201)
    assert done["wording_sha256"] == HASH
    assert done["portal_user_id"]
    assert done["cast_at"]
    again = c.post(f"{P}/circular-resolutions/{mid}/vote", json=vote, headers=w.o1)
    assert again.status_code == 409
    other = c.post(
        f"{P}/circular-resolutions/{mid}/vote", json=vote | {"contract_id": w.u2}, headers=w.o1
    )
    assert other.status_code == 403

    # Foreign tenant owner: nothing visible; the vote is refused (switch of tenant B off: 403).
    assert _ok(c.get(f"{P}/circular-resolutions", headers=w.ob))["circulars"] == []
    foreign = c.post(f"{P}/circular-resolutions/{mid}/vote", json=vote, headers=w.ob)
    assert foreign.status_code in (403, 404)

    # CRM read: one portal vote with evidence, also by community.
    [crm] = _ok(c.get(f"{H}/meetings/{mid}/portal-circular-votes", headers=w.reader))
    assert crm["choice"] == "yes"
    assert crm["wording_sha256"] == HASH
    rows = _ok(c.get(f"{H}/portal-circular-votes?legal_entity_id={w.hoa}", headers=h))
    assert [r["item_title"] for r in rows] == ["Fassadenanstrich"]
    listing = _ok(c.get(f"{P}/circular-resolutions", headers=w.o1))
    assert listing["circulars"][0]["items"][0]["own_votes"][0]["choice"] == "yes"
