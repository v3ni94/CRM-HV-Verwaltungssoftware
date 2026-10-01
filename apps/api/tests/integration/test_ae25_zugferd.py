"""AE25 / S13-03: ZUGFeRD / Factur-X hybrid of an issued Verwalterhonorar invoice.

Expected values, computed by hand: one object with 2 apartments x 40,00 = 80,00 net, 19 % =
15,20 VAT, gross 95,20 (quarter 01.07. to 30.09.2026), number ZF-2026-000001. The credit note
of the cancelled invoice states 95,20 positive with type code 381 and the reference to
ZF-2026-000001.
"""

import asyncio
import io
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from defusedxml import ElementTree as SafeET  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from pypdf import PdfReader

from mhvp.accounting import zugferd
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.receipts import einvoice
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-ae25"
LEITWEG = "04011000-12345-67"
IBAN = "DE02120300000000202051"


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
        a, _ = await services.provision_tenant(factory, slug=f"ae25a-{RUN}", name=f"AE25 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae25b-{RUN}", name=f"AE25 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae25admin", a, "tenant_admin"),
            ("ae25tax", a, "tax_advisor"),
            ("ae25care", a, "caretaker"),
            ("ae25other", b, "tenant_admin"),
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


def _issue(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "825",
                "name": "AE25 Haus 825",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": "25",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    for no in ("01", "02"):
        _unit(client, h, prop["id"], no)
    fee = _ok(
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
    _ok(client.patch(f"{A}/admin-fees/{fee['id']}", json={"interval": "quarterly"}, headers=h))
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "invoice_prefix": "ZF",
                "vat_status": "regelbesteuert",
                "vat_id": "DE123456789",
                "leitweg_id": LEITWEG,
                "payee_iban": IBAN,
            },
            headers=h,
        )
    )
    _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={"company": {**COMPANY, "email": "info@example.org", "phone": "+49 2173 000000"}},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/admin-fees-run",
            json={"period_date": "2026-08-15", "invoice_date": "2026-10-01", "confirm": True},
            headers=h,
        )
    )
    assert run["issued"] == 1
    return run["rows"][0]  # type: ignore[no-any-return]


def _cii(pdf: bytes) -> Any:
    found = einvoice.embedded_xml(pdf)
    assert found is not None
    assert found[0] == "factur-x.xml"
    return SafeET.fromstring(found[1])


def test_zugferd_download_check_and_filing(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae25admin"))
    tax = bearer(login(client, world, "ae25tax"))
    care = bearer(login(client, world, "ae25care"))
    other = bearer(login(client, world, "ae25other"))
    row = _issue(client, h)
    invoice = row["invoice_id"]
    assert row["number"] == "ZF-2026-000001"
    url = f"{A}/admin-fee-invoices/{invoice}/zugferd"

    response = client.get(f"{url}.pdf", headers=h)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-mhvp-zugferd-findings"] == "0"
    assert response.headers["x-mhvp-pdfa-status"] == "not_verified"
    assert "ZF-2026-000001-zugferd.pdf" in response.headers["content-disposition"]
    pdf = response.content
    read = einvoice.read("application/pdf", pdf).einvoice
    assert read is not None
    assert (read.format, read.syntax, read.profile) == ("zugferd", "cii", "EN 16931")
    assert (read.invoice_number, read.net, read.vat, read.gross) == (
        "ZF-2026-000001",
        Decimal("80.00"),
        Decimal("15.20"),
        Decimal("95.20"),
    )
    assert read.buyer_reference == LEITWEG
    assert read.payment.iban == IBAN
    assert (str(read.service_from), str(read.service_to)) == ("2026-07-01", "2026-09-30")
    assert einvoice.container_findings(read) == []
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert einvoice.hybrid_deviations(read, text) == []  # letter and XML agree (D42)

    check = _ok(client.get(f"{url}/check", headers=tax))  # read right suffices
    assert check["structure_ok"] is True
    assert check["findings"] == []
    assert check["profile"] == "EN 16931"
    assert check["official_validation"] == "not_run"
    pdfa = check["pdfa"]
    assert pdfa["official"] is False
    assert pdfa["conformance"] == "not_verified"
    assert pdfa["claimed"] == "PDF/A-3B"
    # The letterhead renderer uses the non embedded standard fonts (AE25-01).
    assert [b for b in pdfa["blockers"] if not b.startswith("Schriften nicht eingebettet")] == []
    assert any("Helvetica" in b for b in pdfa["blockers"])

    # Authorisation, tenant separation and validation.
    assert client.get(f"{url}.pdf", headers=care).status_code == 403
    assert client.get(f"{url}.pdf", headers=other).status_code == 404
    assert client.get(f"{url}/check", headers=other).status_code == 404
    assert client.post(f"{url}/document", headers=tax).status_code == 403
    assert client.post(f"{url}/document", headers=other).status_code == 404
    assert (
        client.get(f"{A}/admin-fee-invoices/not-a-uuid/zugferd.pdf", headers=h).status_code == 422
    )
    unknown = "0190a000-0000-7000-8000-000000000000"
    assert client.get(f"{A}/admin-fee-invoices/{unknown}/zugferd.pdf", headers=h).status_code == 404

    stored = _ok(client.post(f"{url}/document", headers=h), 201)
    assert stored["created"] is True
    assert stored["check"]["structure_ok"] is True
    assert stored["check"]["pdfa"]["conformance"] == "not_verified"
    again = _ok(client.post(f"{url}/document", headers=h), 201)
    assert again["created"] is False
    assert again["document_id"] == stored["document_id"]
    detail = _ok(client.get(f"{A}/admin-fee-invoices/{invoice}", headers=h))
    assert detail["zugferd_document_id"] == stored["document_id"]
    assert detail["zugferd_url"].endswith(f"/admin-fee-invoices/{invoice}/zugferd.pdf")

    # Credit note: type 381, positive amounts, reference to the original.
    credit = _ok(
        client.post(
            f"{A}/admin-fee-invoices/{invoice}/cancel",
            json={"reason": "Einheitenzahl korrigiert", "credit_note_date": "2026-10-01"},
            headers=h,
        ),
        201,
    )
    credit_pdf = client.get(f"{A}/admin-fee-invoices/{credit['id']}/zugferd.pdf", headers=h)
    assert credit_pdf.status_code == 200, credit_pdf.text
    assert credit_pdf.headers["x-mhvp-zugferd-findings"] == "0"
    root = _cii(credit_pdf.content)
    ns = zugferd.CII_NS
    assert root.find("rsm:ExchangedDocument/ram:TypeCode", ns).text == "381"
    settlement = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement"
    assert (
        root.find(
            f"{settlement}/ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:GrandTotalAmount",
            ns,
        ).text
        == "95.20"
    )
    assert (
        root.find(f"{settlement}/ram:InvoiceReferencedDocument/ram:IssuerAssignedID", ns).text
        == "ZF-2026-000001"
    )
