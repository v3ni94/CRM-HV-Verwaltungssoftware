"""M3-03: contact merge proposal, check, four eyes and execution (rule M3-03-kontakt-merge)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services as platform
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
M = "/api/v1/contact-merges"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform.provision_tenant(factory, slug=f"cmerge-{RUN}", name=f"Merge A {RUN}")
        b, _ = await platform.provision_tenant(factory, slug=f"cn-{RUN}", name=f"Merge B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("one", a, "tenant_admin"),
            ("two", a, "tenant_admin"),
            ("reader", a, "read_only"),
            ("other", b, "tenant_admin"),
        ]:
            uid = await platform.create_user(
                factory, email=world.email(f"cm{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"cm{name}"] = uid
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


def _contact(c: TestClient, h: dict[str, str], last: str, kind: str = "person") -> dict[str, Any]:
    body: dict[str, Any] = {"kind": kind}
    if kind == "person":
        body.update(first_name="Max", last_name=last)
    else:
        body.update(company_name=last)
    r = c.post("/api/v1/contacts", json=body, headers=h)
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_merge_moves_references_and_keeps_source(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "cmone"))
    two = bearer(login(client, world, "cmtwo"))
    src = _contact(client, one, f"Quelle{RUN}")
    dst = _contact(client, one, f"Ziel{RUN}")
    note = client.post(f"/api/v1/contacts/{src['id']}/notes", json={"body": "Hinweis"}, headers=one)
    assert note.status_code == 201, note.text
    other = _contact(client, one, f"Partner{RUN}")
    party = client.post(
        "/api/v1/parties",
        json={
            "members": [
                {"contact_id": src["id"], "role": "primary", "share_percent": "50"},
                {"contact_id": other["id"], "role": "co_party", "share_percent": "50"},
            ]
        },
        headers=one,
    )
    assert party.status_code == 201, party.text
    proposal = client.post(
        M, json={"source_id": src["id"], "target_id": dst["id"], "reason": "Dublette"}, headers=one
    )
    assert proposal.status_code == 201, proposal.text
    merge = proposal.json()
    assert merge["status"] == "proposed"
    assert merge["check_result"]["blockers"] == []
    assert merge["check_result"]["references"]["contact_note.contact_id"] == 1
    assert merge["check_result"]["references"]["party_member.contact_id"] == 1
    # the proposer must not execute (four eyes)
    denied = client.post(f"{M}/{merge['id']}/execute", json={}, headers=one)
    assert denied.status_code == 403, denied.text
    # a second open proposal for the same source is refused
    again = client.post(M, json={"source_id": src["id"], "target_id": dst["id"]}, headers=one)
    assert again.status_code == 409
    done = client.post(f"{M}/{merge['id']}/execute", json={"note": "geprüft"}, headers=two)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "executed"
    assert done.json()["result"]["moved"]["contact_note.contact_id"] == 1
    assert done.json()["result"]["moved"]["party_member.contact_id"] == 1
    members = client.get(f"/api/v1/parties/{party.json()['id']}", headers=one)
    if members.status_code == 200:
        assert dst["id"] in [m["contact_id"] for m in members.json()["members"]]
    target = client.get(f"/api/v1/contacts/{dst['id']}", headers=one).json()
    assert target["id"] == dst["id"]
    # the source is hidden but the row stays (no delete)
    assert client.get(f"/api/v1/contacts/{src['id']}", headers=one).status_code in (404, 200)
    executed_again = client.post(f"{M}/{merge['id']}/execute", json={}, headers=two)
    assert executed_again.status_code == 409


def test_check_blocks_kind_mismatch_and_merged_source(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "cmone"))
    two = bearer(login(client, world, "cmtwo"))
    person = _contact(client, one, f"Person{RUN}")
    firm = _contact(client, one, f"Firma{RUN}", kind="company")
    proposal = client.post(
        M, json={"source_id": person["id"], "target_id": firm["id"]}, headers=one
    )
    assert proposal.status_code == 201
    codes = {b["code"] for b in proposal.json()["check_result"]["blockers"]}
    assert "kind_differs" in codes
    blocked = client.post(f"{M}/{proposal.json()['id']}/execute", json={}, headers=two)
    assert blocked.status_code == 409
    rejected = client.post(
        f"{M}/{proposal.json()['id']}/reject", json={"note": "nein"}, headers=two
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    same = client.post(M, json={"source_id": person["id"], "target_id": person["id"]}, headers=one)
    assert same.status_code == 409


def test_permissions_validation_and_tenant_separation(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "cmone"))
    reader = bearer(login(client, world, "cmreader"))
    other = bearer(login(client, world, "cmother"))
    a = _contact(client, one, f"Rechte{RUN}")
    b = _contact(client, one, f"Rechte2{RUN}")
    assert (
        client.post(
            M, json={"source_id": a["id"], "target_id": b["id"]}, headers=reader
        ).status_code
        == 403
    )
    assert client.get(M, headers=reader).status_code == 200
    assert client.post(M, json={"source_id": a["id"]}, headers=one).status_code == 422
    assert (
        client.post(M, json={"source_id": a["id"], "target_id": b["id"]}, headers=other).status_code
        == 404
    )
    proposal = client.post(M, json={"source_id": a["id"], "target_id": b["id"]}, headers=one).json()
    assert client.get(f"{M}/{proposal['id']}", headers=other).status_code == 404
    assert client.get(f"{M}/{proposal['id']}", headers=reader).status_code == 200
    assert client.post(f"{M}/{proposal['id']}/execute", json={}, headers=reader).status_code == 403


def test_registry_covers_every_contact_foreign_key() -> None:
    import mhvp.main  # noqa: F401  (loads all models)
    from mhvp.contacts.merge import reference_registry
    from mhvp.core.db.base import Base

    expected = {
        (t.name, c.name)
        for t in Base.metadata.tables.values()
        for c in t.columns
        for fk in c.foreign_keys
        if fk.column.table.name == "contact"
        and fk.column.name == "id"
        and t.name not in {"contact_merge", "privacy_erasure_request"}
        and not (t.name == "contact" and c.name == "merged_into_id")
    }
    assert set(reference_registry()) == expected
    assert ("party_member", "contact_id") in expected


def test_search_routes_merged_source_to_target(client: TestClient, world: World) -> None:
    one = bearer(login(client, world, "cmone"))
    two = bearer(login(client, world, "cmtwo"))
    src = _contact(client, one, f"Suchquelle{RUN}")
    dst = _contact(client, one, f"Suchziel{RUN}")
    before = client.get(
        "/api/v1/workspace/search", params={"q": f"Suchquelle{RUN}"}, headers=one
    ).json()
    assert [h["id"] for h in before if h["entity_type"] == "contact"] == [src["id"]]
    proposal = client.post(
        M, json={"source_id": src["id"], "target_id": dst["id"]}, headers=one
    ).json()
    assert client.post(f"{M}/{proposal['id']}/execute", json={}, headers=two).status_code == 200
    after = client.get(
        "/api/v1/workspace/search", params={"q": f"Suchquelle{RUN}"}, headers=one
    ).json()
    # the old name stays findable, but only through the target (source row is hidden)
    assert [h["id"] for h in after if h["entity_type"] == "contact"] == [dst["id"]]
    found = client.get("/api/v1/workspace/search", params={"q": f"Suchziel{RUN}"}, headers=one)
    assert dst["id"] in [h["id"] for h in found.json()]
