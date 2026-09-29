"""Deadline type catalogue, deadline entries, notice period orientation, property checklists
and the rent increase receipt action (rule WS-01): happy path, authorization (403), tenant
separation, validation, fixed expected values and the nightly job mirror."""

import asyncio
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.tasks import deadlines_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"
TODAY = date(2026, 9, 28)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dlt-{RUN}", name=f"Fristen {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dlt2-{RUN}", name=f"Fristen2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("dltadmin", a, "tenant_admin"),
            ("dltclerk", a, "standard"),
            ("dltreader", a, "read_only"),
            ("dltcaretaker", a, "caretaker"),
            ("dltother", b, "tenant_admin"),
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
    return response.json() if response.content else None


def _property_with_contract(
    client: TestClient, h: dict[str, str], number: str = "771"
) -> dict[str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": "Fristenhaus",
                "management_type": "rental",
                "city": f"Teststadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "VermieterDL", "company")
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
                "rooms": "2.5",
            },
            headers=h,
        ),
        201,
    )["id"]
    tenant, _ = _party(client, h, "MieterDL")
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
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": f"Mieterwechsel DL {RUN}", "property_id": prop["id"], "unit_id": unit},
            headers=h,
        ),
        201,
    )
    return {"property": prop["id"], "unit": unit, "contract": contract, "ticket": ticket["id"]}


def test_deadline_types_entries_and_job(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "dltadmin"))
    clerk = bearer(login(client, world, "dltclerk"))
    reader = bearer(login(client, world, "dltreader"))
    other = bearer(login(client, world, "dltother"))

    # Catalogue: seeded once per tenant, without durations (no default, "zu verifizieren").
    types = _ok(client.get(f"{W}/deadline-types", headers=clerk))
    by_code = {t["code"]: t for t in types}
    assert set(by_code) == {"verwalterwechsel", "kautionsabrechnung", "mieterhoehung"}
    assert all(t["duration_months"] is None and t["duration_days"] is None for t in types)
    assert all(t["is_system"] for t in types)
    assert by_code["mieterhoehung"]["trigger"] == "rent_increase_access"
    assert len(_ok(client.get(f"{W}/deadline-types", headers=admin))) == 3  # idempotent seed

    # Maintenance needs tenant_settings:update.
    new_type = {
        "code": "nachforderung",
        "name": "Nachforderung Unterlagen",
        "trigger": "management_start",
        "duration_days": 14,
        "responsible_role": "standard",
        "source_note": "Betreibervorgabe, zu verifizieren",
    }
    assert client.post(f"{W}/deadline-types", json=new_type, headers=clerk).status_code == 403
    created = _ok(client.post(f"{W}/deadline-types", json=new_type, headers=admin), 201)
    assert created["is_system"] is False
    assert created["duration_days"] == 14
    assert client.post(f"{W}/deadline-types", json=new_type, headers=admin).status_code == 409
    assert (
        client.post(
            f"{W}/deadline-types", json=new_type | {"code": "x", "trigger": "bogus"}, headers=admin
        ).status_code
        == 422
    )
    kaution = by_code["kautionsabrechnung"]["id"]
    patched = _ok(
        client.patch(
            f"{W}/deadline-types/{kaution}",
            json={"duration_days": 90, "source_note": "Entwurf, zu verifizieren"},
            headers=admin,
        )
    )
    assert patched["duration_days"] == 90
    assert patched["duration_months"] is None
    assert (
        client.patch(
            f"{W}/deadline-types/{kaution}", json={"duration_days": 1}, headers=other
        ).status_code
        == 404
    )
    assert client.get(f"{W}/deadline-types", headers=other)  # other tenant gets its own seed
    assert {t["code"] for t in _ok(client.get(f"{W}/deadline-types", headers=other))} == {
        "verwalterwechsel",
        "kautionsabrechnung",
        "mieterhoehung",
    }

    # Compute preview: fixed expected value 30.09.2026 + 90 days = 29.12.2026.
    preview = _ok(
        client.get(
            f"{W}/deadline-entries/compute",
            params={"type_id": kaution, "trigger_on": "2026-09-30"},
            headers=clerk,
        )
    )
    assert preview["due_on"] == "2026-12-29"
    assert preview["verify"] is True
    no_duration = _ok(
        client.get(
            f"{W}/deadline-entries/compute",
            params={"type_id": by_code["mieterhoehung"]["id"], "trigger_on": "2026-09-30"},
            headers=clerk,
        )
    )
    assert no_duration["due_on"] is None

    ids = _property_with_contract(client, admin)
    users = _ok(client.get(f"{W}/assignable-users", headers=clerk))
    names = {u["display_name"]: u["user_id"] for u in users}
    assert {"dltadmin", "dltclerk"} <= set(names)
    assert "dltother" not in names

    # Entry without a duration and without a due date: MHVP-WS-0001, never a silent default.
    body = {
        "type_id": by_code["mieterhoehung"]["id"],
        "source_type": "ticket",
        "source_id": ids["ticket"],
        "trigger_on": "2026-10-01",
    }
    missing = client.post(f"{W}/deadline-entries", json=body, headers=clerk)
    assert missing.status_code == 422
    assert missing.json()["code"] == "MHVP-WS-0001"
    # Entered due date, no responsible person: created with the ES-10 warning (advisory).
    entered = _ok(
        client.post(f"{W}/deadline-entries", json=body | {"due_on": "2026-12-31"}, headers=clerk),
        201,
    )
    assert entered["due_computed"] is False
    assert entered["warnings"] == ["ES-10"]
    assert entered["href"] == f"/tickets/{ids['ticket']}"
    assert entered["property_id"] == ids["property"]
    assert entry_unit(entered) == ids["unit"]
    assert entered["type_name"] == "Mieterhöhung"

    # Computed from the type, responsible person, immediately in the deadline list.
    computed = _ok(
        client.post(
            f"{W}/deadline-entries",
            json={
                "type_id": kaution,
                "source_type": "contract",
                "source_id": ids["contract"],
                "trigger_on": "2026-09-30",
                "responsible_user_id": names["dltclerk"],
            },
            headers=clerk,
        ),
        201,
    )
    assert computed["due_on"] == "2026-12-29"
    assert computed["due_computed"] is True
    assert computed["responsible_name"] == "dltclerk"
    assert computed["warnings"] == []
    assert computed["href"] == f"/vertraege/{ids['contract']}"
    assert computed["title"].startswith("Kautionsabrechnung Vertrag ")
    listed = _ok(client.get(f"{W}/deadlines", params={"kind": "custom_deadline"}, headers=clerk))
    mirrored = {d["source_id"]: d for d in listed}
    assert computed["id"] in mirrored
    assert mirrored[computed["id"]]["due_on"] == "2026-12-29"
    assert mirrored[computed["id"]]["reference"] == f"Kautionsabrechnung: {computed['title']}"
    assert mirrored[computed["id"]]["href"] == "/fristen"

    # Authorization and validation.
    assert client.post(f"{W}/deadline-entries", json=body, headers=reader).status_code == 403
    assert (
        client.post(
            f"{W}/deadline-entries",
            json=body | {"source_type": "bogus", "due_on": "2026-12-31"},
            headers=clerk,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{W}/deadline-entries",
            json=body | {"source_id": ids["contract"], "due_on": "2026-12-31"},
            headers=clerk,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{W}/deadline-entries",
            json=body
            | {"due_on": "2026-12-31", "responsible_user_id": str(world.users["dltother"])},
            headers=clerk,
        ).status_code
        == 422
    )
    _ok(
        client.patch(
            f"{W}/deadline-types/{created['id']}", json={"is_active": False}, headers=admin
        )
    )
    inactive = client.post(
        f"{W}/deadline-entries", json=body | {"type_id": created["id"]}, headers=clerk
    )
    assert inactive.status_code == 422
    assert inactive.json()["code"] == "MHVP-WS-0002"

    # Tenant separation: the other tenant sees nothing and cannot finish the entry.
    assert _ok(client.get(f"{W}/deadline-entries", headers=other)) == []
    assert (
        client.post(f"{W}/deadline-entries/{entered['id']}/done", headers=other).status_code == 404
    )
    assert (
        client.post(f"{W}/deadline-entries/{entered['id']}/done", headers=reader).status_code == 403
    )

    # Filter by source and finish: the mirror closes at once.
    by_ticket = _ok(
        client.get(
            f"{W}/deadline-entries",
            params={"source_type": "ticket", "source_id": ids["ticket"]},
            headers=clerk,
        )
    )
    assert [e["id"] for e in by_ticket] == [entered["id"]]
    done = _ok(client.post(f"{W}/deadline-entries/{entered['id']}/done", headers=clerk))
    assert done["status"] == "done"
    assert done["done_by"] == str(world.users["dltclerk"])
    assert (
        _ok(
            client.get(
                f"{W}/deadline-entries",
                params={"source_type": "ticket", "source_id": ids["ticket"]},
                headers=clerk,
            )
        )
        == []
    )
    closed = _ok(
        client.get(
            f"{W}/deadlines", params={"kind": "custom_deadline", "status": "done"}, headers=clerk
        )
    )
    assert entered["id"] in {d["source_id"] for d in closed}

    # Nightly job: idempotent mirror, the responsible person gets the lead time notification.
    settings = _settings(database, redis_url)
    soon = _ok(
        client.post(
            f"{W}/deadline-entries",
            json={
                "type_id": kaution,
                "source_type": "unit",
                "source_id": ids["unit"],
                "trigger_on": TODAY.isoformat(),
                "due_on": (TODAY + timedelta(days=5)).isoformat(),
                "responsible_user_id": names["dltclerk"],
                "title": "Kaution Einheit 01",
            },
            headers=clerk,
        ),
        201,
    )
    assert soon["href"] == f"/vermietung/einheit/{ids['unit']}"
    _ok(client.post(f"{W}/notifications/read", headers=clerk), 204)
    _ok(client.post(f"{W}/notifications/read", headers=admin), 204)
    asyncio.run(deadlines_once(settings, TODAY))
    asyncio.run(deadlines_once(settings, TODAY))
    rows = _ok(client.get(f"{W}/deadlines", params={"kind": "custom_deadline"}, headers=clerk))
    assert [d["source_id"] for d in rows if d["source_id"] == soon["id"]] == [soon["id"]]
    clerk_notes = _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=clerk))
    admin_notes = _ok(client.get(f"{W}/notifications", params={"unread": True}, headers=admin))
    # The lead time notification goes to the responsible person only; the calendar reminder
    # of the generated entry (kind calendar_reminder) follows the permission like every kind.
    lead = [
        n
        for n in clerk_notes
        if n["kind"] == "compliance_deadline" and "Kaution Einheit 01" in n["title"]
    ]
    assert len(lead) == 1
    assert "Frist in 5 Tagen" in lead[0]["title"]
    assert not [
        n
        for n in admin_notes
        if n["kind"] == "compliance_deadline" and "Kaution Einheit 01" in n["title"]
    ]


def entry_unit(entry: dict[str, Any]) -> Any:
    return entry["unit_id"]


def test_notice_period_orientation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "dltadmin"))
    reader = bearer(login(client, world, "dltreader"))
    caretaker = bearer(login(client, world, "dltcaretaker"))
    params: dict[str, Any] = {"termination_on": "2026-09-05", "months": 3, "to_month_end": True}
    out = _ok(client.get(f"{W}/notice-period", params=params, headers=reader))
    assert out["end_on"] == "2026-12-31"
    assert out["verify"] is True
    assert out["contract_end_date"] is None
    assert out["contract_end_covers"] is None
    assert "zu verifizieren" in out["note"]
    plain = _ok(
        client.get(
            f"{W}/notice-period",
            params={"termination_on": "2026-09-05", "months": 3, "days": 2},
            headers=reader,
        )
    )
    assert plain["end_on"] == "2026-12-07"
    # Caretakers read properties and tickets, not contracts.
    assert client.get(f"{W}/notice-period", params=params, headers=caretaker).status_code == 403
    assert (
        client.get(f"{W}/notice-period", params=params | {"months": -1}, headers=reader).status_code
        == 422
    )
    ids = _property_with_contract(client, admin, "773")
    _ok(
        client.post(
            f"/api/v1/contracts/{ids['contract']}/termination",
            json={"end_date": "2026-11-30", "termination_date": "2026-09-05"},
            headers=admin,
        )
    )
    compared = _ok(
        client.get(
            f"{W}/notice-period", params=params | {"contract_id": ids["contract"]}, headers=admin
        )
    )
    assert compared["contract_end_date"] == "2026-11-30"
    assert compared["contract_end_covers"] is False  # before the orientation, still accepted
    other = bearer(login(client, world, "dltother"))
    assert (
        client.get(
            f"{W}/notice-period", params=params | {"contract_id": ids["contract"]}, headers=other
        ).status_code
        == 404
    )


def test_property_checklist(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "dltadmin"))
    caretaker = bearer(login(client, world, "dltcaretaker"))
    other = bearer(login(client, world, "dltother"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Übernahme", "management_type": "hoa", "city": "Ort"},
            headers=admin,
        ),
        201,
    )["id"]
    templates = _ok(client.get(f"{W}/checklists/templates", headers=caretaker))
    assert len(templates["manager_change"]) == 10
    assert (
        client.post(f"{W}/checklists", json={"property_id": prop}, headers=caretaker).status_code
        == 403
    )
    assert (
        client.post(
            f"{W}/checklists", json={"property_id": prop, "kind": "x"}, headers=admin
        ).status_code
        == 422
    )
    checklist = _ok(client.post(f"{W}/checklists", json={"property_id": prop}, headers=admin), 201)
    assert checklist["kind"] == "manager_change"
    assert checklist["status"] == "open"
    assert [i["code"] for i in checklist["items"]][:2] == ["management_type", "property_created"]
    assert all(i["done_at"] is None for i in checklist["items"])
    duplicate = client.post(f"{W}/checklists", json={"property_id": prop}, headers=admin)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "MHVP-WS-0003"
    assert (
        client.post(f"{W}/checklists", json={"property_id": prop}, headers=other).status_code == 404
    )

    cid = checklist["id"]
    ticked = _ok(
        client.post(
            f"{W}/checklists/{cid}/items/management_type", json={"done": True}, headers=admin
        )
    )
    first = ticked["items"][0]
    assert first["done_by"] == str(world.users["dltadmin"])
    assert first["done_by_name"] == "dltadmin"
    assert first["done_at"] is not None
    assert ticked["status"] == "open"
    assert (
        client.post(
            f"{W}/checklists/{cid}/items/management_type", json={"done": True}, headers=caretaker
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{W}/checklists/{cid}/items/management_type", json={"done": True}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{W}/checklists/{cid}/items/unknown", json={"done": True}, headers=admin
        ).status_code
        == 404
    )
    for item in checklist["items"][1:]:
        last = _ok(
            client.post(
                f"{W}/checklists/{cid}/items/{item['code']}", json={"done": True}, headers=admin
            )
        )
    assert last["status"] == "done"
    assert last["done_at"] is not None
    reopened = _ok(
        client.post(f"{W}/checklists/{cid}/items/legal_review", json={"done": False}, headers=admin)
    )
    assert reopened["status"] == "open"
    assert reopened["items"][-1]["done_by_name"] is None
    listed = _ok(client.get(f"{W}/checklists", params={"property_id": prop}, headers=caretaker))
    assert [c["id"] for c in listed] == [cid]
    assert _ok(client.get(f"{W}/checklists", params={"property_id": prop}, headers=other)) == []


def test_rent_increase_receipt_action(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "dltadmin"))
    clerk = bearer(login(client, world, "dltclerk"))
    ids = _property_with_contract(client, admin, "774")
    case = _ok(
        client.post(
            "/api/v1/letting/rent-increases",
            json={
                "contract_id": ids["contract"],
                "basis": "mietspiegel",
                "effective_date": "2027-01-01",
                "target_rent": "650.00",
                "source_note": "Testwerte, keine Rechtsquelle",
            },
            headers=admin,
        ),
        201,
    )
    act = f"/api/v1/letting/rent-increases/{case['id']}/actions"
    assert case["received_on"] is None
    assert case["status"] == "draft"
    assert client.post(act, json={"action": "receipt"}, headers=admin).status_code == 422
    # Standard clerks lack contracts:approve like every other process step.
    assert (
        client.post(
            act, json={"action": "receipt", "received_on": "2026-10-02"}, headers=clerk
        ).status_code
        == 403
    )
    updated = _ok(
        client.post(act, json={"action": "receipt", "received_on": "2026-10-02"}, headers=admin)
    )
    assert updated["received_on"] == "2026-10-02"
    assert updated["status"] == "draft"
    # Without released rules no deadline hint is derived (M26-01 stays a draft).
    assert "consent_until" not in updated["check"]
    # A deadline of the seeded type from the case: due date entered, source resolved.
    types = {t["code"]: t for t in _ok(client.get(f"{W}/deadline-types", headers=admin))}
    entry = _ok(
        client.post(
            f"{W}/deadline-entries",
            json={
                "type_id": types["mieterhoehung"]["id"],
                "source_type": "rent_increase_case",
                "source_id": case["id"],
                "trigger_on": "2026-10-02",
                "due_on": "2026-12-31",
                "responsible_user_id": str(world.users["dltadmin"]),
            },
            headers=admin,
        ),
        201,
    )
    assert entry["contract_id"] == ids["contract"]
    assert entry["unit_id"] == ids["unit"]
    assert entry["href"] == f"/vermietung/mieterhoehung/{case['id']}"
