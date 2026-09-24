"""PÜ01, PÜ02, PÜ04 hints on incoming invoices (findings only, no automatic decision):
recipient differs from the legal entity of the ledger, missing order or contract reference,
same amount and day under another number, one original document on two invoices."""

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
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pue-{RUN}", name=f"PUE {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("pueadmin"), display_name="pue", password=PASSWORD
        )
        world.users["pueadmin"] = uid
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_invoice_hints(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "pueadmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "793", "name": "Prüfhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": hoa["id"], "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Dachdecker {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("rechnung.pdf", b"%PDF-1.4 r", "application/pdf")},
            headers=h,
        ),
        201,
    )["id"]
    base = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": "D-1",
        "invoice_date": "2026-03-01",
        "service_from": "2026-02-01",
        "net": "100.00",
        "vat": "19.00",
        "gross": "119.00",
        "document_id": doc,
        "recipient_name": f"  {hoa['name'].upper()}  c/o Verwaltung ",
        "lines": [
            {
                "account_id": acc["043000"],
                "net": "100.00",
                "vat_percent": "19",
                "vat": "19.00",
                "text": "Reparatur",
            }
        ],
    }
    first = _ok(client.post(f"{A}/invoices", json=base, headers=h), 201)
    # Recipient contains the community name (case and spaces ignored): no recipient finding.
    assert not any("Rechnungsempfänger" in f for f in first["findings"])
    assert any("Auftrags- oder Vertragsbezug" in f for f in first["findings"])

    second = _ok(
        client.post(
            f"{A}/invoices",
            json={**base, "number": "D-2", "recipient_name": "Fremde Eigentümer GbR"},
            headers=h,
        ),
        201,
    )
    joined = " | ".join(second["findings"])
    assert "Rechnungsempfänger weicht" in joined
    assert "gleicher Betrag und Tag" in joined
    assert "Originalbeleg ist bereits" in joined
    assert second["review_status"] == "open"  # hints never decide
