"""AG11: payment type mappings list, creditor id list and property filter of the Excel export.

Expected by hand: two cost bookings on 2026-03-01, 100,00 EUR for property A and 40,00 EUR for
property B; the Excel journal filtered by property A holds only the 100,00 line (2 lines: cost
debit and bank credit), the unfiltered journal 4 lines.
"""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m18_reports import _ok

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
P = {"start": "2026-01-01", "end": "2026-12-31"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag11a-{RUN}", name=f"AG11 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag11b-{RUN}", name=f"AG11 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ag11admin", "tenant_admin", a),
            ("ag11sup", "support", a),
            ("ag11other", "tenant_admin", b),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _property(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AG11 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )


@pytest.fixture(scope="module")
def booked(database: Database, redis_url: str, world: World) -> dict[str, Any]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        h = bearer(login(c, world, "ag11admin"))
        pa = _property(c, h, "811")
        pb = _property(c, h, "812")
        hoa = next(e["id"] for e in pa["legal_entities"] if e["kind"] == "hoa")
        template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
        ledger = _ok(
            c.post(
                f"{A}/ledgers",
                json={"legal_entity_id": hoa, "template_id": template["id"]},
                headers=h,
            ),
            201,
        )["id"]
        acc = {a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
        for prop, amount in ((pa["id"], "100.00"), (pb["id"], "40.00")):
            draft = _ok(
                c.post(
                    f"{A}/ledgers/{ledger}/entries",
                    json={
                        "kind": "custom",
                        "booking_date": "2026-03-01",
                        "text": "Kosten",
                        "lines": [
                            {
                                "account_id": acc["043000"]["id"],
                                "debit": amount,
                                "property_id": prop,
                            },
                            {"account_id": acc["001200"]["id"], "credit": amount},
                        ],
                    },
                    headers=h,
                ),
                201,
            )
            _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
        return {"ledger": ledger, "acc": acc, "property_a": pa["id"], "hoa": hoa}


def _rows(content: bytes) -> list[list[Any]]:
    sheet = load_workbook(io.BytesIO(content)).active
    assert sheet is not None
    return [[c.value for c in row] for row in sheet.iter_rows()]


def test_xlsx_property_filter(client: TestClient, world: World, booked: dict[str, Any]) -> None:
    h = bearer(login(client, world, "ag11admin"))
    url = f"{A}/ledgers/{booked['ledger']}/reports/xlsx"
    full = client.get(url, params={"report": "journal", **P}, headers=h)
    assert full.status_code == 200, full.text
    filtered = client.get(
        url,
        params={"report": "journal", "property_id": booked["property_a"], **P},
        headers=h,
    )
    assert filtered.status_code == 200, filtered.text

    def data_rows(content: bytes) -> list[list[Any]]:
        rows = _rows(content)
        idx = next(i for i, r in enumerate(rows) if r[0] == "Jahr")
        return rows[idx + 1 :]

    assert len(data_rows(full.content)) == 4
    only = data_rows(filtered.content)
    assert len(only) == 1  # only the line carrying the object, 100,00 debit
    assert str(only[0][8]) in {"100.00", "100"}
    # report without object axis rejects the filter
    bad = client.get(
        url,
        params={"report": "trial_balance", "property_id": booked["property_a"], **P},
        headers=h,
    )
    assert bad.status_code == 422
    assert (
        client.get(
            url, params={"report": "journal", "property_id": "nope", **P}, headers=h
        ).status_code
        == 422
    )


def test_xlsx_property_filter_permissions(
    client: TestClient, world: World, booked: dict[str, Any]
) -> None:
    url = f"{A}/ledgers/{booked['ledger']}/reports/xlsx"
    params = {"report": "journal", "property_id": booked["property_a"], **P}
    sup = bearer(login(client, world, "ag11sup"))
    assert client.get(url, params=params, headers=sup).status_code == 403
    other = bearer(login(client, world, "ag11other"))
    assert client.get(url, params=params, headers=other).status_code == 404


def test_payment_type_accounts_list(
    client: TestClient, world: World, booked: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "ag11admin"))
    url = f"{A}/ledgers/{booked['ledger']}/payment-type-accounts"
    assert _ok(client.get(url, headers=h)) == []
    revenue = booked["acc"]["060100"]
    _ok(
        client.put(
            url, json={"payment_type_code": "hoa_fee", "account_id": revenue["id"]}, headers=h
        )
    )
    rows = _ok(client.get(url, headers=h))
    assert rows == [
        {
            "payment_type_code": "hoa_fee",
            "account_id": revenue["id"],
            "account_number": "060100",
            "account_name": revenue["name"],
        }
    ]
    assert client.get(url, params={"x": "1"}, headers=h).status_code == 422
    other = bearer(login(client, world, "ag11other"))
    assert client.get(url, headers=other).status_code == 404


def test_creditor_ids_list(client: TestClient, world: World, booked: dict[str, Any]) -> None:
    h = bearer(login(client, world, "ag11admin"))
    base = f"{A}/direct-debits/creditor-ids"
    _ok(
        client.put(
            f"{base}/legal-entities/{booked['hoa']}",
            json={"sepa_creditor_id": "DE98ZZZ09999999999"},
            headers=h,
        )
    )
    rows = _ok(client.get(base, headers=h))
    mine = next(r for r in rows if r["legal_entity_id"] == booked["hoa"])
    assert mine["sepa_creditor_id"] == "DE98ZZZ09999999999"
    assert rows[-1]["legal_entity_id"] is None
    other = bearer(login(client, world, "ag11other"))
    assert booked["hoa"] not in [r["legal_entity_id"] for r in _ok(client.get(base, headers=other))]
    assert client.get(base, params={"x": "1"}, headers=h).status_code == 422
