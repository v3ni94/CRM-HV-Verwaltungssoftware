"""AE21 (Welle 16, Punkt 21, Q15-01): object column ``journal_line.property_id``.

Expected values, computed by hand:
- Object A (unit A01), object B (unit B01), HOA ledger of object A, ownership contract on A01.
- Entry 1 (posted 10.03.2026): bank 119,00 debit without unit, revenue 119,00 credit on A01
  with 19,00 VAT on 100,00 net: bank line without object, revenue line object A.
- Entry 2 (draft, contract on A01): both lines without unit get object A from the contract.
- Entry 3 (posted 11.03.2026): revenue 59,50 credit with explicit object B, 9,50 VAT on 50,00
  net: object B; a hint ``ledger_mismatch`` (the ledger belongs to object A).
- VAT overview by object: A 19,00, B 9,50, total 28,50 (equal to the plain VAT overview).
- Monthly matrix with object A: revenue 119,00; with object B: 59,50.
- Reversal of entry 1 keeps object A on the revenue line.
- Migration 0377 (downgrade to 0376 and upgrade again): the posted revenue line with unit A01
  and both lines of the posted contract entry get object A, the bank line without unit and
  contract stays empty; the posted line guard is enabled again afterwards.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration import conftest as itc
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae21a-{RUN}", name=f"AE21 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae21b-{RUN}", name=f"AE21 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae21admin", a, "tenant_admin"),
            ("ae21care", a, "caretaker"),
            ("ae21other", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"AE21 Haus {number}",
                "management_type": "hoa",
                "street": "Rheinpromenade",
                "house_number": number,
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )


def _setup(client: TestClient, h: dict[str, str], prefix: str) -> dict[str, Any]:
    prop_a = _property(client, h, f"{prefix}1")
    prop_b = _property(client, h, f"{prefix}2")
    unit_a = _unit(client, h, prop_a["id"], "01")
    unit_b = _unit(client, h, prop_b["id"], "01")
    hoa = next(e["id"] for e in prop_a["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/accounts/{acc['060100']['id']}/tax-flags",
            json={"eur_relevant": True, "ust_relevant": True, "mixed_use_review": False},
            headers=h,
        )
    )
    owner, _ = _party(client, h, "Eigentuemerin")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit_a,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    return {
        "a": prop_a["id"],
        "b": prop_b["id"],
        "unit_a": unit_a,
        "unit_b": unit_b,
        "ledger": ledger,
        "bank": acc["001200"]["id"],
        "revenue": acc["060100"]["id"],
        "contract": contract["id"],
    }


def _entry(
    w: dict[str, Any],
    day: str,
    gross: str,
    *,
    net: str | None = None,
    vat: str | None = None,
    revenue_extra: dict[str, Any] | None = None,
    contract: bool = False,
) -> dict[str, Any]:
    revenue: dict[str, Any] = {"account_id": w["revenue"], "credit": gross}
    if vat is not None:
        revenue |= {"vat_percent": "19", "vat_amount": vat, "net_amount": net}
    revenue |= revenue_extra or {}
    body: dict[str, Any] = {
        "kind": "custom",
        "booking_date": day,
        "text": "Erlös AE21",
        "lines": [{"account_id": w["bank"], "debit": gross}, revenue],
    }
    if contract:
        body["contract_id"] = w["contract"]
    return body


def _draft(client: TestClient, h: dict[str, str], w: dict[str, Any], body: Any) -> Any:
    return client.post(f"{A}/ledgers/{w['ledger']}/entries", json=body, headers=h)


def _post(client: TestClient, h: dict[str, str], w: dict[str, Any], entry_id: str) -> Any:
    return _ok(client.post(f"{A}/ledgers/{w['ledger']}/entries/{entry_id}/post", headers=h))


def test_line_property_derivation_reports_and_drift(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae21admin"))
    care = bearer(login(client, world, "ae21care"))
    other = bearer(login(client, world, "ae21other"))
    w = _setup(client, h, "21")
    ledger = w["ledger"]

    # Entry 1: object from the unit; the bank line has neither unit nor contract.
    first = _ok(
        _draft(
            client,
            h,
            w,
            _entry(
                w,
                "2026-03-10",
                "119.00",
                net="100.00",
                vat="19.00",
                revenue_extra={"unit_id": w["unit_a"]},
            ),
        ),
        201,
    )
    assert [ln["property_id"] for ln in first["lines"]] == [None, w["a"]]
    first = _post(client, h, w, first["id"])

    # Entry 2: object from the contract of the entry (lines without unit).
    second = _ok(_draft(client, h, w, _entry(w, "2026-03-12", "40.00", contract=True)), 201)
    assert [ln["property_id"] for ln in second["lines"]] == [w["a"], w["a"]]

    # Entry 3: explicit object B without unit (hint: the ledger belongs to object A).
    third = _ok(
        _draft(
            client,
            h,
            w,
            _entry(
                w,
                "2026-03-11",
                "59.50",
                net="50.00",
                vat="9.50",
                revenue_extra={"property_id": w["b"]},
            ),
        ),
        201,
    )
    assert third["lines"][1]["property_id"] == w["b"]
    _post(client, h, w, third["id"])

    # Validation: explicit object against the unit, unknown unit, unknown or foreign object.
    mismatch = _draft(
        client,
        h,
        w,
        _entry(
            w, "2026-03-13", "10.00", revenue_extra={"unit_id": w["unit_a"], "property_id": w["b"]}
        ),
    )
    assert mismatch.status_code == 422, mismatch.text
    assert "Objekt der Einheit" in mismatch.json()["detail"]
    unknown_unit = _draft(
        client, h, w, _entry(w, "2026-03-13", "10.00", revenue_extra={"unit_id": str(uuid.uuid4())})
    )
    assert unknown_unit.status_code == 422
    unknown_prop = _draft(
        client,
        h,
        w,
        _entry(w, "2026-03-13", "10.00", revenue_extra={"property_id": str(uuid.uuid4())}),
    )
    assert unknown_prop.status_code == 422
    other_prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "219",
                "name": "AE21 fremd",
                "management_type": "hoa",
                "street": "Weg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=other,
        ),
        201,
    )
    foreign = _draft(
        client,
        h,
        w,
        _entry(w, "2026-03-13", "10.00", revenue_extra={"property_id": other_prop["id"]}),
    )
    assert foreign.status_code == 422

    # Reversal keeps the object of the original lines.
    rev = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{first['id']}/reverse",
            json={"reason": "AE21 Storno", "booking_date": "2026-03-20"},
            headers=h,
        ),
        201,
    )
    assert [ln["property_id"] for ln in rev["lines"]] == [None, w["a"]]

    # VAT overview by object reads the column (reversal date outside the period).
    params = {"start": "2026-03-01", "end": "2026-03-15"}
    vat = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/reports/vat-overview-by-property", params=params, headers=h
        )
    )
    by_prop = {r["property_id"]: r for r in vat["rows"]}
    assert Decimal(by_prop[w["a"]]["output_vat"]) == Decimal("19.00")
    assert Decimal(by_prop[w["b"]]["output_vat"]) == Decimal("9.50")
    assert Decimal(vat["total_output_vat"]) == Decimal("28.50")
    plain = _ok(client.get(f"{A}/ledgers/{ledger}/reports/vat-overview", params=params, headers=h))
    assert Decimal(plain["total_output_vat"]) == Decimal(vat["total_output_vat"])

    # Monthly matrix and income statement filtered by object.
    url = f"{A}/ledgers/{ledger}/reports/monthly-matrix"
    for prop, total in ((w["a"], "119.00"), (w["b"], "59.50")):
        matrix = _ok(client.get(url, params={**params, "property_id": prop}, headers=h))
        assert matrix["header"]["filters"]["property_id"] == prop
        revenue = next(a for a in matrix["accounts"] if a["number"] == "060100")
        assert Decimal(revenue["total"]) == Decimal(total)
    income = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/reports/income-expense",
            params={**params, "property_id": w["b"]},
            headers=h,
        )
    )
    assert Decimal(income["total_revenue"]) == Decimal("59.50")

    # Journal filter by object.
    journal = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries", params={"property_id": w["b"]}, headers=h)
    )
    assert [e["id"] for e in journal] == [third["id"]]

    # Drift: the explicit object B in the ledger of object A is a hint, no finding.
    drift_url = f"{A}/ledgers/{ledger}/reports/line-property-drift"
    drift = _ok(client.get(drift_url, headers=h))
    assert drift["counts"]["ledger_mismatch"] == 1
    assert drift["findings"] == 0
    assert drift["counts"]["contract_unfilled"] == 0
    hint = drift["rows"][0]
    assert (hint["kind"], hint["severity"], hint["expected_property_id"]) == (
        "ledger_mismatch",
        "hint",
        w["a"],
    )
    assert drift["header"]["report"] == "line_property_drift"
    checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert not [f for f in checks["findings"] if "Objekt" in f]

    # Database rule for every writer: a line with unit keeps the object of its unit.
    engine = create_engine(world.app_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            line_id = conn.execute(
                text(
                    "SELECT l.id FROM journal_line l WHERE l.journal_entry_id = :e "
                    "AND l.line_no = 2"
                ),
                {"e": second["id"]},
            ).scalar_one()
            # Draft line without unit: the object can be removed (legacy state for the drift).
            conn.execute(
                text("UPDATE journal_line SET property_id = NULL WHERE id = :i"), {"i": line_id}
            )
            conn.execute(
                text("UPDATE journal_line SET unit_id = :u WHERE id = :i"),
                {"u": w["unit_a"], "i": line_id},
            )
            filled = conn.execute(
                text("SELECT property_id FROM journal_line WHERE id = :i"), {"i": line_id}
            ).scalar_one()
            assert str(filled) == w["a"]
            conn.execute(
                text("UPDATE journal_line SET unit_id = NULL, property_id = NULL WHERE id = :i"),
                {"i": line_id},
            )
        with engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            refused = text("UPDATE journal_line SET unit_id = :u, property_id = :p WHERE id = :i")
            with pytest.raises(DBAPIError, match="differs from the property of unit"):
                conn.execute(refused, {"u": w["unit_a"], "p": w["b"], "i": line_id})
            conn.rollback()
    finally:
        engine.dispose()
    drift = _ok(client.get(drift_url, headers=h))
    assert drift["counts"]["contract_unfilled"] == 1
    # Without object: bank lines of entries 1 and 3 and of the reversal, revenue line of entry 2.
    assert drift["without_property"] == 4
    period = _ok(
        client.get(drift_url, params={"start": "2026-03-12", "end": "2026-03-12"}, headers=h)
    )
    assert period["counts"]["contract_unfilled"] == 1
    assert period["counts"]["ledger_mismatch"] == 0

    # Authorization, tenant separation, validation.
    assert client.get(drift_url, headers=care).status_code == 403
    assert client.get(drift_url, headers=other).status_code == 404
    bad = client.get(drift_url, params={"start": "2026-03-31", "end": "2026-03-01"}, headers=h)
    assert bad.status_code == 422
    assert client.get(drift_url, params={"foo": "1"}, headers=h).status_code == 422


def test_migration_0377_fills_posted_lines(
    client: TestClient, world: World, database: Database, migrator_engine: Engine
) -> None:
    """Runs last in this module: it downgrades to 0376 and upgrades to head again."""
    h = bearer(login(client, world, "ae21admin"))
    w = _setup(client, h, "22")
    unit_entry = _ok(
        _draft(
            client,
            h,
            w,
            _entry(w, "2026-04-01", "20.00", revenue_extra={"unit_id": w["unit_a"]}),
        ),
        201,
    )
    _post(client, h, w, unit_entry["id"])
    contract_entry = _ok(_draft(client, h, w, _entry(w, "2026-04-02", "30.00", contract=True)), 201)
    _post(client, h, w, contract_entry["id"])
    config = itc.alembic_config(database.migrator_url)
    command.downgrade(config, "0376")
    try:
        with migrator_engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'journal_line' AND column_name = 'property_id'"
                )
            ).scalar_one()
            assert columns == 0
        # As in production: the migrator without tenant context, posted lines in the table.
        command.upgrade(config, "0377")
        with migrator_engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            rows = conn.execute(
                text(
                    "SELECT journal_entry_id, line_no, property_id FROM journal_line "
                    "WHERE journal_entry_id IN (:a, :b) ORDER BY journal_entry_id, line_no"
                ),
                {"a": unit_entry["id"], "b": contract_entry["id"]},
            ).all()
            got = {(str(r[0]), r[1]): (str(r[2]) if r[2] else None) for r in rows}
            assert got == {
                (unit_entry["id"], 1): None,
                (unit_entry["id"], 2): w["a"],
                (contract_entry["id"], 1): w["a"],
                (contract_entry["id"], 2): w["a"],
            }
            enabled = conn.execute(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'journal_line_guard'")
            ).scalar_one()
            assert enabled == "O"
            with pytest.raises(DBAPIError, match="immutable"):
                conn.execute(
                    text(
                        "UPDATE journal_line SET property_id = :p "
                        "WHERE journal_entry_id = :e AND line_no = 1"
                    ),
                    {"p": w["b"], "e": unit_entry["id"]},
                )
            conn.rollback()
    finally:
        command.upgrade(config, "head")
