"""AF02 (GAB-02, GAB-03, GAE-23): scheduled EBICS C53 fetch task with the in memory bank
double (no network), the sync protocol fields, and the INI/HIA letter as PDF. Own world with
prefix af02."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking import ebics_keys, ebics_transport, tasks
from mhvp.banking.ebics_transport import EbicsTransportError
from mhvp.main import create_app
from mhvp.platform import services
from tests.ebics_fake import FakeEbicsBank, c53_zip
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.unit.test_ae23_ebics import camt

pytestmark = pytest.mark.integration
E = "/api/v1/banking/ebics"
IBAN = "DE02500105170137075030"
COMPANY = {
    "name": "AF02 Testverwaltung GmbH",
    "legal_form": "GmbH",
    "street": "Teststraße 1",
    "postal_code": "40000",
    "city": "Teststadt",
    "register_court": "Amtsgericht Teststadt",
    "register_number": "HRB 1",
    "management": ["Test Person"],
    "management_title": "Geschäftsführer",
}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af02a-{RUN}", name=f"AF02 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af02b-{RUN}", name=f"AF02 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af02admin", a, "tenant_admin"),
            ("af02second", a, "tenant_admin"),
            ("af02reader", a, "read_only"),
            ("af02other", b, "tenant_admin"),
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
def bank(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEbicsBank]:
    monkeypatch.setattr(ebics_keys, "STRICT_FROM", date(2099, 1, 1))
    fake = FakeEbicsBank()
    ebics_transport.set_transport_factory(lambda: fake)
    try:
        yield fake
    finally:
        ebics_transport.set_transport_factory(None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ready_subscriber(client: TestClient, h: dict[str, str], h2: dict[str, str]) -> str:
    _ok(client.put(f"{E}/settings", json={"enabled": True}, headers=h))
    body = {
        "label": "AF02 Hausbank",
        "host_id": "HOSTAF02",
        "partner_id": f"P{RUN}"[:30],
        "ebics_user_id": "UAF02",
        "url": "https://ebics.bank.example/ebicsweb",
        "ebics_version": "3.0",
        "signature_version": "A006",
        "key_bits": 2048,
    }
    sid = str(_ok(client.post(f"{E}/subscribers", json=body, headers=h), 201)["id"])
    _ok(client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h))
    signer = ebics_keys.generate_key_pair(2048)
    _ok(
        client.post(
            f"{E}/subscribers/{sid}/signature-key",
            json={"public_key_pem": signer.public_pem},
            headers=h,
        )
    )
    _ok(client.post(f"{E}/subscribers/{sid}/ini", headers=h))
    _ok(client.post(f"{E}/subscribers/{sid}/hia", headers=h))
    _ok(
        client.post(
            f"{E}/subscribers/{sid}/activation", json={"activated_on": "2026-09-30"}, headers=h
        )
    )
    sub = _ok(client.post(f"{E}/subscribers/{sid}/hpb", headers=h))
    bank_keys = {k["usage"]: k for k in sub["keys"] if k["owner"] == "bank"}
    right = {
        "authentication_hash": bank_keys["authentication"]["letter_hash"],
        "encryption_hash": bank_keys["encryption"]["letter_hash"],
    }
    assert (
        _ok(client.post(f"{E}/subscribers/{sid}/bank-keys/verify", json=right, headers=h2))[
            "status"
        ]
        == "ready"
    )
    return sid


def _property_account(client: TestClient, h: dict[str, str]) -> None:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "902", "name": "Objekt AF02", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": IBAN,
                "holder": "GdWE AF02",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )


def test_ebics_fetch_task_letter_pdf_and_runs(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    bank: FakeEbicsBank,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "af02admin"))
    h2 = bearer(login(client, world, "af02second"))
    r = bearer(login(client, world, "af02reader"))
    o = bearer(login(client, world, "af02other"))
    sid = _ready_subscriber(client, h, h2)

    # GAE-23: letter as PDF on the tenant letterhead
    assert client.get(f"{E}/subscribers/{sid}/letters.pdf", headers=r).status_code == 422
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pdf = client.get(f"{E}/subscribers/{sid}/letters.pdf", headers=r)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"{E}/subscribers/{sid}/letters.pdf", headers=o).status_code == 404

    # GAB-02: the task imports like the manual download, idempotent on repetition
    _property_account(client, h)
    bank.zip_content = c53_zip(
        {
            f"2026-02-01_C53_{IBAN}_EUR_000001.xml": camt(
                f"A{RUN}", IBAN, [(f"F1{RUN}", "10.00", "2026-01-15")]
            )
        }
    )
    tenant = world.tenant_a
    sub_uuid = uuid.UUID(sid)
    first = asyncio.run(tasks._ebics_fetch_once(settings, tenant, sub_uuid))
    assert first["new"] == 1
    assert "error" not in first
    assert bank.downloads[-1] == ("EOP/DE//camt.053/ZIP", None, None)
    again = asyncio.run(tasks._ebics_fetch_once(settings, tenant, sub_uuid))
    assert again["new"] == 0
    assert again["duplicates"] == 1

    # bank error: transient, failed order and failed sync run
    bank.fail_next = EbicsTransportError("Bank nicht erreichbar", code="061001")
    failed = asyncio.run(tasks._ebics_fetch_once(settings, tenant, sub_uuid))
    assert failed["error"] == "MHVP-BANK-0056"
    assert tasks.is_transient_ebics_error(failed["error"])

    # no transport: clean error code, nothing sent
    ebics_transport.set_transport_factory(None)
    calls = len(bank.downloads)
    none = asyncio.run(tasks._ebics_fetch_once(settings, tenant, sub_uuid))
    assert none["error"] == "MHVP-BANK-0050"
    assert not tasks.is_transient_ebics_error(none["error"])
    assert len(bank.downloads) == calls

    # beat: only tenants with the switch on and ready subscribers are queued
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(tasks.ebics_fetch, "delay", lambda *a: queued.append(a))
    totals = asyncio.run(tasks.ebics_scheduled_fetch_once(settings))
    assert (str(tenant), sid) in queued
    assert all(t != str(world.tenant_b) for t, _ in queued)
    assert totals["queued"] >= 1

    # GAB-03: sync protocol with time, connection and status
    runs = _ok(client.get("/api/v1/banking/runs", headers=r))
    ebics = [x for x in runs if x["source"] == "ebics:C53"]
    assert {x["status"] for x in ebics} >= {"failed"}
    assert all(x["created_at"] and "connection_id" in x for x in ebics)
    assert any("MHVP-BANK-0050" in e for x in ebics for e in x["errors"])
    assert all(
        x["source"] != "ebics:C53" for x in _ok(client.get("/api/v1/banking/runs", headers=o))
    )
    assert client.get("/api/v1/banking/runs?x=1", headers=r).status_code == 422
