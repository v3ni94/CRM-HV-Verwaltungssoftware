"""R07-01: closing of the owners' meeting minutes with four eyes. Expected by hand: the
first person requests the closing with the signed minutes (status closing, meeting locked),
the same person cannot confirm (409), a second person confirms with the same document
(status closed, event meeting.closed); votes, announcements and changes answer 409 afterwards.
No statutory minutes period is computed; the response carries a hint text only."""

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

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cl25-{RUN}", name=f"Abschluss {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cm25-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("cl25admin", a, "tenant_admin"),
            ("cl25reader", a, "read_only"),
            ("cl25second", a, "tenant_admin"),
            ("cl25other", b, "tenant_admin"),
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


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def test_r07_01_close_four_eyes_lock_and_event(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cl25admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "753", "name": "WEG Abschluss", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party_a, _ = _party(client, h, "Abschluss")
    unit = _unit(client, h, prop["id"], "01")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party_a,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )["id"]
    mid = _ok(
        client.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"},
            headers=h,
        ),
        201,
    )["id"]
    item = _ok(
        client.post(f"{H}/meetings/{mid}/agenda", json={"title": "Wirtschaftsplan"}, headers=h),
        201,
    )
    minutes = _doc(client, h, "protokoll.pdf")
    # not yet held: no closing
    close = {"minutes_document_id": minutes}
    assert client.post(f"{H}/meetings/{mid}/close", json=close, headers=h).status_code == 409
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-05-29"}, headers=h))
    _ok(
        client.post(
            f"{H}/meetings/{mid}/attendance",
            json={"contract_id": contract, "present": True},
            headers=h,
        ),
        201,
    )
    # validation: document mandatory and existing
    assert client.post(f"{H}/meetings/{mid}/close", json={}, headers=h).status_code == 422
    missing = {"minutes_document_id": "00000000-0000-7000-8000-000000000000"}
    assert client.post(f"{H}/meetings/{mid}/close", json=missing, headers=h).status_code == 422
    # Review W79: a document linked only to another community is refused.
    neighbour = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "756", "name": "WEG Nachbar", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    foreign = _doc(client, h, "fremd.pdf")
    _ok(
        client.post(
            f"/api/v1/documents/{foreign}/links",
            json={"entity_type": "property", "entity_id": neighbour["id"]},
            headers=h,
        ),
        201,
    )
    refused = client.post(
        f"{H}/meetings/{mid}/close", json={"minutes_document_id": foreign}, headers=h
    )
    assert refused.status_code == 422, refused.text
    assert "anderen Gemeinschaft" in refused.json()["detail"]
    # read only 403, foreign tenant 404
    reader = bearer(login(client, world, "cl25reader"))
    assert client.post(f"{H}/meetings/{mid}/close", json=close, headers=reader).status_code == 403
    other = bearer(login(client, world, "cl25other"))
    assert client.post(f"{H}/meetings/{mid}/close", json=close, headers=other).status_code == 404

    requested = _ok(client.post(f"{H}/meetings/{mid}/close", json=close, headers=h))
    assert requested["status"] == "closing"
    assert requested["minutes_document_id"] == minutes
    assert "Protokollfrist" in requested["note"]
    # locked while closing
    vote = {"contract_id": contract, "choice": "yes"}
    assert client.post(f"{H}/agenda/{item['id']}/votes", json=vote, headers=h).status_code == 409
    assert client.post(f"{H}/meetings/{mid}/close", json=close, headers=h).status_code == 409
    # same person cannot confirm
    assert (
        client.post(f"{H}/meetings/{mid}/close/confirm", json=close, headers=h).status_code == 409
    )
    second = bearer(login(client, world, "cl25second"))
    other_doc = {"minutes_document_id": _doc(client, h, "anderes.pdf")}
    assert (
        client.post(f"{H}/meetings/{mid}/close/confirm", json=other_doc, headers=second).status_code
        == 409
    )
    assert (
        client.post(f"{H}/meetings/{mid}/close/confirm", json=close, headers=other).status_code
        == 404
    )
    closed = _ok(client.post(f"{H}/meetings/{mid}/close/confirm", json=close, headers=second))
    assert closed["status"] == "closed"
    assert closed["closed_by"] == str(world.users["cl25second"])
    assert closed["close_requested_by"] == str(world.users["cl25admin"])

    # after closing: no change of agenda, votes, announcement, deadline or withdrawal
    assert client.post(f"{H}/agenda/{item['id']}/votes", json=vote, headers=h).status_code == 409
    announce = {"outcome": "positive", "majority_basis": "einfache Mehrheit"}
    assert (
        client.post(f"{H}/agenda/{item['id']}/announce", json=announce, headers=h).status_code
        == 409
    )
    assert (
        client.post(f"{H}/meetings/{mid}/agenda", json={"title": "Neu"}, headers=h).status_code
        == 409
    )
    assert (
        client.patch(
            f"{H}/meetings/{mid}", json={"resolution_deadline_at": None}, headers=h
        ).status_code
        == 409
    )
    assert client.post(f"{H}/meetings/{mid}/close/withdraw", headers=h).status_code == 409
    detail = _ok(client.get(f"{H}/meetings/{mid}", headers=h))
    assert detail["status"] == "closed"


def test_r07_01_withdraw_reopens_meeting(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cl25admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "754", "name": "WEG Rueckzug", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party_a, _ = _party(client, h, "Rueckzug")
    unit = _unit(client, h, prop["id"], "01")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party_a,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )["id"]
    mid = _ok(
        client.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(client.post(f"{H}/meetings/{mid}/agenda", json={"title": "TOP"}, headers=h), 201)
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-05-29"}, headers=h))
    _ok(
        client.post(
            f"{H}/meetings/{mid}/attendance",
            json={"contract_id": contract, "present": True},
            headers=h,
        ),
        201,
    )
    close = {"minutes_document_id": _doc(client, h, "p.pdf")}
    _ok(client.post(f"{H}/meetings/{mid}/close", json=close, headers=h))
    back = _ok(client.post(f"{H}/meetings/{mid}/close/withdraw", headers=h))
    assert back["status"] == "held"
    assert back["minutes_document_id"] is None
    assert back["close_requested_by"] is None
