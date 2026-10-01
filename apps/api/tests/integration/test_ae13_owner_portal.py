"""AE13 (P13-01, M21-06): owner portal switches. Rental income view off by default and only
for own units; ticket scope none, released (default) or property. Other tenant keeps its own
switches, read only role 403, bad value 422, unknown query parameter 422."""

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
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
F = "/api/v1/portal-admin/features"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae13a-{RUN}", name=f"AE13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae13b-{RUN}", name=f"AE13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae13admin", a, "tenant_admin"),
            ("ae13adminb", b, "tenant_admin"),
            ("ae13ro", a, "read_only"),
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


def _owner(c: TestClient, h: dict[str, str], world: World, no: str, login_name: str) -> Any:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AE13-WEG {no}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, weg["id"], "01")
    party, _ = _party(c, h, f"AE13Eigentuemer{no}")
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
    portal = _portal_user(c, h, world, login_name, _contact_of(c, h, party))
    return weg["id"], portal


def test_owner_switches(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae13admin"))
    hb = bearer(login(client, world, "ae13adminb"))
    ro = bearer(login(client, world, "ae13ro"))
    prop, owner = _owner(client, ha, world, "931", "ae13own1")

    defaults = _ok(client.get(F, headers=ha))
    assert defaults["owner_rental_income_enabled"] is False
    assert defaults["owner_ticket_scope"] == "released"
    income = _ok(client.get(f"{P}/owner/rental-income", headers=owner))
    assert income["enabled"] is False
    assert income["items"] == []

    for title, visible in (("AE13 frei", ["owner"]), ("AE13 intern", [])):
        _ok(
            client.post(
                "/api/v1/tickets",
                json={"title": title, "property_id": prop, "visible_for": visible},
                headers=ha,
            ),
            201,
        )
    titles = {t["title"] for t in _ok(client.get(f"{P}/owner/tickets", headers=owner))}
    assert titles == {"AE13 frei"}

    # validation, permission, unknown parameter
    assert client.patch(F, json={"owner_ticket_scope": "all"}, headers=ha).status_code == 422
    assert client.patch(F, json={"owner_ticket_scope": "none"}, headers=ro).status_code == 403
    assert client.get(f"{P}/owner/tickets?x=1", headers=owner).status_code in (401, 422)

    _ok(client.patch(F, json={"owner_ticket_scope": "property"}, headers=ha))
    titles = {t["title"] for t in _ok(client.get(f"{P}/owner/tickets", headers=owner))}
    assert titles == {"AE13 frei", "AE13 intern"}
    _ok(client.patch(F, json={"owner_ticket_scope": "none"}, headers=ha))
    assert _ok(client.get(f"{P}/owner/tickets", headers=owner)) == []

    patched = _ok(client.patch(F, json={"owner_rental_income_enabled": True}, headers=ha))
    assert patched["owner_rental_income_enabled"] is True
    income = _ok(client.get(f"{P}/owner/rental-income", headers=owner))
    assert income["enabled"] is True
    assert income["items"] == []  # no SEV unit

    # tenant separation: tenant B keeps its own defaults
    other = _ok(client.get(F, headers=hb))
    assert other["owner_rental_income_enabled"] is False
    assert other["owner_ticket_scope"] == "released"
