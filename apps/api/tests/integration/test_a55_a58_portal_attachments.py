"""A55 and A58 (14, M21/M22): photos of a damage report are real document links on the ticket
(only own portal uploads, foreign or CRM documents answered as not found, metadata stripped);
providers send up to three appointment proposals per order, only the affected resident accepts
one, acceptance schedules the order and leaves an event; execution photos are linked to the
order. A second tenant (organisation) never sees or touches any of it."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a58a-{RUN}", name=f"A58 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"a58b-{RUN}", name=f"A58 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("a58admin", a), ("a58adminb", b)):
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


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (2400, 1200), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 10.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str) -> str:
    return str(
        _ok(c.post(f"{P}/uploads", files={"file": (name, data, mime)}, headers=h), 201)["id"]
    )


def _rental(c: TestClient, h: dict[str, str], number: str) -> tuple[str, dict[str, Any]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Haus {number}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, f"Vermieter{number}", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    return str(prop["id"]), prop


def _tenancy(c: TestClient, h: dict[str, str], prop_id: str, no: str) -> dict[str, Any]:
    unit = _unit(c, h, prop_id, no)
    party, _ = _party(c, h, f"Mieter{no}")
    created: dict[str, Any] = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    return created


def test_a55_photo_is_a_document_link_on_the_ticket(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a58admin", tenant_id=world.tenant_a))
    prop_id, _ = _rental(client, h, "851")
    tenancy = _tenancy(client, h, prop_id, "A")
    ta = _portal_user(client, h, world, "a55tenantA", _contact_of(client, h, tenancy["party_id"]))
    tb = _portal_user(
        client,
        h,
        world,
        "a55tenantB",
        _contact_of(client, h, _tenancy(client, h, prop_id, "B")["party_id"]),
    )

    # Upload: EXIF and GPS are removed, the photo is scaled, the original is not kept.
    photo = _upload(client, ta, "schaden.jpg", _jpeg_with_exif(), "image/jpeg")
    stored = client.get(f"/api/v1/documents/{photo}/content", headers=h)
    assert stored.status_code == 200
    assert b"TestCam" not in stored.content
    with Image.open(io.BytesIO(stored.content)) as img:
        assert max(img.size) <= 2000
        assert len(img.getexif()) == 0
    pdf = _upload(client, ta, "beleg.pdf", b"%PDF-1.4 beleg", "application/pdf")
    # Unsupported photo types are refused instead of stored with their metadata.
    assert (
        client.post(
            f"{P}/uploads",
            files={"file": ("x.heic", b"\x00\x00\x00\x18ftypheic", "image/heic")},
            headers=ta,
        ).status_code
        == 422
    )

    # A document of another portal user and a CRM document are answered as not found.
    foreign = _upload(client, tb, "fremd.jpg", _jpeg_with_exif(), "image/jpeg")
    crm_doc = _ok(
        client.post(
            "/api/v1/documents",
            data={"title": "Intern"},
            files={"file": ("intern.txt", b"intern", "text/plain")},
            headers=h,
        ),
        201,
    )["id"]
    for bad in (foreign, crm_doc, "00000000-0000-7000-8000-000000000000"):
        response = client.post(
            f"{P}/tickets",
            json={"title": "Fenster klemmt", "description": "Küche", "document_ids": [bad]},
            headers=ta,
        )
        assert response.status_code == 404, response.text
    # More than ten attachments are a validation error.
    assert (
        client.post(
            f"{P}/tickets",
            json={"title": "Zu viele", "description": "Fotos", "document_ids": [photo] * 11},
            headers=ta,
        ).status_code
        == 422
    )

    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={
                "title": "Fenster klemmt",
                "description": "Küche",
                "unit_id": tenancy["unit_id"],
                "document_ids": [photo, pdf, photo],
            },
            headers=ta,
        ),
        201,
    )
    assert [a["id"] for a in ticket["attachments"]] == [photo, pdf]
    mine = _ok(client.get(f"{P}/tickets", headers=ta))
    assert [a["id"] for a in mine[0]["attachments"]] == [photo, pdf]
    # The CRM ticket detail carries the same links; the document lists the ticket as link.
    detail = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    assert [a["id"] for a in detail["attachments"]] == [photo, pdf]
    links = _ok(client.get(f"/api/v1/documents/{photo}", headers=h))["links"]
    assert {"ticket", "contact"} <= {link["entity_type"] for link in links}
    # Tenant B sees neither the ticket nor the photo.
    assert all(t["id"] != ticket["id"] for t in _ok(client.get(f"{P}/tickets", headers=tb)))
    assert client.get(f"{P}/documents/{photo}/download", headers=tb).status_code == 404


def test_a58_appointment_proposals_and_execution_photos(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a58admin", tenant_id=world.tenant_a))
    prop_id, _ = _rental(client, h, "852")
    tenancy = _tenancy(client, h, prop_id, "A")
    other = _tenancy(client, h, prop_id, "B")
    ta = _portal_user(client, h, world, "a58tenantA", _contact_of(client, h, tenancy["party_id"]))
    tb = _portal_user(client, h, world, "a58tenantB", _contact_of(client, h, other["party_id"]))
    provider_contact = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Dach {RUN}"}, headers=h
        ),
        201,
    )["id"]
    pv = _portal_user(client, h, world, "a58provider", provider_contact)
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Dach undicht", "description": "Tropft", "unit_id": tenancy["unit_id"]},
            headers=ta,
        ),
        201,
    )
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop_id,
                "provider_contact_id": provider_contact,
                "description": "Ziegel ersetzen",
            },
            headers=h,
        ),
        201,
    )
    oid = order["id"]
    _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json={"status": "requested"}, headers=h))
    two = {
        "proposals": [
            {"starts_at": "2026-10-05T09:00:00Z"},
            {"starts_at": "2026-10-06T14:00:00Z", "note": "nachmittags"},
        ]
    }
    # Not before approval; not by the resident; not by a foreign provider; at most three.
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals", json=two, headers=pv
        ).status_code
        == 409
    )
    _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json={"status": "approved"}, headers=h))
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals", json=two, headers=ta
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={"proposals": [{"starts_at": f"2026-10-0{i}T09:00:00Z"} for i in range(1, 5)]},
            headers=pv,
        ).status_code
        == 422
    )
    first = _ok(
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={"proposals": [{"starts_at": "2026-10-01T09:00:00Z"}]},
            headers=pv,
        ),
        201,
    )
    proposals = _ok(
        client.post(f"{P}/work-orders/{oid}/appointment-proposals", json=two, headers=pv), 201
    )
    assert len(proposals) == 2
    assert all(p["status"] == "proposed" for p in proposals)
    # The earlier round is superseded.
    by_id = {
        p["id"]: p
        for p in _ok(client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=pv))
    }
    assert by_id[first[0]["id"]]["status"] == "superseded"

    # The affected resident sees the open proposals on the ticket, another tenant does not.
    mine = next(t for t in _ok(client.get(f"{P}/tickets", headers=ta)) if t["id"] == ticket["id"])
    assert [p["id"] for p in mine["appointment_proposals"]] == [p["id"] for p in proposals]
    assert _ok(client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=ta))
    assert client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=tb).status_code == 404
    chosen = proposals[1]["id"]
    accept = f"{P}/work-orders/{oid}/appointment-proposals/{chosen}/accept"
    # Only the affected resident confirms: not the other tenant, not the provider.
    assert client.post(accept, headers=tb).status_code == 404
    assert client.post(accept, headers=pv).status_code == 404
    # Superseded proposals cannot be accepted.
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals/{first[0]['id']}/accept", headers=ta
        ).status_code
        == 409
    )
    result = _ok(client.post(accept, headers=ta))
    assert result["order"]["status"] == "scheduled"
    assert result["order"]["scheduled_at"].startswith("2026-10-06T14:00:00")
    assert result["proposal"]["status"] == "accepted"
    assert client.post(accept, headers=ta).status_code == 409  # already decided
    statuses = {
        p["id"]: p["status"]
        for p in _ok(client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=pv))
    }
    assert statuses[proposals[0]["id"]] == "declined"
    assert statuses[chosen] == "accepted"
    # The confirmation is visible on the ticket (comment) and in the order history (event).
    mine = next(t for t in _ok(client.get(f"{P}/tickets", headers=ta)) if t["id"] == ticket["id"])
    assert any(c.startswith("Termin bestätigt: 06.10.2026 16:00") for c in mine["comments"])
    detail = _ok(client.get(f"/api/v1/tickets/{ticket['id']}", headers=h))
    crm_order = next(o for o in detail["work_orders"] if o["id"] == oid)
    assert crm_order["status"] == "scheduled"
    assert crm_order["scheduled_at"].startswith("2026-10-06T14:00:00")

    # Execution photos: own uploads only, linked to the order.
    photo = _upload(client, pv, "fertig.jpg", _jpeg_with_exif(), "image/jpeg")
    foreign = _upload(client, ta, "fremd.jpg", _jpeg_with_exif(), "image/jpeg")
    assert (
        client.post(
            f"{P}/work-orders/{oid}/complete",
            json={"report": "Ziegel ersetzt", "document_ids": [foreign]},
            headers=pv,
        ).status_code
        == 404
    )
    done = _ok(
        client.post(
            f"{P}/work-orders/{oid}/complete",
            json={"report": "Ziegel ersetzt", "document_ids": [photo]},
            headers=pv,
        )
    )
    assert done["status"] == "done"
    assert [p["id"] for p in done["photos"]] == [photo]
    links = _ok(client.get(f"/api/v1/documents/{photo}", headers=h))["links"]
    assert "work_order" in {link["entity_type"] for link in links}


def test_a58_other_tenant_organisation_sees_nothing(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a58admin", tenant_id=world.tenant_a))
    hb = bearer(login(client, world, "a58adminb", tenant_id=world.tenant_b))
    prop_id, _ = _rental(client, h, "853")
    tenancy = _tenancy(client, h, prop_id, "A")
    ta = _portal_user(client, h, world, "a58sepA", _contact_of(client, h, tenancy["party_id"]))
    provider_contact = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Sep {RUN}"}, headers=h
        ),
        201,
    )["id"]
    pv = _portal_user(client, h, world, "a58sepP", provider_contact)
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Sep", "description": "Sep", "unit_id": tenancy["unit_id"]},
            headers=ta,
        ),
        201,
    )
    oid = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop_id,
                "provider_contact_id": provider_contact,
                "description": "Sep",
            },
            headers=h,
        ),
        201,
    )["id"]
    for status in ("requested", "approved"):
        _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json={"status": status}, headers=h))
    proposal = _ok(
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={"proposals": [{"starts_at": "2026-10-07T09:00:00Z"}]},
            headers=pv,
        ),
        201,
    )[0]
    photo = _upload(client, ta, "a.jpg", _jpeg_with_exif(), "image/jpeg")

    # Tenant B: own rental, own resident and provider portal users.
    prop_b, _ = _rental(client, hb, "854")
    tenancy_b = _tenancy(client, hb, prop_b, "A")
    tb = _portal_user(client, hb, world, "a58sepB", _contact_of(client, hb, tenancy_b["party_id"]))
    provider_b = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"SepB {RUN}"}, headers=hb
        ),
        201,
    )["id"]
    pvb = _portal_user(client, hb, world, "a58sepPB", provider_b)
    assert _ok(client.get(f"{P}/work-orders", headers=pvb)) == []
    assert (
        client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=pvb).status_code == 404
    )
    assert client.get(f"{P}/work-orders/{oid}/appointment-proposals", headers=tb).status_code == 404
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals/{proposal['id']}/accept", headers=tb
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={"proposals": [{"starts_at": "2026-10-08T09:00:00Z"}]},
            headers=pvb,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{P}/work-orders/{oid}/complete",
            json={"report": "fremd", "document_ids": []},
            headers=pvb,
        ).status_code
        == 404
    )
    # A tenant A photo cannot be attached to a tenant B ticket.
    assert (
        client.post(
            f"{P}/tickets",
            json={"title": "Fremd", "description": "Foto", "document_ids": [photo]},
            headers=tb,
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/documents/{photo}", headers=hb).status_code == 404
    assert all(t["id"] != ticket["id"] for t in _ok(client.get(f"{P}/tickets", headers=tb)))
