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

    # A level only ever reaches "sent" once letters and delivery are built (M16-02, still
    # open); until then the preview always proposes level 1. This test therefore configures a
    # single-level ladder (fee_from_level 1) to exercise the fee and Mahnbescheid mechanics on
    # that first, reachable level; the multi level ladder itself is covered by the presets
    # assertions above and by ``test_dunning_preview_and_locks`` (level stays 1 without fees).
    settings = _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop["id"],
                "levels": [
                    {"level": 1, "min_days_overdue": 10, "text": "Mahnung", "fee_amount": "5.00"}
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 1,
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

    lead = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-25"}, headers=h), 201)
    case = next(c for c in lead["cases"] if c["contract_id"] == c1["id"])
    assert case["level"] == 1
    assert case["fee_amount"] == "5.00"
    approved = _ok(gated.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    approved_case = next(c for c in approved["cases"] if c["contract_id"] == c1["id"])
    assert approved_case["fee_entry_id"] is not None
    assert approved_case["fee_invoice_draft_id"] is not None  # claim holder is the WEG, not HVM

    entry = _ok(
        gated.get(f"{A}/ledgers/{ledger}/entries/{approved_case['fee_entry_id']}", headers=h)
    )
    assert entry["status"] == "draft"  # posting itself needs a further, separate release

    # A single-level ladder means level 1 is already the highest configured level.
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
