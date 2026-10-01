"""M25-03 / V13: invitation period per tenant (latest dispatch date, short notice only with a
documented reason noted in the minutes, calendar entry "Einladung spätestens"), virtual form
locked without the tenant switch and without an enabling resolution with validity end,
dial-in data visible to owners of the community in the portal only, tenant separation.

Expected values by hand: meeting 10.12.2026, period 2 weeks -> latest dispatch 26.11.2026;
invitation recorded 30.11.2026 is short notice. Own world (slugs and e-mails differ from
test_m21_portal_owner so both modules can run in one session)."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

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
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m2503a-{RUN}", name=f"VV A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"m2503b-{RUN}", name=f"VV B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("m2503_admin", a), ("m2503_admin_b", b)):
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


@dataclass
class OwnerWorld:
    admin: dict[str, str]
    owner1: dict[str, str]
    tenant: dict[str, str]
    owner_b: dict[str, str]
    hoa: str


@pytest.fixture(scope="module")
def owner_world(client: TestClient, world: World) -> OwnerWorld:
    """Community with two owners and a final external resolution (basis for the virtual
    form), a tenant of a rental property (no owner role) and another tenant with its own
    community and owner."""
    c = client
    h = bearer(login(c, world, "m2503_admin"))
    weg, hoa = _weg(c, h, "871", "M25-03 WEG Versammlung")
    owner1_party, _ = _party(c, h, "V2503Eig01")
    owner2_party, _ = _party(c, h, "V2503Eig02")
    _ownership(c, h, _unit(c, h, weg["id"], "01"), owner1_party)
    _ownership(c, h, _unit(c, h, weg["id"], "02"), owner2_party)
    _ok(
        c.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2026-03-01",
                "subject": "Virtuelle Versammlungen",
                "wording": "Versammlungen können virtuell stattfinden.",
                "status": "final",
                "kind": "external",
            },
            headers=h,
        ),
        201,
    )
    rental = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "872", "name": "M25-03 Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, "V2503Vermieter", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant_party, _ = _party(c, h, "V2503Mieter")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": _unit(c, h, rental["id"], "A"),
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    hb = bearer(login(c, world, "m2503_admin_b"))
    weg_b, _ = _weg(c, hb, "881", "M25-03 Fremder Mandant")
    owner_b_party, _ = _party(c, hb, "V2503FremdEig")
    _ownership(c, hb, _unit(c, hb, weg_b["id"], "01"), owner_b_party)
    return OwnerWorld(
        admin=h,
        owner1=_portal_user(c, h, world, "m2503_owner1", _contact_of(c, h, owner1_party)),
        tenant=_portal_user(c, h, world, "m2503_tenant", _contact_of(c, h, tenant_party)),
        owner_b=_portal_user(c, hb, world, "m2503_owner_b", _contact_of(c, hb, owner_b_party)),
        hoa=hoa,
    )


def test_invitation_period_dial_in_portal_and_virtual_lock(
    client: TestClient, world: World, owner_world: OwnerWorld
) -> None:
    c, h, hoa = client, owner_world.admin, owner_world.hoa

    # Tenant setting: draft default 3 weeks, virtual form off.
    settings = _ok(c.get(f"{H}/meeting-settings", headers=h))
    assert settings == {"invitation_weeks": 3, "virtual_meetings_enabled": False} | {
        "virtual_basis_term_lock_enabled": False,  # GA07-01, default off
        "note": settings["note"],
    }
    assert (
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 0, "virtual_meetings_enabled": False},
            headers=h,
        ).status_code
        == 422
    )
    _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 2, "virtual_meetings_enabled": False},
            headers=h,
        )
    )

    # Hybrid meeting: latest dispatch date from the setting, dial-in data before the invitation.
    meeting = _ok(
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
    mid = meeting["id"]
    assert meeting["invitation_weeks"] == 2
    assert meeting["latest_invitation_at"] == "2026-11-26"
    assert meeting["has_dial_in"] is False
    _ok(c.post(f"{H}/meetings/{mid}/agenda", json={"title": "Dachsanierung"}, headers=h), 201)
    _ok(
        c.put(
            f"{H}/meetings/{mid}/dial-in",
            json={"dial_in_url": "https://meet.example.org/weg-851", "dial_in_access": "PIN 4711"},
            headers=h,
        )
    )

    # Calendar: "Einladung spätestens" on 26.11.2026 for the planned meeting, tenant B sees none.
    cal = _ok(
        c.get(f"{W}/calendar", params={"start": "2026-11-01", "end": "2026-11-30"}, headers=h)
    )
    entries = [i for i in cal["items"] if i["kind"] == "hoa_invitation_deadline"]
    assert [i["date"] for i in entries if i["entity_id"] == mid] == ["2026-11-26"]
    assert entries[0]["title"].startswith("Einladung spätestens")
    hb = bearer(login(c, world, "m2503_admin_b"))
    cal_b = _ok(
        c.get(f"{W}/calendar", params={"start": "2026-11-01", "end": "2026-11-30"}, headers=hb)
    )
    assert not [i for i in cal_b["items"] if i["kind"] == "hoa_invitation_deadline"]

    # Portal: nothing before the invitation (planned meetings are internal).
    owner_before = _ok(c.get(f"{P}/meetings", headers=owner_world.owner1))
    assert mid not in {m["id"] for m in owner_before}

    # Short notice: refused without reason, recorded with reason, noted for the minutes.
    late = c.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-11-30"}, headers=h)
    assert late.status_code == 422, late.text
    assert "26.11.2026" in late.json()["detail"]
    invited = _ok(
        c.post(
            f"{H}/meetings/{mid}/invite",
            json={"invited_at": "2026-11-30", "urgency_reason": "Rohrbruch, Sanierung eilt"},
            headers=h,
        )
    )
    assert invited["short_notice"] is True
    assert invited["latest_invitation_at"] == "2026-11-26"
    detail = _ok(c.get(f"{H}/meetings/{mid}", headers=h))
    assert detail["invitation_short_notice"] is True
    assert "Rohrbruch" in detail["short_notice_note"]
    assert "26.11.2026" in detail["short_notice_note"]
    assert "hybride Versammlung" in detail["invitation_notice"]
    assert "PIN" not in detail["invitation_notice"]

    # Attendance channels: owner 1 online, owner 2 absent.
    members = _ok(c.get(f"{H}/meetings/{mid}/members", headers=h))
    first = members[0]["contract_id"]
    _ok(
        c.post(
            f"{H}/meetings/{mid}/attendance",
            json={"contract_id": first, "present": True, "online": True},
            headers=h,
        ),
        201,
    )
    att = _ok(c.get(f"{H}/meetings/{mid}/attendance-list", headers=h))
    channels = {r["contract_id"]: r["channel"] for r in att["rows"]}
    assert channels[first] == "online"
    assert att["counts"]["online"] == 1
    assert att["counts"]["absent"] == len(members) - 1
    assert {
        r["contract_id"]: r["channel"] for r in _ok(c.get(f"{H}/meetings/{mid}/members", headers=h))
    }[first] == "online"

    # Portal: owner of the community sees the dial-in data, tenant 403, other tenant nothing.
    rows = {m["id"]: m for m in _ok(c.get(f"{P}/meetings", headers=owner_world.owner1))}
    assert rows[mid]["dial_in_url"] == "https://meet.example.org/weg-851"
    assert rows[mid]["dial_in_access"] == "PIN 4711"
    assert rows[mid]["mode"] == "hybrid"
    assert rows[mid]["notice"]
    assert c.get(f"{P}/meetings", headers=owner_world.tenant).status_code == 403
    assert mid not in {m["id"] for m in _ok(c.get(f"{P}/meetings", headers=owner_world.owner_b))}
    # Staff token is no portal account.
    assert c.get(f"{P}/meetings", headers=h).status_code in (401, 403)

    # Virtual form: tenant switch off -> 403, then enabling resolution with validity end.
    base = {"legal_entity_id": hoa, "scheduled_at": "2027-03-04T18:00:00+01:00", "mode": "virtual"}
    resolutions = _ok(c.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    basis = next(r["id"] for r in resolutions if r["status"] in ("positive", "final"))
    locked = c.post(
        f"{H}/meetings",
        json=base
        | {"virtual_basis_resolution_id": basis, "virtual_basis_valid_until": "2029-01-01"},
        headers=h,
    )
    assert locked.status_code == 403, locked.text
    assert locked.json()["code"] == "MHVP-HOA-0003"
    _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 2, "virtual_meetings_enabled": True},
            headers=h,
        )
    )
    for body in (
        base,
        base | {"virtual_basis_resolution_id": basis},
        base | {"virtual_basis_resolution_id": basis, "virtual_basis_valid_until": "2027-03-03"},
    ):
        refused = c.post(f"{H}/meetings", json=body, headers=h)
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "MHVP-HOA-0004"
    # A presence meeting never carries a basis.
    assert (
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2027-03-04T18:00:00+01:00",
                "virtual_basis_valid_until": "2029-01-01",
            },
            headers=h,
        ).status_code
        == 422
    )
    virtual = _ok(
        c.post(
            f"{H}/meetings",
            json=base
            | {"virtual_basis_resolution_id": basis, "virtual_basis_valid_until": "2029-01-01"},
            headers=h,
        ),
        201,
    )
    assert virtual["mode"] == "virtual"
    assert virtual["virtual_basis_valid_until"] == "2029-01-01"
    vdetail = _ok(c.get(f"{H}/meetings/{virtual['id']}", headers=h))
    assert vdetail["virtual_basis"]["id"] == basis
    assert "gültig bis 01.01.2029" in vdetail["invitation_notice"]

    # Dial-in data are refused for a presence meeting.
    presence = _ok(
        c.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2027-05-04T18:00:00+02:00"},
            headers=h,
        ),
        201,
    )
    assert (
        c.put(
            f"{H}/meetings/{presence['id']}/dial-in",
            json={"dial_in_url": "https://meet.example.org/x"},
            headers=h,
        ).status_code
        == 422
    )

    # Reset the tenant switch (default off) for the other tests of this module set.
    _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 3, "virtual_meetings_enabled": False},
            headers=h,
        )
    )
