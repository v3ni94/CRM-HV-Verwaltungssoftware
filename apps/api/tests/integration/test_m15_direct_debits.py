"""M15 direct debits (pain.008, rule M15-02): due receivables are collected only under an
active SEPA mandate of the contract party (rule M3-02, revoked mandates are never debited),
the creditor identifier must be entered, the lead time is a mandatory parameter, two different
persons approve a snapshot, the file is generated, checked and filed as a document, the
download is refused while gate G2 is closed (403 MHVP-GATE-0001), a handed out file turns
the next collection under the same mandate into RCUR, pre-notifications are drafts only, and
another tenant sees nothing."""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.accounting import direct_debit as dd
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
D = "/api/v1/accounting/direct-debits"
OWN = "DE02120300000000202051"
PAYER_A = "DE89370400440532013000"
PAYER_B = "DE75512108001245126199"
PAYER_C = "DE12500105170648489890"
CREDITOR_ID = "TESTGLAEUBIGERID0001"  # operator entry in the test; no claim on the real format


class OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


class OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dd-{RUN}", name=f"Einzug {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ddb-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ddadmin", a, "tenant_admin"),
            ("ddacc", a, "accountant_banking"),
            ("ddother", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings, release_gate_resolver=OpenG1())) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG1G2())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _payer(
    c: TestClient, h: dict[str, str], name: str, iban: str, mandate: dict[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    account: dict[str, Any] = {"iban": iban, "valid_from": "2020-01-01", "holder": f"{name} Test"}
    if mandate is not None:
        account.update(
            {
                "sepa_enabled": True,
                "mandate_reference": f"MREF-{name}-{RUN}",
                "mandate_signed_on": "2024-01-10",
                "mandate_granted_via": "brief",
                "mandate_note": "Mandat liegt in der Akte",
            }
            | mandate
        )
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": name,
                "last_name": f"Zahler{RUN}",
                "emails": [{"label": "private", "email": f"{name.lower()}-{RUN}@example.com"}],
                "bank_accounts": [account],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    return str(party["id"]), contact


def _contract(c: TestClient, h: dict[str, str], prop: str, unit_no: str, party: str) -> str:
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": _unit(c, h, prop, unit_no),
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in [("hoa_fee", "300.00"), ("reserve", "50.00")]:
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2020-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    return str(contract["id"])


def _receivables(c: TestClient, h: dict[str, str], ledger: str, month: str) -> None:
    run = _ok(c.post(f"{A}/receivable-runs", json={"period_month": month}, headers=h), 201)
    _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))


def test_direct_debit_run(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, open_g2 = clients
    h = bearer(login(client, world, "ddadmin"))
    acc_user = bearer(login(client, world, "ddacc"))
    other = bearer(login(client, world, "ddother"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "771", "name": "Einzugshaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE Einzugshaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    party_a, contact_a = _payer(client, h, "Anna", PAYER_A, {})
    party_b, _ = _payer(client, h, "Bernd", PAYER_B, None)  # no mandate
    party_c, _ = _payer(
        client,
        h,
        "Carla",
        PAYER_C,
        {"mandate_status": "revoked", "mandate_revoked_on": "2026-01-15"},
    )
    c_a = _contract(client, h, prop["id"], "01", party_a)
    c_b = _contract(client, h, prop["id"], "02", party_b)
    c_c = _contract(client, h, prop["id"], "03", party_c)
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(client.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    _receivables(client, h, ledger, "2026-03-01")
    today = local_today()
    collection = (today + timedelta(days=7)).isoformat()
    base = {"ledger_id": ledger, "collection_date": collection, "lead_days": 5}

    # Without a creditor identifier nothing is collected; the value is never invented.
    assert client.post(f"{D}/preview", json=base, headers=h).status_code == 422
    _ok(
        client.put(
            f"{D}/creditor-ids/legal-entities/{hoa}",
            json={"sepa_creditor_id": CREDITOR_ID},
            headers=h,
        )
    )

    # Lead time is mandatory and enforced.
    assert client.post(f"{D}/preview", json={**base, "lead_days": 8}, headers=h).status_code == 422
    assert (
        client.post(
            f"{D}/preview", json={"ledger_id": ledger, "collection_date": collection}, headers=h
        ).status_code
        == 422
    )

    preview = _ok(client.post(f"{D}/preview", json=base, headers=h))
    assert preview["creditor_id"] == CREDITOR_ID
    # One open item per posted payment type (hoa_fee and reserve) and contract.
    by_contract: dict[str, list[dict[str, Any]]] = {}
    for item in preview["items"]:
        by_contract.setdefault(item["contract_id"], []).append(item)
    assert {len(v) for v in by_contract.values()} == {2}
    assert all(i["eligible"] for i in by_contract[c_a])
    assert {i["sequence_type"] for i in by_contract[c_a]} == {"FRST"}
    assert by_contract[c_a][0]["iban_masked"].endswith("3000")
    assert PAYER_A not in str(preview)  # IBAN only masked
    assert not any(i["eligible"] for i in by_contract[c_b])
    assert not any(i["eligible"] for i in by_contract[c_c])
    assert {i["block_reason"] for i in by_contract[c_c]} == {"Mandat widerrufen"}
    assert preview["count"] == 2
    assert preview["control_sum"] == "350.00"

    # Explicitly requesting a blocked item is refused (revoked mandate is never debited).
    refused = client.post(
        f"{D}",
        json={
            **base,
            "property_bank_account_id": bank,
            "open_item_ids": [by_contract[c_c][0]["open_item_id"]],
        },
        headers=h,
    )
    assert refused.status_code == 409, refused.text
    assert "widerrufen" in refused.json()["detail"]

    run = _ok(client.post(f"{D}", json={**base, "property_bank_account_id": bank}, headers=h), 201)
    assert run["status"] == "draft"
    assert run["transaction_count"] == 2
    assert run["control_sum"] == "350.00"
    assert run["format"] == dd.PAIN_FORMAT
    assert [o["sequence_type"] for o in run["orders"]] == ["FRST", "FRST"]
    assert run["orders"][0]["contact_id"] == contact_a["id"]
    assert run["orders"][0]["debtor_iban_suffix"] == "3000"
    assert {e["contract_id"] for e in run["excluded"]} == {c_b, c_c}
    # The same receivable is not collected twice while the run is active.
    again = client.post(f"{D}", json={**base, "property_bank_account_id": bank}, headers=h)
    assert again.status_code == 422, again.text

    # Tenant separation: another tenant sees nothing and cannot approve.
    assert client.get(f"{D}/{run['id']}", headers=other).status_code == 404
    assert client.post(f"{D}/{run['id']}/approve", headers=other).status_code == 404
    assert client.get(f"{D}", headers=other).json() == []

    # Four eyes: the same person twice counts once; file needs the full approval.
    first = _ok(client.post(f"{D}/{run['id']}/approve", headers=h))
    assert first["approvals"] == 1
    assert first["status"] == "draft"
    same = _ok(client.post(f"{D}/{run['id']}/approve", headers=h))
    assert same["approvals"] == 1
    incomplete = client.post(f"{D}/{run['id']}/file", headers=h)
    assert incomplete.status_code == 403, incomplete.text
    assert incomplete.json()["code"] == "MHVP-GATE-0002"  # four eyes, not the release gate
    approved = _ok(client.post(f"{D}/{run['id']}/approve", headers=acc_user))
    assert approved["approvals"] == 2
    assert approved["status"] == "approved"

    # Pre-notifications are drafts filed at the contact; a repeated call adds nothing.
    notes = _ok(client.post(f"{D}/{run['id']}/pre-notifications", headers=h))
    assert len(notes) == 1  # one draft per payer covering both items
    assert notes[0]["created"] is True
    assert len(notes[0]["order_ids"]) == 2
    again_notes = _ok(client.post(f"{D}/{run['id']}/pre-notifications", headers=h))
    assert again_notes[0]["created"] is False
    assert again_notes[0]["document_id"] == notes[0]["document_id"]
    history = _ok(client.get(f"/api/v1/contacts/{contact_a['id']}/history", headers=h))
    kinds = {e["kind"]: e["status"] for e in history}
    assert kinds.get("email_out") == "draft"  # mail draft only, nothing sent
    assert kinds.get("dispatch_email") not in ("sent", "delivered")
    draft = client.get(f"/api/v1/documents/{notes[0]['document_id']}/content", headers=h)
    assert draft.status_code == 200, draft.text
    assert "Vorabinformation" in draft.text
    assert f"MREF-Anna-{RUN}" in draft.text
    assert CREDITOR_ID in draft.text
    assert "Gesamtbetrag: 350,00 EUR" in draft.text

    # File: generated, checked and filed; never handed out while G2 is closed.
    generated = _ok(client.post(f"{D}/{run['id']}/file", headers=h))
    assert generated["status"] == "file_generated"
    assert generated["document_id"]
    blocked = client.get(f"{D}/{run['id']}/file", headers=h)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "MHVP-GATE-0001"
    assert _ok(client.get(f"{D}/{run['id']}", headers=h))["status"] == "file_generated"

    # Behind G2 the file is handed out once and the run counts as exported.
    gh = bearer(login(open_g2, world, "ddadmin"))
    xml = open_g2.get(f"{D}/{run['id']}/file", headers=gh)
    assert xml.status_code == 200, xml.text
    assert dd.validate_pain008(xml.content) == []
    assert "<SeqTp>FRST</SeqTp>" in xml.text
    assert f"<MndtId>MREF-Anna-{RUN}</MndtId>" in xml.text
    assert f"<Id>{CREDITOR_ID}</Id>" in xml.text
    assert f"<IBAN>{OWN}</IBAN>" in xml.text
    assert _ok(client.get(f"{D}/{run['id']}", headers=h))["status"] == "exported"
    assert client.post(f"{D}/{run['id']}/cancel", headers=h).status_code == 409

    # The next collection under the same mandate is a recurring one.
    _receivables(client, h, ledger, "2026-04-01")
    second = _ok(
        client.post(f"{D}", json={**base, "property_bank_account_id": bank}, headers=h), 201
    )
    assert [o["sequence_type"] for o in second["orders"]] == ["RCUR", "RCUR"]
    assert second["transaction_count"] == 2
    assert {o["open_item_id"] for o in second["orders"]}.isdisjoint(
        {o["open_item_id"] for o in run["orders"]}
    )

    # A change of the run after approval invalidates approvals (snapshot): cancel keeps history.
    _ok(client.post(f"{D}/{second['id']}/approve", headers=h))
    cancelled = _ok(client.post(f"{D}/{second['id']}/cancel", headers=h))
    assert cancelled["status"] == "cancelled"
    assert cancelled["approvals"] == 0
    assert client.post(f"{D}/{second['id']}/approve", headers=acc_user).status_code == 409


def test_direct_debit_requires_leading_ledger_and_own_account(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ddadmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Vergleichshaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE Vergleichshaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{D}/creditor-ids/legal-entities/{hoa}",
            json={"sepa_creditor_id": CREDITOR_ID},
            headers=h,
        )
    )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    collection = (local_today() + timedelta(days=7)).isoformat()
    body = {
        "ledger_id": ledger,
        "collection_date": collection,
        "lead_days": 5,
        "property_bank_account_id": bank,
    }
    # A comparison ledger (Immoware24 leading, 13.1) never collects (D52 lock).
    refused = client.post(f"{D}", json=body, headers=h)
    assert refused.status_code == 409, refused.text
    assert "führende System" in refused.json()["detail"]
