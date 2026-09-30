"""M16-01 delivery proofs, M16-02 Basiszinssatz history, M16-03 structured blocks per item,
M16-04 check hints, M16-05 interest as draft receivable on request, M16-06 spread proposal.
Tenant separation (404 for tenant B), read only role (403) and validation (422)."""

import asyncio
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
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m16_dunning_default_and_account import (
    HOA_IBAN,
    _hoa_property_without_account,
)
from tests.integration.test_m16_dunning_letters import (
    BUCKET,
    OpenG1,
    _debtor_contract,
    _ok,
    _settings,
)

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dpb-{RUN}", name=f"Nachweis {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pc-{RUN}", name=f"Fremd3 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("pbadmin", a, "tenant_admin"),
            ("pbacc", a, "accountant_no_banking"),
            ("pbread", a, "read_only"),
            ("pbother", b, "tenant_admin"),
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
def gated(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(
            create_app(_settings(database, redis_url), release_gate_resolver=OpenG1())
        ) as client:
            yield client


def test_rates_blocks_interest_draft_and_proofs(gated: TestClient, world: World) -> None:
    h = bearer(login(gated, world, "pbadmin"))
    acc_user = bearer(login(gated, world, "pbacc"))
    reader = bearer(login(gated, world, "pbread"))
    other = bearer(login(gated, world, "pbother"))
    prop, ledger, hoa = _hoa_property_without_account(gated, h, "791", "Nachweishaus")
    _ok(
        gated.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": HOA_IBAN,
                "holder": "WEG Nachweishaus",
                "valid_from": "2020-01-01",
                "is_default": True,
            },
            headers=h,
        ),
        201,
    )
    contract = _debtor_contract(gated, h, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))

    # M16-02: rate history with source; validation, permission and tenant separation.
    rate_body = {"valid_from": "2026-01-01", "base_rate": "2.00", "source": "Bundesbank Test"}
    assert (
        gated.post(f"{A}/dunning-interest-rates", json=rate_body, headers=reader).status_code == 403
    )
    bad = gated.post(f"{A}/dunning-interest-rates", json={**rate_body, "source": ""}, headers=h)
    assert bad.status_code == 422
    _ok(gated.post(f"{A}/dunning-interest-rates", json=rate_body, headers=h), 201)
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 5, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 5, "text": "Mahnung"},
                ],
                "threshold_amount": "1.00",
                "interest_enabled": True,
                "interest_base_rate": "2.00",
                "interest_spread": "5",
                "default_start_mode": "calendar_due_date",
            },
            headers=h,
        )
    )
    _ok(
        gated.post(
            f"{A}/dunning-interest-rates",
            json={"valid_from": "2026-04-01", "base_rate": "1.50", "source": "Bundesbank Test"},
            headers=h,
        ),
        201,
    )
    dup = gated.post(f"{A}/dunning-interest-rates", json=rate_body, headers=h)
    assert dup.status_code == 409
    rates = _ok(gated.get(f"{A}/dunning-interest-rates", headers=h))
    assert [r["valid_to"] for r in rates] == ["2026-03-31", None]
    assert _ok(gated.get(f"{A}/dunning-interest-rates", headers=other)) == []

    # Level 1 (reminder, no interest), approved and sent.
    first = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    case1 = next(c for c in first["cases"] if c["contract_id"] == contract["id"])
    assert case1["status"] == "proposed"
    assert case1["interest_amount"] == "0.00"
    assert case1["interest_spread_suggestion"]["hinweis"]
    assert any("Verjährung prüfen" in hint for hint in case1["check_hints"])
    _ok(gated.post(f"{A}/dunning-runs/{first['id']}/approve", headers=acc_user))
    # M16-01: no proof before the case counts as sent.
    proof_body = {"kind": "registered_mail", "proof_date": "2026-03-22", "reference": "RR1"}
    early = gated.post(
        f"{A}/dunning-cases/{case1['id']}/delivery-proofs", json=proof_body, headers=h
    )
    assert early.status_code == 409
    _ok(
        gated.post(
            f"{A}/dunning-cases/{case1['id']}/mark-sent", json={"channel": "post"}, headers=h
        )
    )
    bad_kind = gated.post(
        f"{A}/dunning-cases/{case1['id']}/delivery-proofs",
        json={**proof_body, "kind": "brieftaube"},
        headers=h,
    )
    assert bad_kind.status_code == 422
    assert (
        gated.post(
            f"{A}/dunning-cases/{case1['id']}/delivery-proofs", json=proof_body, headers=reader
        ).status_code
        == 403
    )
    proof = _ok(
        gated.post(f"{A}/dunning-cases/{case1['id']}/delivery-proofs", json=proof_body, headers=h),
        201,
    )
    assert proof["kind"] == "registered_mail"
    listed = _ok(gated.get(f"{A}/dunning-cases/{case1['id']}/delivery-proofs", headers=h))
    assert [p["reference"] for p in listed] == ["RR1"]
    assert (
        gated.get(f"{A}/dunning-cases/{case1['id']}/delivery-proofs", headers=other).status_code
        == 404
    )

    # Level 2 across the rate change: interest split into two periods (M16-02).
    second = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-04-20"}, headers=h), 201)
    case2 = next(c for c in second["cases"] if c["contract_id"] == contract["id"])
    assert case2["level"] == 2
    assert case2["status"] == "proposed", case2["reason"]
    periods = case2["interest_detail"]
    assert [p["base_rate"] for p in periods] == ["2.00000000", "1.50000000"]
    assert sum(int(p["days"]) for p in periods) == 47  # 04.03. to 19.04.2026 inclusive (28 + 19)
    # M16-05: no draft before approval, draft only on request, idempotent.
    assert (
        gated.post(f"{A}/dunning-cases/{case2['id']}/interest-draft", headers=h).status_code == 409
    )
    approved = _ok(gated.post(f"{A}/dunning-runs/{second['id']}/approve", headers=acc_user))
    assert next(c for c in approved["cases"] if c["id"] == case2["id"])["interest_entry_id"] is None
    assert (
        gated.post(f"{A}/dunning-cases/{case2['id']}/interest-draft", headers=reader).status_code
        == 403
    )
    assert (
        gated.post(f"{A}/dunning-cases/{case2['id']}/interest-draft", headers=other).status_code
        == 404
    )
    draft = _ok(gated.post(f"{A}/dunning-cases/{case2['id']}/interest-draft", headers=h), 201)
    assert draft["status"] == "draft"
    again = _ok(gated.post(f"{A}/dunning-cases/{case2['id']}/interest-draft", headers=h), 201)
    assert again["entry_id"] == draft["entry_id"]
    entry = _ok(gated.get(f"{A}/ledgers/{ledger}/entries/{draft['entry_id']}", headers=h))
    assert entry["status"] == "draft"
    assert entry["kind"] == "interest"

    # M16-03: structured block per item keeps it out of the next run; release is recorded.
    item_id = case2["open_items"][0]["open_item_id"]
    bad_reason = gated.post(
        f"{A}/open-items/{item_id}/dunning-blocks", json={"reason_code": "laune"}, headers=h
    )
    assert bad_reason.status_code == 422
    assert (
        gated.post(
            f"{A}/open-items/{item_id}/dunning-blocks",
            json={"reason_code": "disputed"},
            headers=other,
        ).status_code
        == 404
    )
    block = _ok(
        gated.post(
            f"{A}/open-items/{item_id}/dunning-blocks",
            json={"reason_code": "disputed", "note": "Schuldner bestreitet"},
            headers=h,
        ),
        201,
    )
    assert block["active"] is True
    # The case holds several items (Miete and Nebenkosten); only a block on every item excludes it.
    second_block = _ok(
        gated.post(
            f"{A}/open-items/{case2['open_items'][1]['open_item_id']}/dunning-blocks",
            json={"reason_code": "disputed", "note": "Schuldner bestreitet"},
            headers=h,
        ),
        201,
    )
    third = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-05-20"}, headers=h), 201)
    case3 = next(c for c in third["cases"] if c["contract_id"] == contract["id"])
    assert case3["status"] == "excluded"
    assert "bestrittener Posten" in case3["reason"]
    released = _ok(gated.post(f"{A}/dunning-blocks/{block['id']}/release", headers=h))
    assert released["active"] is False
    assert gated.post(f"{A}/dunning-blocks/{block['id']}/release", headers=h).status_code == 409
    _ok(gated.post(f"{A}/dunning-blocks/{second_block['id']}/release", headers=h))
    assert _ok(gated.get(f"{A}/dunning-blocks?active=true", headers=h)) == []
