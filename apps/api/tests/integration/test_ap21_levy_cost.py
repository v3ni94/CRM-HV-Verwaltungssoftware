"""AP21 (GAM-109, GAM-110). Expected values by hand:

* GAM-109: one cost position 1.000,00 assigned to sub community H1 without basis resolution or
  document -> hint ``sub_community_basis_missing``; switch off: internal approval passes the
  sub community check; switch on: 409 MHVP-HOA-0046.
* GAM-110: levy 10.000,00 in 3 instalments from 01.03.2026, MEA 600 / 400 -> unit 01 charged
  2.000,00 in March (only the March run is posted), paid 1.500,00 -> open 500,00; April and May
  0,00. Use of funds 800,00 on the use account -> one usage row 800,00. Refund proposals:
  switch off -> 409 MHVP-HOA-0047; on: 1.600,00 > 1.500,00 received -> 422; 1.000,00 -> 201;
  further 600,00 > 500,00 still available -> 422; withdraw -> status withdrawn.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m24_hoa import _book_cost, _hoa_ledger, _owner

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap21a-{RUN}", name=f"AP21 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap21b-{RUN}", name=f"AP21 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ap21admin", a, "tenant_admin"),
            ("ap21second", a, "tenant_admin"),
            ("ap21reader", a, "read_only"),
            ("ap21other", b, "tenant_admin"),
        ):
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


def _settings_put(client: TestClient, h: dict[str, str], lock: bool, refunds: bool) -> Any:
    return _ok(
        client.put(
            f"{H}/levy-cost-settings",
            json={"sub_community_basis_lock": lock, "levy_refund_proposals": refunds},
            headers=h,
        )
    )


def test_gam109_sub_community_basis(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ap21admin"))
    h2 = bearer(login(client, world, "ap21second"))
    hr = bearer(login(client, world, "ap21reader"))
    hb = bearer(login(client, world, "ap21other"))
    defaults = _ok(client.get(f"{H}/levy-cost-settings", headers=h))
    assert (defaults["sub_community_basis_lock"], defaults["levy_refund_proposals"]) == (
        False,
        False,
    )
    assert (
        client.put(
            f"{H}/levy-cost-settings",
            json={"sub_community_basis_lock": True, "levy_refund_proposals": False},
            headers=hr,
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{H}/levy-cost-settings", json={"sub_community_basis_lock": True}, headers=h
        ).status_code
        == 422
    )

    w = _hoa_ledger(client, h, "821")
    for no in ("01", "02"):
        _owner(client, h, w["property"], no, "500", w["keys"]["MEA"], {})
    sub = _ok(
        client.post(
            f"/api/v1/properties/{w['property']}/sub-communities",
            json={"code": "H1", "name": "Haus 1"},
            headers=h,
        ),
        201,
    )["id"]
    other = _hoa_ledger(client, h, "822")
    foreign_sub = _ok(
        client.post(
            f"/api/v1/properties/{other['property']}/sub-communities",
            json={"code": "H9", "name": "Haus 9"},
            headers=h,
        ),
        201,
    )["id"]
    _book_cost(
        client, h, w["ledger"], w["acc"]["001200"], w["acc"]["043000"], "1000.00", "2025-02-01"
    )
    sid = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h),
        201,
    )["id"]
    cost = {
        "label": "Aufzug Haus 1",
        "amount": "1000.00",
        "allocation_key_id": w["keys"]["MEA"],
        "basis": "Gemeinschaftsordnung, Verteilung nach MEA",
        "account_id": w["acc"]["043000"],
    }
    bad = client.post(
        f"{H}/statements/{sid}/costs", json=cost | {"sub_community_id": foreign_sub}, headers=h
    )
    assert bad.status_code == 422, bad.text
    _ok(
        client.post(
            f"{H}/statements/{sid}/costs", json=cost | {"sub_community_id": sub}, headers=h
        ),
        201,
    )
    item = _ok(client.get(f"{H}/statements/{sid}", headers=h))["cost_items"][0]
    assert item["sub_community_id"] == sub
    assert item["sub_community_basis_missing"] is True

    check = _ok(client.get(f"{H}/statements/{sid}/sub-community-check", headers=h))
    assert (check["lock_active"], check["blocks_internal_approval"]) == (False, False)
    assert [(i["label"], i["amount"]) for i in check["issues"]] == [("Aufzug Haus 1", "1000.00")]
    assert client.get(f"{H}/statements/{sid}/sub-community-check", headers=hb).status_code == 404
    assert client.get(f"{H}/statements/{sid}/sub-community-check?x=1", headers=h).status_code == 422

    _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))
    _settings_put(client, h, True, False)
    assert _ok(client.get(f"{H}/statements/{sid}/sub-community-check", headers=h))[
        "blocks_internal_approval"
    ]
    blocked = client.post(
        f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "MHVP-HOA-0046"
    assert "Aufzug Haus 1" in blocked.json()["detail"]
    assert _ok(client.get(f"{H}/statements/{sid}", headers=h))["status"] == "calculated"

    # Default (switch off): hint only, the approval is not stopped by the sub community check.
    _settings_put(client, h, False, False)
    approved = _ok(
        client.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    assert approved["status"] == "internally_approved"


def test_gam110_payment_status_and_refund_proposals(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ap21admin"))
    hr = bearer(login(client, world, "ap21reader"))
    hb = bearer(login(client, world, "ap21other"))
    w = _hoa_ledger(client, h, "823")
    u1, c1 = _owner(client, h, w["property"], "01", "600", w["keys"]["MEA"], {})
    u2, _ = _owner(client, h, w["property"], "02", "400", w["keys"]["MEA"], {})
    ledger, acc = w["ledger"], w["acc"]

    def account(number: str, name: str, category: str, type_: str) -> str:
        return str(
            _ok(
                client.post(
                    f"{A}/ledgers/{ledger}/accounts",
                    json={"number": number, "name": name, "category": category, "type": type_},
                    headers=h,
                ),
                201,
            )["id"]
        )

    use = account("049900", "Dachsanierung", "cost", "expense")
    revenue = account("060300", "Sonderumlage", "revenue", "income")
    lid = _ok(
        client.post(
            f"{H}/special-levies",
            json={
                "ledger_id": ledger,
                "purpose": "Dachsanierung",
                "total": "10000.00",
                "allocation_key_id": w["keys"]["MEA"],
                "first_due": "2026-03-01",
                "instalments": 3,
                "account_id": use,
            },
            headers=h,
        ),
        201,
    )["id"]
    calc = _ok(client.post(f"{H}/special-levies/{lid}/calculate", headers=h))

    def resolution(hash_: str | None, subject: str) -> str:
        return str(
            _ok(
                client.post(
                    f"{H}/resolutions",
                    json={
                        "legal_entity_id": w["hoa"],
                        "decided_on": "2026-02-10",
                        "subject": subject,
                        "wording": f"{subject} wird beschlossen.",
                        "status": "positive",
                        "subject_type": "special_levy",
                        "subject_id": lid,
                        "snapshot_hash": hash_,
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    _ok(
        client.post(
            f"{H}/special-levies/{lid}/resolve",
            json={"resolution_id": resolution(calc["snapshot_hash"], "Sonderumlage Dach")},
            headers=h,
        )
    )
    _ok(client.post(f"{H}/special-levies/{lid}/apply", headers=h))
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "special_levy", "account_id": revenue},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = next(
        i
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h
            )
        )
        if i["account_id"] != acc["001200"]
    )
    for lines, settle, kind in [
        (
            [
                {"account_id": acc["001200"], "debit": "1500.00"},
                {"account_id": item["account_id"], "credit": "1500.00"},
            ],
            [{"open_item_id": item["id"], "amount": "1500.00"}],
            "debtor_payment",
        ),
        (
            [
                {"account_id": use, "debit": "800.00"},
                {"account_id": acc["001200"], "credit": "800.00"},
            ],
            [],
            "custom",
        ),
    ]:
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": kind,
                    "booking_date": "2026-03-10",
                    "text": "Dachdecker" if kind == "custom" else "Zahlung",
                    "lines": lines,
                    "settlements": settle,
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))

    status = _ok(client.get(f"{H}/special-levies/{lid}/payment-status", headers=h))
    by = {u["unit_number"]: u for u in status["units"]}
    assert [
        (i["due_month"], i["charged"], i["received"], i["open"]) for i in by["01"]["instalments"]
    ] == [
        ("2026-03-01", "2000.00", "1500.00", "500.00"),
        ("2026-04-01", "0.00", "0.00", "0.00"),
        ("2026-05-01", "0.00", "0.00", "0.00"),
    ]
    assert (by["01"]["charged"], by["01"]["received"], by["01"]["open"]) == (
        "2000.00",
        "1500.00",
        "500.00",
    )
    assert by["02"]["received"] == "0.00"
    assert [(u["text"], u["amount"]) for u in status["usage"]] == [("Dachdecker", "800.00")]
    assert status["usage_truncated"] is False
    assert client.get(f"{H}/special-levies/{lid}/payment-status", headers=hb).status_code == 404
    assert client.get(f"{H}/special-levies/{lid}/payment-status?x=1", headers=h).status_code == 422

    refund_res = resolution(None, "Teilerstattung Sonderumlage")
    body = {
        "unit_id": u1,
        "amount": "1000.00",
        "reason": "Kosten geringer",
        "resolution_id": refund_res,
    }
    off = client.post(f"{H}/special-levies/{lid}/refunds", json=body, headers=h)
    assert off.status_code == 409, off.text
    assert off.json()["code"] == "MHVP-HOA-0047"
    _settings_put(client, h, False, True)
    assert (
        client.post(f"{H}/special-levies/{lid}/refunds", json=body, headers=hr).status_code == 403
    )
    assert (
        client.post(f"{H}/special-levies/{lid}/refunds", json=body, headers=hb).status_code == 404
    )
    assert (
        client.post(
            f"{H}/special-levies/{lid}/refunds", json=body | {"amount": "0"}, headers=h
        ).status_code
        == 422
    )
    too_much = client.post(
        f"{H}/special-levies/{lid}/refunds", json=body | {"amount": "1600.00"}, headers=h
    )
    assert too_much.status_code == 422, too_much.text
    assert (
        client.post(
            f"{H}/special-levies/{lid}/refunds", json=body | {"unit_id": c1["id"]}, headers=h
        ).status_code
        == 422
    )
    created = _ok(client.post(f"{H}/special-levies/{lid}/refunds", json=body, headers=h), 201)
    assert (created["status"], created["amount"], created["payout_locked"]) == (
        "proposed",
        "1000.00",
        True,
    )
    assert "G2" in created["note"]
    assert (
        client.post(
            f"{H}/special-levies/{lid}/refunds", json=body | {"amount": "600.00"}, headers=h
        ).status_code
        == 422
    )
    status = _ok(client.get(f"{H}/special-levies/{lid}/payment-status", headers=h))
    assert next(u for u in status["units"] if u["unit_id"] == u1)["refunds_proposed"] == "1000.00"
    listed = _ok(client.get(f"{H}/special-levies/{lid}/refunds", headers=h))
    assert [r["id"] for r in listed] == [created["id"]]
    assert client.get(f"{H}/special-levies/{lid}/refunds", headers=hb).status_code == 404
    rid = created["id"]
    assert (
        client.post(
            f"{H}/special-levies/{lid}/refunds/{rid}/withdraw", json={"reason": "x"}, headers=h
        ).status_code
        == 422
    )
    withdrawn = _ok(
        client.post(
            f"{H}/special-levies/{lid}/refunds/{rid}/withdraw",
            json={"reason": "Beschluss aufgehoben"},
            headers=h,
        )
    )
    assert (withdrawn["status"], withdrawn["withdrawn_reason"]) == (
        "withdrawn",
        "Beschluss aufgehoben",
    )
    assert (
        client.post(
            f"{H}/special-levies/{lid}/refunds/{rid}/withdraw",
            json={"reason": "nochmal"},
            headers=h,
        ).status_code
        == 409
    )
    events = _ok(
        client.get(
            "/api/v1/tenant/events", params={"type": "special_levy_refund.proposed"}, headers=h
        )
    )
    assert events
    assert u2
