"""GA02-02 (6.2 notice_board_post): category, type, audiences as a list (including provider),
several attachments and read confirmation per notice with read quota in the CRM."""

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
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_notices import _d, _notice, _titles
from tests.integration.test_m21_portal import _contact_of, _doc, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
VIS = {"tenant", "owner", "provider"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"gb-{RUN}", name=f"Brett {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"gc-{RUN}", name=f"Brett2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("gbadmin", a), ("gbother", b)):
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _owner_setup(
    client: TestClient, h: dict[str, str], world: World
) -> tuple[dict[str, Any], dict[str, str]]:
    weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "831", "name": "Brett-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(client, h, "BrettEig")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": _unit(client, h, weg["id"], "01"),
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    owner = _portal_user(client, h, world, "brettowner", _contact_of(client, h, party))
    return weg, owner


def test_notice_board_fields_audiences_attachments_and_reads(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "gbadmin"))
    weg, owner = _owner_setup(client, h, world)
    prop = weg["id"]

    # Validation: type, audiences, category from the catalogue, document visibility.
    url = f"/api/v1/properties/{prop}/notices"
    base = {"title": "x", "body": "y", "valid_from": _d(0)}
    assert client.post(url, json={**base, "type": "fatal"}, headers=h).status_code == 422
    assert client.post(url, json={**base, "audiences": []}, headers=h).status_code == 422
    assert client.post(url, json={**base, "audiences": ["staff"]}, headers=h).status_code == 422
    assert client.post(url, json={**base, "category": "gibtesnicht"}, headers=h).status_code == 422

    # Two attachments visible for owners; an owner-only document does not fit a provider notice.
    a1 = _doc(client, h, "Hausordnung", "property", prop, ["owner"])
    a2 = _doc(client, h, "Reinigungsplan", "property", prop, ["owner"])
    rows = _notice(
        client,
        h,
        prop,
        "Warnung Aufzug",
        type="warning",
        category="wartung_und_service",
        audiences=["owner"],
        document_ids=[a1, a2],
    )
    assert rows["type"] == "warning"
    assert rows["category"] == "wartung_und_service"
    assert rows["audiences"] == ["owner"]
    assert rows["audience"] == "owner"
    assert rows["document_ids"] == [a1, a2]
    assert rows["read_count"] == 0
    assert rows["recipient_count"] == 1
    bad = client.post(
        url,
        json={**base, "audiences": ["owner", "provider"], "document_ids": [a1]},
        headers=h,
    )
    assert bad.status_code == 422

    # Provider only notice is not shown to the owner; a legacy audience value still works.
    _notice(client, h, prop, "Nur Dienstleister", audiences=["provider"])
    legacy = _notice(client, h, prop, "Legacy alle", audience="all")
    assert legacy["audiences"] == ["tenant", "owner"]
    assert legacy["audience"] == "all"
    assert _titles(client, owner) == ["Legacy alle", "Warnung Aufzug"]

    # Portal list carries level, category, documents and the read state; reading writes nothing.
    portal = {n["title"]: n for n in _ok(client.get(f"{P}/notices", headers=owner))}
    n = portal["Warnung Aufzug"]
    assert n["type"] == "warning"
    assert n["read"] is False
    assert n["read_at"] is None
    assert [d["filename"] for d in n["documents"]] == ["Hausordnung.txt", "Reinigungsplan.txt"]
    assert client.get(f"/api/v1/notices/{rows['id']}/reads", headers=h).json()["read_count"] == 0

    # Both attachments can be downloaded, a foreign document id answers 404.
    for d in n["documents"]:
        assert (
            client.get(f"{P}/notices/{n['id']}/documents/{d['id']}", headers=owner).status_code
            == 200
        )
    other = _doc(client, h, "Fremd", "property", prop, ["owner"])
    assert client.get(f"{P}/notices/{n['id']}/documents/{other}", headers=owner).status_code == 404

    # Read confirmation: idempotent, visible notices only, shown in the CRM.
    r1 = _ok(client.post(f"{P}/notices/{n['id']}/read", headers=owner))
    r2 = _ok(client.post(f"{P}/notices/{n['id']}/read", headers=owner))
    assert r1["read"] is True
    assert r1["read_at"] == r2["read_at"]
    hidden = next(
        x
        for x in _ok(client.get(f"/api/v1/properties/{prop}/notices", headers=h))
        if x["title"] == "Nur Dienstleister"
    )
    assert client.post(f"{P}/notices/{hidden['id']}/read", headers=owner).status_code == 404
    reads = _ok(client.get(f"/api/v1/notices/{rows['id']}/reads", headers=h))
    assert reads["read_count"] == 1
    assert reads["recipient_count"] == 1
    assert len(reads["reads"]) == 1
    portal = {x["title"]: x for x in _ok(client.get(f"{P}/notices", headers=owner))}
    assert portal["Warnung Aufzug"]["read"] is True

    # Patch: several attachments, type and category, clear category.
    patched = _ok(
        client.patch(
            f"/api/v1/notices/{rows['id']}",
            json={"type": "danger", "clear_category": True, "document_ids": [a1]},
            headers=h,
        )
    )
    assert patched["type"] == "danger"
    assert patched["category"] is None
    assert patched["document_ids"] == [a1]
    widened = client.patch(
        f"/api/v1/notices/{rows['id']}", json={"audiences": ["owner", "provider"]}, headers=h
    )
    assert widened.status_code == 422


def test_notice_board_reads_are_tenant_isolated_and_need_permission(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "gbadmin"))
    other = bearer(login(client, world, "gbother"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "832", "name": "Brett-Fremd", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )["id"]
    notice = _notice(client, h, prop, "Isoliert")
    assert client.get(f"/api/v1/notices/{notice['id']}/reads", headers=other).status_code == 404
    assert client.get(f"/api/v1/notices/{notice['id']}/reads").status_code == 401
    # A CRM account is no portal account: the read confirmation is refused.
    assert client.post(f"{P}/notices/{notice['id']}/read", headers=h).status_code == 403
