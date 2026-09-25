"""M18: liquidity per legal entity (free funds, reserves, deposits and expected flows apart;
receivables are not liquidity), payments by debtor, revenue, journal export with checksum,
tax advisor may read and export but not post, DATEV refused until specified."""

import asyncio
import hashlib
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rp-{RUN}", name=f"Bericht {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("m18admin", "tenant_admin"),
            ("m18tax", "tax_advisor"),
            ("m18acc", "accountant_no_banking"),
        ]:
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_reports_and_exports(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m18admin"))
    acc_user = bearer(login(client, world, "m18acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "781", "name": "Berichthaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": unit, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Eva", "last_name": f"R{RUN}"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    debtor = next(a["id"] for a in acc.values() if a["category"] == "debtor")

    def book(body: dict[str, Any]) -> dict[str, Any]:
        draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
        if body["kind"] == "opening_balance":
            _ok(
                client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=acc_user)
            )
        return _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]

    book(
        {
            "kind": "opening_balance",
            "booking_date": "2026-01-01",
            "text": "Anfangsbestand",
            "lines": [
                {"account_id": acc["001200"]["id"], "debit": "5000.00"},
                {"account_id": acc["001201"]["id"], "debit": "20000.00"},
                {"account_id": acc["009000"]["id"], "credit": "25000.00"},
            ],
        }
    )
    book(
        {
            "kind": "receivable",
            "booking_date": "2026-09-01",
            "due_date": "2026-09-03",
            "text": "Hausgeld",
            "lines": [
                {"account_id": debtor, "debit": "400.00"},
                {"account_id": acc["060100"]["id"], "credit": "400.00"},
            ],
        }
    )
    oi = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-09-30"}, headers=h)
    )[0]["id"]
    book(
        {
            "kind": "debtor_payment",
            "booking_date": "2026-09-05",
            "text": "Zahlung",
            "settlements": [{"open_item_id": oi, "amount": "150.00"}],
            "lines": [
                {"account_id": acc["001200"]["id"], "debit": "150.00"},
                {"account_id": debtor, "credit": "150.00"},
            ],
        }
    )

    liq = _ok(
        client.get(f"{A}/ledgers/{ledger}/liquidity", params={"as_of": "2026-09-30"}, headers=h)
    )
    assert Decimal(liq["free_funds"]) == Decimal("5150.00")
    assert Decimal(liq["reserve_funds"]) == Decimal("20000.00")
    assert Decimal(liq["expected_inflows"]) == Decimal("250.00")
    assert Decimal(liq["projected_free_funds"]) == Decimal("5150.00")  # receivable not counted
    pays = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/payments-by-debtor",
            params={"start": "2026-09-01", "end": "2026-09-30"},
            headers=h,
        )
    )
    assert [Decimal(p["settled"]) for p in pays] == [Decimal("150.00")]
    rev = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/revenue",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        )
    )
    assert [(r["number"], r["amount"]) for r in rev] == [("060100", "400.00")]

    tax = bearer(login(client, world, "m18tax"))
    export = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/exports/journal",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=tax,
        ),
        201,
    )
    assert export["rows"] == 7
    assert export["sha256"] == hashlib.sha256(export["content"].encode("utf-8")).hexdigest()
    assert "5000,00" in export["content"]
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={"kind": "custom", "booking_date": "2026-09-01", "text": "x", "lines": []},
            headers=tax,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/exports/datev",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=tax,
        ).status_code
        == 409
    )
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "datev_consultant_number": "12345",
                "datev_client_number": "6789",
                "datev_chart_of_accounts": "skr03",
                "datev_account_length": 4,
            },
            headers=h,
        )
    )
    datev = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/exports/datev",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=tax,
        ),
        201,
    )
    assert datev["content"].startswith('"EXTF";"7";"21";"Buchungsstapel"')
    assert "001200" in datev["content"]  # CRM account number emitted unmapped (M18-02)
