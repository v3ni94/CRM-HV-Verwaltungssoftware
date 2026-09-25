"""M26 rent increase process, vacancies, exposé draft, prospects. Expected values by hand:
current rent 600,00; entered reference rent 600,00 and cap 15 % -> cap 690,00; entered
comparison rent 11,50 EUR/m² x 60 m² = 690,00. Target 690,00 -> +90,00 = 15,00 %, no flag.
Target 700,00 -> two flags. After consent: rent line 600,00 ends 30.11.2026, 690,00 from
01.12.2026. Vacancy: tenancy ended 30.06.2026 -> vacant since 01.07.2026, 85 days on
23.09.2026 (31 + 31 + 23). The values for cap and comparison rent are test inputs, not law."""

import asyncio
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"vm26-{RUN}", name=f"VM {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("m26admin", "m26second"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        uid = await services.create_user(
            factory,
            email=world.email("m26padmin"),
            display_name="m26padmin",
            password=PASSWORD,
            is_platform_admin=True,
        )
        world.users["m26padmin"] = uid
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def test_rent_increase_vacancy_prospects(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    client, gated = clients
    h = bearer(login(client, world, "m26admin"))
    h2 = bearer(login(client, world, "m26second"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "761",
                "name": "Mietshaus",
                "management_type": "rental",
                "city": f"Teststadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter26", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    units = {}
    for no in ("01", "02"):
        units[no] = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/units",
                json={
                    "building_id": building,
                    "number": no,
                    "unit_type": "apartment",
                    "living_area_sqm": "60",
                    "rooms": "2.5",
                },
                headers=h,
            ),
            201,
        )["id"]
    tenant, _ = _party(client, h, "Mieter26")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": units["01"],
                "party_id": tenant,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "gross": "600.00",
                "valid_from": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )
    former, _ = _party(client, h, "Vormieter26")
    old = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": units["02"],
                "party_id": former,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{old}/termination",
            json={
                "end_date": "2026-06-30",
                "termination_date": "2026-03-31",
                "termination_reason": "Kündigung Mieter",
            },
            headers=h,
        )
    )

    base = {
        "contract_id": contract,
        "basis": "mietspiegel",
        "effective_date": "2026-12-01",
        "reference_rent": "600.00",
        "cap_limit_percent": "15",
        "comparison_rent_per_sqm": "11.50",
        "source_note": "Testwerte, keine Rechtsquelle",
    }
    high = _ok(
        client.post(f"{L}/rent-increases", json=base | {"target_rent": "700.00"}, headers=h), 201
    )
    assert len(high["check"]["flags"]) == 2
    assert high["check"]["ok"] is False
    blocked = client.post(
        f"{L}/rent-increases/{high['id']}/actions", json={"action": "approve"}, headers=h2
    )
    assert blocked.status_code == 409
    case = _ok(
        client.post(f"{L}/rent-increases", json=base | {"target_rent": "690.00"}, headers=h), 201
    )
    check = case["check"]
    assert (check["increase"], check["increase_percent"]) == ("90.00", "15.00")
    assert (check["cap_max_rent"], check["comparison_rent"], check["ok"]) == (
        "690.00",
        "690.00",
        True,
    )
    assert "Keine Aussage zur Zulässigkeit" in check["note"]
    act = f"{L}/rent-increases/{case['id']}/actions"
    assert client.post(act, json={"action": "approve"}, headers=h).status_code == 403
    _ok(client.post(act, json={"action": "approve"}, headers=h2))
    assert client.post(act, json={"action": "send"}, headers=h2).status_code == 403  # G3 closed
    gh = bearer(login(gated, world, "m26second"))
    assert gated.post(act, json={"action": "send"}, headers=gh).status_code == 422
    review = _doc(client, h, "pruefung.pdf")
    sent = _ok(
        gated.post(
            act,
            json={"action": "send", "document_id": review, "received_on": "2026-09-15"},
            headers=gh,
        )
    )
    assert sent["received_on"] == "2026-09-15"
    assert sent["status"] == "sent"
    assert client.post(act, json={"action": "apply"}, headers=h).status_code == 409
    assert client.post(act, json={"action": "consent"}, headers=h).status_code == 422
    _ok(
        client.post(
            act, json={"action": "consent", "document_id": _doc(client, h, "ok.pdf")}, headers=h
        )
    )
    applied = _ok(client.post(act, json={"action": "apply"}, headers=h))
    assert applied["status"] == "applied"
    cases = _ok(client.get(f"{L}/rent-increases", params={"contract_id": contract}, headers=h))
    assert {c["status"] for c in cases} == {"applied", "draft"}
    pays = sorted(
        (
            p
            for p in _ok(client.get(f"/api/v1/contracts/{contract}/payments", headers=h))
            if p["payment_type_code"] == "rent"
        ),
        key=lambda p: p["valid_from"],
    )
    assert [(p["net"], p["valid_from"], p["valid_to"]) for p in pays] == [
        ("600.00", "2023-01-01", "2026-11-30"),
        ("690.00", "2026-12-01", None),
    ]
    assert client.post(act, json={"action": "apply"}, headers=h).status_code == 409

    vac = _ok(client.get(f"{L}/vacancies", params={"as_of": "2026-09-23"}, headers=h))
    mine = [v for v in vac if v["property_number"] == "761"]
    assert [(v["unit_number"], v["vacant_since"], v["vacant_days"]) for v in mine] == [
        ("02", "2026-07-01", 85)
    ]
    exp = _ok(client.get(f"{L}/units/{units['02']}/expose", headers=h))
    assert exp["status"] == "draft"
    assert Decimal(exp["fields"]["living_area_sqm"]) == Decimal("60")
    assert "energy_certificate" in exp["missing"]

    _, contact = _party(client, h, "Interessent26")
    pbody = {"unit_id": units["02"], "contact_id": contact["id"], "delete_after": "2020-01-01"}
    assert client.post(f"{L}/prospects", json=pbody, headers=h).status_code == 422
    p = _ok(
        client.post(f"{L}/prospects", json=pbody | {"delete_after": "2027-03-31"}, headers=h), 201
    )
    _ok(client.patch(f"{L}/prospects/{p['id']}", json={"status": "viewing"}, headers=h))
    listed = _ok(client.get(f"{L}/prospects", params={"unit_id": units["02"]}, headers=h))
    assert [x["status"] for x in listed] == ["viewing"]
    from datetime import date

    from mhvp.letting.tasks import purge_prospects_once

    assert asyncio.run(purge_prospects_once(settings, date(2027, 4, 1)))["deleted"] >= 1
    assert _ok(client.get(f"{L}/prospects", params={"unit_id": units["02"]}, headers=h)) == []
    p = _ok(
        client.post(f"{L}/prospects", json=pbody | {"delete_after": "2027-03-31"}, headers=h), 201
    )
    assert client.delete(f"{L}/prospects/{p['id']}", headers=h).status_code == 204
    assert _ok(client.get(f"{L}/prospects", params={"unit_id": units["02"]}, headers=h)) == []


RULES = (
    "waiting_months",
    "cap_percent",
    "cap_window_years",
    "comparison_flats_min",
    "consent_months",
    "effective_month",
)


def test_rent_law_rules_and_cap_area(clients: tuple[TestClient, TestClient], world: World) -> None:
    """M26-01: checks only with released parameters (test run releases and resets them).
    Values below are the pre-filled draft values, used here as test inputs. Rent 600,00 since
    01.01.2023, effective 01.12.2026: waiting period met; reference rent on 01.12.2023 600,00;
    cap area of the test city 15 % -> maximum 690,00; 700,00 exceeds it. Receipt 15.09.2026 ->
    consent until 30.11.2026, increased rent from 01.12.2026."""
    from mhvp.letting.rentlaw import deadlines

    assert deadlines(date(2026, 9, 15), 2, 3) == {
        "consent_until": date(2026, 11, 30),
        "effective_from": date(2026, 12, 1),
    }
    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    ph = bearer(login(client, world, "m26padmin"))
    pl = "/api/v1/platform/rent-law"
    rules = {r["code"]: r for r in _ok(client.get(f"{L}/rent-law/rules", headers=h))}
    assert set(RULES) <= set(rules)
    assert all(not rules[c]["source_verified"] for c in RULES)
    # Release is refused without a verified source.
    assert (
        client.put(f"{pl}/rules/cap_percent", json={"status": "released"}, headers=ph).status_code
        == 409
    )
    assert client.put(f"{pl}/rules/cap_percent", json={"note": "x"}, headers=h).status_code == 403
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "762",
                "name": "Kappungshaus",
                "management_type": "rental",
                "city": f"Kappstadt {RUN}",
                "state": "Nordrhein-Westfalen",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter262", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "60",
            },
            headers=h,
        ),
        201,
    )["id"]
    tenant, _ = _party(client, h, "Mieter262")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "gross": "600.00",
                "valid_from": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )
    base = {
        "contract_id": contract,
        "basis": "comparison",
        "target_rent": "690.00",
        "effective_date": "2026-12-01",
        "reference_rent": "600.00",
        "cap_limit_percent": "15",
        "comparison_rent_per_sqm": "11.50",
        "source_note": "Testwerte",
    }
    inactive = _ok(client.post(f"{L}/rent-increases", json=base, headers=h), 201)
    assert inactive["check"]["statutory"]["active"] is False
    area = _ok(
        client.post(
            f"{pl}/cap-areas",
            json={
                "state": "NW",
                "municipality": f"Kappstadt {RUN}",
                "cap_percent": "15",
                "valid_from": "2020-01-01",
                "source": "Testeintrag ohne Rechtswirkung",
            },
            headers=ph,
        ),
        201,
    )
    try:
        for code in RULES:
            _ok(
                client.put(
                    f"{pl}/rules/{code}",
                    json={"source_verified": True, "status": "released"},
                    headers=ph,
                )
            )
        two = [{"address": f"Weg {i}", "rent_per_sqm": "11.50"} for i in (1, 2)]
        few = _ok(
            client.post(
                f"{L}/rent-increases",
                json=base | {"justification": "vergleichswohnungen", "comparison_flats": two},
                headers=h,
            ),
            201,
        )
        stat = few["check"]["statutory"]
        assert stat["active"] is True
        assert (stat["cap_percent"], stat["cap_max_rent"]) == ("15.00000000", "690.00")
        assert stat["cap_source"].startswith(f"Kappstadt {RUN}")
        assert stat["flags"] == ["Mindestens 3 Vergleichswohnungen benennen."]
        three = [*two, {"address": "Weg 3", "rent_per_sqm": "11.60"}]
        ok = _ok(
            client.post(
                f"{L}/rent-increases",
                json=base | {"justification": "vergleichswohnungen", "comparison_flats": three},
                headers=h,
            ),
            201,
        )
        assert ok["check"]["statutory"]["flags"] == []
        assert ok["check"]["ok"] is True
        letter = _ok(client.get(f"{L}/rent-increases/{ok['id']}/letter", headers=h))
        assert letter["status"] == "draft"
        assert "ENTWURF" in letter["text"]
        assert "690,00 EUR" in letter["text"]
        assert "Weg 3: 11,60 EUR je m²" in letter["text"]
        assert letter["placeholders"]
        too_high = _ok(
            client.post(
                f"{L}/rent-increases",
                json=base
                | {
                    "target_rent": "700.00",
                    "justification": "mietspiegel",
                    "rent_index_name": "Testmietspiegel 2025",
                },
                headers=h,
            ),
            201,
        )
        assert (
            "Kappungsgrenze überschritten: höchstens 690.00 EUR."
            in too_high["check"]["statutory"]["flags"]
        )
    finally:
        for code in RULES:
            _ok(
                client.put(
                    f"{pl}/rules/{code}",
                    json={"source_verified": False, "status": "draft"},
                    headers=ph,
                )
            )
        _ok(
            client.put(
                f"{pl}/cap-areas/{area['id']}",
                json={
                    "state": "NW",
                    "municipality": f"Kappstadt {RUN}",
                    "cap_percent": "15",
                    "valid_from": "2020-01-01",
                    "valid_to": "2020-01-02",
                    "source": "Testeintrag beendet",
                },
                headers=ph,
            )
        )


def test_listings(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """M28-01 stage 2: listings for rent and sale, no FLOWFACT connection."""
    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "763",
                "name": "Maklerhaus",
                "management_type": "rental",
                "city": f"Maklerstadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "60",
                "rooms": "2.5",
                "floor": "2",
                "street": "Musterweg",
                "house_number": "1",
                "postal_code": "12345",
                "city": "Maklerstadt",
            },
            headers=h,
        ),
        201,
    )["id"]

    prefill = _ok(client.get(f"{L}/listings/prefill", params={"unit_id": unit}, headers=h))
    assert Decimal(prefill["living_area_sqm"]) == Decimal("60")
    assert prefill["rooms"]
    assert prefill["floor"] == "2"

    listing = _ok(
        client.post(f"{L}/listings", json={"unit_id": unit, "kind": "rental"}, headers=h), 201
    )
    assert listing["status"] == "draft"
    assert listing["publication_status"] == "not_published"
    assert listing["title"] == prefill["title"]
    assert Decimal(listing["living_area_sqm"]) == Decimal("60")

    # activation without price and available_from fails
    act = client.patch(f"{L}/listings/{listing['id']}", json={"status": "active"}, headers=h)
    assert act.status_code == 422

    updated = _ok(
        client.patch(
            f"{L}/listings/{listing['id']}",
            json={"price": "850.00", "available_from": "2026-11-01"},
            headers=h,
        )
    )
    assert updated["price"] == "850.00"

    active = _ok(
        client.patch(f"{L}/listings/{listing['id']}", json={"status": "active"}, headers=h)
    )
    assert active["status"] == "active"

    second = _ok(
        client.post(f"{L}/listings", json={"unit_id": unit, "kind": "rental"}, headers=h), 201
    )
    _ok(
        client.patch(
            f"{L}/listings/{second['id']}",
            json={"price": "900.00", "available_from": "2026-11-01"},
            headers=h,
        )
    )
    dup = client.patch(f"{L}/listings/{second['id']}", json={"status": "active"}, headers=h)
    assert dup.status_code == 409

    # a sale listing for the same unit does not conflict with the active rental listing
    sale = _ok(client.post(f"{L}/listings", json={"unit_id": unit, "kind": "sale"}, headers=h), 201)
    _ok(client.patch(f"{L}/listings/{sale['id']}", json={"price": "250000.00"}, headers=h))
    sale_active = _ok(
        client.patch(f"{L}/listings/{sale['id']}", json={"status": "active"}, headers=h)
    )
    assert sale_active["status"] == "active"

    rentals = _ok(client.get(f"{L}/listings", params={"kind": "rental"}, headers=h))
    assert {r["id"] for r in rentals} == {listing["id"], second["id"]}
    active_rentals = _ok(
        client.get(f"{L}/listings", params={"kind": "rental", "status": "active"}, headers=h)
    )
    assert {r["id"] for r in active_rentals} == {listing["id"]}
    by_prop = _ok(client.get(f"{L}/listings", params={"property_id": prop["id"]}, headers=h))
    assert len(by_prop) == 3
    by_text = _ok(client.get(f"{L}/listings", params={"q": "763"}, headers=h))
    assert len(by_text) == 3

    assert client.delete(f"{L}/listings/{listing['id']}", headers=h).status_code == 409
    draft = _ok(
        client.post(f"{L}/listings", json={"unit_id": unit, "kind": "sale"}, headers=h), 201
    )
    assert client.delete(f"{L}/listings/{draft['id']}", headers=h).status_code == 204

    async def _other_tenant_world(settings: Any) -> World:
        from mhvp.core import crypto
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            b, _ = await services.provision_tenant(factory, slug=f"vm28-{RUN}", name=f"VM28 {RUN}")
            other = World(tenant_a=b, tenant_b=b, app_url=world.app_url)
            uid = await services.create_user(
                factory, email=other.email("m28other"), display_name="m28other", password=PASSWORD
            )
            other.users["m28other"] = uid
            await services.add_member(
                factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
            return other
        finally:
            await engine.dispose()

    other_world = asyncio.run(_other_tenant_world(_settings(database, redis_url)))
    ho = bearer(login(client, other_world, "m28other"))
    assert _ok(client.get(f"{L}/listings", headers=ho)) == []


def test_listing_flow_fields(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """M28-01 stage 3 preparation: warm rent computation, heating and energy certificate
    validation, external_uuid uniqueness. Warm rent by hand: price 800,00 + additional_costs
    150,00 + heating_costs 60,00 = 1.010,00 EUR (heating_in_additional_costs False).
    With heating_in_additional_costs True: 800,00 + 150,00 = 950,00 EUR (heating_costs 60,00
    is already part of additional_costs, not added again)."""
    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "764",
                "name": "Maklerhaus Flow",
                "management_type": "rental",
                "city": f"Maklerstadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "60",
                "street": "Musterweg",
                "house_number": "2",
                "postal_code": "12345",
                "city": "Maklerstadt",
            },
            headers=h,
        ),
        201,
    )["id"]

    listing = _ok(
        client.post(
            f"{L}/listings",
            json={
                "unit_id": unit,
                "kind": "rental",
                "price": "800.00",
                "additional_costs": "150.00",
                "heating_costs": "60.00",
            },
            headers=h,
        ),
        201,
    )
    assert listing["warm_rent"] == "1010.00"

    with_included = _ok(
        client.post(
            f"{L}/listings",
            json={
                "unit_id": unit,
                "kind": "rental",
                "price": "800.00",
                "additional_costs": "150.00",
                "heating_costs": "60.00",
                "heating_in_additional_costs": True,
            },
            headers=h,
        ),
        201,
    )
    assert with_included["warm_rent"] == "950.00"

    # heating_costs above additional_costs when included is rejected
    bad = client.post(
        f"{L}/listings",
        json={
            "unit_id": unit,
            "kind": "rental",
            "price": "800.00",
            "additional_costs": "50.00",
            "heating_costs": "60.00",
            "heating_in_additional_costs": True,
        },
        headers=h,
    )
    assert bad.status_code == 422

    # activation requires warm_rent to be computable (price missing)
    no_price = _ok(
        client.post(f"{L}/listings", json={"unit_id": unit, "kind": "rental"}, headers=h), 201
    )
    act = client.patch(
        f"{L}/listings/{no_price['id']}",
        json={"status": "active", "available_from": "2026-11-01"},
        headers=h,
    )
    assert act.status_code == 422

    # activation with energy_status liegt_vor requires type, value and class
    energy_incomplete = _ok(
        client.patch(
            f"{L}/listings/{listing['id']}",
            json={"available_from": "2026-11-01", "energy_status": "liegt_vor"},
            headers=h,
        )
    )
    assert energy_incomplete["energy_status"] == "liegt_vor"
    act2 = client.patch(f"{L}/listings/{listing['id']}", json={"status": "active"}, headers=h)
    assert act2.status_code == 422

    complete = _ok(
        client.patch(
            f"{L}/listings/{listing['id']}",
            json={
                "energy_type": "verbrauch",
                "energy_value": "85.00",
                "energy_class": "C",
            },
            headers=h,
        )
    )
    assert complete["energy_class"] == "C"
    active = _ok(
        client.patch(f"{L}/listings/{listing['id']}", json={"status": "active"}, headers=h)
    )
    assert active["status"] == "active"
    assert active["warnings"] == []

    # activation with energy_status in_erstellung (default) is allowed but carries a warning
    warn_listing = _ok(
        client.post(
            f"{L}/listings",
            json={"unit_id": unit, "kind": "sale", "price": "250000.00"},
            headers=h,
        ),
        201,
    )
    warn_active = _ok(
        client.patch(f"{L}/listings/{warn_listing['id']}", json={"status": "active"}, headers=h)
    )
    assert warn_active["status"] == "active"
    assert warn_active["warnings"]

    # features: unknown keys rejected, known keys stored as booleans
    feat = client.post(
        f"{L}/listings",
        json={"unit_id": unit, "kind": "sale", "features": {"unbekannt": True}},
        headers=h,
    )
    assert feat.status_code == 422
    feat_ok = _ok(
        client.post(
            f"{L}/listings",
            json={"unit_id": unit, "kind": "sale", "features": {"balkon": True, "keller": False}},
            headers=h,
        ),
        201,
    )
    assert feat_ok["features"] == {"balkon": True, "keller": False}


FLOW_DUMP = """
INSERT INTO `listings` (`id`, `uuid`, `objektnummer`, `vermarktungsart`, `objektart`, `titel`,
  `strasse`, `hausnummer`, `plz`, `ort`, `adresse_im_inserat_anzeigen`, `wohnflaeche_qm`,
  `zimmer`, `etage`, `status`)
VALUES
(1, '{uuid}', 'MF-2026-9001', 'miete', 'wohnung', 'FLOW Musterwohnung', 'Flowweg', '9',
  '99999', 'Flowstadt', 1, 55.00, 2.0, 1, 'veroeffentlicht');

INSERT INTO `listing_prices`
  (`listing_id`, `kaltmiete_cent`, `nebenkosten_cent`, `heizkosten_cent`,
   `heizkosten_in_nebenkosten_enthalten`, `kaution_cent`, `provision_typ`)
VALUES
  (1, 70000, 18000, NULL, 0, 140000, 'provisionsfrei');

INSERT INTO `listing_energies` (`listing_id`, `status`)
VALUES
  (1, 'in_erstellung');

INSERT INTO `listing_internals` (`listing_id`, `verwaltungsobjekt_referenz`)
VALUES
  (1, '{number}');

INSERT INTO `listing_flowfact_links` (`listing_id`, `flowfact_entity_id`, `sync_status`)
VALUES
  (1, NULL, 'nicht_uebertragen');
"""


def test_flow_import_preview_apply_idempotency_and_tenant_separation(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """M28 stage 4 (docs/rules/M28-01.md): preview, apply, re-apply is idempotent (no new
    listing on the second apply), and the import run is tenant separated."""
    import uuid as uuid_mod

    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "765",
                "name": "Maklerhaus FLOW",
                "management_type": "rental",
                "city": f"Maklerstadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "street": "Flowweg",
                "house_number": "9",
                "postal_code": "99999",
                "city": "Flowstadt",
            },
            headers=h,
        ),
        201,
    )["id"]

    dump = FLOW_DUMP.format(uuid=str(uuid_mod.uuid4()), number=prop["number"])
    preview = _ok(
        client.post(
            f"{L}/flow-import/preview",
            files={"file": ("flow_export.sql", dump.encode("utf-8"), "application/sql")},
            headers=h,
        ),
        201,
    )
    assert preview["row_count"] == 1
    row = preview["rows"][0]
    assert row["kind"] == "rental"
    assert row["listing_fields"]["price"] == "700.00"
    assert row["match"]["property_number"] == prop["number"]
    assert row["match"]["unit_id"] is None  # FLOW has no unit label; property match only
    run_id = preview["id"]

    fetched = _ok(client.get(f"{L}/flow-import/{run_id}", headers=h))
    assert fetched["row_count"] == 1

    applied = _ok(
        client.post(
            f"{L}/flow-import/{run_id}/apply",
            json={"items": [{"index": 0, "action": "create", "unit_id": unit}]},
            headers=h,
        )
    )
    assert applied["created_count"] == 1
    listing_id = applied["rows"][0]["listing_id"]
    listing = _ok(client.get(f"{L}/listings/{listing_id}", headers=h))
    assert listing["source"] == "flow_import"
    assert listing["price"] == "700.00"
    # Re-apply is idempotent: no new listing is created for the same run.
    reapplied = _ok(
        client.post(
            f"{L}/flow-import/{run_id}/apply",
            json={"items": [{"index": 0, "action": "create", "unit_id": unit}]},
            headers=h,
        )
    )
    assert reapplied["created_count"] == 1  # unchanged, no new creation this time
    assert reapplied["skipped_count"] == 1
    assert reapplied["rows"][0]["outcome"] == "created"  # row keeps its first outcome

    listings = _ok(client.get(f"{L}/listings", params={"q": "FLOW Musterwohnung"}, headers=h))
    assert len(listings) == 1

    # tenant separation: a second tenant cannot read the first tenant's import run
    async def _other_tenant_world(settings: Any) -> World:
        from mhvp.core import crypto
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            b, _ = await services.provision_tenant(
                factory, slug=f"vmflow-{RUN}", name=f"VMFlow {RUN}"
            )
            other = World(tenant_a=b, tenant_b=b, app_url=world.app_url)
            uid = await services.create_user(
                factory,
                email=other.email("mflowother"),
                display_name="mflowother",
                password=PASSWORD,
            )
            other.users["mflowother"] = uid
            await services.add_member(
                factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
            return other
        finally:
            await engine.dispose()

    other_world = asyncio.run(_other_tenant_world(_settings(database, redis_url)))
    ho = bearer(login(client, other_world, "mflowother"))
    assert client.get(f"{L}/flow-import/{run_id}", headers=ho).status_code == 404


def test_listing_openimmo_export(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """M26-02: OpenImmo 1.2.7 export, read only, no portal upload (docs/rules/M26-02.md)."""
    import xml.etree.ElementTree as ET

    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "766",
                "name": "OpenImmo-Haus",
                "management_type": "rental",
                "street": "Exportweg",
                "house_number": "9",
                "postal_code": "40001",
                "city": f"Exportstadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "70",
                "rooms": "3",
                "floor": "1",
            },
            headers=h,
        ),
        201,
    )["id"]

    # freshly created listing: check names the missing fields, no XML claim beyond that
    listing = _ok(
        client.post(f"{L}/listings", json={"unit_id": unit, "kind": "rental"}, headers=h), 201
    )
    check = _ok(client.get(f"{L}/listings/{listing['id']}/openimmo-check", headers=h))
    assert any("Preis" in w for w in check["warnings"])
    assert any("beschreibung" in w.lower() for w in check["warnings"])
    assert any("Energieausweis" in w for w in check["warnings"])

    filled = _ok(
        client.patch(
            f"{L}/listings/{listing['id']}",
            json={
                "price": "900.00",
                "additional_costs": "150.00",
                "heating_costs": "40.00",
                "available_from": "2026-12-01",
                "description": "Helle Wohnung mit Balkon.",
                "features": {"balkon": True, "keller": True},
                "energy_status": "liegt_vor",
                "energy_type": "verbrauch",
                "energy_value": "80.00",
                "energy_class": "C",
                "energy_valid_until": "2030-01-01",
            },
            headers=h,
        )
    )
    assert filled["warm_rent"] == "1090.00"
    check2 = _ok(client.get(f"{L}/listings/{listing['id']}/openimmo-check", headers=h))
    assert check2["warnings"] == []

    resp = client.get(f"{L}/listings/{listing['id']}/openimmo.xml", headers=h)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(resp.content)  # raises on malformed XML  # noqa: S314
    assert root.tag == "openimmo"
    immobilie = root.find("anbieter/immobilie")
    assert immobilie is not None
    nutzungsart = immobilie.find("objektkategorie/nutzungsart")
    assert nutzungsart is not None
    assert nutzungsart.get("WOHNEN") == "true"
    vermarktungsart = immobilie.find("objektkategorie/vermarktungsart")
    assert vermarktungsart is not None
    assert vermarktungsart.get("MIETE_PACHT") == "true"
    assert immobilie.find("objektkategorie/objektart/wohnung") is not None
    geo = immobilie.find("geo")
    assert geo is not None
    assert geo.findtext("plz") == "40001"
    assert geo.findtext("ort") == f"Exportstadt {RUN}"
    assert geo.findtext("strasse") == "Exportweg"
    assert geo.findtext("hausnummer") == "9"
    preise = immobilie.find("preise")
    assert preise is not None
    assert preise.findtext("kaltmiete") == "900.00"
    assert preise.findtext("nebenkosten") == "150.00"
    assert preise.findtext("warmmiete") == "1090.00"
    flaechen = immobilie.find("flaechen")
    assert flaechen is not None
    assert flaechen.findtext("wohnflaeche") == "70.00"
    ausstattung = immobilie.find("ausstattung")
    assert ausstattung is not None
    assert ausstattung.find("balkon") is not None
    assert ausstattung.find("keller") is not None
    energiepass = immobilie.find("zustand_angaben/energiepass")
    assert energiepass is not None
    assert energiepass.get("epart") == "energieverbrauchkennwert"
    assert energiepass.get("wertklasse") == "C"
    assert energiepass.findtext("energieverbrauchkennwert") == "80.00"
    freitexte = immobilie.find("freitexte")
    assert freitexte is not None
    assert freitexte.findtext("objekttitel") == filled["title"]
    assert freitexte.findtext("objektbeschreibung") == "Helle Wohnung mit Balkon."
    verwaltung = immobilie.find("verwaltung_techn")
    assert verwaltung is not None
    assert verwaltung.findtext("objektnr_intern") == listing["id"]
    aktion = verwaltung.find("aktion")
    assert aktion is not None
    assert aktion.get("aktionart") == "CHANGE"

    # address release restricted to PLZ/Ort masks street and house number
    _ok(
        client.patch(
            f"{L}/listings/{listing['id']}", json={"address_release": "nur_plz_ort"}, headers=h
        )
    )
    masked = client.get(f"{L}/listings/{listing['id']}/openimmo.xml", headers=h)
    masked_geo = ET.fromstring(masked.content).find("anbieter/immobilie/geo")  # noqa: S314
    assert masked_geo is not None
    assert masked_geo.findtext("plz") == "40001"
    assert masked_geo.find("strasse") is None
    assert masked_geo.find("hausnummer") is None

    not_found = client.get(f"{L}/listings/{UUID(int=0)}/openimmo.xml", headers=h)
    assert not_found.status_code == 404

    zipped = client.get(f"{L}/listings/openimmo.zip", headers=h)
    assert zipped.status_code == 200
    assert zipped.headers["content-type"] == "application/zip"

    # tenant separation and authorization
    async def _other_tenant_world(settings: Any) -> World:
        from mhvp.core import crypto
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            b, _ = await services.provision_tenant(factory, slug=f"voi-{RUN}", name=f"VOI {RUN}")
            other = World(tenant_a=b, tenant_b=b, app_url=world.app_url)
            uid = await services.create_user(
                factory, email=other.email("moiother"), display_name="moiother", password=PASSWORD
            )
            other.users["moiother"] = uid
            await services.add_member(
                factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
            return other
        finally:
            await engine.dispose()

    other_world = asyncio.run(_other_tenant_world(_settings(database, redis_url)))
    ho = bearer(login(client, other_world, "moiother"))
    assert client.get(f"{L}/listings/{listing['id']}/openimmo.xml", headers=ho).status_code == 404
