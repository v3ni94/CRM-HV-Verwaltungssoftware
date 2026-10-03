"""AN19 (GAK-204, GAK-205, GAK-206, GAK-208).

Expected values by hand: MEA 600 / 400, total 1.000,00 in one instalment from 01.03.2026 ->
unit 01: 600,00, unit 02: 400,00. Unit 02 changes owner on 15.02.2026, so with the reference
date 10.02.2026 the owner at the reference date differs from the owner at the first due date;
unit 01 keeps its owner. Handover: protocol deposit 1.500,00 against the contract deposit
1.000,00 -> difference 500,00.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
H = "/api/v1/hoa"
HO = "/api/v1/handover/protocols"
L = "/api/v1/letting"
IBAN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an19a-{RUN}", name=f"AN19 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"an19b-{RUN}", name=f"AN19 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("an19one", a), ("an19other", b)):
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _owner_contract(
    c: TestClient, h: dict[str, str], unit: str, name: str, start: str, end: str | None
) -> str:
    party, _ = _party(c, h, name)
    body: dict[str, Any] = {
        "kind": "ownership",
        "unit_id": unit,
        "party_id": party,
        "start_date": start,
        "title_transfer_date": start,
        "acquisition_kind": "first_acquisition",
    }
    if end:
        body["end_date"] = end
    return str(_ok(c.post("/api/v1/contracts", json=body, headers=h), 201)["id"])


def _weg(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "917", "name": "WEG AN19", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    units = {}
    for no, mea in (("01", "600"), ("02", "400")):
        unit = _unit(c, h, prop["id"], no)
        _ok(
            c.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": keys["MEA"], "value": mea, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        units[no] = unit
    _owner_contract(c, h, units["01"], "Eigner01", "2020-01-01", None)
    _owner_contract(c, h, units["02"], "Alt02", "2020-01-01", "2026-02-14")
    _owner_contract(c, h, units["02"], "Neu02", "2026-02-15", None)
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]

    def account(number: str, category: str, type_: str) -> str:
        return str(
            _ok(
                c.post(
                    f"{A}/ledgers/{ledger}/accounts",
                    json={
                        "number": number,
                        "name": f"Konto {number}",
                        "category": category,
                        "type": type_,
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    return {
        "hoa": hoa,
        "ledger": ledger,
        "mea": keys["MEA"],
        "revenue": account("049801", "revenue", "income"),
        "cost": account("049802", "cost", "expense"),
    }


def _levy_body(w: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "ledger_id": w["ledger"],
        "purpose": "Aufzug",
        "total": "1000.00",
        "allocation_key_id": w["mea"],
        "first_due": "2026-03-01",
        "instalments": 1,
        **extra,
    }


def test_levy_terms_contest_and_review_deadline(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "an19one"))
    other = bearer(login(client, world, "an19other"))
    w = _weg(client, h)

    # GAK-205: validation of revenue account and reference date.
    bad_kind = client.post(
        f"{H}/special-levies", json=_levy_body(w, revenue_account_id=w["cost"]), headers=h
    )
    assert bad_kind.status_code == 422, bad_kind.text
    late = client.post(
        f"{H}/special-levies", json=_levy_body(w, reference_date="2026-03-02"), headers=h
    )
    assert late.status_code == 422, late.text
    levy = _ok(
        client.post(
            f"{H}/special-levies",
            json=_levy_body(w, revenue_account_id=w["revenue"], reference_date="2026-02-10"),
            headers=h,
        ),
        201,
    )
    assert levy["revenue_account_id"] == w["revenue"]
    assert levy["reference_date"] == "2026-02-10"
    assert levy["status"] == "draft"
    calc = _ok(client.post(f"{H}/special-levies/{levy['id']}/calculate", headers=h))
    assert calc["snapshot"]["terms"] == {
        "revenue_account_id": w["revenue"],
        "reference_date": "2026-02-10",
    }
    by = {u["unit_number"]: u for u in calc["snapshot"]["units"]}
    assert by["01"]["amount"] == "600.00"
    assert by["02"]["amount"] == "400.00"
    assert by["01"]["owner_changed"] is False
    assert by["02"]["owner_changed"] is True
    assert calc["booking_proposal"] == {
        "revenue_account_id": w["revenue"],
        "total": "1000.00",
        "gate": "G4",
        "draft_only": True,
    }

    # Resolution on the snapshot, levy resolved.
    res = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2026-02-10",
                "subject": "Sonderumlage Aufzug",
                "wording": "Sonderumlage Aufzug wird beschlossen.",
                "status": "positive",
                "subject_type": "special_levy",
                "subject_id": levy["id"],
                "snapshot_hash": calc["snapshot_hash"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/special-levies/{levy['id']}/resolve",
            json={"resolution_id": res["id"]},
            headers=h,
        )
    )
    deps = _ok(client.get(f"{H}/resolutions/{res['id']}/dependents", headers=h))
    assert deps["contested"] is False
    assert [(d["type"], d["id"], d["contested"]) for d in deps["items"]] == [
        ("special_levy", levy["id"], False)
    ]

    # GAK-204: contest -> dependents flagged, approvers notified, nothing cancelled.
    _ok(client.patch(f"{H}/resolutions/{res['id']}", json={"status": "contested"}, headers=h))
    deps = _ok(client.get(f"{H}/resolutions/{res['id']}/dependents", headers=h))
    assert deps["contested"] is True
    assert deps["items"][0]["contested"] is True
    assert _ok(client.get(f"{H}/special-levies/{levy['id']}", headers=h))["status"] == "resolved"
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=h))
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["kind"] == "hoa.resolution_contested" for n in items)

    # Review date: no duration on the type -> date required; entered date is kept.
    missing = client.post(f"{H}/resolutions/{res['id']}/review-deadline", json={}, headers=h)
    assert missing.status_code == 422, missing.text
    entry = _ok(
        client.post(
            f"{H}/resolutions/{res['id']}/review-deadline",
            json={"due_on": "2026-03-10"},
            headers=h,
        ),
        201,
    )
    assert entry["due_on"] == "2026-03-10"
    assert entry["due_computed"] is False
    assert entry["verify"] is True

    # Tenant separation and unknown ids.
    assert client.get(f"{H}/resolutions/{res['id']}/dependents", headers=other).status_code == 404
    assert (
        client.post(
            f"{H}/resolutions/{res['id']}/review-deadline",
            json={"due_on": "2026-03-10"},
            headers=other,
        ).status_code
        == 404
    )
    assert client.get(f"{H}/resolutions/{uuid.uuid4()}/dependents", headers=h).status_code == 404
    assert client.get(f"{H}/resolutions/{res['id']}/dependents").status_code == 401


def test_handover_deposit_link(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "an19one"))
    other = bearer(login(client, world, "an19other"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "918", "name": "Haus AN19", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter19", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, prop["id"], "19")
    party, contact = _party(client, h, "Mieter19")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    deposit = _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/deposits",
            json={"kind": "cash", "amount_due": "1000.00", "valid_from": "2024-01-01"},
            headers=h,
        ),
        201,
    )
    p = _ok(
        client.post(
            HO,
            json={"kind": "rental", "unit_id": unit, "contract_id": contract["id"]},
            headers=h,
        ),
        201,
    )
    pid = p["id"]
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _ok(
        client.patch(
            f"{HO}/{pid}",
            json={
                "deposit_amount": "1500.00",
                "deposit_iban": IBAN,
                "deposit_account_holder": "Mieter19",
            },
            headers=h,
        )
    )
    _ok(
        client.post(
            f"{HO}/{pid}/participants",
            json={"contact_id": contact["id"], "role": "moving_out"},
            headers=h,
        ),
        201,
    )
    # Preview before completion; linking is refused until the protocol is completed.
    state = _ok(client.get(f"{HO}/{pid}/deposit/link", headers=h))
    assert state["deposit_id"] == deposit["id"]
    assert state["difference"] == "500.00"
    assert state["iban_suffix"] == IBAN[-4:]
    assert state["bank_account_id"] is None
    early = client.post(f"{HO}/{pid}/deposit/link", json={}, headers=h)
    assert early.status_code == 409, early.text
    _ok(client.post(f"{HO}/{pid}/complete", json={"force": True}, headers=h))
    linked = _ok(client.post(f"{HO}/{pid}/deposit/link", json={}, headers=h))
    assert linked["bank_account_created"] is True
    assert linked["bank_account_approval"] == "pending"  # four eyes release
    again = _ok(client.post(f"{HO}/{pid}/deposit/link", json={}, headers=h))
    assert again["bank_account_created"] is False
    assert again["bank_account_id"] == linked["bank_account_id"]
    # Deposit untouched.
    deps = _ok(client.get(f"/api/v1/contracts/{contract['id']}/deposits", headers=h))
    assert [d["amount_due"] for d in deps] == ["1000.00"]
    # A contact that is no participant is refused; tenant separation.
    assert (
        client.post(
            f"{HO}/{pid}/deposit/link", json={"contact_id": str(uuid.uuid4())}, headers=h
        ).status_code
        == 422
    )
    assert client.get(f"{HO}/{pid}/deposit/link", headers=other).status_code == 404
    assert client.post(f"{HO}/{pid}/deposit/link", json={}, headers=other).status_code == 404


def test_sale_listing_behind_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "an19one"))
    other = bearer(login(client, world, "an19other"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "919", "name": "Verkauf AN19", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, prop["id"], "03")
    assert _ok(client.get(f"{L}/settings/sale-marketing", headers=h))["enabled"] is False
    sale = _ok(
        client.post(
            f"{L}/listings",
            json={"unit_id": unit, "kind": "sale", "price": "250000.00"},
            headers=h,
        ),
        201,
    )
    locked = client.patch(f"{L}/listings/{sale['id']}", json={"status": "active"}, headers=h)
    assert locked.status_code == 409, locked.text
    assert "AN19-02" in locked.json()["detail"]
    _ok(client.put(f"{L}/settings/sale-marketing", json={"enabled": True}, headers=h))
    assert _ok(client.get(f"{L}/settings/sale-marketing", headers=h))["enabled"] is True
    # The other tenant keeps the default.
    assert _ok(client.get(f"{L}/settings/sale-marketing", headers=other))["enabled"] is False
    active = _ok(client.patch(f"{L}/listings/{sale['id']}", json={"status": "active"}, headers=h))
    assert active["status"] == "active"
    _ok(client.put(f"{L}/settings/sale-marketing", json={"enabled": False}, headers=h))
    bad = client.put(f"{L}/settings/sale-marketing", json={"enabled": True, "x": 1}, headers=h)
    assert bad.status_code == 422
    assert client.get(f"{L}/settings/sale-marketing").status_code == 401
