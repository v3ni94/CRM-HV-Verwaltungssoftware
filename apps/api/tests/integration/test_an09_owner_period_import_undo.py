"""AN09 (AM03 rest) against PostgreSQL: the ownership import ends the open owner of another
party the day before the key date; the undo of that import removes the new owner and restores
the previous end (open again). Rows and column headers are invented for the test."""

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
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, XLSX, _mapping, _settings, _stage, _xlsx

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/immoware24"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an09-{RUN}", name=f"AN09 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("an09admin"), display_name="an09admin", password=PASSWORD
        )
        world.users["an09admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _apply(c: TestClient, h: dict[str, str], source: Any, mapping: Any) -> Any:
    _ok(
        c.post(
            f"{BASE}/files/{source['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        ),
        200,
    )
    return _ok(c.post(f"{BASE}/files/{source['id']}/apply", headers=h))


def test_import_end_of_previous_owner_is_restored_by_undo(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "an09admin"))
    props = _stage(
        client,
        h,
        "properties",
        "objekte.xlsx",
        _xlsx([["Nr", "Name", "Typ"], ["901", "AN09 Haus", "Miete"]]),
        XLSX,
    )
    prop_map = _mapping(
        client,
        h,
        "properties",
        {"number": "Nr", "name": "Name", "management_type": "Typ"},
        {"management_type": {"Miete": "rental"}},
    )
    _apply(client, h, props, prop_map)
    units = _stage(
        client,
        h,
        "units",
        "einheiten.xlsx",
        _xlsx([["Objekt", "Einheit", "Art"], ["901", "01", "Wohnung"]]),
        XLSX,
    )
    unit_map = _mapping(
        client,
        h,
        "units",
        {"property_number": "Objekt", "number": "Einheit", "unit_type": "Art"},
        {"unit_type": {"Wohnung": "apartment"}},
    )
    _apply(client, h, units, unit_map)
    contacts = _stage(
        client,
        h,
        "contacts",
        "adressbuch.csv",
        f"ID;Art;Name\nN1;P;Neueigner{RUN}\n".encode(),
        "text/csv",
    )
    contact_map = _mapping(
        client,
        h,
        "contacts",
        {"external_id": "ID", "kind": "Art", "last_name": "Name"},
        {"kind": {"P": "person"}},
    )
    _apply(client, h, contacts, contact_map)

    listed = _ok(client.get("/api/v1/properties", params={"q": "901"}, headers=h), 200)
    items = listed["items"] if isinstance(listed, dict) else listed
    prop = next(p for p in items if p["number"] == "901")
    owners_url = f"/api/v1/properties/{prop['id']}/owners"
    old_party, _ = _party(client, h, "Alteigner")
    _ok(
        client.post(owners_url, json={"party_id": old_party, "valid_from": "2020-01-01"}, headers=h)
    )

    owners = _stage(
        client,
        h,
        "ownerships",
        "eigentuemer.xlsx",
        _xlsx(
            [
                ["Objekt", "Einheit", "Kontakt", "Beginn", "Grundbuch"],
                ["901", "01", "N1", "01.07.2024", "01.07.2024"],
            ]
        ),
        XLSX,
    )
    owner_map = _mapping(
        client,
        h,
        "ownerships",
        {
            "property_number": "Objekt",
            "unit_number": "Einheit",
            "contact_external_id": "Kontakt",
            "start_date": "Beginn",
            "title_transfer_date": "Grundbuch",
        },
    )
    applied = _apply(client, h, owners, owner_map)
    assert applied["report"]["apply"]["counts"] == {"created": 1}

    def _current() -> dict[str, Any]:
        rows = _ok(client.get(owners_url, headers=h), 200)
        return {str(r["party_id"]): r for r in rows}

    after = _current()
    assert old_party not in after  # ended 30.06.2024 by the import
    assert len(after) == 1

    undone = _ok(client.post(f"/api/v1/imports/{applied['import_run_id']}/undo", headers=h), 200)
    assert undone["status"] == "undone"
    restored = _current()
    assert list(restored) == [old_party]  # new owner removed
    assert restored[old_party]["valid_to"] is None  # previous end restored
