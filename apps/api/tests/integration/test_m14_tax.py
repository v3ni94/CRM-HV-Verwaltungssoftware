"""M14-02/03/04 tax drafts of the invoice intake (docs/rules/M14-02.md, M14-03.md, M14-04.md).

Switches per tenant (default off), input tax proposal by revenue key (190,00 at 60 % ->
114,00), construction withholding proposal (1.190,00 at 15 % -> 178,50) blocking the posting
until a second person decides, approval limits per role (500,00 for the accountant, second
approval by a third person), § 35a markers per line and the certificate draft (400,00 labour
at 25 % -> 100,00), permissions and tenant separation. Nothing here opens a release gate.
"""

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
T = f"{A}/tax"
IBAN = "DE89370400440532013000"
BUCKET = "mhvp-m14-tax"
COMPANY = {
    "name": "Hausverwaltung Müller GmbH",
    "legal_form": "GmbH",
    "street": "Rheinpromenade 13",
    "postal_code": "40789",
    "city": "Monheim am Rhein",
    "register_court": "Amtsgericht Düsseldorf",
    "register_number": "HRB 104762",
    "management": ["Timo Müller"],
    "management_title": "Geschäftsführer",
}


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tx-{RUN}", name=f"Steuer {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ty-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("txadmin", a, "tenant_admin"),
            ("txadmin2", a, "tenant_admin"),
            ("txacc", a, "accountant_no_banking"),
            ("txacc2", a, "accountant_no_banking"),
            ("txstd", a, "standard"),
            ("txread", a, "read_only"),
            ("tyadmin", b, "tenant_admin"),
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
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    accepted = (200, 201) if status == 200 else (status,)
    assert response.status_code in accepted, response.text
    return response.json()


def _review_all(c: TestClient, h: dict[str, str], inv: str) -> None:
    for step in ("completeness", "factual", "arithmetic_tax"):
        _ok(
            c.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": "ok", "reason": f"{step} geprüft"},
                headers=h,
            ),
            201,
        )


class Setup:
    def __init__(self, c: TestClient, h: dict[str, str], approver: dict[str, str]) -> None:
        prop = _ok(
            c.post(
                "/api/v1/properties",
                json={
                    "number": "751",
                    "name": "Steuerhaus",
                    "management_type": "rental",
                    "street": "Rheinpromenade",
                    "house_number": "13",
                    "postal_code": "40789",
                    "city": "Monheim am Rhein",
                },
                headers=h,
            ),
            201,
        )
        self.property_id = str(prop["id"])
        owner, _ = _party(c, h, "Eigentuemer", "company")
        self.entity = str(
            _ok(
                c.post(
                    f"/api/v1/properties/{self.property_id}/owners",
                    json={"party_id": owner, "valid_from": "2020-01-01"},
                    headers=h,
                )
            )["legal_entity_id"]
        )
        template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
        self.ledger = str(
            _ok(
                c.post(
                    f"{A}/ledgers",
                    json={"legal_entity_id": self.entity, "template_id": template["id"]},
                    headers=h,
                ),
                201,
            )["id"]
        )
        accounts = _ok(c.get(f"{A}/ledgers/{self.ledger}/accounts", headers=h))
        self.cost_account = str(next(a["id"] for a in accounts if a["category"] == "cost"))
        self.provider = str(
            _ok(
                c.post(
                    "/api/v1/contacts",
                    json={
                        "kind": "company",
                        "company_name": f"Bau {RUN} GmbH",
                        "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}],
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
        approve_bank_accounts(c, approver, self.provider)
        self.unit = _unit(c, h, self.property_id, "01")
        tenant, _ = _party(c, h, "Mieter")
        self.contract = str(
            _ok(
                c.post(
                    "/api/v1/contracts",
                    json={
                        "kind": "tenancy",
                        "unit_id": self.unit,
                        "party_id": tenant,
                        "start_date": "2025-01-01",
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    def invoice(self, c: TestClient, h: dict[str, str], number: str, gross: str = "1190.00") -> Any:
        net = f"{float(gross) / 1.19:.2f}"
        vat = f"{float(gross) - float(net):.2f}"
        return _ok(
            c.post(
                f"{A}/invoices",
                json={
                    "ledger_id": self.ledger,
                    "provider_contact_id": self.provider,
                    "number": number,
                    "invoice_date": "2026-02-01",
                    "due_date": "2026-02-15",
                    "net": net,
                    "vat": vat,
                    "gross": gross,
                    "payee_iban": IBAN,
                    "lines": [
                        {
                            "account_id": self.cost_account,
                            "net": net,
                            "vat_percent": "19",
                            "vat": vat,
                            "text": "Dachreparatur",
                        }
                    ],
                },
                headers=h,
            ),
            201,
        )


@pytest.fixture(scope="module")
def setup(world: World, database: Database, redis_url: str) -> Setup:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        h = bearer(login(c, world, "txadmin"))
        return Setup(c, h, bearer(login(c, world, "txadmin2")))


def _settings_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "input_tax_enabled": False,
        "input_tax_account_number": None,
        "construction_withholding_enabled": False,
        "construction_withholding_percent": "15.00",
        "section_35a_enabled": False,
        "approval_limits_enabled": False,
        "approval_limits": [],
    }
    body.update(overrides)
    return body


def test_settings_default_off_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "txadmin"))
    std = bearer(login(client, world, "txstd"))
    current = _ok(client.get(f"{T}/settings", headers=std))
    assert current["input_tax_enabled"] is False
    assert current["construction_withholding_enabled"] is False
    assert current["section_35a_enabled"] is False
    assert current["approval_limits_enabled"] is False
    assert Decimal(current["construction_withholding_percent"]) == Decimal("15")
    assert client.put(f"{T}/settings", json=_settings_body(), headers=std).status_code == 403
    out = _ok(
        client.put(
            f"{T}/settings",
            json=_settings_body(input_tax_enabled=True, input_tax_account_number="026000"),
            headers=h,
        )
    )
    assert out["input_tax_enabled"] is True
    assert out["input_tax_account_number"] == "026000"
    assert (
        client.put(
            f"{T}/settings", json=_settings_body(input_tax_account_number="12"), headers=h
        ).status_code
        == 422
    )


def test_input_tax_proposal_by_revenue_key(client: TestClient, world: World, setup: Setup) -> None:
    h = bearer(login(client, world, "txadmin"))
    read = bearer(login(client, world, "txread"))
    foreign = bearer(login(client, world, "tyadmin"))
    _ok(client.put(f"{T}/settings", json=_settings_body(input_tax_enabled=True), headers=h))
    inv = setup.invoice(client, h, "R-TAX-1")
    data = _ok(client.get(f"{T}/invoices/{inv['id']}", headers=read))
    assert data["deductible_input_tax"] == "0.00"
    assert data["deductible_percent"] is None
    assert any("ohne Umsatzsteueroption" in w for w in data["warnings"])
    assert any(
        "Vorsteuerkonto ist in den Steuereinstellungen nicht hinterlegt" in w
        for w in data["warnings"]
    )
    # Opted property without a revenue key: still no deduction, explicit warning.
    assert (
        client.put(
            f"{T}/properties/{setup.property_id}/profile", json={"vat_opted": True}, headers=read
        ).status_code
        == 403
    )
    _ok(
        client.put(
            f"{T}/properties/{setup.property_id}/profile", json={"vat_opted": True}, headers=h
        )
    )
    data = _ok(client.get(f"{T}/invoices/{inv['id']}", headers=h))
    assert data["deductible_input_tax"] == "0.00"
    assert any("Umsatzschlüssel des Objekts fehlt" in w for w in data["warnings"])
    # 190,00 input tax at 60 % -> 114,00; a missing account in the chart is flagged.
    _ok(
        client.put(
            f"{T}/properties/{setup.property_id}/profile",
            json={"vat_opted": True, "revenue_key_percent": "60"},
            headers=h,
        )
    )
    _ok(
        client.put(
            f"{T}/settings",
            json=_settings_body(input_tax_enabled=True, input_tax_account_number="999999"),
            headers=h,
        )
    )
    data = _ok(client.get(f"{T}/invoices/{inv['id']}", headers=h))
    assert Decimal(data["deductible_percent"]) == Decimal("60")
    assert data["deductible_input_tax"] == "114.00"
    assert any("999999 fehlt im Kontenrahmen" in w for w in data["warnings"])
    _ok(
        client.put(
            f"{T}/settings",
            json=_settings_body(input_tax_enabled=True, input_tax_account_number="026000"),
            headers=h,
        )
    )
    data = _ok(client.get(f"{T}/invoices/{inv['id']}", headers=h))
    assert not any("Kontenrahmen" in w or "Steuereinstellungen" in w for w in data["warnings"])
    # Recorded values: rate and input tax separately, reverse charge contradiction flagged.
    data = _ok(
        client.put(
            f"{T}/invoices/{inv['id']}",
            json={"vat_rate": "19", "input_tax_amount": "190.00", "reverse_charge": True},
            headers=h,
        )
    )
    assert Decimal(data["vat_rate"]) == Decimal("19")
    assert data["input_tax_amount"] == "190.00"
    assert any("Reverse Charge" in w for w in data["warnings"])
    _ok(
        client.put(
            f"{T}/invoices/{inv['id']}",
            json={"vat_rate": "19", "input_tax_amount": "190.00"},
            headers=h,
        )
    )
    # Tenant separation and the switch off: no proposal at all.
    assert client.get(f"{T}/invoices/{inv['id']}", headers=foreign).status_code == 404
    assert (
        client.get(f"{T}/properties/{setup.property_id}/profile", headers=foreign).status_code
        == 404
    )
    _ok(client.put(f"{T}/settings", json=_settings_body(), headers=h))
    data = _ok(client.get(f"{T}/invoices/{inv['id']}", headers=h))
    assert data["deductible_input_tax"] is None
    assert data["warnings"] == []


def test_construction_withholding_proposal_blocks_posting_until_decided(
    client: TestClient, world: World, setup: Setup
) -> None:
    h = bearer(login(client, world, "txadmin"))
    acc = bearer(login(client, world, "txacc"))
    _ok(
        client.put(
            f"{T}/settings", json=_settings_body(construction_withholding_enabled=True), headers=h
        )
    )
    profile = _ok(
        client.put(
            f"{T}/suppliers/{setup.provider}/profile",
            json={
                "construction_services": True,
                "exemption_number": "FA-123",
                "exemption_valid_from": "2026-01-01",
            },
            headers=h,
        )
    )
    assert profile["exemption_valid_today"] is False  # no document filed
    assert (
        client.put(
            f"{T}/suppliers/{setup.provider}/profile",
            json={"exemption_valid_from": "2026-05-01", "exemption_valid_to": "2026-01-01"},
            headers=h,
        ).status_code
        == 422
    )
    inv = setup.invoice(client, h, "R-TAX-2")
    data = _ok(
        client.put(f"{T}/invoices/{inv['id']}", json={"construction_service": True}, headers=h)
    )
    # 1.190,00 at 15 % -> 178,50 as a proposal; the invoice itself is untouched.
    assert data["withholding_proposal"] == "178.50"
    assert Decimal(data["withholding_percent"]) == Decimal("15")
    assert any("Freistellungsbescheinigung fehlt" in w for w in data["warnings"])
    assert _ok(client.get(f"{A}/invoices/{inv['id']}", headers=h))["gross"] == "1190.00"
    _review_all(client, h, inv["id"])
    _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=acc))
    blocked = client.post(f"{A}/invoices/{inv['id']}/post", headers=h)
    assert blocked.status_code == 409, blocked.text
    assert "Bauabzugsteuer" in blocked.text
    # The creator may not confirm the withholding; a second person may.
    assert (
        client.post(f"{T}/invoices/{inv['id']}/withholding/approve", headers=h).status_code == 403
    )
    approved = _ok(client.post(f"{T}/invoices/{inv['id']}/withholding/approve", headers=acc))
    assert approved["withholding_approved_amount"] == "178.50"
    assert approved["withholding_approved_by"] == str(world.users["txacc"])
    posted = _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h))
    assert posted["posting_status"] == "posted"
    # Review 27.09.2026 (M14-04): a document id of another tenant passes the foreign key but
    # must not count as a filed exemption; only a document of this tenant lifts the block.
    other = bearer(login(client, world, "tyadmin"))
    foreign_doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("fremd.pdf", b"%PDF-1.4 x", "application/pdf")},
            headers=other,
        ),
        201,
    )
    rejected = client.put(
        f"{T}/suppliers/{setup.provider}/profile",
        json={
            "construction_services": True,
            "exemption_number": "FA-999",
            "exemption_valid_from": "2026-01-01",
            "exemption_valid_to": "2026-12-31",
            "exemption_document_id": foreign_doc["id"],
        },
        headers=h,
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"] == "Freistellungsbescheinigung nicht gefunden."
    # A valid exemption with a filed document removes the proposal.
    links = json.dumps(
        [{"entity_type": "contact", "entity_id": setup.provider, "role": "attachment"}]
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("freistellung.pdf", b"%PDF-1.4 f", "application/pdf")},
            data={"links": links},
            headers=h,
        ),
        201,
    )
    profile = _ok(
        client.put(
            f"{T}/suppliers/{setup.provider}/profile",
            json={
                "construction_services": True,
                "exemption_number": "FA-123",
                "exemption_valid_from": "2026-01-01",
                "exemption_valid_to": "2026-12-31",
                "exemption_document_id": doc["id"],
            },
            headers=h,
        )
    )
    assert profile["exemption_valid_today"] is True
    later = setup.invoice(client, h, "R-TAX-3")
    data = _ok(
        client.put(f"{T}/invoices/{later['id']}", json={"construction_service": True}, headers=h)
    )
    assert data["withholding_proposal"] == "0.00"
    assert data["warnings"] == []
    _ok(client.put(f"{T}/settings", json=_settings_body(), headers=h))


def test_approval_limits_need_third_person(client: TestClient, world: World, setup: Setup) -> None:
    h = bearer(login(client, world, "txadmin"))
    acc = bearer(login(client, world, "txacc"))
    acc2 = bearer(login(client, world, "txacc2"))
    std = bearer(login(client, world, "txstd"))
    _ok(
        client.put(
            f"{T}/settings",
            json=_settings_body(
                approval_limits_enabled=True,
                approval_limits=[{"role_code": "accountant_no_banking", "limit_amount": "500.00"}],
            ),
            headers=h,
        )
    )
    inv = setup.invoice(client, h, "R-TAX-4", "1190.00")
    small = setup.invoice(client, h, "R-TAX-5", "500.00")
    state = _ok(client.get(f"{T}/invoices/{inv['id']}/approval", headers=acc))
    assert state == {
        "enabled": True,
        "limit_amount": "500.00",
        "second_approval_required": True,
        "second_approval_valid": False,
        "second_approved_by": None,
    }
    assert (
        _ok(client.get(f"{T}/invoices/{small['id']}/approval", headers=acc))[
            "second_approval_required"
        ]
        is False
    )
    for i in (inv, small):
        _review_all(client, h, i["id"])
        _ok(client.post(f"{A}/invoices/{i['id']}/release", headers=acc))
    # Below the limit: posts as before.
    assert (
        _ok(client.post(f"{A}/invoices/{small['id']}/post", headers=h))["posting_status"]
        == "posted"
    )
    blocked = client.post(f"{A}/invoices/{inv['id']}/post", headers=h)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "MHVP-ACC-0006"
    # Neither the creator nor the first releaser nor a role without approve may second approve.
    assert client.post(f"{T}/invoices/{inv['id']}/second-approval", headers=h).status_code == 403
    assert client.post(f"{T}/invoices/{inv['id']}/second-approval", headers=acc).status_code == 403
    assert client.post(f"{T}/invoices/{inv['id']}/second-approval", headers=std).status_code == 403
    state = _ok(client.post(f"{T}/invoices/{inv['id']}/second-approval", headers=acc2))
    assert state["second_approval_valid"] is True
    assert state["second_approved_by"] == str(world.users["txacc2"])
    assert (
        _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h))["posting_status"] == "posted"
    )
    # Without the switch a tenant_admin release needs nothing more (roles without limit).
    _ok(client.put(f"{T}/settings", json=_settings_body(), headers=h))
    assert _ok(client.get(f"{T}/invoices/{inv['id']}/approval", headers=acc))["enabled"] is False


def test_section35a_markers_and_certificate_draft(
    client: TestClient, world: World, setup: Setup
) -> None:
    h = bearer(login(client, world, "txadmin"))
    read = bearer(login(client, world, "txread"))
    foreign = bearer(login(client, world, "tyadmin"))
    inv = _ok(client.get(f"{A}/invoices", headers=h, params={"page_size": 50}))
    target = next(i for i in inv if i["number"] == "R-TAX-1")
    full = _ok(client.get(f"{A}/invoices/{target['id']}", headers=h))
    line_id = full["lines"][0]["id"]
    too_much = client.put(
        f"{T}/invoice-lines/{line_id}/section35a",
        json={"kind": "craftsman", "labor_amount": "1000.00", "material_amount": "500.00"},
        headers=h,
    )
    assert too_much.status_code == 422
    assert (
        client.put(
            f"{T}/invoice-lines/{line_id}/section35a",
            json={"kind": "craftsman", "labor_amount": "400.00", "material_amount": "200.00"},
            headers=read,
        ).status_code
        == 403
    )
    marker = _ok(
        client.put(
            f"{T}/invoice-lines/{line_id}/section35a",
            json={"kind": "craftsman", "labor_amount": "400.00", "material_amount": "200.00"},
            headers=h,
        )
    )
    assert marker["labor_amount"] == "400.00"
    assert marker["kind"] == "craftsman"
    # GAK-103: before any certificate the marker can still be removed and set again.
    assert client.delete(f"{T}/invoice-lines/{line_id}/section35a", headers=h).status_code == 204
    assert _ok(client.get(f"{T}/invoices/{target['id']}/section35a", headers=h)) == []
    marker = _ok(
        client.put(
            f"{T}/invoice-lines/{line_id}/section35a",
            json={"kind": "craftsman", "labor_amount": "400.00", "material_amount": "200.00"},
            headers=h,
        )
    )
    listed = _ok(client.get(f"{T}/invoices/{target['id']}/section35a", headers=read))
    assert [m["invoice_line_id"] for m in listed] == [line_id]
    params: dict[str, str | int] = {
        "contract_id": setup.contract,
        "year": 2026,
        "share_percent": "25",
    }
    assert client.get(f"{T}/section35a/certificate", params=params, headers=h).status_code == 409
    _ok(client.put(f"{T}/settings", json=_settings_body(section_35a_enabled=True), headers=h))
    cert = _ok(client.get(f"{T}/section35a/certificate", params=params, headers=read))
    # 400,00 labour shared at 25 % -> 100,00 craftsman, material 200,00 at 25 % -> 50,00.
    assert cert["labor_by_kind"] == {"household_service": "0.00", "craftsman": "100.00"}
    assert cert["labor_total"] == "100.00"
    assert cert["material_total"] == "50.00"
    assert len(cert["lines"]) == 1
    assert cert["lines"][0]["invoice_number"] == "R-TAX-1"
    assert "Steuerberater" in cert["notice"]
    # AI18 (GAH-101): default basis unchanged, each line carries its payment state.
    assert cert["basis"] == "invoice_date"
    assert cert["lines"][0]["paid"] is False
    assert cert["lines"][0]["paid_on"] is None
    assert cert["unpaid_lines"] == 1
    assert cert["previous"] == []
    assert cert["repeat_notice"] is None
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pdf = client.get(f"{T}/section35a/certificate.pdf", params=params, headers=h)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    stored = _ok(client.post(f"{T}/section35a/certificate/document", params=params, headers=h), 201)
    assert stored["contract_id"] == setup.contract
    # PDF and filed document were both recorded; the second one already carried the notice.
    assert stored["repeat_notice"] is not None
    again = _ok(client.get(f"{T}/section35a/certificate", params=params, headers=read))
    assert [p["output"] for p in again["previous"]] == ["pdf", "document"]
    assert again["previous"][1]["document_id"] == stored["document_id"]
    assert again["previous"][1]["labor_total"] == "100.00"
    assert again["repeat_notice"] is not None
    # Variant payment_date: the unpaid invoice drops out of the certificate.
    bad = _settings_body(section_35a_enabled=True, section_35a_basis="cash")
    assert client.put(f"{T}/settings", json=bad, headers=h).status_code == 422
    _ok(
        client.put(
            f"{T}/settings",
            json=_settings_body(section_35a_enabled=True, section_35a_basis="payment_date"),
            headers=h,
        )
    )
    by_payment = _ok(client.get(f"{T}/section35a/certificate", params=params, headers=read))
    assert by_payment["basis"] == "payment_date"
    assert by_payment["lines"] == []
    assert by_payment["labor_total"] == "0.00"
    _ok(client.put(f"{T}/settings", json=_settings_body(section_35a_enabled=True), headers=h))
    assert (
        client.get(f"{T}/section35a/certificate", params=params, headers=foreign).status_code == 404
    )
    # GAK-103 (7.6 A01, B03): a marker used in an issued certificate is neither removed nor
    # changed silently; 409 MHVP-ACC-0040, correction through a new certificate version.
    removed = client.delete(f"{T}/invoice-lines/{line_id}/section35a", headers=h)
    assert removed.status_code == 409, removed.text
    assert removed.json()["code"] == "MHVP-ACC-0040"
    changed = client.put(
        f"{T}/invoice-lines/{line_id}/section35a",
        json={"kind": "craftsman", "labor_amount": "300.00", "material_amount": "200.00"},
        headers=h,
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["code"] == "MHVP-ACC-0040"
    kept = _ok(client.get(f"{T}/invoices/{target['id']}/section35a", headers=h))
    assert [m["labor_amount"] for m in kept] == ["400.00"]
    _ok(client.put(f"{T}/settings", json=_settings_body(), headers=h))
