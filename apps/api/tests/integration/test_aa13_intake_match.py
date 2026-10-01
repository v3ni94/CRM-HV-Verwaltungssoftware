"""AA13 (GA10-01 to GA10-03): intake assignment over unit, contract, IBAN and customer number;
follow-up proposals after acceptance; direct filing behind the tenant switch (default off)."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents import intake
from mhvp.documents.models import Document
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.platform.models import TenantSettings
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _property, _unit

pytestmark = pytest.mark.integration
BUCKET = "mhvp-aa13"
IBAN = "DE89370400440532013000"
P = "/api/v1/documents/intake-proposals"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa13a-{RUN}", name=f"AA13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa13b-{RUN}", name=f"AA13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aaadmin", a, "tenant_admin"),
            ("aaread", a, "caretaker"),
            ("aaother", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for i, line in enumerate(lines):
        canvas.drawString(72, 720 - 16 * i, line)
    canvas.save()
    return buffer.getvalue()


def _upload(client: TestClient, h: dict[str, str], name: str, *lines: str) -> str:
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (name, _pdf(*lines), "application/pdf")},
            headers=h,
        )
    )
    return str(doc["id"])


def _analyse_and_propose(
    database: Database, redis_url: str, tenant: Any, doc_id: str, switch: dict[str, Any] | None
) -> dict[str, Any]:
    settings = _settings(database, redis_url)

    async def go() -> dict[str, Any]:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant) as session:
                if switch is not None:
                    row = await session.scalar(select(TenantSettings))
                    assert row is not None
                    row.sources = {**row.sources, intake.AUTO_FILE_KEY: switch}
                document = await session.get(Document, __import__("uuid").UUID(doc_id))
                assert document is not None
                result = await intake.analyse(session, tenant, document, source="mailbox")
                proposal = await intake.propose(session, tenant, document, result)
                assert proposal is not None
                return {"result": result.as_dict(), "decision": proposal.decision.value}
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _setup(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    prop = _property(client, h, "731", "rental")
    unit = _unit(client, h, prop["id"], "12")
    owner = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"V {RUN} GmbH"}, headers=h
        )
    )
    owner_party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h)
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner_party["id"], "valid_from": "2020-01-01"},
            headers=h,
        )
    )
    tenant = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Tina",
                "last_name": f"Mieter{RUN}",
                "identifiers": [{"kind": "customer_number", "value": "KD-47110"}],
                "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01", "is_default": True}],
            },
            headers=h,
        )
    )
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": tenant["id"]}]}, headers=h)
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party["id"],
                "start_date": "2020-01-01",
            },
            headers=h,
        )
    )
    return {
        "property": prop["id"],
        "unit": unit,
        "contact": tenant["id"],
        "contract": contract["id"],
    }


def test_assignment_followups_and_auto_file(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "aaadmin"))
    ids = _setup(client, h)

    # GA10-01: unit, contract (valid on document date), IBAN and customer number.
    doc1 = _upload(
        client,
        h,
        "Rechnung Heizung.pdf",
        "Rechnung Nr. 4711",
        "Objekt 731, Einheit 12",
        "Kundennummer KD-47110",
        "IBAN DE89 3704 0044 0532 0130 00",
    )
    first = _analyse_and_propose(database, redis_url, world.tenant_a, doc1, None)
    out = first["result"]
    assert first["decision"] == "pending", "direct filing is off by default"
    assert out["property_id"] == ids["property"]
    assert out["unit_id"] == ids["unit"]
    assert out["unit_number"].endswith("/12")
    assert out["contract_id"] == ids["contract"]
    assert out["contact_id"] == ids["contact"]
    reasons = " ".join(out["reasons"])
    assert "IBAN endet auf 3000" in reasons or "Kundennummer KD-47110" in reasons

    # GA10-02: accept links unit and contract and proposes the invoice follow-up only.
    pending = [p for p in _ok(client.get(P, headers=h), 200)["data"] if p["document_id"] == doc1]
    accepted = _ok(client.post(f"{P}/{pending[0]['id']}/accept", headers=h), 200)
    assert accepted["decision"] == "accepted"
    assert accepted["final"]["unit_id"] == ids["unit"]
    assert accepted["final"]["contract_id"] == ids["contract"]
    followups = {f["kind"]: f for f in accepted["final"]["followups"]}
    assert followups["invoice"]["status"] == "proposed"
    confirmed = _ok(client.post(f"{P}/{accepted['id']}/followups/invoice/confirm", headers=h), 200)
    assert {f["kind"]: f["status"] for f in confirmed["final"]["followups"]}[
        "invoice"
    ] == "confirmed"
    again = client.post(f"{P}/{accepted['id']}/followups/invoice/confirm", headers=h)
    assert again.status_code == 409
    assert (
        client.post(f"{P}/{accepted['id']}/followups/ticket/confirm", headers=h).status_code == 404
    )

    # Read right only: 403 on confirm; other tenant: 404.
    hr = bearer(login(client, world, "aaread"))
    assert (
        client.post(f"{P}/{accepted['id']}/followups/invoice/confirm", headers=hr).status_code
        == 403
    )
    ho = bearer(login(client, world, "aaother"))
    assert (
        client.post(f"{P}/{accepted['id']}/followups/invoice/confirm", headers=ho).status_code
        == 404
    )

    # GA10-03: switch on, one clear object gets filed directly and can be reverted.
    doc2 = _upload(client, h, "Schreiben.pdf", "Hinweis zu Objekt 731 und Hausordnung")
    second = _analyse_and_propose(
        database, redis_url, world.tenant_a, doc2, {"enabled": True, "threshold": 0.9}
    )
    assert second["decision"] == "accepted"
    link_doc = _ok(client.get(f"/api/v1/documents/{doc2}", headers=h), 200)
    assert any(link["entity_id"] == ids["property"] for link in link_doc["links"])
    auto = next(
        p
        for p in _ok(client.get(P, params={"decision": "accepted"}, headers=h), 200)["data"]
        if p["document_id"] == doc2
    )
    assert auto["final"]["auto_filed"] is True
    assert client.post(f"{P}/{auto['id']}/revert-auto", headers=hr).status_code == 403
    reverted = _ok(client.post(f"{P}/{auto['id']}/revert-auto", headers=h), 200)
    assert reverted["decision"] == "pending"
    link_doc = _ok(client.get(f"/api/v1/documents/{doc2}", headers=h), 200)
    assert not any(link["entity_id"] == ids["property"] for link in link_doc["links"])
