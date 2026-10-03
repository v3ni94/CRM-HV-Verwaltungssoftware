"""AM06 (GAJ-401, GAJ-402, GAJ-202): meter reading with photo, running order status at the
ticket and inspection requests of owners in the portal (switch AG09, own requests only)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"am06a-{RUN}", name=f"AM06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"am06b-{RUN}", name=f"AM06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("am06admin", a), ("am06adminb", b)):
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
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _no(n: int) -> str:
    return f"{(int(RUN, 16) + n) % 900 + 100:03d}"


def _upload(c: TestClient, h: dict[str, str], name: str) -> str:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 20), (10, 120, 10)).save(buf, format="JPEG")
    return str(
        _ok(
            c.post(f"{P}/uploads", files={"file": (name, buf.getvalue(), "image/jpeg")}, headers=h),
            201,
        )["id"]
    )


def _tenancy(c: TestClient, h: dict[str, str], no: str) -> dict[str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AM06 Haus {no}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, f"AM06Vermieter{no}", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, prop["id"], "01")
    party, _ = _party(c, h, f"AM06Mieter{no}")
    _ok(
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
    return {"property": str(prop["id"]), "unit": unit, "party": party}


def _owner(c: TestClient, h: dict[str, str], no: str) -> dict[str, str]:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AM06-WEG {no}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, weg["id"], "01")
    party, _ = _party(c, h, f"AM06Eigentuemer{no}")
    _ok(
        c.post(
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
    return {"property": str(weg["id"]), "party": party}


def _hoa_entity(database: Database, tenant: Any, prop: str) -> str:
    import uuid

    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_engine(database.migrator_url)
    try:
        with Session(engine) as s, s.begin():
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            row = s.scalar(
                select(LegalEntity).where(
                    LegalEntity.property_id == uuid.UUID(prop),
                    LegalEntity.kind == LegalEntityKind.HOA,
                )
            )
            assert row is not None
            return str(row.id)
    finally:
        engine.dispose()


def test_meter_reading_with_photo_and_order_status(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "am06admin", tenant_id=world.tenant_a))
    t = _tenancy(client, h, _no(11))
    ta = _portal_user(client, h, world, "am06tenant", _contact_of(client, h, t["party"]))
    other = _tenancy(client, h, _no(12))
    tb = _portal_user(client, h, world, "am06tenant2", _contact_of(client, h, other["party"]))
    meter = _ok(
        client.post(
            f"/api/v1/properties/{t['property']}/meters",
            json={
                "unit_id": t["unit"],
                "meter_type_code": "cold_water",
                "number": f"AM06-{RUN}",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    body = {"meter_id": meter["id"], "value": "12.5", "read_at": "2026-09-30"}
    # without photo: accepted as proposal with hint
    plain = _ok(client.post(f"{P}/meter-readings", json=body, headers=ta), 201)
    assert plain["photo_missing"] is True
    assert plain["note"]
    # photo of someone else: not found; too many ids or unknown field: 422
    foreign = _upload(client, tb, "fremd.jpg")
    assert (
        client.post(
            f"{P}/meter-readings", json={**body, "document_ids": [foreign]}, headers=ta
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{P}/meter-readings", json={**body, "document_ids": [foreign] * 6}, headers=ta
        ).status_code
        == 422
    )
    assert client.post(f"{P}/meter-readings", json={**body, "x": 1}, headers=ta).status_code == 422
    # CRM bearer is no portal user
    assert client.post(f"{P}/meter-readings", json=body, headers=h).status_code in (401, 403)
    photo = _upload(client, ta, "zaehler.jpg")
    with_photo = _ok(
        client.post(f"{P}/meter-readings", json={**body, "document_ids": [photo]}, headers=ta), 201
    )
    assert with_photo["photo_missing"] is False
    assert [a["id"] for a in with_photo["attachments"]] == [photo]
    queue = {r["id"]: r for r in _ok(client.get(f"{PA}/change-requests", headers=h))}
    assert queue[with_photo["id"]]["payload"]["document_ids"] == [photo]
    _ok(
        client.post(
            f"{PA}/change-requests/{with_photo['id']}/decide", json={"accept": True}, headers=h
        )
    )

    # GAJ-402: running order status at the ticket
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Heizung kalt", "description": "Seit gestern", "unit_id": t["unit"]},
            headers=ta,
        ),
        201,
    )
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"AM06 SHK {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": t["property"],
                "provider_contact_id": provider,
                "description": "Heizung prüfen",
            },
            headers=h,
        ),
        201,
    )
    mine = {r["id"]: r for r in _ok(client.get(f"{P}/tickets", headers=ta))}
    assert mine[ticket["id"]]["work_orders"] == []  # draft stays internal
    _ok(
        client.post(
            f"/api/v1/work-orders/{order['id']}/steps", json={"status": "requested"}, headers=h
        )
    )
    mine = {r["id"]: r for r in _ok(client.get(f"{P}/tickets", headers=ta))}
    orders = mine[ticket["id"]]["work_orders"]
    assert [o["status"] for o in orders] == ["requested"]
    assert set(orders[0]) == {"id", "status", "scheduled_at"}


def test_owner_inspection_requests(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "am06admin", tenant_id=world.tenant_a))
    hb = bearer(login(client, world, "am06adminb", tenant_id=world.tenant_b))
    meta = _owner(client, h, _no(21))
    entity = _hoa_entity(database, world.tenant_a, meta["property"])
    foreign_weg = _owner(client, h, _no(22))
    foreign_entity = _hoa_entity(database, world.tenant_a, foreign_weg["property"])
    owner = _portal_user(client, h, world, "am06owner", _contact_of(client, h, meta["party"]))
    rent = _tenancy(client, h, _no(23))
    tenant_user = _portal_user(
        client, h, world, "am06renter", _contact_of(client, h, rent["party"])
    )
    meta_b = _owner(client, hb, _no(24))
    owner_b = _portal_user(
        client, hb, world, "am06ownerb", _contact_of(client, hb, meta_b["party"])
    )
    url = f"{P}/owner/inspection-requests"
    body = {"legal_entity_id": entity, "scope_kinds": ["receipts"], "scope_text": "Belege 2025"}

    # switch off (default): list empty with note, filing refused
    off = _ok(client.get(url, headers=owner))
    assert off["enabled"] is False
    assert off["items"] == []
    assert client.post(url, json=body, headers=owner).status_code == 403
    _ok(client.patch(f"{PA}/features", json={"portal_owner_receipts_enabled": True}, headers=h))

    # 403: no owner grant; CRM bearer is no portal user
    assert client.post(url, json=body, headers=tenant_user).status_code == 403
    assert client.get(url, headers=h).status_code in (401, 403)
    # 422: unknown scope, no scope, unknown field, unknown query
    assert client.post(url, json={**body, "scope_kinds": ["x"]}, headers=owner).status_code == 422
    assert (
        client.post(
            url, json={"legal_entity_id": entity, "scope_kinds": []}, headers=owner
        ).status_code
        == 422
    )
    assert client.post(url, json={**body, "status": "released"}, headers=owner).status_code == 422
    assert client.get(f"{url}?bogus=1", headers=owner).status_code == 422
    # community of someone else: 404
    assert (
        client.post(
            url, json={**body, "legal_entity_id": foreign_entity}, headers=owner
        ).status_code
        == 404
    )

    created = _ok(client.post(url, json=body, headers=owner), 201)
    assert created["status"] == "requested"
    assert [s["to_status"] for s in created["steps"]] == ["requested"]
    # lands in the CRM process
    crm = _ok(client.get(f"/api/v1/hoa/inspection-requests?legal_entity_id={entity}", headers=h))
    assert created["id"] in {r["id"] for r in crm}
    _ok(
        client.post(
            f"/api/v1/hoa/inspection-requests/{created['id']}/transition",
            json={"status": "released"},
            headers=h,
        )
    )
    got = _ok(client.get(f"{url}/{created['id']}", headers=owner))
    assert [s["to_status"] for s in got["steps"]] == ["requested", "released"]
    listed = _ok(client.get(url, headers=owner))
    assert [i["id"] for i in listed["items"]] == [created["id"]]
    assert [c["id"] for c in listed["communities"]] == [entity]

    # other tenant: 404 for the id, nothing listed
    assert client.get(f"{url}/{created['id']}", headers=owner_b).status_code == 404
    assert client.get(f"{url}/{created['id']}", headers=tenant_user).status_code == 403
    assert client.get(f"{url}/not-a-uuid", headers=owner).status_code == 422
