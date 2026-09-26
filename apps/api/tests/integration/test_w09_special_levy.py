"""W09 special levy. Expected values by hand: MEA 600 / 400, total 10.000,00 in 3 instalments
from 01.03.2026 -> unit 01: 6.000,00 = 3 x 2.000,00; unit 02: 4.000,00 = 1.333,33 + 1.333,33 +
1.333,34 (remainder on the last instalment). March run for unit 01 charges 2.000,00; paid
1.500,00 -> open 500,00. Use of funds 800,00 on the levy account -> earmarked 700,00."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m24_hoa import _owner

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
        a, _ = await services.provision_tenant(factory, slug=f"su-{RUN}", name=f"SU {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("w09admin", "w09second"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def test_special_levy(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w09admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "791", "name": "WEG Dach", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    u1, c1 = _owner(client, h, prop["id"], "01", "600", keys["MEA"], {})
    u2, _ = _owner(client, h, prop["id"], "02", "400", keys["MEA"], {})
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
    use = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "049900",
                "name": "Dachsanierung",
                "category": "cost",
                "type": "expense",
            },
            headers=h,
        ),
        201,
    )["id"]
    levy = _ok(
        client.post(
            f"{H}/special-levies",
            json={
                "ledger_id": ledger,
                "purpose": "Dachsanierung",
                "total": "10000.00",
                "allocation_key_id": keys["MEA"],
                "first_due": "2026-03-01",
                "instalments": 3,
                "account_id": use,
            },
            headers=h,
        ),
        201,
    )
    lid = levy["id"]
    assert client.post(f"{H}/special-levies/{lid}/apply", headers=h).status_code == 409
    calc = _ok(client.post(f"{H}/special-levies/{lid}/calculate", headers=h))
    by = {u["unit_number"]: u for u in calc["snapshot"]["units"]}
    assert [i["amount"] for i in by["01"]["instalments"]] == ["2000.00"] * 3
    assert [i["amount"] for i in by["02"]["instalments"]] == ["1333.33", "1333.33", "1333.34"]
    assert [i["due_month"] for i in by["02"]["instalments"]] == [
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
    ]

    def resolution(hash_: str) -> str:
        return str(
            _ok(
                client.post(
                    f"{H}/resolutions",
                    json={
                        "legal_entity_id": hoa,
                        "decided_on": "2026-02-10",
                        "subject": "Sonderumlage Dach",
                        "wording": "Sonderumlage für die Dachsanierung wird beschlossen.",
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

    wrong = resolution("0" * 64)
    assert (
        client.post(
            f"{H}/special-levies/{lid}/resolve", json={"resolution_id": wrong}, headers=h
        ).status_code
        == 409
    )
    right = resolution(calc["snapshot_hash"])
    _ok(client.post(f"{H}/special-levies/{lid}/resolve", json={"resolution_id": right}, headers=h))
    applied = _ok(client.post(f"{H}/special-levies/{lid}/apply", headers=h))
    assert applied["payments_created"] == 6
    again = _ok(client.post(f"{H}/special-levies/{lid}/apply", headers=h))
    assert "payments_created" not in again  # idempotent

    # Overlapping second levy cannot be applied (report would mix receivables).
    other = _ok(
        client.post(
            f"{H}/special-levies",
            json={
                "ledger_id": ledger,
                "purpose": "Fassade",
                "total": "1000.00",
                "allocation_key_id": keys["MEA"],
                "unit_ids": [u2],
                "first_due": "2026-05-01",
            },
            headers=h,
        ),
        201,
    )
    oc = _ok(client.post(f"{H}/special-levies/{other['id']}/calculate", headers=h))
    assert [u["amount"] for u in oc["snapshot"]["units"]] == ["1000.00"]  # only unit 02
    _ok(
        client.post(
            f"{H}/special-levies/{other['id']}/resolve",
            json={"resolution_id": resolution(oc["snapshot_hash"])},
            headers=h,
        )
    )
    assert client.post(f"{H}/special-levies/{other['id']}/apply", headers=h).status_code == 409

    # March receivable run, partial payment, use of funds.
    revenue = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "060300",
                "name": "Sonderumlage",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "special_levy", "account_id": revenue},
            headers=h,
        )
    )
    _ok(
        client.post(
            f"/api/v1/contracts/{c1['id']}/schedules",
            json={"valid_from": "2026-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    assert run["totals"]["ready"] == {"count": 1, "amount": "2000.00"}
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )[0]
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
                    "text": "Test",
                    "lines": lines,
                    "settlements": settle,
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    report = _ok(client.get(f"{H}/special-levies/{lid}/report", headers=h))
    assert (report["resolved"], report["charged"], report["received"], report["open"]) == (
        "10000.00",
        "2000.00",
        "1500.00",
        "500.00",
    )
    assert (report["used"], report["earmarked_remaining"]) == ("800.00", "700.00")
    listed = _ok(client.get(f"{H}/special-levies", params={"legal_entity_id": hoa}, headers=h))
    assert {x["id"] for x in listed} == {lid, other["id"]}
    assert u1

    # W09-01 (decided 24.09.2026): amendment to 12.000,00 -> +1.200,00 / +800,00 as charges in
    # July; second amendment to 9.000,00 -> -1.800,00 / -1.200,00 as draft credits.
    def amend(levy_id: str, total: str, due: str) -> dict[str, Any]:
        new = _ok(
            client.post(
                f"{H}/special-levies/{levy_id}/amend",
                json={"total": total, "difference_due": due, "reason": "Änderungsbeschluss"},
                headers=h,
            ),
            201,
        )
        calc2 = _ok(client.post(f"{H}/special-levies/{new['id']}/calculate", headers=h))
        _ok(
            client.post(
                f"{H}/special-levies/{new['id']}/resolve",
                json={"resolution_id": resolution(calc2["snapshot_hash"])},
                headers=h,
            )
        )
        return {
            "calc": calc2,
            "applied": _ok(client.post(f"{H}/special-levies/{new['id']}/apply", headers=h)),
        }

    up = amend(lid, "12000.00", "2026-07-01")
    diffs = {u["unit_number"]: u["difference"] for u in up["calc"]["snapshot"]["units"]}
    assert diffs == {"01": "1200.00", "02": "800.00"}
    assert (up["applied"]["charges_created"], up["applied"]["credit_drafts"]) == (2, 0)
    assert up["applied"]["version"] == 2
    assert _ok(client.get(f"{H}/special-levies/{lid}", headers=h))["status"] == "superseded"
    assert (
        client.post(
            f"{H}/special-levies/{lid}/amend",
            json={"total": "1.00", "difference_due": "2026-08-01", "reason": "abc"},
            headers=h,
        ).status_code
        == 409
    )  # superseded versions cannot be amended again
    down = amend(up["applied"]["id"], "9000.00", "2026-09-01")
    diffs = {u["unit_number"]: u["difference"] for u in down["calc"]["snapshot"]["units"]}
    assert diffs == {"01": "-1800.00", "02": "-1200.00"}
    assert (down["applied"]["charges_created"], down["applied"]["credit_drafts"]) == (0, 2)
    entries = _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h))
    credits = [e for e in entries if e["text"].startswith("Gutschrift Sonderumlage V3")]
    assert {e["status"] for e in credits} == {"draft"}  # no automatic posting or payout
    assert len(credits) == 2
    rep3 = _ok(client.get(f"{H}/special-levies/{down['applied']['id']}/report", headers=h))
    # Chain months March to May plus July and September; only March was charged so far.
    assert (rep3["resolved"], rep3["charged"], rep3["received"]) == (
        "9000.00",
        "2000.00",
        "1500.00",
    )


def test_w12_package_blocks_release(client: TestClient, world: World) -> None:
    """Unit 02 has no owner and the cost item has no account: both block the approval."""
    h = bearer(login(client, world, "w09admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "792", "name": "WEG Paket", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    _owner(client, h, prop["id"], "01", "500", keys["MEA"], {})
    from tests.integration.test_m5_contracts import _unit

    u2 = _unit(client, h, prop["id"], "02")
    _ok(
        client.post(
            f"/api/v1/units/{u2}/allocation-values",
            json={"allocation_key_id": keys["MEA"], "value": "500", "valid_from": "2020-01-01"},
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
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201
    )
    _ok(
        client.post(
            f"{H}/statements/{st['id']}/costs",
            json={
                "label": "Versicherung",
                "amount": "1000.00",
                "allocation_key_id": keys["MEA"],
                "basis": "Gemeinschaftsordnung",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{H}/statements/{st['id']}/calculate", headers=h))
    pkg = _ok(client.get(f"{H}/statements/{st['id']}/package", headers=h))
    codes = sorted(f["code"] for f in pkg["blocking"])
    assert codes == ["no_account", "owner_gap"]
    assert pkg["releasable"] is False
    h2 = bearer(login(client, world, "w09second"))
    blocked = client.post(
        f"{H}/statements/{st['id']}/transition", json={"target": "internally_approved"}, headers=h2
    )
    assert blocked.status_code == 409
    assert "W12" in blocked.json()["detail"]


def test_d20_levy_instalments_with_partial_refund(client: TestClient, world: World) -> None:
    """D20 (W09): levy 6.000,00 for the facade in 3 instalments from March 2026 (MEA 600 / 400:
    unit 01 3 x 1.200,00, unit 02 3 x 800,00). March charged and paid for unit 01 (1.200,00),
    use of funds 500,00. Amendment to 4.500,00 with the refund reason: differences -900,00 /
    -600,00 as draft credits only. Purpose, Soll/Ist, use, due months and the reason stay; the
    use of funds is not counted twice."""
    h = bearer(login(client, world, "w09admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "793", "name": "WEG Fassade", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    _, c1 = _owner(client, h, prop["id"], "01", "600", keys["MEA"], {})
    _owner(client, h, prop["id"], "02", "400", keys["MEA"], {})
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
    use, revenue = (
        _ok(
            client.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={"number": number, "name": name, "category": category, "type": type_},
                headers=h,
            ),
            201,
        )["id"]
        for number, name, category, type_ in [
            ("049900", "Fassadensanierung", "cost", "expense"),
            ("060300", "Sonderumlage", "revenue", "income"),
        ]
    )
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "special_levy", "account_id": revenue},
            headers=h,
        )
    )

    def resolution(levy_id: str, hash_: str, wording: str) -> str:
        return str(
            _ok(
                client.post(
                    f"{H}/resolutions",
                    json={
                        "legal_entity_id": hoa,
                        "decided_on": "2026-02-10",
                        "subject": "Sonderumlage Fassade",
                        "wording": wording,
                        "status": "positive",
                        "subject_type": "special_levy",
                        "subject_id": levy_id,
                        "snapshot_hash": hash_,
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    lid = _ok(
        client.post(
            f"{H}/special-levies",
            json={
                "ledger_id": ledger,
                "purpose": "Fassadensanierung",
                "total": "6000.00",
                "allocation_key_id": keys["MEA"],
                "first_due": "2026-03-01",
                "instalments": 3,
                "account_id": use,
            },
            headers=h,
        ),
        201,
    )["id"]
    calc = _ok(client.post(f"{H}/special-levies/{lid}/calculate", headers=h))
    by = {u["unit_number"]: u for u in calc["snapshot"]["units"]}
    assert [i["amount"] for i in by["01"]["instalments"]] == ["1200.00"] * 3
    assert [i["amount"] for i in by["02"]["instalments"]] == ["800.00"] * 3
    _ok(
        client.post(
            f"{H}/special-levies/{lid}/resolve",
            json={"resolution_id": resolution(lid, calc["snapshot_hash"], "Sonderumlage.")},
            headers=h,
        )
    )
    assert _ok(client.post(f"{H}/special-levies/{lid}/apply", headers=h))["payments_created"] == 6

    # March instalment of unit 01 charged and paid in full; 500,00 spent on the facade.
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    assert run["totals"]["ready"] == {"count": 1, "amount": "1200.00"}
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )[0]
    for lines, settle, kind in [
        (
            [
                {"account_id": acc["001200"], "debit": "1200.00"},
                {"account_id": item["account_id"], "credit": "1200.00"},
            ],
            [{"open_item_id": item["id"], "amount": "1200.00"}],
            "debtor_payment",
        ),
        (
            [
                {"account_id": use, "debit": "500.00"},
                {"account_id": acc["001200"], "credit": "500.00"},
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
                    "booking_date": "2026-03-12",
                    "text": "Fassade",
                    "lines": lines,
                    "settlements": settle,
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    report = _ok(client.get(f"{H}/special-levies/{lid}/report", headers=h))
    assert (report["resolved"], report["charged"], report["received"], report["open"]) == (
        "6000.00",
        "1200.00",
        "1200.00",
        "0.00",
    )
    assert (report["used"], report["earmarked_remaining"]) == ("500.00", "700.00")

    # Partial refund by amendment: reason and purpose are kept, credits stay drafts.
    reason = "Maßnahme günstiger abgeschlossen, Teilerstattung an die Eigentümer"
    new = _ok(
        client.post(
            f"{H}/special-levies/{lid}/amend",
            json={"total": "4500.00", "difference_due": "2026-08-01", "reason": reason},
            headers=h,
        ),
        201,
    )
    assert (new["purpose"], new["change_reason"], new["version"]) == (
        "Fassadensanierung",
        reason,
        2,
    )
    assert new["supersedes_id"] == lid
    calc2 = _ok(client.post(f"{H}/special-levies/{new['id']}/calculate", headers=h))
    diffs = {u["unit_number"]: u["difference"] for u in calc2["snapshot"]["units"]}
    assert diffs == {"01": "-900.00", "02": "-600.00"}
    _ok(
        client.post(
            f"{H}/special-levies/{new['id']}/resolve",
            json={
                "resolution_id": resolution(
                    new["id"], calc2["snapshot_hash"], "Sonderumlage wird auf 4.500,00 gesenkt."
                )
            },
            headers=h,
        )
    )
    applied = _ok(client.post(f"{H}/special-levies/{new['id']}/apply", headers=h))
    assert (applied["charges_created"], applied["credit_drafts"]) == (0, 2)
    entries = _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h))
    credits = [e for e in entries if e["text"].startswith("Gutschrift Sonderumlage V2")]
    assert len(credits) == 2
    assert {e["status"] for e in credits} == {"draft"}  # no automatic payout or posting
    old = _ok(client.get(f"{H}/special-levies/{lid}", headers=h))
    assert (old["status"], old["purpose"], old["total"]) == (
        "superseded",
        "Fassadensanierung",
        "6000.00",
    )
    rep2 = _ok(client.get(f"{H}/special-levies/{new['id']}/report", headers=h))
    assert (rep2["resolved"], rep2["charged"], rep2["received"], rep2["open"]) == (
        "4500.00",
        "1200.00",
        "1200.00",
        "0.00",
    )
    assert (rep2["used"], rep2["earmarked_remaining"]) == ("500.00", "700.00")  # not twice
    units = {u["unit_number"]: u for u in rep2["units"]}
    assert (units["01"]["resolved"], units["01"]["charged"], units["01"]["received"]) == (
        "2700.00",
        "1200.00",
        "1200.00",
    )
    assert [i["due_month"] for i in by["01"]["instalments"]] == [
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
    ]
    assert new["difference_due"] == "2026-08-01"
