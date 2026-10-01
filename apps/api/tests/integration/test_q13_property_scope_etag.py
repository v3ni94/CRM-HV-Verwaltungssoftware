"""M2-02/S16-02 (Objektzuordnung je Mitgliedschaft wirkt in properties, contracts, tickets,
documents, accounting) and S12-04 (optional If-Match/ETag on contracts, invoices, tickets,
documents): filtered lists, 404 outside the assignment, 403 without write permission, 412 on a
stale If-Match, 422 on invalid input, tenant separation."""

import asyncio
import json
import uuid
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
from tests.integration.test_m5_contracts import _party, _property, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
T = "/api/v1/tenant"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q13-{RUN}", name=f"Q13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q13b-{RUN}", name=f"Q13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("q13admin", a, "tenant_admin"),
            ("q13admin_b", b, "tenant_admin"),
            ("q13clerk", a, "standard"),
            ("q13reader", a, "read_only"),
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _membership(client: TestClient, h: dict[str, str], user_id: uuid.UUID) -> str:
    rows = _ok(client.get(f"{T}/members", headers=h))
    return next(str(r["membership_id"]) for r in rows if r["user_id"] == str(user_id))


def _assign(client: TestClient, h: dict[str, str], user: uuid.UUID, props: list[str]) -> None:
    member = _membership(client, h, user)
    done = client.put(f"{T}/members/{member}/properties", json={"property_ids": props}, headers=h)
    assert done.status_code == 204, done.text


def _estate(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    """Property with unit, ownership contract, ticket, document and ledger invoice."""
    prop = _property(client, h, number, "hoa")
    unit = _unit(client, h, prop["id"], "01")
    party, _ = _party(client, h, f"Eigent{number}")
    contract = _ok(
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
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={
                "category": "Sonstiges",
                "title": f"Anliegen {number}",
                "property_id": prop["id"],
                "public_description": "Test",
                "source": "phone",
            },
            headers=h,
        ),
        201,
    )
    document = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (f"d{number}.txt", b"Inhalt", "text/plain")},
            data={
                "title": f"Dokument {number} {RUN}",
                "links": json.dumps([{"entity_type": "property", "entity_id": prop["id"]}]),
            },
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = client.post("/api/v1/accounting/templates/default", headers=h)
    assert template.status_code in (200, 201), template.text
    ledger = _ok(
        client.post(
            "/api/v1/accounting/ledgers",
            json={"legal_entity_id": hoa, "template_id": template.json()["id"]},
            headers=h,
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"/api/v1/accounting/ledgers/{ledger}/accounts", headers=h))
    }
    _, provider = _party(client, h, f"Firma{number}", kind="company")
    invoice = _ok(
        client.post(
            "/api/v1/accounting/invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider["id"],
                "number": f"R-{number}",
                "invoice_date": "2026-09-01",
                "net": "100.00",
                "vat": "0.00",
                "gross": "100.00",
                "lines": [{"account_id": accounts["041400"], "net": "100.00"}],
            },
            headers=h,
        ),
        201,
    )
    return {
        "property": prop["id"],
        "unit": unit,
        "contract": contract["id"],
        "ticket": ticket["id"],
        "document": document["id"],
        "invoice": invoice["id"],
    }


def test_property_assignment_filters_all_domains(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q13admin"))
    own = _estate(client, h, "701")
    foreign = _estate(client, h, "702")
    _assign(client, h, world.users["q13clerk"], [own["property"]])
    c = bearer(login(client, world, "q13clerk"))

    # Lists contain only the assigned property.
    props = {p["id"] for p in _ok(client.get("/api/v1/properties", headers=c))["items"]}
    assert own["property"] in props
    assert foreign["property"] not in props
    contracts = {x["id"] for x in _ok(client.get("/api/v1/contracts", headers=c))}
    assert own["contract"] in contracts
    assert foreign["contract"] not in contracts
    tickets = _ok(client.get("/api/v1/tickets", headers=c))
    ticket_ids = {x["id"] for x in (tickets["items"] if isinstance(tickets, dict) else tickets)}
    assert own["ticket"] in ticket_ids
    assert foreign["ticket"] not in ticket_ids
    docs = {x["id"] for x in _ok(client.get("/api/v1/documents", headers=c))["items"]}
    assert own["document"] in docs
    assert foreign["document"] not in docs
    invoices = {x["id"] for x in _ok(client.get("/api/v1/accounting/invoices", headers=c))}
    assert own["invoice"] in invoices
    assert foreign["invoice"] not in invoices

    # Detail reads: own 200, foreign 404 (existence is not disclosed).
    for path_own, path_foreign in (
        (f"/api/v1/properties/{own['property']}", f"/api/v1/properties/{foreign['property']}"),
        (
            f"/api/v1/properties/{own['property']}/units",
            f"/api/v1/properties/{foreign['property']}/units",
        ),
        (f"/api/v1/units/{own['unit']}", f"/api/v1/units/{foreign['unit']}"),
        (f"/api/v1/contracts/{own['contract']}", f"/api/v1/contracts/{foreign['contract']}"),
        (f"/api/v1/tickets/{own['ticket']}", f"/api/v1/tickets/{foreign['ticket']}"),
        (f"/api/v1/documents/{own['document']}", f"/api/v1/documents/{foreign['document']}"),
        (
            f"/api/v1/accounting/invoices/{own['invoice']}",
            f"/api/v1/accounting/invoices/{foreign['invoice']}",
        ),
    ):
        _ok(client.get(path_own, headers=c))
        assert client.get(path_foreign, headers=c).status_code == 404, path_foreign

    # A ticket cannot be moved to a property outside the assignment.
    moved = client.patch(
        f"/api/v1/tickets/{own['ticket']}", json={"property_id": foreign["property"]}, headers=c
    )
    assert moved.status_code == 404, moved.text

    # The administrator role is never limited; an empty list lifts the restriction.
    admin_props = {p["id"] for p in _ok(client.get("/api/v1/properties", headers=h))["items"]}
    assert {own["property"], foreign["property"]} <= admin_props
    _assign(client, h, world.users["q13clerk"], [])
    c = bearer(login(client, world, "q13clerk"))
    _ok(client.get(f"/api/v1/tickets/{foreign['ticket']}", headers=c))

    # Tenant separation: tenant B sees nothing of tenant A.
    hb = bearer(login(client, world, "q13admin_b"))
    assert client.get(f"/api/v1/contracts/{own['contract']}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/tickets/{own['ticket']}", headers=hb).status_code == 404


def test_if_match_optional_lock(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q13admin"))
    e = _estate(client, h, "703")
    stale = '"t1"'
    cases: list[tuple[str, str, str, dict[str, Any]]] = [
        ("patch", f"/api/v1/contracts/{e['contract']}", "/notes", {"notes": "Hinweis"}),
        ("patch", f"/api/v1/tickets/{e['ticket']}", "", {"internal_description": f"Notiz {RUN}"}),
        ("patch", f"/api/v1/documents/{e['document']}", "", {"title": f"Neu {RUN}"}),
    ]
    for method, base, suffix, body in cases:
        read = client.get(base, headers=h)
        assert read.status_code == 200, read.text
        etag = read.headers["ETag"]
        url = base + suffix
        conflict = client.request(method, url, json=body, headers={**h, "If-Match": stale})
        assert conflict.status_code == 412, (url, conflict.text)
        done = client.request(method, url, json=body, headers={**h, "If-Match": etag})
        assert done.status_code == 200, (url, done.text)
        assert done.headers["ETag"] != etag
        # The old token is stale now; without the header the write stays unchecked.
        again = client.request(method, url, json=body, headers={**h, "If-Match": etag})
        assert again.status_code == 412, url
        _ok(client.request(method, url, json=body, headers=h))

    # Invoice: the optimistic version is the token.
    inv_url = f"/api/v1/accounting/invoices/{e['invoice']}"
    read = client.get(inv_url, headers=h)
    assert read.headers["ETag"] == f'"{read.json()["version"]}"'
    body = {
        k: read.json()[k]
        for k in ("ledger_id", "provider_contact_id", "number", "invoice_date", "net", "vat")
    }
    body |= {
        "gross": read.json()["gross"],
        "lines": [
            {"account_id": ln["account_id"], "net": ln["net"]} for ln in read.json()["lines"]
        ],
    }
    assert client.put(inv_url, json=body, headers={**h, "If-Match": '"99"'}).status_code == 412
    updated = client.put(inv_url, json=body, headers={**h, "If-Match": read.headers["ETag"]})
    assert updated.status_code == 200, updated.text
    assert updated.headers["ETag"] == f'"{read.json()["version"] + 1}"'

    # Authorization and validation stay ahead of the lock.
    reader = bearer(login(client, world, "q13reader"))
    denied = client.patch(
        f"/api/v1/documents/{e['document']}", json={"title": "x"}, headers={**reader}
    )
    assert denied.status_code == 403, denied.text
    invalid = client.patch(
        f"/api/v1/contracts/{e['contract']}/notes", json={"dunning_block": "vielleicht"}, headers=h
    )
    assert invalid.status_code == 422, invalid.text


def test_key_rotation_dry_run_apply_and_back(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """S16-03: dry run writes nothing, apply re-encrypts and recomputes the IBAN fingerprint,
    a second run is idempotent, rotating back restores the tenant for the other tests."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.key_rotation import run

    h = bearer(login(client, world, "q13admin"))
    _party(client, h, "Iban", iban="DE02120300000000202051")
    old, new = b"k" * 32, b"q" * 32

    async def rotate(a: bytes, b: bytes, dry: bool) -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            return await run(
                create_session_factory(engine),
                a,
                b,
                dry_run=dry,
                tenant_ids=[world.tenant_a],
                include_platform=False,
            )
        finally:
            await engine.dispose()

    dry = asyncio.run(rotate(old, new, True))
    assert not dry.errors, dry.errors
    if dry.blockers:  # e.g. embedded webhook secrets: apply refuses to write
        assert asyncio.run(rotate(old, new, False)).counts.get("rotated", 0) >= 1
        return
    assert dry.rows["contact_bank_account.iban"]["rotated"] >= 1
    assert dry.rows["contact_bank_account.iban_fingerprint"]["recomputed"] >= 1
    assert asyncio.run(rotate(old, new, True)).counts["rotated"] == dry.counts["rotated"]
    applied = asyncio.run(rotate(old, new, False))
    assert applied.ok, applied.as_dict()
    repeat = asyncio.run(rotate(old, new, True))
    assert repeat.counts.get("rotated", 0) == 0
    assert repeat.counts["already_rotated"] >= applied.counts["rotated"]
    back = asyncio.run(rotate(new, old, False))
    assert back.ok
    assert back.counts["rotated"] == applied.counts["rotated"]
    text = json.dumps(back.as_dict())
    assert "DE02120300000000202051" not in text
    assert "0202051" not in text
    # The tenant works with the original key again.
    rows = _ok(client.get("/api/v1/contacts", params={"q": "Iban"}, headers=h))
    assert rows
