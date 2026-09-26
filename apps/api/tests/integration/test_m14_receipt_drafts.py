"""M14 Belegeingang: a receipt draft is a proposal only (no invoice, no posting until
confirmed), the provider receives masked text (no IBAN, e-mail, phone), the IBAN is never
taken over without an explicit confirmation, drafts are tenant separated."""

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
R = "/api/v1/receipts"
BUCKET = "mhvp-receipts"
KNOWN = "DE89370400440532013000"
RECEIPT_TEXT = (
    f"Belegki Handwerk {RUN} GmbH\nz. Hd. Herrn Max Mustermann\n"
    "Rechnung RE-2026-042 vom 01.03.2026\nObjekt: Belegki-Haus, Musterstraße 12\n"
    f"IBAN: DE89 3704 0044 0532 0130 00\nRückfragen: buchhaltung{RUN}@example.org, "
    "Tel. 0211 1234567\nNetto 500,00 EUR, USt 95,00 EUR, Brutto 595,00 EUR"
).encode()


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
        a, _ = await services.provision_tenant(factory, slug=f"rcpa-{RUN}", name=f"Beleg A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rcpb-{RUN}", name=f"Beleg B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("rcadmin", a), ("rcsecond", a), ("rcother", b)]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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

INVOICE_OUTPUT: dict[str, Any] = {
    "invoice": {
        "supplier_name": f"Belegki Handwerk {RUN} GmbH",
        "iban": None,
        "invoice_number": "RE-2026-042",
        "invoice_date": "2026-03-01",
        "due_date": "2026-03-15",
        "net": "500.00",
        "vat": "95.00",
        "gross": "595.00",
        "currency": "EUR",
        "discount_percent": None,
        "discount_until": None,
        "order_reference": None,
        "property_number_guess": "Belegki-Haus, Musterstraße 12",
        "warnings": [],
        "confidence": 0.87,
    },
    "questions": ["Leistungszeitraum fehlt im Beleg."],
}


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str) -> str:
    return str(
        _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h), 201)["id"]
    )


def _setup_provider(c: TestClient, world: World) -> dict[str, str]:
    admin = bearer(login(c, world, "rcadmin"))
    second = bearer(login(c, world, "rcsecond"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        )
    )
    assert c.post("/api/v1/ai/providers/anthropic/release", headers=second).status_code == 200
    return admin


def _setup_ledger(
    c: TestClient, h: dict[str, str], offset: int = 0
) -> tuple[str, dict[str, str], str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": str(700 + (int(RUN, 16) + offset) % 100),
                "name": "Belegki-Haus",
                "management_type": "hoa",
                "street": "Musterstraße",
                "house_number": "12",
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
    return ledger, accounts, provider, str(prop["id"])


def _start(c: TestClient, h: dict[str, str], doc: str) -> dict[str, Any]:
    return _ok(c.post(f"{R}/drafts", json={"document_id": doc}, headers=h), 202)  # type: ignore[no-any-return]


def _confirm_body(
    ledger: str, accounts: dict[str, str], provider: str, **extra: Any
) -> dict[str, Any]:
    return {
        "invoice": {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": "RE-2026-042",
            "invoice_date": "2026-03-01",
            "net": "500.00",
            "vat": "95.00",
            "gross": "595.00",
            "lines": [
                {
                    "account_id": accounts["040100"],
                    "net": "500.00",
                    "vat_percent": "19",
                    "vat": "95.00",
                }
            ],
            **extra.pop("invoice", {}),
        },
        **extra,
    }


def test_draft_is_proposal_only_and_provider_sees_masked_text(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _setup_provider(client, world)
    ledger, accounts, provider, property_id = _setup_ledger(client, admin, offset=3)
    doc = _upload(client, admin, "beleg.txt", RECEIPT_TEXT, "text/plain")
    fake.queue.append(INVOICE_OUTPUT)
    draft = _start(client, admin, doc)

    # Masking (rule 0.1.13): nothing personal reached the provider.
    sent = json.dumps(fake.calls[-1], default=str)
    assert KNOWN not in sent
    assert "DE89 3704" not in sent
    assert f"buchhaltung{RUN}@example.org" not in sent
    assert "0211 1234567" not in sent
    assert "Max Mustermann" not in sent
    assert f"Belegki Handwerk {RUN} GmbH" in sent  # supplier name is the extraction target
    assert "[IBAN]" in (draft["masked_excerpt"] or "")

    # Proposal with per-field confidence, IBAN only as masked local candidate.
    assert draft["status"] == "proposed"
    assert draft["fields"]["gross"] == {
        "value": "595.00",
        "confidence": 0.97,
        "source": "ai",
        "note": None,
    }
    assert draft["fields"]["supplier_name"]["confidence"] == 0.87
    assert "iban" not in draft["fields"]
    assert draft["iban_candidates"] == [
        {"masked": "DE89 ... 3000", "checksum_ok": True, "source": "local"}
    ]
    assert draft["fields"]["property_ref"]["value"] == property_id
    assert draft["fields"]["property_ref"]["source"] == "local"
    assert draft["property_suggestions"][0]["score"] == 0.7
    assert draft["supplier_candidates"][0]["contact_id"] == provider
    assert draft["questions"] == ["Leistungszeitraum fehlt im Beleg."]

    # No invoice exists yet (draft, never a booking).
    assert all(
        i["number"] != "RE-2026-042" for i in _ok(client.get(f"{A}/invoices", headers=admin))
    )
    listed = _ok(client.get(f"{R}/drafts?status=open", headers=admin))
    assert any(d["id"] == draft["id"] for d in listed["items"])

    # A second open draft for the same document is refused.
    assert client.post(f"{R}/drafts", json={"document_id": doc}, headers=admin).status_code == 409

    # IBAN needs an explicit confirmation (rule 0.1.6).
    body = _confirm_body(ledger, accounts, provider, invoice={"payee_iban": KNOWN})
    refused = client.post(f"{R}/drafts/{draft['id']}/confirm", json=body, headers=admin)
    assert refused.status_code == 422
    assert "iban_confirmed" in refused.json()["detail"]

    confirmed = _ok(
        client.post(
            f"{R}/drafts/{draft['id']}/confirm",
            json=_confirm_body(
                ledger, accounts, provider, iban_confirmed=True, invoice={"payee_iban": KNOWN}
            ),
            headers=admin,
        ),
        201,
    )
    assert confirmed["status"] == "confirmed"
    invoice = _ok(client.get(f"{A}/invoices/{confirmed['invoice_id']}", headers=admin))
    assert invoice["posting_status"] == "unposted"
    assert invoice["review_status"] == "open"
    assert invoice["document_id"] == doc
    # Decided drafts cannot be decided again.
    assert (
        client.post(f"{R}/drafts/{draft['id']}/reject", json={}, headers=admin).status_code == 409
    )


def test_reject_and_failed_run_leave_no_invoice(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _setup_provider(client, world)
    doc = _upload(client, admin, "beleg2.txt", b"Rechnung ohne Nummer 12,00 EUR", "text/plain")
    fake.queue.append(
        {
            "invoice": {**INVOICE_OUTPUT["invoice"], "invoice_number": None, "gross": "12"},
            "questions": [],
        }
    )
    draft = _start(client, admin, doc)
    assert draft["fields"]["invoice_number"]["source"] == "none"
    rejected = _ok(
        client.post(
            f"{R}/drafts/{draft['id']}/reject", json={"reason": "kein Beleg"}, headers=admin
        )
    )
    assert rejected["status"] == "rejected"
    assert rejected["invoice_id"] is None

    pending = _upload(client, admin, "scan.pdf", b"%PDF-1.4 no text layer", "application/pdf")
    without_text = client.post(f"{R}/drafts", json={"document_id": pending}, headers=admin)
    assert without_text.status_code == 422
    assert "Texterkennung" in without_text.json()["detail"]


def test_tenant_separation_and_permissions(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _setup_provider(client, world)
    other = bearer(login(client, world, "rcother"))
    doc = _upload(client, admin, "beleg3.txt", RECEIPT_TEXT, "text/plain")
    fake.queue.append(INVOICE_OUTPUT)
    draft = _start(client, admin, doc)
    assert client.get(f"{R}/drafts/{draft['id']}", headers=other).status_code == 404
    assert (
        client.post(f"{R}/drafts/{draft['id']}/reject", json={}, headers=other).status_code == 404
    )
    assert all(
        d["id"] != draft["id"] for d in _ok(client.get(f"{R}/drafts", headers=other))["items"]
    )
    assert client.post(f"{R}/drafts", json={"document_id": doc}, headers=other).status_code == 404
    assert client.get(f"{R}/drafts", headers={}).status_code == 401
