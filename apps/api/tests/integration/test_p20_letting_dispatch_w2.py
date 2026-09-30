"""P20 (30.09.2026): rent index, basis checks, vacancy measures, prospect match, exposé PDF,
dispatch channels, serial merge, calendar feed token. Expected values by hand:
index 600,00 x 105 / 100 = 630,00; modernization (12.000,00 - 0) x 8 % / 12 = 80,00 -> 680,00;
vacancy 01.07.2026 to 23.09.2026 = 85 days, lost rent 600,00 x 12 / 365 x 85 = 1.676,71,
costs 100,00 x 12 / 365 x 85 = 279,45. All percentages and amounts are test inputs, not law."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m6_documents import BUCKET, COMPANY, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p20a-{RUN}", name=f"P20 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p20b-{RUN}", name=f"P20 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("p20admin", a, "tenant_admin"),
            ("p20other", b, "tenant_admin"),
            ("p20care", a, "caretaker"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


CSV = (
    "gemeinde;name;stand;baujahr_von;baujahr_bis;flaeche_von;flaeche_bis;ausstattung;min;mittel;"
    "max;quelle\n"
    "Testdorf;Mietspiegel Testdorf;01.01.2025;1950;1979;40;80;;7,50;8,25;9,00;Testdaten\n"
    "Testdorf;Mietspiegel Testdorf;01.01.2025;1980;2000;40;80;;9,10;9,80;10,50;Testdaten\n"
)


def test_rent_index_csv_lookup_isolation_and_rights(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p20admin"))
    other = bearer(login(client, world, "p20other"))
    care = bearer(login(client, world, "p20care"))
    bad = client.post(
        f"{L}/rent-index/import", json={"csv_text": CSV + "x;y;zz;;;;;;1;;2;q\n"}, headers=h
    )
    preview = _ok(bad)
    assert preview["dry_run"] is True
    assert preview["rows"] == 2
    assert len(preview["errors"]) == 1
    assert _ok(client.get(f"{L}/rent-index", headers=h)) == []  # preview writes nothing
    refused = client.post(
        f"{L}/rent-index/import",
        json={"csv_text": CSV + "x;y;zz;;;;;;1;;2;q\n", "dry_run": False},
        headers=h,
    )
    assert refused.status_code == 422
    done = _ok(
        client.post(f"{L}/rent-index/import", json={"csv_text": CSV, "dry_run": False}, headers=h)
    )
    assert (done["created"], done["skipped"]) == (2, 0)
    again = _ok(
        client.post(f"{L}/rent-index/import", json={"csv_text": CSV, "dry_run": False}, headers=h)
    )
    assert (again["created"], again["skipped"]) == (0, 2)
    hit = _ok(
        client.get(
            f"{L}/rent-index/lookup",
            params={"municipality": "testdorf", "year_built": 1985, "living_area_sqm": "60"},
            headers=h,
        )
    )
    assert hit["found"] is True
    assert len(hit["matches"]) == 1
    assert Decimal(hit["matches"][0]["rent_min"]) == Decimal("9.10")
    assert Decimal(hit["matches"][0]["rent_max"]) == Decimal("10.50")
    no_year = _ok(
        client.get(f"{L}/rent-index/lookup", params={"municipality": "Testdorf"}, headers=h)
    )
    assert no_year["found"] is False
    assert any("Baujahr" in n for n in no_year["notes"])
    assert (
        _ok(client.get(f"{L}/rent-index/lookup", params={"municipality": "Andernorts"}, headers=h))[
            "found"
        ]
        is False
    )
    # tenant separation and rights
    assert _ok(client.get(f"{L}/rent-index", headers=other)) == []
    assert (
        _ok(
            client.get(
                f"{L}/rent-index/lookup",
                params={"municipality": "Testdorf", "year_built": 1985},
                headers=other,
            )
        )["found"]
        is False
    )
    row_id = _ok(client.get(f"{L}/rent-index", headers=h))[0]["id"]
    assert client.delete(f"{L}/rent-index/{row_id}", headers=other).status_code == 404
    assert client.get(f"{L}/rent-index", headers=care).status_code == 403
    invalid = {
        "municipality": "Testdorf",
        "index_name": "X",
        "valid_from": "2025-01-01",
        "rent_min": "9",
        "rent_max": "8",
        "source_note": "Testdaten",
    }
    assert client.post(f"{L}/rent-index", json=invalid, headers=h).status_code == 422
    assert (
        client.post(
            f"{L}/rent-index", json=invalid | {"rent_max": "10", "source_note": ""}, headers=h
        ).status_code
        == 422
    )
    assert client.delete(f"{L}/rent-index/{row_id}", headers=h).status_code == 204


def _setup(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": "Mietshaus",
                "management_type": "rental",
                "city": f"Teststadt {RUN}",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "VermieterP20", "company")
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
    tenant, _ = _party(client, h, "MieterP20")
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
    former, _ = _party(client, h, "VormieterP20")
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
    return {"prop": prop["id"], "units": units, "contract": contract}


def test_basis_checks_vacancy_prospects_expose(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p20admin"))
    other = bearer(login(client, world, "p20other"))
    s = _setup(client, h, "771")
    doc = _doc(client, h, "vereinbarung.pdf")

    def case(basis: str, target: str, data: dict[str, Any], **extra: Any) -> Any:
        body = {
            "contract_id": s["contract"],
            "basis": basis,
            "effective_date": "2026-12-01",
            "target_rent": target,
            "source_note": "Testwerte, keine Rechtsquelle",
            "basis_data": data,
            **extra,
        }
        return client.post(f"{L}/rent-increases", json=body, headers=h)

    idx = {"index_base": "100", "index_current": "105"}
    ok = _ok(case("index", "630.00", idx, source_document_id=doc), 201)
    assert ok["check"]["basis"]["index_max_rent"] == "630.00"
    assert ok["check"]["ok"] is True
    assert ok["basis_data"]["index_current"] == "105"
    over = _ok(case("index", "640.00", idx, source_document_id=doc), 201)
    assert over["check"]["ok"] is False
    assert "Indexanpassung" in over["check"]["flags"][0]
    no_doc = _ok(case("index", "630.00", idx), 201)
    assert any("Quelldokument" in f for f in no_doc["check"]["flags"])
    mod = {"costs": "12000.00", "umlage_percent": "8"}
    assert (
        _ok(case("modernization", "680.00", mod, source_document_id=doc), 201)["check"]["ok"]
        is True
    )
    flagged = _ok(case("modernization", "690.00", mod, source_document_id=doc), 201)
    assert flagged["check"]["basis"]["umlage_monthly"] == "80.00"
    assert flagged["check"]["ok"] is False
    step = {"steps": [{"valid_from": "2026-12-01", "rent": "650.00"}]}
    assert (
        _ok(case("graduated", "650.00", step, source_document_id=doc), 201)["check"]["ok"] is True
    )
    assert (
        _ok(case("graduated", "660.00", step, source_document_id=doc), 201)["check"]["ok"] is False
    )
    assert case("graduated", "650.00", {}, source_document_id=doc).status_code == 422
    assert case("index", "630.00", {"index_base": "0", "index_current": "1"}).status_code == 422
    assert case("mietspiegel", "630.00", {"x": 1}).status_code == 422

    # vacancy measures
    units = s["units"]
    vac = _ok(client.get(f"{L}/vacancies", params={"as_of": "2026-09-23"}, headers=h))
    mine = [v for v in vac if v["property_number"] == "771"]
    assert [(v["unit_number"], v["vacant_days"], v["status"]) for v in mine] == [("02", 85, "open")]
    assert mine[0]["lost_rent"] is None  # no target rent: nothing estimated
    put = {
        "status": "viewing",
        "target_rent": "600.00",
        "monthly_costs": "100.00",
        "follow_up_on": "2026-09-20",
        "note": "Besichtigung",
    }
    _ok(client.put(f"{L}/vacancies/{units['02']}", json=put, headers=h))
    mine = [
        v
        for v in _ok(client.get(f"{L}/vacancies", params={"as_of": "2026-09-23"}, headers=h))
        if v["property_number"] == "771"
    ]
    assert (Decimal(mine[0]["lost_rent"]), Decimal(mine[0]["vacancy_costs"])) == (
        Decimal("1676.71"),
        Decimal("279.45"),
    )
    assert mine[0]["follow_up_due"] is True
    assert mine[0]["status"] == "viewing"
    due = _ok(
        client.get(
            f"{L}/vacancies", params={"as_of": "2026-09-15", "follow_up_due": "true"}, headers=h
        )
    )
    assert [v for v in due if v["property_number"] == "771"] == []
    assert (
        client.put(f"{L}/vacancies/{units['02']}", json={"status": "bogus"}, headers=h).status_code
        == 422
    )
    assert client.put(f"{L}/vacancies/{units['02']}", json=put, headers=other).status_code == 404
    wrong = _ok(client.post(f"{L}/vacancies/{units['02']}/listing", headers=h), 201)
    assert wrong["kind"] == "rental"
    assert Decimal(wrong["price"]) == Decimal("600.00")
    after = [
        v
        for v in _ok(client.get(f"{L}/vacancies", params={"as_of": "2026-09-23"}, headers=h))
        if v["property_number"] == "771"
    ]
    assert after[0]["status"] == "viewing"  # not reset: only ``open`` becomes advertised
    assert after[0]["listing_id"] == wrong["id"]

    # prospects with search profile and match
    _, c1 = _party(client, h, "InteressentA")
    _, c2 = _party(client, h, "InteressentB")
    base = {"unit_id": units["02"], "delete_after": "2027-03-31"}
    a = _ok(
        client.post(
            f"{L}/prospects",
            json=base
            | {
                "contact_id": c1["id"],
                "listing_id": wrong["id"],
                "search_profile": {"max_rent": "650.00", "min_rooms": "2", "min_area_sqm": "50"},
            },
            headers=h,
        ),
        201,
    )
    b = _ok(
        client.post(
            f"{L}/prospects",
            json=base
            | {
                "contact_id": c2["id"],
                "search_profile": {"max_rent": "500.00", "required_features": ["balkon"]},
            },
            headers=h,
        ),
        201,
    )
    assert a["search_profile"]["max_rent"] == "650.00"
    matches = _ok(client.get(f"{L}/listings/{wrong['id']}/prospect-matches", headers=h))
    assert [m["prospect_id"] for m in matches] == [a["id"], b["id"]]
    assert matches[0]["met"] == ["Kaltmiete", "Zimmer", "Wohnfläche"]
    assert matches[0]["unmet"] == []
    assert "Kaltmiete" in matches[1]["unmet"]
    assert "Ausstattung balkon" in matches[1]["unmet"]
    assert (
        client.get(f"{L}/listings/{wrong['id']}/prospect-matches", headers=other).status_code == 404
    )
    bad = base | {"unit_id": units["01"], "contact_id": c1["id"], "listing_id": wrong["id"]}
    assert client.post(f"{L}/prospects", json=bad, headers=h).status_code == 422

    # exposé PDF
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    exp = _ok(client.post(f"{L}/units/{units['02']}/expose/pdf", headers=h), 201)
    assert exp["listing_id"] == wrong["id"]
    assert exp["draft"] is True
    meta = _ok(client.get(f"/api/v1/documents/{exp['document_id']}", headers=h))
    assert meta["title"].startswith("Exposé")
    assert client.post(f"{L}/units/{units['02']}/expose/pdf", headers=other).status_code == 404


def test_dispatch_channels_serial_merge_and_calendar_feed(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p20admin"))
    other = bearer(login(client, world, "p20other"))
    care = bearer(login(client, world, "p20care"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    address = {
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    no_phone = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Anna",
                "last_name": f"OhneTel{RUN}",
                "addresses": [address],
            },
            headers=h,
        ),
        201,
    )
    with_phone = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Bernd",
                "last_name": f"MitTel{RUN}",
                "addresses": [address],
                "phones": [{"label": "mobile", "number": "+491715550123", "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    doc = _doc(client, h, "schreiben.pdf")

    def dispatch(contact: str, channel: str, **extra: Any) -> Any:
        return client.post(
            "/api/v1/dispatches",
            json={"document_id": doc, "contact_id": contact, "channel": channel, **extra},
            headers=h,
        )

    assert dispatch(no_phone["id"], "sms").status_code == 422
    assert dispatch(no_phone["id"], "fax").status_code == 422
    sms = _ok(dispatch(with_phone["id"], "sms"), 201)
    assert sms["channel"] == "sms"
    assert sms["status"] == "prepared"
    ev = f"/api/v1/dispatches/{sms['id']}/evidence"
    assert (
        client.post(
            ev,
            json={"status": "delivered", "evidence_kind": "registered_mail", "evidence_ref": "X"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        _ok(
            client.post(
                ev,
                json={
                    "status": "delivered",
                    "evidence_kind": "sms_log",
                    "evidence_ref": "Protokoll 1",
                },
                headers=h,
            )
        )["status"]
        == "delivered"
    )
    registered = _ok(dispatch(no_phone["id"], "registered"), 201)
    rev = f"/api/v1/dispatches/{registered['id']}/evidence"
    assert (
        client.post(
            rev,
            json={"status": "delivered", "evidence_kind": "hand_delivery", "evidence_ref": "X"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        _ok(
            client.post(
                rev,
                json={
                    "status": "delivered",
                    "evidence_kind": "registered_mail",
                    "evidence_ref": "RS 123",
                },
                headers=h,
            )
        )["evidence_ref"]
        == "RS 123"
    )
    courier = _ok(dispatch(no_phone["id"], "courier"), 201)
    assert courier["channel"] == "courier"
    plain = _ok(dispatch(no_phone["id"], "post"), 201)
    jobs = _ok(client.get("/api/v1/postal/jobs", headers=h))
    assert plain["id"] not in {j["dispatch_id"] for j in jobs}
    auto = _ok(dispatch(no_phone["id"], "post", submit_postal=True), 201)
    jobs = _ok(client.get("/api/v1/postal/jobs", headers=h))
    assert auto["id"] in {j["dispatch_id"] for j in jobs}
    assert (
        client.post(
            "/api/v1/dispatches",
            json={"document_id": doc, "contact_id": no_phone["id"], "channel": "post"},
            headers=care,
        ).status_code
        == 403
    )

    # serial merge: one document per recipient, nothing half done
    free = next(
        t
        for t in _ok(client.get("/api/v1/document-templates", headers=h))
        if t["code"] == "free_letter"
    )
    body = {
        "template_id": free["id"],
        "contact_ids": [no_phone["id"], with_phone["id"]],
        "channel": "post",
        "fields": {"betreff": "Ablesetermin", "text": "Der Ablesetermin ist am 01.10.2026."},
    }
    merged = _ok(client.post("/api/v1/dispatches/serial-merge", json=body, headers=h), 201)
    assert merged["counts"]["post"] == 2
    docs = {d["document_id"] for d in merged["by_channel"]["post"]}
    assert len(docs) == 2  # one own document per recipient
    nobody = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Clara", "last_name": f"OhneAdresse{RUN}"},
            headers=h,
        ),
        201,
    )
    half = client.post(
        "/api/v1/dispatches/serial-merge",
        json=body | {"contact_ids": [with_phone["id"], nobody["id"]]},
        headers=h,
    )
    assert half.status_code == 422
    assert client.post("/api/v1/dispatches/serial-merge", json=body, headers=other).status_code in (
        404,
        422,
    )
    assert (
        client.post("/api/v1/dispatches/serial-merge", json=body, headers=care).status_code == 403
    )

    # history of the contact (M23-01 endpoint already exists): dispatches are listed
    hist = _ok(client.get(f"/api/v1/contacts/{no_phone['id']}/history", headers=h))
    assert {"dispatch_registered", "dispatch_post"} <= {e["kind"] for e in hist}

    # calendar feed token (M23-06)
    status = _ok(client.get("/api/v1/workspace/calendar-feed/token", headers=h))
    assert status["active"] is False
    made = _ok(client.post("/api/v1/workspace/calendar-feed/token", headers=h), 201)
    path = made["path"]
    feed = client.get(path)  # no login
    assert feed.status_code == 200
    assert feed.text.startswith("BEGIN:VCALENDAR")
    assert feed.headers["content-type"].startswith("text/calendar")
    assert client.get(path.replace(made["token"][-6:], "AAAAAA")).status_code == 404
    assert client.get("/api/v1/workspace/calendar-feed/zzz.ics").status_code == 404
    assert _ok(client.get("/api/v1/workspace/calendar-feed/token", headers=h))["active"] is True
    rotated = _ok(client.post("/api/v1/workspace/calendar-feed/token", headers=h), 201)
    assert client.get(path).status_code == 404  # old token revoked
    assert client.get(rotated["path"]).status_code == 200
    assert client.get("/api/v1/workspace/calendar-feed/token", headers=care).status_code == 403
    gone = client.delete("/api/v1/workspace/calendar-feed/token", headers=h)
    assert gone.status_code == 204, gone.text
    assert client.get(rotated["path"]).status_code == 404
