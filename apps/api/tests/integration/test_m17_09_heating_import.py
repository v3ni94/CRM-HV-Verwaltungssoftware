"""M17-09 metering service import over the API: CSV with column map, user mapping, sum and CO2
check (existing step model: 3.400 kg / 100 m2 = 34 kg/m2 -> tenant 50 %, landlord 50,00 EUR of
100,00 EUR), duplicate check against the invoice book, feed into a draft statement.
Expected fed amounts: 1.300,00 - 30,00 = 1.270,00; 350,00 - 5,00 = 345,00;
650,00 - 15,00 = 635,00; total 2.250,00 EUR."""

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

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m17_heating import _setup

pytestmark = pytest.mark.integration
P = "/api/v1/billing/heating-cost-imports"
S = "/api/v1/statements"
CSV = (
    "Nutzer;HZ Grund;HZ Verbrauch;WW Grund;WW Verbrauch;CO2 VM;CO2 MI\n"
    "1001;600,00;400,00;100,00;200,00;30,00;20,00\n"
    "1002;200,00;100,00;30,00;20,00;5,00;5,00\n"
    "1003;300,00;200,00;50,00;100,00;15,00;25,00\n"
)
MAP = {
    "user_number": "Nutzer",
    "heating_base": "HZ Grund",
    "heating_consumption": "HZ Verbrauch",
    "hot_water_base": "WW Grund",
    "hot_water_consumption": "WW Verbrauch",
    "co2_landlord": "CO2 VM",
    "co2_tenant": "CO2 MI",
}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"hci-{RUN}", name=f"HCI {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"hcib-{RUN}", name=f"HCIB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("hciadmin", a, "tenant_admin"),
            ("hciclerk", a, "clerk_no_accounting"),
            ("hciother", b, "tenant_admin"),
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
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


@pytest.fixture
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def _invoice(settings: Any, tenant: uuid.UUID, ledger: str, provider: str) -> None:
    from mhvp.accounting.models import Invoice, InvoiceKind
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
            session.add(
                Invoice(
                    tenant_id=tenant,
                    ledger_id=uuid.UUID(ledger),
                    provider_contact_id=uuid.UUID(provider),
                    kind=InvoiceKind.INVOICE,
                    number=f"HK-{RUN}",
                    invoice_date=date(2026, 3, 1),
                    service_from=date(2025, 1, 1),
                    service_to=date(2025, 12, 31),
                    net=Decimal("2300.00"),
                    vat=Decimal("0.00"),
                    gross=Decimal("2300.00"),
                )
            )
    finally:
        await engine.dispose()


def test_heating_cost_import_flow(client: TestClient, world: World, settings: Any) -> None:
    h = bearer(login(client, world, "hciadmin"))
    st_id, contracts = _setup(client, h)
    st = _ok(client.get(f"{S}/{st_id}", headers=h))
    prop = st["property_id"]
    units = {
        u["number"]: u["id"] for u in _ok(client.get(f"/api/v1/properties/{prop}/units", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Messdienst {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("hk.pdf", b"%PDF-1.4 Heizkosten", "application/pdf")},
            data={"links": f'[{{"entity_type": "property", "entity_id": "{prop}"}}]'},
            headers=h,
        ),
        201,
    )["id"]
    header = {
        "property_id": prop,
        "provider_contact_id": provider,
        "provider_name": "Messdienst Test",
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "document_total": "2300.00",
        "co2": {
            "building_kind": "residential",
            "costs": "100.00",
            "emissions_kg": "3400",
            "reference_area_m2": "100",
        },
    }
    # Validation 422 and authorization 403.
    assert client.post(P, json={**header, "period_to": "2024-12-31"}, headers=h).status_code == 422
    assert client.post(P, json={**header, "document_total": "1.001"}, headers=h).status_code == 422
    clerk = bearer(login(client, world, "hciclerk"))
    assert client.post(P, json=header, headers=clerk).status_code == 403

    imp = _ok(client.post(P, json=header, headers=h), 201)
    url = f"{P}/{imp['id']}"
    assert imp["status"] == "draft"

    # Tenant separation: the other tenant sees nothing.
    other = bearer(login(client, world, "hciother"))
    assert client.get(url, headers=other).status_code == 404
    assert _ok(client.get(P, headers=other)) == []

    r = _ok(
        client.post(
            f"{url}/csv",
            json={"content": CSV, "delimiter": ";", "decimal_comma": True, "column_map": MAP},
            headers=h,
        )
    )
    assert len(r["rows"]) == 3
    assert r["csv_meta"]["row_count"] == 3

    # Without original document and mapping the check stays draft.
    r = _ok(client.post(f"{url}/check", json={}, headers=h))
    assert r["status"] == "draft"
    findings = r["check_result"]["findings"]
    assert any("Originaldokument" in f for f in findings)
    assert any("keine Einheit" in f for f in findings)
    assert r["check_result"]["grand_total"] == "2300.00"
    assert r["check_result"]["co2"]["landlord"] == "50.00"

    # Apply before a successful check is refused.
    assert client.post(f"{url}/apply", json={"statement_id": st_id}, headers=h).status_code == 422

    _ok(client.put(url, json={**header, "document_id": doc}, headers=h))
    _ok(
        client.put(
            f"{url}/mapping",
            json={
                "mapping": {
                    "1001": {"unit_id": units["01"], "contract_id": contracts["a"]},
                    "1002": {"unit_id": units["02"], "contract_id": contracts["b"]},
                    "1003": {"unit_id": units["02"], "contract_id": contracts["c"]},
                }
            },
            headers=h,
        )
    )
    # Duplicate in the invoice book: same issuer and period -> needs a reason.
    asyncio.run(_invoice(settings, world.tenant_a, st["ledger_id"], provider))
    r = _ok(client.post(f"{url}/check", json={}, headers=h))
    assert r["status"] == "draft"
    assert [d["kind"] for d in r["check_result"]["duplicates"]] == ["invoice"]
    assert r["check_result"]["findings"] == [
        "Mögliche Doppelerfassung (Rechnungsbuch oder weiterer Import); Prüfung mit "
        "Begründung bestätigen."
    ]
    r = _ok(
        client.post(
            f"{url}/check",
            json={"duplicate_ack_reason": "Rechnung wird nicht separat umgelegt"},
            headers=h,
        )
    )
    assert r["status"] == "checked", r["check_result"]

    # Any edit sets it back to draft; recheck.
    _ok(client.put(f"{url}/mapping", json={"mapping": {}}, headers=h))
    assert _ok(client.get(url, headers=h))["status"] == "draft"
    _ok(
        client.post(
            f"{url}/check",
            json={"duplicate_ack_reason": "Rechnung wird nicht separat umgelegt"},
            headers=h,
        )
    )

    applied = _ok(client.post(f"{url}/apply", json={"statement_id": st_id}, headers=h))
    assert applied["status"] == "applied"
    assert applied["item"]["amount"] == "2250.00"
    items = _ok(client.get(f"{S}/{st_id}", headers=h))["cost_items"]
    fed = next(i for i in items if i["id"] == applied["item"]["id"])
    assert fed["heating"] is True
    assert sorted(fed["external_amounts"].values()) == ["1270.00", "345.00", "635.00"]

    # Locked after apply.
    assert client.put(f"{url}/mapping", json={"mapping": {}}, headers=h).status_code == 409
    assert client.post(f"{url}/apply", json={"statement_id": st_id}, headers=h).status_code == 422

    # A second import of the same provider and period is flagged as duplicate.
    second = _ok(client.post(P, json={**header, "document_id": doc}, headers=h), 201)
    r = _ok(client.post(f"{P}/{second['id']}/check", json={}, headers=h))
    kinds = sorted(d["kind"] for d in r["check_result"]["duplicates"])
    assert kinds == ["heating_cost_import", "invoice"]
