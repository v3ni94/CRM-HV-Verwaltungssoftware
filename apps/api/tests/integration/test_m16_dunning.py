"""M16 dunning: preview with overdue receivables per debtor, dunning block, threshold, level
timing and non leading ledger excluded with reasons; fees stay zero without a configured
amount, interest stays disabled without a maintained Basiszinssatz (V7); approval needs a
second person and the leading system (G1). Presets, fee posting (draft receivable plus draft
HVM outgoing invoice to the claim holder) and Mahnbescheid preparation are covered separately
(operator decision 25.09.2026, docs/OPEN_QUESTIONS.md V7, docs/plans/M16.md)."""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting.tasks import dunning_previews
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m13_receivables import _contract

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


class OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dn-{RUN}", name=f"Mahn {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m16admin", "tenant_admin"), ("m16acc", "accountant_no_banking")]:
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


async def _seed_manager_ledger(settings: Any, tenant_id: UUID) -> None:
    """HVM's own MANAGER legal entity and ledger: no HTTP endpoint creates this yet (M16-08),
    so the test inserts it directly, the way a one-off operator seed step would."""
    from sqlalchemy import select as sa_select

    from mhvp.accounting import services as acc
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            existing = await session.scalar(
                sa_select(LegalEntity).where(LegalEntity.kind == LegalEntityKind.MANAGER)
            )
            if existing is None:
                manager = LegalEntity(
                    tenant_id=tenant_id,
                    kind=LegalEntityKind.MANAGER,
                    name="Hausverwaltung Müller GmbH",
                )
                session.add(manager)
                await session.flush()
                await acc.create_ledger(
                    session,
                    tenant_id=tenant_id,
                    user_id=None,
                    legal_entity_id=manager.id,
                    template=None,
                    fiscal_year_start_month=1,
                    migration_cutoff=None,
                )
    finally:
        await engine.dispose()


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_dunning_preview_and_locks(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m16admin"))
    acc_user = bearer(login(client, world, "m16acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "761", "name": "Mahnhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(client, h, prop["id"], "01", "2020-01-01")
    c2 = _contract(client, h, prop["id"], "02", "2020-01-01")
    blocked = _contract(client, h, prop["id"], "03", "2020-01-01")
    _ok(
        client.post(
            f"/api/v1/contracts/{blocked['id']}/versions",
            json={
                "effective_date": "2026-01-01",
                "dunning_block": True,
                "dunning_block_reason": "Ratenzahlung vereinbart",
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
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))

    # Fees in settings are refused: a configured value is no legal basis (V7).
    bad = client.put(
        f"{A}/dunning-settings",
        json={"levels": [{"level": 1, "min_days_overdue": 10, "fee": "5.00"}]},
        headers=h,
    )
    assert bad.status_code == 422
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 30, "text": "Mahnung"},
                ],
                "threshold_amount": "20.00",
            },
            headers=h,
        )
    )

    early = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-08"}, headers=h), 201)
    assert {c["status"] for c in early["cases"]} == {"excluded"}
    reasons = sorted(c["reason"].split(":")[0] for c in early["cases"])
    assert reasons == [
        "Mahnsperre",
        "Noch nicht 10 Tage überfällig",
        "Noch nicht 10 Tage überfällig",
    ]
    prev = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    assert len(prev["cases"]) == 3
    assert all(c["fee_amount"] == "0.00" and c["interest_amount"] == "0.00" for c in prev["cases"])
    assert all(c["total"] == "350.00" for c in prev["cases"])  # 300,00 hoa_fee + 50,00 reserve
    open_cases = [c for c in prev["cases"] if not c["reason"].startswith("Mahnsperre")]
    assert len(open_cases) == 2
    assert all("nicht führend" in c["reason"] for c in open_cases)  # comparison ledger
    assert (
        client.post(f"{A}/dunning-runs/{prev['id']}/approve", headers=acc_user).status_code == 200
    )  # nothing proposed

    # With G1 the ledger becomes leading; approval needs a second person.
    gh = bearer(login(gated, world, "m16acc"))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    lead = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    assert sorted(c["status"] for c in lead["cases"]) == ["excluded", "proposed", "proposed"]
    assert {c["level"] for c in lead["cases"]} == {1}
    assert client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=h).status_code == 403
    approved = _ok(client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    assert approved["status"] == "approved"
    listed = _ok(client.get(f"{A}/dunning-runs", headers=acc_user))
    assert lead["id"] in {r["id"] for r in listed}
    again = _ok(client.get(f"{A}/dunning-runs/{lead['id']}", headers=acc_user))
    assert (again["status"], len(again["cases"])) == ("approved", 3)
    assert (
        client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user).status_code == 409
    )
    proposed = {c["contract_id"] for c in lead["cases"] if c["status"] == "proposed"}
    assert proposed == {c1["id"], c2["id"]}

    # Scheduled job creates previews only.
    assert asyncio.run(dunning_previews(_settings(database, redis_url)))["runs"] >= 1


def _fee_level_case(
    gated: TestClient,
    h: dict[str, str],
    acc_user: dict[str, str],
    contract_id: str,
    first_date: str,
    second_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Two level flow (M16-14): the first run proposes the Zahlungserinnerung (level 1) without
    fee and interest; it is approved by a second person without any side claim and marked as
    sent, so the next run proposes level 2, where the configured fee applies. Returns the second
    run and the case of ``contract_id`` in it."""
    first = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": first_date}, headers=h), 201)
    reminder = next(c for c in first["cases"] if c["contract_id"] == contract_id)
    assert reminder["level"] == 1
    assert reminder["fee_amount"] == "0.00"
    assert reminder["interest_amount"] == "0.00"
    approved = _ok(gated.post(f"{A}/dunning-runs/{first['id']}/approve", headers=acc_user))
    approved_reminder = next(c for c in approved["cases"] if c["contract_id"] == contract_id)
    assert approved_reminder["fee_entry_id"] is None
    assert approved_reminder["fee_invoice_draft_id"] is None
    sent = _ok(
        gated.post(
            f"{A}/dunning-cases/{approved_reminder['id']}/mark-sent",
            json={"channel": "post"},
            headers=h,
        )
    )
    assert sent["status"] == "sent"
    second = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": second_date}, headers=h), 201)
    case = next(c for c in second["cases"] if c["contract_id"] == contract_id)
    assert case["level"] == 2
    return second, case


def test_dunning_presets_fee_and_mahnbescheid(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """Presets load the V7 ladder with empty fee amounts; a level below fee_from_level or
    without a fee_amount never proposes a fee; once a fee_amount is entered and the level is
    reached, approval creates a draft receivable at the claim holder (WEG) plus a draft HVM
    outgoing invoice to that claim holder (operator clarification 25.09.2026); the last level
    can prepare a Mahnbescheid data set marked for review by a lawyer."""
    _, gated = clients
    h = bearer(login(gated, world, "m16admin"))
    acc_user = bearer(login(gated, world, "m16acc"))
    prop = _ok(
        gated.post(
            "/api/v1/properties",
            json={"number": "762", "name": "Mahnhaus Gebühr", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(gated, h, prop["id"], "01", "2020-01-01")
    template = _ok(gated.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        gated.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    acc = {
        a["number"]: a["id"] for a in _ok(gated.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            gated.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))

    preset = _ok(
        gated.post(
            f"{A}/dunning-settings/presets",
            json={"property_id": prop["id"], "interest_profile": "verbraucher"},
            headers=h,
        ),
        201,
    )
    assert preset["fee_from_level"] == 2
    assert all(lv["fee_amount"] is None for lv in preset["levels"])
    assert preset["status"] == "kein_betrag_hinterlegt"
    assert preset["interest_spread"] == "5.00000000" or float(preset["interest_spread"]) == 5

    # Interest cannot be enabled without a Basiszinssatz.
    bad_interest = gated.put(
        f"{A}/dunning-settings",
        json={
            "property_id": prop["id"],
            "levels": preset["levels"],
            "fee_from_level": 2,
            "interest_enabled": True,
        },
        headers=h,
    )
    assert bad_interest.status_code == 422

    # Two level ladder: the Zahlungserinnerung (level 1) never carries a fee (M16-14), the
    # fee of 5,00 applies from level 2, which is also the highest level (Mahnbescheid).
    settings = _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop["id"],
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 10, "text": "Mahnung", "fee_amount": "5.00"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 2,
            },
            headers=h,
        )
    )
    assert settings["status"] == "nur_gebuehr_hinterlegt"

    # Hausverwaltung Müller GmbH as claim holder of its own (LegalEntityKind.MANAGER) is not
    # created through any HTTP endpoint yet (M16-08, open point); it is inserted directly here
    # so the "claim holder is not HVM" branch (draft outgoing invoice) can be exercised against
    # a real MANAGER ledger, matching how the operator will eventually set this up once.
    asyncio.run(_seed_manager_ledger(_settings(database, redis_url), world.tenant_a))

    lead, case = _fee_level_case(gated, h, acc_user, c1["id"], "2026-03-25", "2026-04-10")
    assert case["fee_amount"] == "5.00"
    approved = _ok(gated.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    approved_case = next(c for c in approved["cases"] if c["contract_id"] == c1["id"])
    assert approved_case["fee_entry_id"] is not None
    assert approved_case["fee_invoice_draft_id"] is not None  # claim holder is the WEG, not HVM

    entry = _ok(
        gated.get(f"{A}/ledgers/{ledger}/entries/{approved_case['fee_entry_id']}", headers=h)
    )
    assert entry["status"] == "draft"  # posting itself needs a further, separate release

    # Level 2 is the highest configured level, so the Mahnbescheid can be prepared.
    prep = _ok(
        gated.post(f"{A}/dunning-cases/{case['id']}/mahnbescheid-vorbereitung", headers=h),
        201,
    )
    assert prep["status"] == "in_vorbereitung"
    assert "Prüfung durch Rechtsanwalt" in prep["hinweis"]
    assert prep["hauptforderung"] == "350.00"
    assert any(n["art"] == "Mahngebühr" for n in prep["nebenforderungen"])
    again = _ok(gated.get(f"{A}/dunning-cases/{case['id']}/mahnbescheid-vorbereitung", headers=h))
    assert again["id"] == prep["id"]  # repeated preparation returns the same record


def test_dunning_mark_sent_advances_level(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """M16-09: nothing advances a case past level 1 until it is marked sent (letters and
    delivery proof itself stay open, M16-02); ``mark-sent`` records channel and time and lets
    the next preview propose level 2, where the fee configured for that level applies."""
    _, gated = clients
    h = bearer(login(gated, world, "m16admin"))
    acc_user = bearer(login(gated, world, "m16acc"))
    prop = _ok(
        gated.post(
            "/api/v1/properties",
            json={"number": "764", "name": "Mahnhaus Stufenaufstieg", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(gated, h, prop["id"], "01", "2020-01-01")
    template = _ok(gated.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        gated.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    acc = {
        a["number"]: a["id"] for a in _ok(gated.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            gated.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop["id"],
                "levels": [
                    {"level": 1, "min_days_overdue": 5, "text": "Erinnerung", "fee_amount": None},
                    {"level": 2, "min_days_overdue": 5, "text": "1. Mahnung", "fee_amount": "7.50"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 2,
            },
            headers=h,
        )
    )

    first = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    first_case = next(c for c in first["cases"] if c["contract_id"] == c1["id"])
    assert first_case["level"] == 1
    assert first_case["fee_amount"] == "0.00"
    approved = _ok(gated.post(f"{A}/dunning-runs/{first['id']}/approve", headers=acc_user))
    approved_case = next(c for c in approved["cases"] if c["contract_id"] == c1["id"])

    # Marking as sent needs a proposed, approved case; the run itself cannot be marked twice.
    refused_again = gated.post(
        f"{A}/dunning-cases/{approved_case['id']}/mahnbescheid-vorbereitung", headers=h
    )
    assert refused_again.status_code == 409  # level 1 is not the highest configured level (2)

    sent = _ok(
        gated.post(
            f"{A}/dunning-cases/{approved_case['id']}/mark-sent",
            json={"channel": "post"},
            headers=h,
        )
    )
    assert sent["status"] == "sent"
    assert sent["delivery_channel"] == "post"
    assert sent["delivered_at"] is not None
    assert (
        gated.post(
            f"{A}/dunning-cases/{approved_case['id']}/mark-sent",
            json={"channel": "post"},
            headers=h,
        ).status_code
        == 409
    )  # already sent

    second = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-04-10"}, headers=h), 201)
    second_case = next(c for c in second["cases"] if c["contract_id"] == c1["id"])
    assert second_case["level"] == 2
    assert second_case["fee_amount"] == "7.50"


def test_d40_dunning_without_fee_amount_and_base_rate_creates_no_side_claim(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D40 (annex D, 7.5 Mahnwesen, docs/rules/M16-01.md): a dunning proposal without a
    maintained fee amount and without a Basiszinssatz creates no side claim. Expected: the
    V7 presets carry no amounts; an amount for the Zahlungserinnerung (level 1) or a fee start
    below level 2 is refused with MHVP-CORE-0004 (M16-14); enabling interest without
    ``interest_base_rate`` is refused with problem code MHVP-CORE-0004; the proposed case
    shows fee 0,00 and interest 0,00, approval creates neither a fee entry nor an HVM invoice
    draft, and the open items stay at the main claim of 350,00."""
    from decimal import Decimal

    _, gated = clients
    h = bearer(login(gated, world, "m16admin"))
    acc_user = bearer(login(gated, world, "m16acc"))
    prop = _ok(
        gated.post(
            "/api/v1/properties",
            json={"number": "765", "name": "Mahnhaus ohne Gebühr", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(gated, h, prop["id"], "01", "2020-01-01")
    template = _ok(gated.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        gated.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    acc = {
        a["number"]: a["id"] for a in _ok(gated.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            gated.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))

    if _ok(gated.get(f"{A}/dunning-settings", headers=h))["status"] == "nicht eingerichtet":
        _ok(gated.post(f"{A}/dunning-settings/presets", json={}, headers=h), 201)
    preset = _ok(
        gated.post(f"{A}/dunning-settings/presets", json={"property_id": prop["id"]}, headers=h),
        201,
    )
    assert preset["fee_from_level"] == 2
    assert all(lv["fee_amount"] is None for lv in preset["levels"])
    assert preset["interest_enabled"] is False
    assert preset["interest_base_rate"] is None
    assert preset["status"] == "kein_betrag_hinterlegt"

    # Interest cannot be switched on without a maintained Basiszinssatz (never hardcoded).
    refused = gated.put(
        f"{A}/dunning-settings",
        json={"property_id": prop["id"], "interest_enabled": True, "interest_spread": "5"},
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "MHVP-CORE-0004"
    assert "Basiszinssatz" in refused.json()["detail"]
    assert (
        _ok(gated.get(f"{A}/dunning-settings", params={"property_id": prop["id"]}, headers=h))[
            "interest_enabled"
        ]
        is False
    )

    # An amount for level 1 is refused: the Zahlungserinnerung is never chargeable (M16-14),
    # and neither is a fee start below level 2; the stored settings stay unchanged.
    levels = [{**lv, "fee_amount": "5.00"} if lv["level"] == 1 else lv for lv in preset["levels"]]
    for body in (
        {"property_id": prop["id"], "levels": levels, "fee_from_level": 2},
        {"property_id": prop["id"], "levels": preset["levels"], "fee_from_level": 1},
    ):
        chargeable = gated.put(f"{A}/dunning-settings", json=body, headers=h)
        assert chargeable.status_code == 422, chargeable.text
        assert chargeable.json()["code"] == "MHVP-CORE-0004"
        assert "Stufe 1" in chargeable.json()["detail"]
    saved = _ok(gated.get(f"{A}/dunning-settings", params={"property_id": prop["id"]}, headers=h))
    assert saved["fee_from_level"] == 2
    assert all(lv["fee_amount"] is None for lv in saved["levels"])

    lead = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-25"}, headers=h), 201)
    case = next(c for c in lead["cases"] if c["contract_id"] == c1["id"])
    assert case["status"] == "proposed"
    assert case["level"] == 1
    assert case["fee_amount"] == "0.00"
    assert case["interest_amount"] == "0.00"
    assert case["total"] == "350.00"
    approved = _ok(gated.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    approved_case = next(c for c in approved["cases"] if c["contract_id"] == c1["id"])
    assert approved_case["fee_entry_id"] is None
    assert approved_case["fee_invoice_draft_id"] is None
    drafts = _ok(gated.get(f"{A}/ledgers/{ledger}/entries", params={"status": "draft"}, headers=h))
    assert [e for e in drafts if e["kind"] == "dunning_fee"] == []
    items = _ok(
        gated.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    assert sum(Decimal(i["remaining"]) for i in items) == Decimal("350.00")
    assert all(i["kind"] == "receivable" for i in items)


def test_d52_comparison_ledger_receivable_run_and_dunning_stay_internal(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D52 (6.9.10, 13.1): exactly one leading system per legal entity, date and process type.
    A comparison ledger (Immoware24 leading, parallel operation) books the Sollstellung only as
    an internal comparison posting: it is not dunned (excluded with reason), and a proposal
    made while the platform was leading can no longer be approved once Immoware24 leads again,
    so no double dunning arises from both systems. Direct debit follows with A11 (pain.008);
    payment orders are covered in test_m15_payments (D52). Expected by hand: 2 contracts with
    300,00 hoa_fee + 50,00 reserve each, run 20.03.2026 -> 2 cases of 350,00."""
    client, gated = clients
    h = bearer(login(client, world, "m16admin"))
    acc_user = bearer(login(client, world, "m16acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "769", "name": "Vergleichshaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    mine = {_contract(client, h, prop["id"], no, "2020-01-01")["id"] for no in ("01", "02")}
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )
    assert ledger["leading_system"] == "immoware24"  # comparison ledger by default
    acc = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger['id']}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger['id']}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    # Sollstellung: posted as comparison booking (daily reconciliation, 13.1), no external effect.
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    assert {i["contract_id"] for i in run["items"]} == mine  # scope=property: only this object
    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["status"] == "posted"
    # Without G1 the platform cannot become leading; Immoware24 stays the only dunning system.
    assert (
        client.post(
            f"{A}/ledgers/{ledger['id']}/leading", json={"leading_system": "mhvp"}, headers=h
        ).status_code
        == 403
    )
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": [{"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"}],
                "threshold_amount": "20.00",
            },
            headers=h,
        )
    )

    def own_cases(run_out: dict[str, Any]) -> list[dict[str, Any]]:
        return [c for c in run_out["cases"] if c["contract_id"] in mine]

    prev = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    cases = own_cases(prev)
    assert len(cases) == 2
    assert all(c["status"] == "excluded" and c["total"] == "350.00" for c in cases)
    assert all("nicht führend" in c["reason"] and "6.9.10" in c["reason"] for c in cases)
    assert all(c["fee_amount"] == "0.00" for c in cases)

    # G1 open: platform leading -> proposals; Immoware24 leading again -> no approval (D52).
    gh = bearer(login(gated, world, "m16acc"))
    _ok(
        gated.post(
            f"{A}/ledgers/{ledger['id']}/leading", json={"leading_system": "mhvp"}, headers=gh
        )
    )
    lead = _ok(client.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    assert {c["status"] for c in own_cases(lead)} == {"proposed"}
    back = _ok(
        client.post(
            f"{A}/ledgers/{ledger['id']}/leading", json={"leading_system": "immoware24"}, headers=h
        )
    )
    assert back["leading_system"] == "immoware24"  # handing back needs no gate
    refused = client.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user)
    assert refused.status_code == 409
    assert "führende System" in refused.json()["detail"]
    assert _ok(client.get(f"{A}/dunning-runs/{lead['id']}", headers=h))["status"] != "approved"
    # No dunning fee or side claim was created for the comparison ledger.
    assert all(
        c["fee_amount"] == "0.00"
        for c in own_cases(_ok(client.get(f"{A}/dunning-runs/{lead['id']}", headers=h)))
    )


async def _fee_invoice_draft(settings: Any, tenant_id: UUID, case_id: str) -> dict[str, str]:
    """Read the draft HVM outgoing invoice of a case (no HTTP endpoint lists drafts yet)."""
    from sqlalchemy import select as sa_select

    from mhvp.accounting.models import DunningFeeInvoiceDraft
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            draft = await session.scalar(
                sa_select(DunningFeeInvoiceDraft).where(
                    DunningFeeInvoiceDraft.case_id == UUID(case_id)
                )
            )
            assert draft is not None
            return {
                "issuer_ledger_id": str(draft.issuer_ledger_id),
                "recipient_legal_entity_id": str(draft.recipient_legal_entity_id),
                "amount": str(draft.amount),
                "status": draft.status,
            }
    finally:
        await engine.dispose()


def test_a32_manager_entity_setup_and_tenancy_fee(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """A32 (M16-08): the managing company's own legal entity (``manager``) and ledger are set
    up through the platform (``POST /tenant/manager-entity``, Einstellungen, Mandant): the
    name comes from the tenant master data, the ledger carries the default accounts that
    apply to ``manager``, a second call changes nothing (idempotent), the status endpoint
    reports ``eingerichtet``; an accountant without ``tenant_settings:update`` is refused.
    Rent case (contract kind ``tenancy``, run scope ``property``): the fee is posted as a
    draft receivable in the landlord's ledger and the draft HVM outgoing invoice names the
    landlord (rental owner legal entity) as recipient and the manager ledger as issuer."""
    from tests.integration.test_m5_contracts import _party
    from tests.integration.test_m5_contracts import _unit as _unit_

    _, gated = clients
    h = bearer(login(gated, world, "m16admin"))
    acc_user = bearer(login(gated, world, "m16acc"))
    t = "/api/v1/tenant/manager-entity"

    # Permission: the accountant role only reads tenant settings.
    assert gated.post(t, headers=acc_user).status_code == 403
    before = _ok(gated.get(t, headers=acc_user))
    assert before["status"] in ("eingerichtet", "nicht_eingerichtet")

    first = _ok(gated.post(t, headers=h))
    assert first["status"] == "eingerichtet"
    assert first["legal_entity_id"]
    assert first["ledger_id"]
    assert first["accounts_count"] > 0
    assert first["name"]  # from tenant master data, never a default
    second = _ok(gated.post(t, headers=h))
    assert second["created"] is False
    assert (second["legal_entity_id"], second["ledger_id"]) == (
        first["legal_entity_id"],
        first["ledger_id"],
    )
    status = _ok(gated.get(t, headers=h))
    assert status["status"] == "eingerichtet"
    assert status["ledger_id"] == first["ledger_id"]
    manager_ledger = _ok(gated.get(f"{A}/ledgers/{first['ledger_id']}", headers=h))
    assert manager_ledger["legal_entity_id"] == first["legal_entity_id"]
    numbers = {
        a["number"] for a in _ok(gated.get(f"{A}/ledgers/{first['ledger_id']}/accounts", headers=h))
    }
    assert "001300" in numbers  # default template rows that apply to "manager"
    assert "060100" not in numbers  # Hausgeld belongs to the GdWE only

    # Rent case: landlord legal entity, tenancy with rent, leading ledger, overdue rent.
    prop = _ok(
        gated.post(
            "/api/v1/properties",
            json={"number": "766", "name": "Mahnhaus Miete", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord_party, _ = _party(gated, h, "Vermieter766", "company")
    landlord = _ok(
        gated.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord_party, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    unit = _unit_(gated, h, prop["id"], "01")
    tenant_party, _ = _party(gated, h, "Mieter766")
    lease = _ok(
        gated.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    assert lease["legal_entity_id"] == landlord
    _ok(
        gated.post(
            f"/api/v1/contracts/{lease['id']}/payments",
            json={
                "payment_type_code": "rent",
                "net": "650.00",
                "gross": "650.00",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        gated.post(
            f"/api/v1/contracts/{lease['id']}/schedules",
            json={"valid_from": "2024-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    template = _ok(gated.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        gated.post(
            f"{A}/ledgers",
            json={"legal_entity_id": landlord, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    rent_account = _ok(
        gated.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "060300", "name": "Mieten", "category": "revenue", "type": "income"},
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        gated.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "rent", "account_id": rent_account},
            headers=h,
        )
    )
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    # Tenant default (needed once) and the object override with the fee for the rent case:
    # the Zahlungserinnerung (level 1) stays free of charge, the fee applies from level 2.
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 10, "text": "Mahnung"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 2,
            },
            headers=h,
        )
    )
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop["id"],
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"},
                    {"level": 2, "min_days_overdue": 10, "text": "Mahnung", "fee_amount": "7.50"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 2,
            },
            headers=h,
        )
    )
    lead, case = _fee_level_case(gated, h, acc_user, lease["id"], "2026-03-25", "2026-04-10")
    assert case["fee_amount"] == "7.50"
    approved = _ok(gated.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    approved_case = next(c for c in approved["cases"] if c["contract_id"] == lease["id"])
    assert approved_case["fee_entry_id"] is not None
    assert approved_case["fee_invoice_draft_id"] is not None
    entry = _ok(
        gated.get(f"{A}/ledgers/{ledger}/entries/{approved_case['fee_entry_id']}", headers=h)
    )
    assert entry["status"] == "draft"  # fee receivable in the landlord's ledger, draft only
    draft = asyncio.run(
        _fee_invoice_draft(_settings(database, redis_url), world.tenant_a, case["id"])
    )
    assert draft["issuer_ledger_id"] == first["ledger_id"]  # HVM invoices the landlord
    assert draft["recipient_legal_entity_id"] == landlord
    assert draft["amount"] == "7.50"
    assert draft["status"] == "draft"  # G1 closed: nothing released, nothing sent
