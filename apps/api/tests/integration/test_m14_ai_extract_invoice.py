"""M14 AI invoice extraction (6.4, 18 M14): extract_invoice run produces a proposal only, apply
creates the invoice as an open draft (never posts, rule 0.1.6/0.1.7), duplicate invoice number
and IBAN mismatch stay findings for the four eyes review already tested in test_m14_invoices.py,
tenant separation and authorization on the proposal, IBAN masked in the read proposal."""

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

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-ai-invoices"
KNOWN = "DE89370400440532013000"
OTHER = "DE75512108001245126199"


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
        self.queue: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = self.queue.pop(0) if self.queue else {"invoice": {}, "questions": []}
        return Completion(
            data=data,
            raw_text=json.dumps(data),
            tokens_in=500,
            tokens_out=200,
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
        a, _ = await services.provision_tenant(factory, slug=f"ivai-{RUN}", name=f"Belegki {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("iaadmin", "tenant_admin"), ("iasecond", "tenant_admin")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "large": {"model": "claude-opus-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"}
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str) -> str:
    doc = _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h), 201)
    return str(doc["id"])


def _setup_provider(c: TestClient, world: World) -> tuple[dict[str, str], dict[str, str]]:
    admin = bearer(login(c, world, "iaadmin"))
    second = bearer(login(c, world, "iasecond"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    assert c.post("/api/v1/ai/providers/anthropic/release", headers=second).status_code == 200
    return admin, second


def _setup_ledger(
    c: TestClient, h: dict[str, str], offset: int = 0
) -> tuple[str, dict[str, str], str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": str(700 + (int(RUN, 16) + offset) % 100),
                "name": "Belegki-Haus",
                "management_type": "hoa",
            },
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Belegki Handwerk {RUN} GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    return ledger, accounts, provider


def _extract(c: TestClient, h: dict[str, str], doc: str) -> dict[str, Any]:
    conversation = _ok(c.post("/api/v1/ai/conversations", json={}, headers=h), 201)
    return _ok(  # type: ignore[no-any-return]
        c.post(
            f"/api/v1/ai/conversations/{conversation['id']}/messages",
            json={"content": "Rechnung erfassen", "task": "extract_invoice", "document_ids": [doc]},
            headers=h,
        ),
        202,
    )


INVOICE_OUTPUT: dict[str, Any] = {
    "invoice": {
        "supplier_name": f"Belegki Handwerk {RUN} GmbH",
        "iban": KNOWN,
        "invoice_number": "RE-2026-042",
        "invoice_date": "2026-03-01",
        "due_date": "2026-03-15",
        "net": "500.00",
        "vat": "95.00",
        "gross": "595.00",
        "currency": "EUR",
        "discount_percent": None,
        "discount_until": None,
        "order_reference": "AUF-9",
        "property_number_guess": "Belegki-Haus",
        "warnings": [],
        "confidence": 0.87,
    },
    "questions": [],
}


def test_extract_invoice_proposal_and_apply_as_draft(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin, _second = _setup_provider(client, world)
    ledger, accounts, provider_contact = _setup_ledger(client, admin)
    doc = _upload(client, admin, "rechnung.txt", b"Rechnung RE-2026-042", "text/plain")

    fake.queue.append(INVOICE_OUTPUT)
    run = _extract(client, admin, doc)
    assert run["status"] == "succeeded"
    proposal_id = run["proposal_id"]
    assert proposal_id is not None

    read = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin))
    assert read["entity_type"] == "invoice"
    assert read["proposed"]["invoice"]["iban"] == f"...{KNOWN[-4:]}"  # masked (rule 0.1.6)
    assert read["proposed"]["invoice"]["invoice_number"] == "RE-2026-042"
    assert read["proposed"]["supplier_candidates"][0]["contact_id"] == provider_contact

    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply",
            json={
                "invoice": {
                    "ledger_id": ledger,
                    "provider_contact_id": provider_contact,
                    "number": "RE-2026-042",
                    "invoice_date": "2026-03-01",
                    "due_date": "2026-03-15",
                    "net": "500.00",
                    "vat": "95.00",
                    "gross": "595.00",
                    "payee_iban": KNOWN,  # confirmed independently by the reviewer, not copied
                    "document_id": doc,
                    "order_reference": "AUF-9",
                    "lines": [
                        {
                            "account_id": accounts["040100"],
                            "net": "500.00",
                            "vat_percent": "19",
                            "vat": "95.00",
                            "text": "Reparatur",
                        }
                    ],
                }
            },
            headers=admin,
        ),
        201,
    )
    invoice_id = applied["items"][0]["entity_id"]
    invoice = _ok(client.get(f"{A}/invoices/{invoice_id}", headers=admin))
    assert invoice["review_status"] == "open"  # draft: nothing reviewed, released or posted
    assert invoice["posting_status"] == "unposted"
    assert invoice["findings"] == ["Leistungszeitraum fehlt"]  # known IBAN, no duplicate yet

    # Second document, same invoice number and a different IBAN: both findings must show up.
    fake.queue.append({**INVOICE_OUTPUT, "invoice": {**INVOICE_OUTPUT["invoice"], "iban": OTHER}})
    doc2 = _upload(client, admin, "rechnung2.txt", b"Rechnung RE-2026-042 erneut", "text/plain")
    run2 = _extract(client, admin, doc2)
    proposal2 = _ok(client.get(f"/api/v1/ai/proposals/{run2['proposal_id']}", headers=admin))
    assert any("Doppelrechnung" in w for w in proposal2["proposed"]["warnings"])
    assert any("IBAN" in w for w in proposal2["proposed"]["warnings"])

    applied2 = _ok(
        client.post(
            f"/api/v1/ai/proposals/{run2['proposal_id']}/apply",
            json={
                "invoice": {
                    "ledger_id": ledger,
                    "provider_contact_id": provider_contact,
                    "number": "RE-2026-042",
                    "invoice_date": "2026-03-01",
                    "net": "500.00",
                    "vat": "95.00",
                    "gross": "595.00",
                    "payee_iban": OTHER,
                    "document_id": doc2,
                    "lines": [
                        {
                            "account_id": accounts["040100"],
                            "net": "500.00",
                            "vat_percent": "19",
                            "vat": "95.00",
                        }
                    ],
                }
            },
            headers=admin,
        ),
        201,
    )
    invoice2 = _ok(client.get(f"{A}/invoices/{applied2['items'][0]['entity_id']}", headers=admin))
    assert "Doppelrechnung" in " ".join(invoice2["findings"])
    assert "IBAN" in " ".join(invoice2["findings"])
    assert invoice2["review_status"] == "open"
    assert invoice2["iban_confirmed"] is False


def test_apply_requires_invoice_body_and_permission(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin, _second = _setup_provider(client, world)
    ledger, accounts, provider_contact = _setup_ledger(client, admin, offset=17)
    doc = _upload(client, admin, "r3.txt", b"Rechnung 3", "text/plain")
    fake.queue.append({**INVOICE_OUTPUT, "invoice": {**INVOICE_OUTPUT["invoice"], "iban": None}})
    run = _extract(client, admin, doc)
    proposal_id = run["proposal_id"]
    missing = client.post(f"/api/v1/ai/proposals/{proposal_id}/apply", json={}, headers=admin)
    assert missing.status_code == 422
    assert "Rechnung" in missing.json()["detail"]
    _ = (ledger, accounts, provider_contact)


def test_apply_blocks_non_eur_currency(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin, _second = _setup_provider(client, world)
    ledger, accounts, provider_contact = _setup_ledger(client, admin, offset=41)
    doc = _upload(client, admin, "usd.txt", b"Invoice in USD", "text/plain")
    fake.queue.append(
        {**INVOICE_OUTPUT, "invoice": {**INVOICE_OUTPUT["invoice"], "currency": "USD"}}
    )
    run = _extract(client, admin, doc)
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{run['proposal_id']}", headers=admin))
    assert any("Fremdwährung" in w for w in proposal["proposed"]["warnings"])  # M14: EUR only

    blocked = client.post(
        f"/api/v1/ai/proposals/{run['proposal_id']}/apply",
        json={
            "invoice": {
                "ledger_id": ledger,
                "provider_contact_id": provider_contact,
                "number": "RE-USD-1",
                "invoice_date": "2026-03-01",
                "net": "500.00",
                "vat": "95.00",
                "gross": "595.00",
                "currency": "USD",
                "lines": [
                    {
                        "account_id": accounts["040100"],
                        "net": "500.00",
                        "vat_percent": "19",
                        "vat": "95.00",
                    }
                ],
            }
        },
        headers=admin,
    )
    assert blocked.status_code == 422
    assert "Fremdwährung" in blocked.json()["detail"]
    # Nothing was created (do not silently create).
    listed = _ok(client.get(f"{A}/invoices", headers=admin), 200)
    assert all(inv["number"] != "RE-USD-1" for inv in listed)
