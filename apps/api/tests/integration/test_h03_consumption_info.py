"""Rule H03 (§ 6a HeizkostenV, D26): monthly consumption information per unit.

Covered: switches (tenant and property, default off, run refused without them), manual run
per month and idempotency (rerun stores nothing twice), missing data flags (unit without
metering assignment, estimated hot water), the operator's verification list in the CRM only,
the portal lock until the template is verified (403), scope to the own unit (other unit 404,
other tenant 403), notification only with the switch, the job's due day check and the
permission of the CRM list (accounting:read)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.billing import consumption_info
from mhvp.billing.consumption_info_tasks import run_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"h03a-{RUN}", name=f"H03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"h03b-{RUN}", name=f"H03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("h03admin", a, "tenant_admin"),
            ("h03clerk", a, "clerk_no_accounting"),
            ("h03adminb", b, "tenant_admin"),
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _portal_user(
    c: TestClient, h: dict[str, str], world: World, name: str, contact_id: str
) -> dict[str, str]:
    inv = _ok(
        c.post(
            f"{PA}/accounts",
            json={"contact_id": contact_id, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return bearer(login(c, world, name))


def _owner(c: TestClient, h: dict[str, str], property_id: str) -> None:
    owner, _ = _party(c, h, "Vermieter", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{property_id}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )


def _tenancy(c: TestClient, h: dict[str, str], unit: str, party: str, start: str) -> str:
    return str(
        _ok(
            c.post(
                "/api/v1/contracts",
                json={"kind": "tenancy", "unit_id": unit, "party_id": party, "start_date": start},
                headers=h,
            ),
            201,
        )["id"]
    )


async def _seed_metering(
    settings: Any, tenant_id: uuid.UUID, property_id: str, unit_id: str
) -> None:
    """Metering rows for unit 01 only: August 2025 heating (actual) and hot water (estimated),
    July 2025 heating (previous month). Written through the ORM under RLS."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.metering.models import (
        MeteringConnection,
        MeteringConsumptionValue,
        MeteringExternalBillingUnit,
        MeteringPropertyAssignment,
        MeteringUnitAssignment,
    )

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            conn = MeteringConnection(
                tenant_id=tenant_id,
                display_name="Messdienst Test",
                provider_code="test",
                environment="test",
            )
            session.add(conn)
            await session.flush()
            ebu = MeteringExternalBillingUnit(
                tenant_id=tenant_id, connection_id=conn.id, external_number="EXT-1"
            )
            session.add(ebu)
            await session.flush()
            pa = MeteringPropertyAssignment(
                tenant_id=tenant_id,
                connection_id=conn.id,
                property_id=uuid.UUID(property_id),
                external_billing_unit_id=ebu.id,
                service_scope="heating",
                valid_from=date(2025, 1, 1),
                status="confirmed",
            )
            session.add(pa)
            await session.flush()
            ua = MeteringUnitAssignment(
                tenant_id=tenant_id,
                property_assignment_id=pa.id,
                unit_id=uuid.UUID(unit_id),
                external_unit_number="NE-01",
                valid_from=date(2025, 1, 1),
                status="confirmed",
            )
            session.add(ua)
            await session.flush()
            for period_from, period_to, kind, value, value_kind in [
                (date(2025, 8, 1), date(2025, 8, 31), "heating", Decimal("123.5"), "actual"),
                (date(2025, 8, 1), date(2025, 8, 31), "hot_water", Decimal("2.4"), "estimated"),
                (date(2025, 7, 1), date(2025, 7, 31), "heating", Decimal("80"), "actual"),
            ]:
                session.add(
                    MeteringConsumptionValue(
                        tenant_id=tenant_id,
                        property_assignment_id=pa.id,
                        unit_assignment_id=ua.id,
                        period_from=period_from,
                        period_to=period_to,
                        kind=kind,
                        unit_of_measure="kWh" if kind == "heating" else "m3",
                        reading_type="period_consumption",
                        source="test",
                        value=value,
                        value_kind=value_kind,
                    )
                )
    finally:
        await engine.dispose()


def test_h03_consumption_info(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    c = client
    h = bearer(login(c, world, "h03admin"))
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "773", "name": "Verbrauchshaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    pid = prop["id"]
    _owner(c, h, pid)
    building = _ok(
        c.post(f"/api/v1/properties/{pid}/buildings", json={"name": "Haus"}, headers=h), 201
    )["id"]
    units = {}
    for number in ("01", "02"):
        units[number] = _ok(
            c.post(
                f"/api/v1/properties/{pid}/units",
                json={"building_id": building, "number": number, "unit_type": "apartment"},
                headers=h,
            ),
            201,
        )["id"]
    party1, contact1 = _party(c, h, "MieterEins")
    party2, contact2 = _party(c, h, "MieterZwei")
    _tenancy(c, h, units["01"], party1, "2024-01-01")
    _tenancy(c, h, units["02"], party2, "2025-09-01")  # starts after August 2025
    asyncio.run(_seed_metering(_settings(database, redis_url), world.tenant_a, pid, units["01"]))
    base = f"/api/v1/properties/{pid}/consumption-info"

    # Default off: run refused, list empty, property switch off.
    listing = _ok(c.get(base, headers=h))
    assert listing["settings"] == {
        "property_id": pid,
        "enabled": False,
        "tenant_enabled": False,
        "notifications_enabled": False,
        "template_verified": False,
        "rule_version": consumption_info.RULE_VERSION,
    }
    assert listing["months"] == []
    assert listing["rows"] == []
    assert {t["status"] for t in listing["to_verify"]} == {"zu verifizieren"}
    assert c.post(f"{base}/run", json={"month": "2025-08-15"}, headers=h).status_code == 422
    _ok(c.patch("/api/v1/tenant/settings", json={"consumption_info_enabled": True}, headers=h))
    assert c.post(f"{base}/run", json={"month": "2025-08-15"}, headers=h).status_code == 422
    assert _ok(c.put(f"{base}/settings", json={"enabled": True}, headers=h))["enabled"] is True

    # Manual run for August 2025: unit 01 with values, unit 02 without assignment.
    first = _ok(c.post(f"{base}/run", json={"month": "2025-08-15"}, headers=h))
    assert first["month"] == "2025-08-01"
    assert first["created"] == 2
    assert first["skipped"] == 0
    assert first["notified"] == 0
    again = _ok(c.post(f"{base}/run", json={"month": "2025-08-01"}, headers=h))
    assert again["created"] == 0
    assert again["skipped"] == 2
    listing = _ok(c.get(base, headers=h))
    assert [m["month"] for m in listing["months"]] == ["2025-08-01"]
    assert listing["months"][0]["units"] == 2
    assert listing["months"][0]["incomplete"] == 1
    by_unit = {r["unit_id"]: r for r in listing["rows"]}
    row1, row2 = by_unit[units["01"]], by_unit[units["02"]]
    assert row1["values"]["heating"] == {
        "value": "123.5",
        "unit_of_measure": "kWh",
        "kind": "actual",
        "source": "metering:test",
    }
    assert row1["values"]["hot_water"]["kind"] == "estimated"
    assert row1["values"]["previous_month"]["heating"]["value"] == "80"
    assert row1["values"]["property_average"]["heating"]["value"] == "123.50"
    assert "hot_water_estimated" in row1["missing"]
    assert "no_previous_year" in row1["missing"]
    assert "heating_missing" not in row1["missing"]
    assert "no_unit_assignment" in row2["missing"]
    assert "heating_missing" in row2["missing"]
    assert "no_tenancy" in row2["missing"]
    assert row1["to_verify"][0]["status"] == "zu verifizieren"
    assert row1["trigger"] == "manual"
    assert row1["snapshot_hash"]

    # Portal: locked until the template is verified; then only the own unit.
    t1 = _portal_user(c, h, world, "h03t1", contact1["id"])
    t2 = _portal_user(c, h, world, "h03t2", contact2["id"])
    assert c.get(f"{P}/consumption-info", headers=t1).status_code == 403
    _ok(
        c.patch(
            "/api/v1/tenant/settings",
            json={"consumption_info_template_verified": True},
            headers=h,
        )
    )
    own = _ok(c.get(f"{P}/consumption-info", headers=t1))
    assert [r["unit_id"] for r in own] == [units["01"]]
    assert "to_verify" not in own[0]["values"]
    assert own[0]["estimated"] == ["hot_water"]
    assert "missing" not in own[0]
    assert "data_basis" not in own[0]
    detail = _ok(c.get(f"{P}/consumption-info/{own[0]['id']}", headers=t1))
    assert "Verbrauchsinformation 08.2025" in detail["snapshot_html"]
    assert "verifizieren" not in detail["snapshot_html"]
    assert "123,50 kWh" in detail["snapshot_html"]
    assert "geschätzt" in detail["snapshot_html"]
    # Tenant 2 moved in on 01.09.2025: August is outside the contract, the other unit is 404.
    assert _ok(c.get(f"{P}/consumption-info", headers=t2)) == []
    assert c.get(f"{P}/consumption-info/{own[0]['id']}", headers=t2).status_code == 404
    # No notification without the switch.
    assert [
        n for n in _ok(c.get(f"{P}/notifications", headers=t1)) if n["kind"] == "consumption_info"
    ] == []

    # Notification switch on: September 2025 notifies tenant 1 (and tenant 2, now in unit 02).
    _ok(
        c.patch(
            "/api/v1/tenant/settings",
            json={"consumption_info_notifications_enabled": True},
            headers=h,
        )
    )
    september = _ok(c.post(f"{base}/run", json={"month": "2025-09-30"}, headers=h))
    assert september["created"] == 2
    assert september["notified"] == 2
    notes = [
        n for n in _ok(c.get(f"{P}/notifications", headers=t1)) if n["kind"] == "consumption_info"
    ]
    assert len(notes) == 1
    assert notes[0]["href"] == "/verbrauch"
    assert [r["month"] for r in _ok(c.get(f"{P}/consumption-info", headers=t2))] == ["2025-09-01"]

    # Job: not due on a Saturday, due on the first working day (nothing new: idempotent).
    settings = _settings(database, redis_url)
    assert asyncio.run(run_once(settings, date(2025, 10, 4)))["not_due"] == 1
    before = len(_ok(c.get(base, headers=h))["rows"])
    totals = asyncio.run(run_once(settings, date(2025, 10, 1)))
    assert totals["not_due"] == 0
    assert totals["skipped"] >= 2  # September of this property already stored
    # Other tenants of the shared test database may add rows; this property gains none.
    assert len(_ok(c.get(base, headers=h))["rows"]) == before

    # Permissions and tenant separation.
    clerk = bearer(login(c, world, "h03clerk"))
    assert c.get(base, headers=clerk).status_code == 403
    # clerk_no_accounting holds properties:update: the switch is allowed, the list is not.
    assert _ok(c.put(f"{base}/settings", json={"enabled": True}, headers=clerk))["enabled"] is True
    assert c.get(base, headers=t1).status_code == 403  # portal account, no CRM permission
    assert c.post(f"{base}/run", json={"month": "2025-10-01"}, headers=t1).status_code == 403
    hb = bearer(login(c, world, "h03adminb"))
    assert c.get(base, headers=hb).status_code == 404
    other_party, other_contact = _party(c, hb, "MieterFremd")
    prop_b = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "774", "name": "Fremdhaus", "management_type": "rental"},
            headers=hb,
        ),
        201,
    )["id"]
    _owner(c, hb, prop_b)
    building_b = _ok(
        c.post(f"/api/v1/properties/{prop_b}/buildings", json={"name": "Haus"}, headers=hb), 201
    )["id"]
    unit_b = _ok(
        c.post(
            f"/api/v1/properties/{prop_b}/units",
            json={"building_id": building_b, "number": "01", "unit_type": "apartment"},
            headers=hb,
        ),
        201,
    )["id"]
    _tenancy(c, hb, unit_b, other_party, "2024-01-01")
    tb = _portal_user(c, hb, world, "h03tb", other_contact["id"])
    assert c.get(f"{P}/consumption-info", headers=tb).status_code == 403  # tenant B: off
    assert c.get(f"{P}/consumption-info/{own[0]['id']}", headers=tb).status_code == 403
