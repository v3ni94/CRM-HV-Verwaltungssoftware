"""AD06 / GA11-03: online meeting in the owner portal (switch off by default, G4 for proxy
and vote).

Expected values by hand: community with units 01 (owner 1), 02 (owner 2), 03 (owner 3, no
portal account). Owner 3 grants owner 1 a proxy (period 01.01.2026 to 31.12.2027) and owner 1
votes for 01 and 03; owner 2 votes for 02. A second vote for 03 is 409, voting before the
opening and after the closing is 409. Results are hidden until the announcement. Own world
(prefix ad06, RUN)."""

import asyncio
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
        a, _ = await services.provision_tenant(factory, slug=f"ad06a-{RUN}", name=f"AD06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ad06b-{RUN}", name=f"AD06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ad06_admin", a, "tenant_admin"),
            ("ad06_reader", a, "read_only"),
            ("ad06_admin_b", b, "tenant_admin"),
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
    admin_b: dict[str, str]
    o1: dict[str, str]
    o2: dict[str, str]
    o3: dict[str, str]
    ob: dict[str, str]
    hoa: str
    hoa_b: str
    u1: str
    u2: str
    u3: str


@pytest.fixture(scope="module")
def w(clients: tuple[TestClient, TestClient], world: World) -> W:
    c, _ = clients
    h = bearer(login(c, world, "ad06_admin"))
    weg, hoa = _weg(c, h, "961", "AD06 WEG Online")
    parties = [_party(c, h, f"AD06Eig0{n}")[0] for n in (1, 2, 3)]
    units = [
        _ownership(c, h, _unit(c, h, weg["id"], f"0{n}"), p)["id"]
        for n, p in zip((1, 2, 3), parties, strict=True)
    ]
    hb = bearer(login(c, world, "ad06_admin_b"))
    weg_b, hoa_b = _weg(c, hb, "962", "AD06 Fremd")
    pb, _ = _party(c, hb, "AD06FremdEig")
    _ownership(c, hb, _unit(c, hb, weg_b["id"], "01"), pb)
    owners = [
        _portal_user(c, h, world, f"ad06_o{n}", _contact_of(c, h, p))
        for n, p in zip((1, 2, 3), parties, strict=True)
    ]
    return W(
        admin=h,
        reader=bearer(login(c, world, "ad06_reader")),
        admin_b=hb,
        o1=owners[0],
        o2=owners[1],
        o3=owners[2],
        ob=_portal_user(c, hb, world, "ad06_ob", _contact_of(c, hb, pb)),
        hoa=hoa,
        hoa_b=hoa_b,
        u1=units[0],
        u2=units[1],
        u3=units[2],
    )


def _meeting(c: TestClient, h: dict[str, str], hoa: str) -> tuple[str, list[str]]:
    m = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2026-12-10T18:00:00+01:00",
                "mode": "hybrid",
            },
            headers=h,
        ),
        201,
    )
    items = [
        _ok(c.post(f"{H}/meetings/{m['id']}/agenda", json={"title": t}, headers=h), 201)["id"]
        for t in ("Dachsanierung", "Hausordnung")
    ]
    _ok(
        c.put(
            f"{H}/meetings/{m['id']}/dial-in",
            json={"dial_in_url": "https://meet.example.org/ad06", "dial_in_access": "PIN 0606"},
            headers=h,
        )
    )
    _ok(
        c.post(
            f"{H}/meetings/{m['id']}/invite",
            json={"invited_at": "2026-11-01"},
            headers=h,
        )
    )
    return m["id"], items


def test_online_meeting_flow(clients: tuple[TestClient, TestClient], w: W) -> None:
    closed, c = clients
    h = w.admin
    mid, (top1, top2) = _meeting(c, h, w.hoa)

    # Switch default off: portal steps 403 MHVP-HOA-0031, CRM opening too.
    assert _ok(c.get(f"{H}/online-meeting-settings", headers=h))["enabled"] is False
    off = c.post(f"{P}/meetings/{mid}/participation", json={}, headers=w.o1)
    assert off.status_code == 403, off.text
    assert off.json()["code"] == "MHVP-HOA-0031"
    assert c.post(f"{H}/meetings/{mid}/agenda/{top1}/voting/open", headers=h).status_code == 403
    detail = _ok(c.get(f"{P}/meetings/{mid}", headers=w.o1))
    assert detail["online_enabled"] is False
    assert detail["conference_url"] is None
    # Reader may not switch it on, invalid body 422.
    assert (
        c.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=w.reader).status_code
        == 403
    )
    assert c.put(f"{H}/online-meeting-settings", json={}, headers=h).status_code == 422
    _ok(c.put(f"{H}/online-meeting-settings", json={"enabled": True}, headers=h))

    # Invitation detail: conference link, agenda without results.
    detail = _ok(c.get(f"{P}/meetings/{mid}", headers=w.o1))
    assert detail["conference_url"] == "https://meet.example.org/ad06"
    assert detail["own_contract_ids"] == [w.u1]
    assert [(u["unit_number"], u["own"]) for u in detail["units"]] == [
        ("01", True),
        ("02", False),
        ("03", False),
    ]
    assert [i["voting_state"] for i in detail["items"]] == ["not_opened", "not_opened"]
    # Tenant separation and roles: other tenant's owner 404, staff token no portal account.
    assert c.get(f"{P}/meetings/{mid}", headers=w.ob).status_code == 404
    assert c.get(f"{P}/meetings/{mid}", headers=h).status_code in (401, 403)
    assert c.get(f"{H}/meetings/{mid}/online", headers=w.admin_b).status_code == 404

    # Participation: owner 1 and owner 2 confirm online, foreign unit 422.
    assert (
        c.post(
            f"{P}/meetings/{mid}/participation", json={"contract_ids": [w.u2]}, headers=w.o1
        ).status_code
        == 422
    )
    _ok(c.post(f"{P}/meetings/{mid}/participation", json={}, headers=w.o1), 201)
    _ok(c.post(f"{P}/meetings/{mid}/participation", json={}, headers=w.o2), 201)

    # Proxy: owner 3 to owner 1. Gate G4 closed -> 403; document must be own upload.
    doc3 = _ok(
        c.post(
            f"{P}/uploads",
            files={"file": ("vollmacht.pdf", b"%PDF-1.4 vollmacht", "application/pdf")},
            headers=w.o3,
        ),
        201,
    )["id"]
    doc1 = _ok(
        c.post(
            f"{P}/uploads",
            files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")},
            headers=w.o1,
        ),
        201,
    )["id"]
    base = {
        "grantor_contract_id": w.u3,
        "proxy_kind": "owner",
        "proxy_contract_id": w.u1,
        "valid_from": "2026-01-01",
        "valid_to": "2027-12-31",
        "document_id": doc3,
    }
    gated = closed.post(f"{P}/meeting-proxies", json=base, headers=w.o3)
    assert gated.status_code == 403, gated.text
    assert gated.json()["code"] != "MHVP-HOA-0031"
    # Limits: foreign document 404, own unit as target 422, manager with unit 422,
    # period end before start 422, grantor not own 404.
    assert (
        c.post(f"{P}/meeting-proxies", json=base | {"document_id": doc1}, headers=w.o3).status_code
        == 404
    )
    assert (
        c.post(
            f"{P}/meeting-proxies", json=base | {"proxy_contract_id": w.u3}, headers=w.o3
        ).status_code
        == 422
    )
    assert (
        c.post(
            f"{P}/meeting-proxies", json=base | {"proxy_kind": "manager"}, headers=w.o3
        ).status_code
        == 422
    )
    assert (
        c.post(
            f"{P}/meeting-proxies", json=base | {"valid_to": "2025-01-01"}, headers=w.o3
        ).status_code
        == 422
    )
    assert c.post(f"{P}/meeting-proxies", json=base, headers=w.o2).status_code == 404
    proxy = _ok(c.post(f"{P}/meeting-proxies", json=base, headers=w.o3), 201)
    assert proxy["active"] is True
    received = _ok(c.get(f"{P}/meeting-proxies", headers=w.o1))["items"]
    assert [(p["id"], p["direction"]) for p in received] == [(proxy["id"], "received")]
    # A second, revoked proxy of owner 2 to the manager stays as evidence.
    doc2 = _ok(
        c.post(
            f"{P}/uploads",
            files={"file": ("v2.pdf", b"%PDF-1.4 v2", "application/pdf")},
            headers=w.o2,
        ),
        201,
    )["id"]
    mgr = _ok(
        c.post(
            f"{P}/meeting-proxies",
            json={
                "grantor_contract_id": w.u2,
                "proxy_kind": "manager",
                "valid_from": "2026-01-01",
                "document_id": doc2,
            },
            headers=w.o2,
        ),
        201,
    )
    assert c.post(f"{P}/meeting-proxies/{mgr['id']}/revoke", headers=w.o1).status_code == 404
    assert _ok(c.post(f"{P}/meeting-proxies/{mgr['id']}/revoke", headers=w.o2))["active"] is False
    assert c.post(f"{P}/meeting-proxies/{mgr['id']}/revoke", headers=w.o2).status_code == 409

    # Speaker request: list with time stamp, handled in the CRM.
    sr = _ok(
        c.post(
            f"{P}/meetings/{mid}/speaker-requests",
            json={"agenda_item_id": top1, "note": "Frage zum Angebot"},
            headers=w.o1,
        ),
        201,
    )
    assert c.post(f"{P}/meetings/{mid}/speaker-requests", json={}, headers=w.o1).status_code == 409

    # Voting: not opened 409, G4 closed 403, then open.
    vote = {"contract_id": w.u1, "choice": "yes"}
    assert (
        c.post(f"{P}/meetings/{mid}/agenda/{top1}/votes", json=vote, headers=w.o1).status_code
        == 409
    )
    assert (
        closed.post(f"{P}/meetings/{mid}/agenda/{top1}/votes", json=vote, headers=w.o1).status_code
        == 403
    )
    assert (
        c.post(f"{H}/meetings/{mid}/agenda/{top1}/voting/open", headers=w.reader).status_code == 403
    )
    _ok(c.post(f"{H}/meetings/{mid}/agenda/{top1}/voting/open", headers=h))
    assert c.post(f"{H}/meetings/{mid}/agenda/{top1}/voting/open", headers=h).status_code == 409
    assert (
        c.post(
            f"{P}/meetings/{mid}/agenda/{top1}/votes",
            json={"contract_id": w.u1, "choice": "maybe"},
            headers=w.o1,
        ).status_code
        == 422
    )
    assert (
        _ok(c.post(f"{P}/meetings/{mid}/agenda/{top1}/votes", json=vote, headers=w.o1), 201)[
            "channel"
        ]
        == "online"
    )
    by_proxy = _ok(
        c.post(
            f"{P}/meetings/{mid}/agenda/{top1}/votes",
            json={"contract_id": w.u3, "choice": "yes"},
            headers=w.o1,
        ),
        201,
    )
    assert by_proxy["proxy_id"] == proxy["id"]
    # Double vote of a unit 409 (also by the grantor himself), unit without proxy 403.
    assert (
        c.post(f"{P}/meetings/{mid}/agenda/{top1}/votes", json=vote, headers=w.o1).status_code
        == 409
    )
    o3_vote = c.post(
        f"{P}/meetings/{mid}/agenda/{top1}/votes",
        json={"contract_id": w.u3, "choice": "no"},
        headers=w.o3,
    )
    assert o3_vote.status_code == 409, o3_vote.text  # owner 3 confirmed nothing
    assert (
        c.post(
            f"{P}/meetings/{mid}/agenda/{top1}/votes",
            json={"contract_id": w.u2, "choice": "no"},
            headers=w.o1,
        ).status_code
        == 403
    )
    _ok(
        c.post(
            f"{P}/meetings/{mid}/agenda/{top1}/votes",
            json={"contract_id": w.u2, "choice": "no"},
            headers=w.o2,
        ),
        201,
    )
    # No result before the announcement, only the own vote markers.
    detail = _ok(c.get(f"{P}/meetings/{mid}", headers=w.o1))
    first = detail["items"][0]
    assert first["voting_state"] == "open"
    assert first["result"] is None
    assert sorted(first["voted_contract_ids"]) == sorted([w.u1, w.u3])
    assert detail["represented_contract_ids"] == [w.u3]

    # Close: votes refused 409 (closed item), TOP 2 never opened.
    _ok(c.post(f"{H}/meetings/{mid}/agenda/{top1}/voting/close", headers=h))
    assert (
        c.post(
            f"{P}/meetings/{mid}/agenda/{top1}/votes",
            json={"contract_id": w.u2, "choice": "yes"},
            headers=w.o2,
        ).status_code
        == 409
    )
    overview = _ok(c.get(f"{H}/meetings/{mid}/online", headers=w.reader))
    assert {r["contract_id"] for r in overview["confirmations"]} == {w.u1, w.u2}
    assert [i["online_votes"] for i in overview["items"]] == [3, 0]
    assert [i["voting_state"] for i in overview["items"]] == ["closed", "not_opened"]
    assert [(r["id"], r["status"]) for r in overview["speaker_requests"]] == [(sr["id"], "open")]
    assert {p["id"]: p["active"] for p in overview["proxies"]} == {
        proxy["id"]: True,
        mgr["id"]: False,
    }
    # Tally from the existing CRM path counts the online channel.
    tally = _ok(c.get(f"{H}/agenda/{top1}/tally", headers=h))
    assert tally["channels"] == {"online": 3}
    assert (tally["yes"], tally["no"]) == ("2", "1")

    # Speaker request handled once.
    assert (
        c.post(
            f"{H}/meetings/{mid}/speaker-requests/{sr['id']}",
            json={"status": "done"},
            headers=w.reader,
        ).status_code
        == 403
    )
    _ok(
        c.post(
            f"{H}/meetings/{mid}/speaker-requests/{sr['id']}", json={"status": "done"}, headers=h
        )
    )
    assert (
        c.post(
            f"{H}/meetings/{mid}/speaker-requests/{sr['id']}", json={"status": "done"}, headers=h
        ).status_code
        == 409
    )

    # Announcement makes the result visible in the portal.
    _ok(
        c.post(
            f"{H}/agenda/{top1}/announce",
            json={"outcome": "positive", "majority_basis": "Einfache Mehrheit, Vorschlag"},
            headers=h,
        ),
        201,
    )
    first = _ok(c.get(f"{P}/meetings/{mid}", headers=w.o1))["items"][0]
    assert first["voting_state"] == "announced"
    assert first["result"] is not None

    # Revoked proxy: no further votes for the unit on another item.
    _ok(c.post(f"{P}/meeting-proxies/{proxy['id']}/revoke", headers=w.o3))
    _ok(c.post(f"{H}/meetings/{mid}/agenda/{top2}/voting/open", headers=h))
    assert (
        c.post(
            f"{P}/meetings/{mid}/agenda/{top2}/votes",
            json={"contract_id": w.u3, "choice": "yes"},
            headers=w.o1,
        ).status_code
        == 403
    )

    # Reset the switch (default off).
    _ok(c.put(f"{H}/online-meeting-settings", json={"enabled": False}, headers=h))
