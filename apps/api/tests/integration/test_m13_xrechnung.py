"""A12 / D41 (formal validity): Verwalterhonorar invoice issued as XRechnung (UBL 2.1,
XRechnung 3.0). Expected values: 3 apartments x 25,00 = 75,00, minimum 100,00 applies, 19 %
= 19,00, gross 119,00. Locks: no Leitweg-ID, no payee IBAN, no seller contact data. Rights:
accounting:read only; a second tenant never sees the invoice; incoming invoices (drafts) answer
409. The official KoSIT validator runs only when MHVP_KOSIT_DIR points to a local copy
(scripts/kosit_validate.sh); otherwise that step is reported as skipped, never as passed."""

import asyncio
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.accounting import xrechnung
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-xrechnung"
IBAN = "DE02120300000000202051"
LEITWEG = "04011000-12345-67"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=2_000_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"xr-{RUN}", name=f"XRechnung {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"xrb-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("xradmin", a, "tenant_admin"),
            ("xrcaretaker", a, "caretaker"),
            ("xrother", b, "tenant_admin"),
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
    assert response.status_code == status, response.text
    return response.json()


def _problem(response: Any, code: str) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == code, response.text


def _kosit(xml: bytes, name: str) -> str:
    """Official validation when a local validator is available; 'skipped' otherwise."""
    kosit = os.environ.get("MHVP_KOSIT_DIR")
    if not kosit or shutil.which("java") is None:
        return "skipped"
    script = Path(__file__).resolve().parents[4] / "scripts" / "kosit_validate.sh"
    target = Path(kosit) / "out" / f"{name}.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(xml)
    result = subprocess.run(  # noqa: S603
        [str(script), str(target)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return "accepted"


def test_d41_xrechnung_issue_generate_check_and_store(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "xradmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "741",
                "name": "XR Haus",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    for no in ("01", "02", "03"):
        _unit(client, h, prop["id"], no)
    fee = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "min_amount": "100.00",
                "amounts_per_unit_type": {"apartment": "25.00"},
            },
            headers=h,
        ),
        201,
    )
    issue = f"{A}/admin-fees/{fee['id']}/invoice-issue"
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"invoice_prefix": "HVM", "vat_status": "regelbesteuert", "vat_id": "DE123456789"},
            headers=h,
        )
    )
    issued = _ok(client.post(issue, headers=h))
    assert issued["status"] == "issued"
    assert issued["number"] == f"HVM-{issued['invoice_date'][:4]}-000001"
    assert issued["gross"] == "119.00"
    invoice_id = issued["id"]
    assert issued["xrechnung_url"] == f"/api/v1/accounting/invoices/{invoice_id}/xrechnung.xml"
    xml_url = f"{A}/invoices/{invoice_id}/xrechnung.xml"

    # Locks, in the order the operator would hit them: Leitweg-ID, payee IBAN, company data.
    _problem(client.get(xml_url, headers=h), "MHVP-BILL-0005")
    _ok(client.patch("/api/v1/tenant/billing-settings", json={"leitweg_id": LEITWEG}, headers=h))
    _problem(client.get(xml_url, headers=h), "MHVP-BILL-0007")
    assert (
        client.patch(
            "/api/v1/tenant/billing-settings", json={"payee_iban": "DE00 1"}, headers=h
        ).status_code
        == 422
    )
    billing = _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"payee_iban": "de02 1203 0000 0000 2020 51"},
            headers=h,
        )
    )
    assert billing["payee_iban_masked"] == "…2051"  # normalised and masked, never returned
    no_address = client.get(xml_url, headers=h)
    assert no_address.status_code == 422, no_address.text
    assert "Fehlende Firmendaten" in no_address.json()["detail"]
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    no_contact = client.get(xml_url, headers=h)
    assert no_contact.status_code == 422, no_contact.text
    assert "E-Mail" in no_contact.json()["detail"]  # BG-6 and BT-34 are mandatory
    _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={"company": {**COMPANY, "email": "info@example.org", "phone": "+49 2173 000000"}},
            headers=h,
        )
    )

    # Happy path: XML, structure findings empty, sums as fixed above.
    response = client.get(xml_url, headers=h)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["x-mhvp-xrechnung-findings"] == "0"
    assert issued["number"] in response.headers["content-disposition"]
    xml = response.content
    assert xrechnung.check_structure(xml) == []
    root = SafeET.fromstring(xml)
    ns = xrechnung.NS
    assert root.find("cbc:ID", ns).text == issued["number"]
    assert root.find("cbc:BuyerReference", ns).text == LEITWEG
    seller = root.find("cac:AccountingSupplierParty/cac:Party", ns)
    assert seller.find("cac:PartyName/cbc:Name", ns).text == "Hausverwaltung Müller GmbH"
    assert seller.find("cac:PartyTaxScheme/cbc:CompanyID", ns).text == "DE123456789"
    assert seller.find("cac:PartyLegalEntity/cbc:CompanyID", ns).text == "HRB 104762"
    buyer = root.find("cac:AccountingCustomerParty/cac:Party", ns)
    hoa_name = next(e["name"] for e in prop["legal_entities"] if e["id"] == hoa)
    assert buyer.find("cac:PartyName/cbc:Name", ns).text == hoa_name
    assert buyer.find("cbc:EndpointID", ns).get("schemeID") == "0204"
    assert buyer.find("cac:PostalAddress/cbc:StreetName", ns).text == "Rheinpromenade 13"
    assert root.find("cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", ns).text == IBAN
    total = root.find("cac:LegalMonetaryTotal", ns)
    assert total.find("cbc:TaxExclusiveAmount", ns).text == "100.00"
    assert total.find("cbc:TaxInclusiveAmount", ns).text == "119.00"
    assert [
        ln.find("cbc:LineExtensionAmount", ns).text for ln in root.findall("cac:InvoiceLine", ns)
    ] == [
        "75.00",
        "25.00",
    ]
    official = _kosit(xml, issued["number"])
    check = _ok(client.get(f"{A}/invoices/{invoice_id}/xrechnung/check", headers=h))
    assert check == {
        "invoice_id": invoice_id,
        "number": issued["number"],
        "structure_ok": True,
        "findings": [],
        "official_validation": "not_run",
    }
    assert official in ("skipped", "accepted")

    # Storage as a generated document, linked to the property and the community; idempotent.
    stored = _ok(client.post(f"{A}/invoices/{invoice_id}/xrechnung/document", headers=h), 201)
    assert stored["created"] is True
    again = _ok(client.post(f"{A}/invoices/{invoice_id}/xrechnung/document", headers=h), 201)
    assert again == {"document_id": stored["document_id"], "created": False}
    document = _ok(client.get(f"/api/v1/documents/{stored['document_id']}", headers=h))
    assert document["mime_type"] == "application/xml"
    assert document["filename"] == f"{issued['number']}.xml"
    assert {(link["entity_type"], link["entity_id"]) for link in document["links"]} == {
        ("property", prop["id"]),
        ("legal_entity", hoa),
    }

    # Rights: caretaker has no accounting:read; the second tenant does not see the invoice.
    caretaker = bearer(login(client, world, "xrcaretaker"))
    assert client.get(xml_url, headers=caretaker).status_code == 403
    other = bearer(login(client, world, "xrother"))
    assert client.get(xml_url, headers=other).status_code == 404
    assert (
        client.get(f"{A}/invoices/{invoice_id}/xrechnung/check", headers=other).status_code == 404
    )
    assert (
        client.post(f"{A}/invoices/{invoice_id}/xrechnung/document", headers=other).status_code
        == 404
    )

    # Incoming invoice drafts (Rechnungseingang) are never rendered as the tenant's XRechnung.
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Hausmeister {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    draft = _ok(
        client.post(
            f"{A}/invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider,
                "number": "R-41",
                "invoice_date": "2026-02-01",
                "net": "100.00",
                "vat": "19.00",
                "gross": "119.00",
                "lines": [
                    {
                        "account_id": acc["040100"],
                        "net": "100.00",
                        "vat_percent": "19",
                        "vat": "19.00",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    _problem(client.get(f"{A}/invoices/{draft['id']}/xrechnung.xml", headers=h), "MHVP-BILL-0006")
    assert client.get(f"{A}/invoices/{world.tenant_b}/xrechnung.xml", headers=h).status_code == 404


def test_d41_kleinunternehmer_and_vat_mismatch_are_locked(client: TestClient, world: World) -> None:
    """A Kleinunternehmer tenant never issues VAT on the XRechnung; the fee with 19 % is locked
    with MHVP-BILL-0003 instead of silently switching the category."""
    h = bearer(login(client, world, "xradmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "742",
                "name": "XR Klein",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    _unit(client, h, prop["id"], "01")
    with_vat = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "amounts_per_unit_type": {"apartment": "40.00"},
            },
            headers=h,
        ),
        201,
    )
    without_vat = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "0",
                "amounts_per_unit_type": {"apartment": "40.00"},
            },
            headers=h,
        ),
        201,
    )
    taxed = _ok(client.post(f"{A}/admin-fees/{with_vat['id']}/invoice-issue", headers=h))
    exempt = _ok(client.post(f"{A}/admin-fees/{without_vat['id']}/invoice-issue", headers=h))
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "vat_status": "kleinunternehmer",
                "kleinunternehmer_note": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
            },
            headers=h,
        )
    )
    _problem(client.get(f"{A}/invoices/{taxed['id']}/xrechnung.xml", headers=h), "MHVP-BILL-0003")
    response = client.get(f"{A}/invoices/{exempt['id']}/xrechnung.xml", headers=h)
    assert response.status_code == 200, response.text
    root = SafeET.fromstring(response.content)
    category = root.find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", xrechnung.NS)
    assert category.find("cbc:ID", xrechnung.NS).text == "E"
    assert "§ 19 UStG" in category.find("cbc:TaxExemptionReason", xrechnung.NS).text
    assert root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", xrechnung.NS).text == "40.00"
    assert xrechnung.check_structure(response.content) == []
    assert _kosit(response.content, exempt["number"]) in ("skipped", "accepted")
    # Back to regelbesteuert so that later modules of this tenant are unaffected.
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings", json={"vat_status": "regelbesteuert"}, headers=h
        )
    )
