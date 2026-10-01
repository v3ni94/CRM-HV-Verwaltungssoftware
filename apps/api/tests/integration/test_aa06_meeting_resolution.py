"""AA06 (GA03-01 to GA03-04, GA07-01): meeting kinds with origin meeting, end, templates and
descriptions; agenda item result, minutes text, item voting principle and the rule all_owners;
vote channel; Beschluss-Sammlung with location, court notes, entered_at and the statuses
deleted and irrelevant; three year term of the enabling resolution of virtual meetings
(notice by default, lock only behind the tenant switch). Tenant separation and permissions.

Expected values by hand: two owners (head principle). Owner 01 votes yes online, owner 02 is
absent: simple majority would pass (1 > 0), all_owners fails (1 of 2 owners) -> negative.
Enabling resolution of 01.03.2026: latest validity end 01.03.2029; 02.03.2029 exceeds it."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m25_meeting import _hoa_with_owners

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa06a-{RUN}", name=f"AA06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa06b-{RUN}", name=f"AA06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("aa06_admin", a, "tenant_admin"),
            ("aa06_reader", a, "read_only"),
            ("aa06_admin_b", b, "tenant_admin"),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _resolution(c: TestClient, h: dict[str, str], hoa: str, **extra: Any) -> dict[str, Any]:
    body = {
        "legal_entity_id": hoa,
        "decided_on": "2026-03-01",
        "subject": "Virtuelle Versammlungen",
        "wording": "Versammlungen können virtuell stattfinden.",
        "status": "final",
        "kind": "external",
    } | extra
    return _ok(c.post(f"{H}/resolutions", json=body, headers=h), 201)  # type: ignore[no-any-return]


def test_meeting_kinds_details_and_portal_fields(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "aa06_admin"))
    _, hoa, _, _ = _hoa_with_owners(c, h, "861")
    base = {"legal_entity_id": hoa, "scheduled_at": "2026-11-10T18:00:00+01:00"}
    origin = _ok(c.post(f"{H}/meetings", json=base, headers=h), 201)
    # repeat without origin, with later origin, end before start: 422
    for body in (
        base | {"kind": "repeat", "scheduled_at": "2026-12-10T18:00:00+01:00"},
        base | {"kind": "repeat", "origin_meeting_id": origin["id"]},
        base | {"kind": "ordinary", "origin_meeting_id": origin["id"]},
        base | {"ends_at": "2026-11-10T17:00:00+01:00"},
        base | {"invitation_template_id": "0190a000-0000-7000-8000-000000000001"},
        base | {"kind": "special"},
    ):
        assert c.post(f"{H}/meetings", json=body, headers=h).status_code == 422, body
    repeat = _ok(
        c.post(
            f"{H}/meetings",
            json=base
            | {
                "kind": "repeat",
                "scheduled_at": "2026-12-10T18:00:00+01:00",
                "ends_at": "2026-12-10T20:00:00+01:00",
                "origin_meeting_id": origin["id"],
                "public_description": "Wiederholung mangels Beschlussfähigkeit.",
                "internal_description": "Intern: Beirat vorab informieren.",
            },
            headers=h,
        ),
        201,
    )
    assert repeat["kind"] == "repeat"
    assert repeat["origin_meeting_id"] == origin["id"]
    assert repeat["internal_description"].startswith("Intern")
    for kind in ("continuation", "partial", "circular_resolution"):
        body = base | {"kind": kind, "scheduled_at": "2027-01-10T18:00:00+01:00"}
        if kind == "continuation":
            body["origin_meeting_id"] = origin["id"]
        assert _ok(c.post(f"{H}/meetings", json=body, headers=h), 201)["kind"] == kind
    patched = _ok(
        c.patch(
            f"{H}/meetings/{origin['id']}",
            json={"public_description": "Ordentliche Versammlung 2026"},
            headers=h,
        )
    )
    assert patched["public_description"] == "Ordentliche Versammlung 2026"
    bad = c.patch(
        f"{H}/meetings/{origin['id']}",
        json={"ends_at": "2026-11-10T10:00:00+01:00"},
        headers=h,
    )
    assert bad.status_code == 422
    # Tenant separation and permissions
    hb = bearer(login(c, world, "aa06_admin_b"))
    assert c.get(f"{H}/meetings/{repeat['id']}", headers=hb).status_code == 404
    assert (
        c.patch(
            f"{H}/meetings/{repeat['id']}", json={"public_description": "x"}, headers=hb
        ).status_code
        == 404
    )
    hr = bearer(login(c, world, "aa06_reader"))
    assert (
        c.patch(
            f"{H}/meetings/{repeat['id']}", json={"public_description": "x"}, headers=hr
        ).status_code
        == 403
    )


def test_agenda_result_all_owners_and_vote_channel(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "aa06_admin"))
    _, hoa, contracts, _ = _hoa_with_owners(c, h, "862")
    meeting = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "mode": "hybrid",
                "scheduled_at": "2026-11-12T18:00:00+01:00",
            },
            headers=h,
        ),
        201,
    )
    mid = meeting["id"]
    # item principle mea without basis: 422
    refused = c.post(
        f"{H}/meetings/{mid}/agenda",
        json={"title": "Dachsanierung", "voting_principle": "mea"},
        headers=h,
    )
    assert refused.status_code == 422
    all_owners = _ok(
        c.post(
            f"{H}/meetings/{mid}/agenda",
            json={
                "title": "Bauliche Veränderung",
                "proposal": "Zustimmung aller Eigentümer.",
                "majority": "all_owners",
                "voting_principle": "unit",
                "voting_principle_basis": "Gemeinschaftsordnung § 5",
            },
            headers=h,
        ),
        201,
    )
    assert all_owners["voting_principle"] == "unit"
    deferred = _ok(
        c.post(f"{H}/meetings/{mid}/agenda", json={"title": "Fassadenfarbe"}, headers=h), 201
    )
    _ok(c.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-10-15"}, headers=h))
    _ok(
        c.post(
            f"{H}/meetings/{mid}/attendance",
            json={"contract_id": contracts["01"], "present": True, "online": True},
            headers=h,
        ),
        201,
    )
    vote = _ok(
        c.post(
            f"{H}/agenda/{all_owners['id']}/votes",
            json={"contract_id": contracts["01"], "choice": "yes"},
            headers=h,
        ),
        201,
    )
    assert vote["channel"] == "online"
    # channel presence cannot be given, circular only in a circular procedure
    for channel in ("presence", "circular"):
        r = c.post(
            f"{H}/agenda/{deferred['id']}/votes",
            json={"contract_id": contracts["01"], "choice": "yes", "channel": channel},
            headers=h,
        )
        assert r.status_code == 422, channel
    tally = _ok(c.get(f"{H}/agenda/{all_owners['id']}/tally", headers=h))
    assert tally["principle"] == "unit"
    assert tally["checks"]["all_owners"] == {"passed": False, "members": 2, "yes": 1}
    assert tally["proposal"] == "negative"
    assert tally["channels"] == {"online": 1}
    wrong = {"outcome": "positive", "majority_basis": "Zustimmung aller Eigentümer"}
    assert (
        c.post(f"{H}/agenda/{all_owners['id']}/announce", json=wrong, headers=h).status_code == 409
    )
    announced = _ok(
        c.post(
            f"{H}/agenda/{all_owners['id']}/announce",
            json=wrong | {"outcome": "negative"},
            headers=h,
        ),
        201,
    )
    # deferred item: result and minutes text; no votes or announcement afterwards
    hr = bearer(login(c, world, "aa06_reader"))
    assert (
        c.patch(f"{H}/agenda/{deferred['id']}", json={"result": "deferred"}, headers=hr).status_code
        == 403
    )
    for body in ({"result": "accepted"}, {"result": "unknown"}):
        assert c.patch(f"{H}/agenda/{deferred['id']}", json=body, headers=h).status_code == 422
    patched = _ok(
        c.patch(
            f"{H}/agenda/{deferred['id']}",
            json={"result": "deferred", "minutes_text": "Vertagt auf die nächste Versammlung."},
            headers=h,
        )
    )
    assert patched["result"] == "deferred"
    blocked = c.post(
        f"{H}/agenda/{deferred['id']}/votes",
        json={"contract_id": contracts["01"], "choice": "yes"},
        headers=h,
    )
    assert blocked.status_code == 409
    # an announced item keeps its result
    assert (
        c.patch(f"{H}/agenda/{all_owners['id']}", json={"result": "no_vote"}, headers=h).status_code
        == 409
    )
    detail = _ok(c.get(f"{H}/meetings/{mid}", headers=h))
    results = {i["id"]: i["result"] for i in detail["agenda"]}
    assert results == {all_owners["id"]: "rejected", deferred["id"]: "deferred"}
    members = _ok(c.get(f"{H}/meetings/{mid}/members", headers=h))
    first = next(m for m in members if m["contract_id"] == contracts["01"])
    assert first["vote_channels"] == {all_owners["id"]: "online"}
    hb = bearer(login(c, world, "aa06_admin_b"))
    assert (
        c.patch(f"{H}/agenda/{deferred['id']}", json={"minutes_text": "x"}, headers=hb).status_code
        == 404
    )
    rows = _ok(c.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    rows = rows["items"] if isinstance(rows, dict) else rows
    row = next(r for r in rows if r["id"] == announced["id"])
    assert row["entered_at"] is not None


def test_circular_procedure_votes_have_channel_circular(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "aa06_admin"))
    _, hoa, contracts, _ = _hoa_with_owners(c, h, "863")
    meeting = _ok(
        c.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "kind": "circular_resolution",
                "scheduled_at": "2026-11-20T12:00:00+01:00",
            },
            headers=h,
        ),
        201,
    )
    item = _ok(
        c.post(f"{H}/meetings/{meeting['id']}/agenda", json={"title": "Umlauf"}, headers=h), 201
    )
    _ok(
        c.post(f"{H}/meetings/{meeting['id']}/invite", json={"invited_at": "2026-10-20"}, headers=h)
    )
    vote = _ok(
        c.post(
            f"{H}/agenda/{item['id']}/votes",
            json={"contract_id": contracts["02"], "choice": "yes", "channel": "circular"},
            headers=h,
        ),
        201,
    )
    assert vote["channel"] == "circular"


def test_resolution_collection_fields_and_statuses(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "aa06_admin"))
    _, hoa, _, _ = _hoa_with_owners(c, h, "864")
    res = _resolution(c, h, hoa, location="Gemeindesaal", status="positive")
    for status in ("deleted", "irrelevant", "void"):
        _ok(c.patch(f"{H}/resolutions/{res['id']}", json={"status": status}, headers=h))
    assert (
        c.patch(f"{H}/resolutions/{res['id']}", json={"status": "gone"}, headers=h).status_code
        == 422
    )
    assert c.patch(f"{H}/resolutions/{res['id']}", json={}, headers=h).status_code == 422
    noted = _ok(
        c.patch(
            f"{H}/resolutions/{res['id']}",
            json={"court_notes": "Anfechtungsklage eingegangen am 01.04.2026."},
            headers=h,
        )
    )
    assert noted["status"] == "void"
    assert noted["court_notes"].startswith("Anfechtungsklage")
    rows = _ok(c.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    rows = rows["items"] if isinstance(rows, dict) else rows
    row = next(r for r in rows if r["id"] == res["id"])
    assert row["location"] == "Gemeindesaal"
    assert row["entered_at"] is not None
    hr = bearer(login(c, world, "aa06_reader"))
    assert (
        c.patch(f"{H}/resolutions/{res['id']}", json={"status": "final"}, headers=hr).status_code
        == 403
    )
    hb = bearer(login(c, world, "aa06_admin_b"))
    assert (
        c.patch(f"{H}/resolutions/{res['id']}", json={"status": "final"}, headers=hb).status_code
        == 404
    )


def test_virtual_basis_three_year_term_notice_and_lock(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "aa06_admin"))
    _, hoa, _, _ = _hoa_with_owners(c, h, "865")
    basis = _resolution(c, h, hoa)
    _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 3, "virtual_meetings_enabled": True},
            headers=h,
        )
    )
    body = {
        "legal_entity_id": hoa,
        "mode": "virtual",
        "scheduled_at": "2026-12-01T18:00:00+01:00",
        "virtual_basis_resolution_id": basis["id"],
    }
    ok = _ok(
        c.post(f"{H}/meetings", json=body | {"virtual_basis_valid_until": "2029-03-01"}, headers=h),
        201,
    )
    assert ok["virtual_basis_term_notice"] is None
    long = body | {"virtual_basis_valid_until": "2029-03-02"}
    noticed = _ok(c.post(f"{H}/meetings", json=long, headers=h), 201)
    assert "01.03.2029" in noticed["virtual_basis_term_notice"]
    settings = _ok(
        c.put(
            f"{H}/meeting-settings",
            json={
                "invitation_weeks": 3,
                "virtual_meetings_enabled": True,
                "virtual_basis_term_lock_enabled": True,
            },
            headers=h,
        )
    )
    assert settings["virtual_basis_term_lock_enabled"] is True
    # omitted keeps the stored value
    kept = _ok(
        c.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 3, "virtual_meetings_enabled": True},
            headers=h,
        )
    )
    assert kept["virtual_basis_term_lock_enabled"] is True
    locked = c.post(f"{H}/meetings", json=long, headers=h)
    assert locked.status_code == 422
    assert locked.json()["code"] == "MHVP-HOA-0030"
    _ok(
        c.post(f"{H}/meetings", json=body | {"virtual_basis_valid_until": "2029-03-01"}, headers=h),
        201,
    )
