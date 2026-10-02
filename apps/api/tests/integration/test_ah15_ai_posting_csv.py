"""AH15 (GAG-23, GAG-24): endpoint tests for the AI posting switch and the AI posting proposal
of a bank transaction (7.4, 9.2) and for the custom CSV mappings per bank account (8, 6.4).

Covered: permission (read_only gets 403 on writes), tenant separation (another tenant gets
404 or an empty list), validation (422), the proposal stays blocked while the switch is off or
no provider is released, and even a successful AI run is a proposal only: the transaction is
not changed and no journal entry is created (rule 0.1.6, no active rule 7.4)."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.ai import providers
from mhvp.ai.providers import Completion
from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m11_banking import _camt, _ntry

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
A = "/api/v1/accounting"
BUCKET = "mhvp-ah15"
BANK = "DE02120300000000202051"
PAYER = "DE89370400440532013000"
MISSING = "00000000-0000-7000-8000-000000000000"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data: dict[str, Any] = {"proposals": [], "questions": []}
        return Completion(
            data=data,
            raw_text=json.dumps(data),
            tokens_in=100,
            tokens_out=50,
            model=kwargs["model"],
        )


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah15a-{RUN}", name=f"AH15 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah15b-{RUN}", name=f"AH15 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = [
            ("ah15admin", a, "tenant_admin"),
            ("ah15second", a, "tenant_admin"),
            ("ah15reader", a, "read_only"),
            ("ah15other", b, "tenant_admin"),
        ]
        for name, tenant, role in specs:
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


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str) -> str:
    doc = _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h), 201)
    return str(doc["id"])


def _bank_account(c: TestClient, h: dict[str, str], number: str) -> str:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AH15 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    return str(
        _ok(
            c.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": "hoa",
                    "iban": BANK,
                    "holder": "GdWE AH15",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def _transaction(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    bank_id = _bank_account(c, h, "151")
    hoa = next(
        a["legal_entity_id"] for a in _ok(c.get(f"{B}/accounts", headers=h)) if a["id"] == bank_id
    )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001211",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=h,
        ),
        201,
    )
    statement = _camt(
        "AH15-1",
        BANK,
        "0.00",
        "250.00",
        [_ntry("AH15T1", "250.00", "CRDT", "2026-01-05", PAYER, "Hausgeld Januar")],
    )
    doc = _upload(c, h, "ah15.xml", statement, "application/xml")
    _ok(c.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)
    (tx,) = _ok(c.get(f"{B}/transactions", headers=h))
    return tx  # type: ignore[no-any-return]


PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "large": {"model": "claude-opus-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
        "small": {"model": "claude-haiku-5", "input_eur_per_mtok": "1", "output_eur_per_mtok": "5"},
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


def test_ai_posting_switch_and_proposal(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    c = client
    admin = bearer(login(c, world, "ah15admin"))
    reader = bearer(login(c, world, "ah15reader"))
    other = bearer(login(c, world, "ah15other"))

    # Switch: default off with a reason, only tenant_settings:update may read or change it.
    state = _ok(c.get("/api/v1/ai/posting-enabled", headers=admin))
    assert state["enabled"] is False
    assert "ai_posting_enabled" in state["blocked_reason"]
    assert c.get("/api/v1/ai/posting-enabled", headers=reader).status_code == 403
    assert (
        c.put("/api/v1/ai/posting-enabled", json={"enabled": True}, headers=reader).status_code
        == 403
    )
    assert c.put("/api/v1/ai/posting-enabled", json={}, headers=admin).status_code == 422
    assert (
        c.put("/api/v1/ai/posting-enabled", json={"enabled": "ja"}, headers=admin).status_code
        == 422
    )

    tx = _transaction(c, admin)
    url = f"{B}/transactions/{tx['id']}/ai-posting"

    # Blocked while the switch is off: nothing is queued, the list stays empty.
    blocked = c.post(url, headers=admin)
    assert blocked.status_code >= 400, blocked.text
    assert blocked.json()["code"] == "MHVP-AI-0001"
    empty = _ok(c.get(url, headers=admin))
    assert empty["proposals"] == []
    assert "keine Buchung" in empty["note"]
    assert c.post(url, headers=reader).status_code == 403
    assert _ok(c.get(url, headers=reader))["proposals"] == []

    # Switch on but no released provider: still blocked (DPA evidence required).
    on = _ok(c.put("/api/v1/ai/posting-enabled", json={"enabled": True}, headers=admin))
    assert on["enabled"] is True
    assert on["blocked_reason"] is not None
    assert c.post(url, headers=admin).json()["code"] == "MHVP-AI-0001"
    assert fake.calls == []

    # Tenant separation: another tenant sees neither the switch state nor the transaction.
    assert _ok(c.get("/api/v1/ai/posting-enabled", headers=other))["enabled"] is False
    assert c.get(url, headers=other).status_code == 404
    assert c.post(url, headers=other).status_code != 202
    assert c.get(f"{B}/transactions/{MISSING}/ai-posting", headers=admin).status_code == 404

    # Released provider (four eyes): the run yields a proposal only, nothing is posted.
    second = bearer(login(c, world, "ah15second"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second))
    assert _ok(c.get("/api/v1/ai/posting-enabled", headers=admin))["blocked_reason"] is None
    started = _ok(c.post(url, headers=admin), 202)
    assert "keine Buchung" in started["note"]
    assert len(fake.calls) == 1
    (after,) = _ok(c.get(f"{B}/transactions", headers=admin))
    assert after["status"] == tx["status"] == "new"
    assert after.get("journal_entry_id") is None
    assert _ok(c.get(f"{B}/transactions", params={"status": "booked"}, headers=admin)) == []
    # The other tenant still cannot start a run on this transaction.
    assert c.post(url, headers=other).status_code != 202

    # Switching off blocks again.
    off = _ok(c.put("/api/v1/ai/posting-enabled", json={"enabled": False}, headers=admin))
    assert off["enabled"] is False
    assert c.post(url, headers=admin).json()["code"] == "MHVP-AI-0001"


def test_csv_mappings(client: TestClient, world: World) -> None:
    c = client
    admin = bearer(login(c, world, "ah15admin"))
    reader = bearer(login(c, world, "ah15reader"))
    other = bearer(login(c, world, "ah15other"))
    account = _bank_account(c, admin, "152")
    mapping = {
        "booking_date": "Buchungstag",
        "amount": "Betrag",
        "purpose": "Verwendungszweck",
    }
    body = {"property_bank_account_id": account, "label": "Sparkasse", "mapping": mapping}

    assert c.post(f"{B}/csv-mappings", json=body, headers=reader).status_code == 403
    assert c.post(f"{B}/csv-mappings", json={**body, "label": ""}, headers=admin).status_code == 422
    assert (
        c.post(f"{B}/csv-mappings", json={**body, "mapping": {}}, headers=admin).status_code == 422
    )
    created = _ok(c.post(f"{B}/csv-mappings", json=body, headers=admin), 201)
    assert created["label"] == "Sparkasse"
    assert created["property_bank_account_id"] == account
    _ok(c.post(f"{B}/csv-mappings", json={**body, "label": "Archiv"}, headers=admin), 201)

    params = {"property_bank_account_id": account}
    listed = _ok(c.get(f"{B}/csv-mappings", params=params, headers=reader))
    assert [m["label"] for m in listed] == ["Archiv", "Sparkasse"]
    assert c.get(f"{B}/csv-mappings", headers=admin).status_code == 422
    assert c.get(f"{B}/csv-mappings", params={**params, "x": "1"}, headers=admin).status_code == 422
    # Tenant separation: RLS hides the mappings of tenant A.
    assert _ok(c.get(f"{B}/csv-mappings", params=params, headers=other)) == []


def test_csv_mapping_foreign_account_rejected(client: TestClient, world: World) -> None:
    """A mapping must not reference the bank account of another tenant."""
    c = client
    admin = bearer(login(c, world, "ah15admin"))
    other = bearer(login(c, world, "ah15other"))
    account = _bank_account(c, admin, "153")
    body = {
        "property_bank_account_id": account,
        "label": "Fremd",
        "mapping": {"booking_date": "Datum", "amount": "Betrag"},
    }
    assert c.post(f"{B}/csv-mappings", json=body, headers=other).status_code == 404
    body["property_bank_account_id"] = MISSING
    assert c.post(f"{B}/csv-mappings", json=body, headers=admin).status_code == 404
