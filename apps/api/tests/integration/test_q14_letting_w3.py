"""Q14 (30.09.2026): rent index range into the rent increase case (comparison rent 60 m2 x
7,20 = 432,00), AI check link, exposé PDF with listing images. Values are test inputs, not law."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m6_documents import BUCKET, COMPANY, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q14a-{RUN}", name=f"Q14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q14b-{RUN}", name=f"Q14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("q14admin", a, "tenant_admin"),
            ("q14other", b, "tenant_admin"),
            ("q14care", a, "caretaker"),
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


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _setup(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": "Mietshaus",
                "management_type": "rental",
                "city": f"Teststadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "VermieterP20", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    units = {}
    for no in ("01", "02"):
        units[no] = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/units",
                json={
                    "building_id": building,
                    "number": no,
                    "unit_type": "apartment",
                    "living_area_sqm": "60",
                    "rooms": "2.5",
                },
                headers=h,
            ),
            201,
        )["id"]
    tenant, _ = _party(client, h, "MieterP20")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": units["01"],
                "party_id": tenant,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "gross": "600.00",
                "valid_from": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )
    former, _ = _party(client, h, "VormieterP20")
    old = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": units["02"],
                "party_id": former,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{old}/termination",
            json={
                "end_date": "2026-06-30",
                "termination_date": "2026-03-31",
                "termination_reason": "Kündigung Mieter",
            },
            headers=h,
        )
    )
    return {"prop": prop["id"], "units": units, "contract": contract}


def _png() -> bytes:
    from mhvp.documents.letters import qr_png

    return qr_png("https://example.org")


def test_adopt_rent_index_and_ai_check_link(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q14admin"))
    other = bearer(login(client, world, "q14other"))
    care = bearer(login(client, world, "q14care"))
    s = _setup(client, h, "781")
    entry = _ok(
        client.post(
            f"{L}/rent-index",
            json={
                "municipality": "Testdorf",
                "index_name": "Mietspiegel Testdorf",
                "valid_from": "2025-01-01",
                "rent_min": "6.50",
                "rent_mid": "7.20",
                "rent_max": "8.10",
                "source_note": "Testdaten",
            },
            headers=h,
        ),
        201,
    )
    no_mid = _ok(
        client.post(
            f"{L}/rent-index",
            json={
                "municipality": "Testdorf",
                "index_name": "Ohne Mitte",
                "valid_from": "2025-01-01",
                "rent_min": "6.00",
                "rent_max": "8.00",
                "source_note": "Testdaten",
            },
            headers=h,
        ),
        201,
    )
    case = _ok(
        client.post(
            f"{L}/rent-increases",
            json={
                "contract_id": s["contract"],
                "basis": "mietspiegel",
                "effective_date": "2026-12-01",
                "target_rent": "620.00",
                "source_note": "vorläufig",
            },
            headers=h,
        ),
        201,
    )
    url = f"{L}/rent-increases/{case['id']}"
    done = _ok(
        client.post(
            f"{url}/adopt-rent-index",
            json={"entry_id": entry["id"], "position": "mid"},
            headers=h,
        )
    )
    # 60 m2 x 7,20 = 432,00 (Vergleichsmiete), Zielmiete 620,00 darüber: Hinweis
    assert Decimal(done["comparison_rent_per_sqm"]) == Decimal("7.20")
    assert done["rent_index_name"] == "Mietspiegel Testdorf"
    assert done["justification"] == "mietspiegel"
    assert done["check"]["comparison_rent"] == "432.00"
    assert done["check"]["ok"] is False
    assert any("Vergleichsmiete" in f for f in done["check"]["flags"])
    mid_missing = client.post(
        f"{url}/adopt-rent-index", json={"entry_id": no_mid["id"], "position": "mid"}, headers=h
    )
    assert mid_missing.status_code == 422
    bad_position = client.post(
        f"{url}/adopt-rent-index", json={"entry_id": entry["id"], "position": "x"}, headers=h
    )
    assert bad_position.status_code == 422
    body = {"entry_id": entry["id"], "position": "max"}
    assert client.post(f"{url}/adopt-rent-index", json=body, headers=other).status_code == 404
    assert client.post(f"{url}/adopt-rent-index", json=body, headers=care).status_code == 403
    unknown = {"entry_id": "0192abcd-0000-7000-8000-00000000ffff", "position": "min"}
    assert client.post(f"{url}/adopt-rent-index", json=unknown, headers=h).status_code == 404

    # AI check reference (6.3 ai_check_id): unknown proposal 404, clearing allowed
    missing = {"proposal_id": "0192abcd-0000-7000-8000-00000000ffff"}
    assert client.put(f"{url}/ai-check", json=missing, headers=h).status_code == 404
    cleared = _ok(client.put(f"{url}/ai-check", json={"proposal_id": None}, headers=h))
    assert cleared["ai_check_id"] is None
    assert client.put(f"{url}/ai-check", json={}, headers=other).status_code == 404
    assert client.put(f"{url}/ai-check", json={}, headers=care).status_code == 403


def test_expose_pdf_embeds_listing_images(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q14admin"))
    other = bearer(login(client, world, "q14other"))
    s = _setup(client, h, "782")
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    unit = s["units"]["02"]
    listing = _ok(client.post(f"{L}/vacancies/{unit}/listing", headers=h), 201)
    plain = _ok(client.post(f"{L}/units/{unit}/expose/pdf", headers=h), 201)
    assert plain["images_embedded"] == 0
    images_url = f"{L}/listings/{listing['id']}/images"
    _ok(
        client.post(images_url, files={"file": ("aussen.png", _png(), "image/png")}, headers=h), 201
    )
    with_image = _ok(client.post(f"{L}/units/{unit}/expose/pdf", headers=h), 201)
    assert with_image["images_embedded"] == 1
    assert client.post(f"{L}/units/{unit}/expose/pdf", headers=other).status_code == 404
