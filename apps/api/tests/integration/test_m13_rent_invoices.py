"""Rent invoices with VAT (Mietrechnung, Dauermietrechnung; rule M13-04 section "Mietrechnung",
M13-03 follow up, V21).

Expected values (precomputed, rule 0.1.8): commercial tenancy with VAT option, 1.000,00 net
and 19 %: tax 190,00, gross 1.190,00 per month (from the receivable items, rule M13-03). A
standing invoice over June and July: 2.000,00 net, 380,00 tax, 2.380,00 gross. A credit note
negates the totals: -1.000,00 / -190,00 / -1.190,00.
Numbers: gapless per legal entity and year ``MR-2026-000001`` and counting; a second legal
entity starts at 000001 again. Locks: no VAT option (BILL-0011), no tax identifier of the
legal entity (BILL-0012), no items (BILL-0013), second credit note (BILL-0014). The PDF is
a draft (watermark) while G1 is closed; with G1 open ``draft`` is false. Tenant separation:
another tenant sees nothing (404).
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m5_deposit_settlement import COMPANY
from tests.integration.test_m13_receivable_rules import _ledger, _ok, _rules, _run
from tests.integration.test_m14_invoices import _set_vat_option

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-rent-invoices"


class OpenG1:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


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
        a, _ = await services.provision_tenant(factory, slug=f"mr-{RUN}", name=f"Mietre {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"mo-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("mradmin", a), ("mrother", b)):
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
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def clients(
    database: Database, redis_url: str, s3: None
) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _contact(c: TestClient, h: dict[str, str], name: str, *, tax_id: str | None) -> str:
    body: dict[str, Any] = {
        "kind": "company",
        "company_name": f"{name} {RUN} GmbH",
        "addresses": [
            {
                "street": "Hauptstraße",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim",
            }
        ],
    }
    if tax_id:
        body["identifiers"] = [{"kind": "vat_id", "value": tax_id}]
    return str(_ok(c.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _party_of(c: TestClient, h: dict[str, str], contact_id: str) -> str:
    return str(
        _ok(
            c.post("/api/v1/parties", json={"members": [{"contact_id": contact_id}]}, headers=h),
            201,
        )["id"]
    )


def _rental(
    c: TestClient, h: dict[str, str], number: str, *, tax_id: str | None
) -> tuple[dict[str, Any], str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Gewerbehaus {number}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner = _party_of(c, h, _contact(c, h, f"Vermieter{number}", tax_id=tax_id))
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    return prop, str(entity)


def _tenancy(
    c: TestClient, h: dict[str, str], prop: str, unit_no: str, *, vat_option: str | None
) -> dict[str, Any]:
    unit = _unit(c, h, prop, unit_no)
    party = _party_of(c, h, _contact(c, h, f"Laden{unit_no}", tax_id=None))
    extra = {"vat_option": vat_option} if vat_option else {}
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                **extra,
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/payments",
            json={
                "payment_type_code": "rent",
                "net": "1000.00",
                "vat_percent": "19",
                "gross": "1190.00",
                "valid_from": "2020-01-01",
                "valid_to": None,
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
    return contract  # type: ignore[no-any-return]


def _vat_ledger(
    c: TestClient, h: dict[str, str], entity: str, world: World, database: Database, redis_url: str
) -> None:
    ledger, _acc = _ledger(c, h, entity)
    asyncio.run(_set_vat_option(_settings(database, redis_url), world.tenant_a, ledger))
    tax = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "017600",
                "name": "Umsatzsteuer Sollstellung",
                "category": "tax",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "vat_output", "account_id": tax["id"]},
            headers=h,
        )
    )


def _invoice(
    c: TestClient, h: dict[str, str], contract: str, start: str, end: str, **extra: Any
) -> Any:
    return c.post(
        f"/api/v1/contracts/{contract}/rent-invoices",
        json={"period_start": start, "period_end": end, **extra},
        headers=h,
    )


def _problem(response: Any, code: str) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == code, response.text


def test_rent_invoices_numbering_locks_credit_note_and_tenant_separation(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, open_ = clients
    h = bearer(login(closed, world, "mradmin"))
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _rules(closed, h, vat_enabled=True)
    prop, entity = _rental(closed, h, "801", tax_id="DE123456789")
    _vat_ledger(closed, h, entity, world, database, redis_url)
    shop = _tenancy(closed, h, prop["id"], "01", vat_option="commercial_full_vat")
    plain = _tenancy(closed, h, prop["id"], "02", vat_option=None)

    # Field list of mandatory content (documentation, to be checked by the tax adviser).
    fields = _ok(closed.get(f"{A}/rent-invoices/fields", headers=h))
    assert {f["field"] for f in fields} >= {"invoice_number", "issuer_tax_id", "vat", "gross"}

    # No items yet: locked, no number consumed.
    _problem(_invoice(closed, h, shop["id"], "2026-06-01", "2026-06-30"), "MHVP-BILL-0013")
    # Without VAT option: locked.
    _problem(_invoice(closed, h, plain["id"], "2026-06-01", "2026-06-30"), "MHVP-BILL-0011")

    june = _run(closed, h, "2026-06-01", "contract", shop["id"])
    assert june["items"][0]["status"] == "ready"
    _ok(open_.post(f"{A}/receivable-runs/{june['id']}/post", headers=h))
    july = _run(closed, h, "2026-07-01", "contract", shop["id"])
    assert july["items"][0]["status"] == "ready"  # stays a preview (G1 closed)

    # June from the posted item: draft (G1 closed), gapless number, precomputed amounts.
    first = _ok(_invoice(closed, h, shop["id"], "2026-06-01", "2026-06-30"), 201)
    assert first["number"] == "ENTWURF-2026-000001"
    assert (first["kind"], first["status"], first["draft"]) == ("invoice", "issued", True)
    assert (first["net_total"], first["vat_total"], first["gross_total"]) == (
        "1000.00",
        "190.00",
        "1190.00",
    )
    assert first["tax_identifier_kind"] == "vat_id"
    assert first["document_id"] is not None
    [line] = first["lines"]
    assert (line["net"], line["vat"], line["gross"]) == ("1000.00", "190.00", "1190.00")
    assert Decimal(line["vat_percent"]) == Decimal("19")
    assert (line["period_start"], line["period_end"]) == ("2026-06-01", "2026-06-30")

    # July from the ready preview item; still numbered in sequence.
    second = _ok(_invoice(closed, h, shop["id"], "2026-07-01", "2026-07-31"), 201)
    assert second["number"] == "ENTWURF-2026-000002"

    # Standing invoice over both months: one line per month, summed totals.
    standing = _ok(_invoice(closed, h, shop["id"], "2026-06-01", "2026-07-31", standing=True), 201)
    assert (standing["kind"], standing["number"]) == ("standing", "ENTWURF-2026-000003")
    assert len(standing["lines"]) == 2
    assert (standing["net_total"], standing["vat_total"], standing["gross_total"]) == (
        "2000.00",
        "380.00",
        "2380.00",
    )

    # PDF: stored document handed out, draft watermark text in the letter.
    pdf = closed.get(f"/api/v1/contracts/{shop['id']}/rent-invoices/{first['id']}/pdf", headers=h)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    # With G1 open the invoice is no draft.
    released = _ok(
        open_.post(
            f"/api/v1/contracts/{shop['id']}/rent-invoices",
            json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
            headers=h,
        ),
        201,
    )
    assert (released["draft"], released["number"]) == (False, "MR-2026-000001")

    # Cancellation only by credit note: the invoice stays, negated amounts, new number.
    note = _ok(
        closed.post(
            f"/api/v1/contracts/{shop['id']}/rent-invoices/{first['id']}/credit-note", headers=h
        ),
        201,
    )
    assert (note["kind"], note["number"], note["cancels_invoice_id"]) == (
        "credit_note",
        "ENTWURF-2026-000004",
        first["id"],
    )
    assert (note["net_total"], note["vat_total"], note["gross_total"]) == (
        "-1000.00",
        "-190.00",
        "-1190.00",
    )
    listed = {
        r["id"]: r
        for r in _ok(closed.get(f"/api/v1/contracts/{shop['id']}/rent-invoices", headers=h))
    }
    assert len(listed) == 5
    assert listed[first["id"]]["status"] == "cancelled"
    assert listed[first["id"]]["cancelled_by_invoice_id"] == note["id"]
    _problem(
        closed.post(
            f"/api/v1/contracts/{shop['id']}/rent-invoices/{first['id']}/credit-note", headers=h
        ),
        "MHVP-BILL-0014",
    )
    assert closed.delete(
        f"/api/v1/contracts/{shop['id']}/rent-invoices/{first['id']}", headers=h
    ).status_code in (404, 405)  # no delete route exists (rule 0.1.7)

    # Second legal entity: own number series; without a tax identifier the output is locked.
    prop2, entity2 = _rental(closed, h, "802", tax_id=None)
    _vat_ledger(closed, h, entity2, world, database, redis_url)
    shop2 = _tenancy(closed, h, prop2["id"], "01", vat_option="commercial_full_vat")
    _run(closed, h, "2026-06-01", "contract", shop2["id"])
    _problem(_invoice(closed, h, shop2["id"], "2026-06-01", "2026-06-30"), "MHVP-BILL-0012")
    assert _ok(closed.get(f"/api/v1/contracts/{shop2['id']}/rent-invoices", headers=h)) == []
    prop3, entity3 = _rental(closed, h, "803", tax_id="DE987654321")
    _vat_ledger(closed, h, entity3, world, database, redis_url)
    shop3 = _tenancy(closed, h, prop3["id"], "01", vat_option="commercial_full_vat")
    _run(closed, h, "2026-06-01", "contract", shop3["id"])
    other_entity = _ok(_invoice(closed, h, shop3["id"], "2026-06-01", "2026-06-30"), 201)
    assert other_entity["number"] == "ENTWURF-2026-000001"
    assert other_entity["legal_entity_id"] == entity3

    # Tenant separation: the other tenant sees neither list nor PDF.
    other = bearer(login(closed, world, "mrother"))
    assert (
        closed.get(f"/api/v1/contracts/{shop['id']}/rent-invoices", headers=other).status_code
        == 404
    )
    assert (
        closed.get(
            f"/api/v1/contracts/{shop['id']}/rent-invoices/{first['id']}/pdf", headers=other
        ).status_code
        == 404
    )

    # AC03-01: switch for draft numbers. Default draft_numbers; regular_numbers consumes MR-;
    # reject_when_g1_closed refuses without consuming a number; G1 open keeps the MR- series.
    mode_url = f"{A}/rent-invoices/numbering-mode"
    assert _ok(closed.get(mode_url, headers=h))["mode"] == "draft_numbers"
    assert _ok(closed.get(mode_url, headers=other))["mode"] == "draft_numbers"
    assert closed.get(mode_url, params={"x": "1"}, headers=h).status_code == 422
    assert closed.put(mode_url, json={"mode": "bogus"}, headers=h).status_code == 422
    assert closed.put(mode_url, json={"mode": "regular_numbers"}, headers=other).status_code == 200
    assert _ok(closed.get(mode_url, headers=h))["mode"] == "draft_numbers"  # tenant separation
    _ok(closed.put(mode_url, json={"mode": "regular_numbers"}, headers=h))
    regular = _ok(_invoice(closed, h, shop3["id"], "2026-06-01", "2026-06-30"), 201)
    assert regular["number"] == "MR-2026-000001"
    assert regular["draft"] is True
    assert regular["legal_entity_id"] == entity3
    _ok(closed.put(mode_url, json={"mode": "reject_when_g1_closed"}, headers=h))
    _problem(_invoice(closed, h, shop3["id"], "2026-06-01", "2026-06-30"), "MHVP-BILL-0360")
    released3 = _ok(
        open_.post(
            f"/api/v1/contracts/{shop3['id']}/rent-invoices",
            json={"period_start": "2026-06-01", "period_end": "2026-06-30"},
            headers=h,
        ),
        201,
    )
    assert (released3["draft"], released3["number"]) == (False, "MR-2026-000002")
    _ok(closed.put(mode_url, json={"mode": "draft_numbers"}, headers=h))
    again = _ok(_invoice(closed, h, shop3["id"], "2026-06-01", "2026-06-30"), 201)
    assert again["number"] == "ENTWURF-2026-000002"
