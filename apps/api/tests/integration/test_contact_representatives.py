"""Authorised representatives with delivery rule (operator decision 26.09.2026): relation
endpoints with audit, recipient resolution in mail dispatch, serial letters and WEG invitation
recipients for each delivery mode, tenant separation."""

import asyncio
import io
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import BUCKET, COMPANY, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rp-a-{RUN}", name=f"Rep A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rp-b-{RUN}", name=f"Rep B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("repadmin", a), ("repother", b)):
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _person(
    c: TestClient, h: dict[str, str], first: str, last: str, **extra: Any
) -> dict[str, Any]:
    body = {
        "kind": "person",
        "first_name": first,
        "last_name": f"{last}{RUN}",
        "addresses": [
            {
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            }
        ],
        **extra,
    }
    return _ok(c.post("/api/v1/contacts", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _dispatch_targets(c: TestClient, h: dict[str, str], doc: str, contact: str) -> set[str]:
    res = _ok(
        c.post(
            "/api/v1/dispatches/serial",
            json={"items": [{"document_id": doc, "contact_id": contact}]},
            headers=h,
        ),
        201,
    )
    return {d["contact_id"] for rows in res["by_channel"].values() for d in rows}


def _set_mode(c: TestClient, h: dict[str, str], owner: str, relation: str, mode: str) -> None:
    out = _ok(
        c.patch(
            f"/api/v1/contacts/{owner}/contact-relations/{relation}",
            json={"delivery_mode": mode, "fields": ["delivery_mode"]},
            headers=h,
        )
    )
    assert out["delivery_mode"] == mode


def test_representative_delivery_modes(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "repadmin"))
    owner = _person(client, h, "Timo", "Eigner", salutation="Herr")
    rep = _person(
        client,
        h,
        "Jan",
        "Vertreter",
        preferred_channel="email",
        emails=[{"email": f"jan{RUN}@example.com"}],
    )

    # Relation endpoints: default rule both, validation, listing in both directions.
    wrong = client.post(
        f"/api/v1/contacts/{owner['id']}/relations",
        json={"related_contact_id": rep["id"], "kind": "spouse", "delivery_mode": "owner_only"},
        headers=h,
    )
    assert wrong.status_code == 422
    relation = _ok(
        client.post(
            f"/api/v1/contacts/{owner['id']}/relations",
            json={"related_contact_id": rep["id"], "kind": "representative"},
            headers=h,
        ),
        201,
    )
    assert relation["delivery_mode"] == "both"
    assert relation["related_display_name"] == rep["display_name"]
    outgoing = _ok(client.get(f"/api/v1/contacts/{owner['id']}/contact-relations", headers=h))
    assert [(r["direction"], r["related_contact_id"]) for r in outgoing] == [
        ("outgoing", rep["id"])
    ]
    incoming = _ok(client.get(f"/api/v1/contacts/{rep['id']}/contact-relations", headers=h))
    assert [(r["direction"], r["related_contact_id"]) for r in incoming] == [
        ("incoming", owner["id"])
    ]

    # Mail and post dispatch: both, representative only, owner only.
    doc = _ok(
        client.post(
            "/api/v1/documents",
            data={"title": "Rundschreiben"},
            files={"file": ("rund.txt", b"Rundschreiben", "text/plain")},
            headers=h,
        ),
        201,
    )["id"]
    assert _dispatch_targets(client, h, doc, owner["id"]) == {owner["id"], rep["id"]}
    _set_mode(client, h, owner["id"], relation["id"], "representative_only")
    assert _dispatch_targets(client, h, doc, owner["id"]) == {rep["id"]}
    _set_mode(client, h, owner["id"], relation["id"], "owner_only")
    assert _dispatch_targets(client, h, doc, owner["id"]) == {owner["id"]}
    audit = _ok(client.get(f"/api/v1/tenant/audit-log?entity_id={owner['id']}", headers=h))
    updates = [e for e in audit if "delivery_mode" in (e["changes"] or {})]
    assert len(updates) == 2
    assert updates[0]["changes"]["delivery_mode"] == {
        "old": "representative_only",
        "new": "owner_only",
    }

    # Serial letters on the letterhead: both gives two letters, the representative's letter
    # names the represented contact and is linked to both contacts.
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    free = next(
        t
        for t in _ok(client.get("/api/v1/document-templates", headers=h))
        if t["code"] == "free_letter"
    )
    letter = {
        "template_id": free["id"],
        "contact_ids": [owner["id"]],
        "fields": {"betreff": "Ablesetermin", "text": "Der Ablesetermin ist am 01.10.2026."},
    }
    _set_mode(client, h, owner["id"], relation["id"], "both")
    serial = _ok(client.post("/api/v1/letters/serial", json=letter, headers=h), 201)
    assert len(serial["documents"]) == 2
    rep_doc = next(
        d
        for d in serial["documents"]
        if {x["entity_id"] for x in d["links"]} == {owner["id"], rep["id"]}
    )
    pdf = client.get(f"/api/v1/documents/{rep_doc['id']}/content", headers=h)
    assert pdf.status_code == 200
    text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert f"für {owner['display_name']}" in text
    _set_mode(client, h, owner["id"], relation["id"], "representative_only")
    only_rep = _ok(client.post("/api/v1/letters/serial", json=letter, headers=h), 201)
    assert [{x["entity_id"] for x in d["links"]} for d in only_rep["documents"]] == [
        {owner["id"], rep["id"]}
    ]

    # WEG invitation recipients per ownership contract.
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "917", "name": "WEG Vertreter", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h),
        201,
    )["id"]
    unit = _unit(client, h, prop["id"], "01")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    meeting = _ok(
        client.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2026-11-20T10:00:00+01:00",
                "voting_principle": "head",
            },
            headers=h,
        ),
        201,
    )

    def invited() -> list[tuple[str, str | None, str]]:
        rows = _ok(client.get(f"{H}/meetings/{meeting['id']}/invitation-recipients", headers=h))
        assert len(rows) == 1
        assert rows[0]["party_id"] == party
        assert rows[0]["member_contact_ids"] == [owner["id"]]
        return [
            (r["contact_id"], r["represents_contact_id"], r["channel"])
            for r in rows[0]["recipients"]
        ]

    assert invited() == [(rep["id"], owner["id"], "email")]
    _set_mode(client, h, owner["id"], relation["id"], "both")
    assert invited() == [(owner["id"], None, "post"), (rep["id"], owner["id"], "email")]
    _set_mode(client, h, owner["id"], relation["id"], "owner_only")
    assert invited() == [(owner["id"], None, "post")]

    # An expired authorisation counts no longer: the owner receives everything.
    _set_mode(client, h, owner["id"], relation["id"], "representative_only")
    _ok(
        client.patch(
            f"/api/v1/contacts/{owner['id']}/contact-relations/{relation['id']}",
            json={"valid_to": "2020-12-31", "fields": ["valid_to"]},
            headers=h,
        )
    )
    assert invited() == [(owner["id"], None, "post")]
    assert _dispatch_targets(client, h, doc, owner["id"]) == {owner["id"]}

    # Tenant separation: the other tenant sees and changes nothing.
    other = bearer(login(client, world, "repother", tenant_id=world.tenant_b))
    assert (
        client.get(f"/api/v1/contacts/{owner['id']}/contact-relations", headers=other).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/contacts/{owner['id']}/contact-relations/{relation['id']}",
            json={"delivery_mode": "both", "fields": ["delivery_mode"]},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/contacts/{owner['id']}/contact-relations/{relation['id']}", headers=other
        ).status_code
        == 404
    )

    # Ending the relation is audited; afterwards the list is empty.
    assert (
        client.delete(
            f"/api/v1/contacts/{owner['id']}/contact-relations/{relation['id']}", headers=h
        ).status_code
        == 204
    )
    assert _ok(client.get(f"/api/v1/contacts/{owner['id']}/contact-relations", headers=h)) == []
    audit = _ok(client.get(f"/api/v1/tenant/audit-log?entity_id={owner['id']}", headers=h))
    assert any(
        (e["changes"] or {}).get("representative", {}).get("new", "x") is None for e in audit
    )
    assert (
        client.get(f"/api/v1/contacts/{uuid.uuid4()}/contact-relations", headers=h).status_code
        == 404
    )
