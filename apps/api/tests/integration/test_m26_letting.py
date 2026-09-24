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
