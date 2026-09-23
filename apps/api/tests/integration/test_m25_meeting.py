"""M25 owners' meeting, circular resolution, board audit. Expected values by hand:
owner A holds units 01 and 02 (MEA 400 + 300), owner B unit 03 (MEA 300).
Head principle (§ 25 Abs. 2 WEG): A yes (counted once), B no -> 1 : 1 -> negative.
MEA principle: 700 : 300 -> positive. Abstentions are not counted. Circular resolution only
with every owner agreeing in text form. Audit report separates checked count and value from
the population; a new statement version marks items outdated."""

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
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ev25-{RUN}", name=f"EV {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m25admin"), display_name="m25", password=PASSWORD
        )
        world.users["m25admin"] = uid
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


def test_meeting_votes_circular_audit(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m25admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "751", "name": "WEG Versammlung", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    party_a, _ = _party(client, h, "OwnerA")
    party_b, _ = _party(client, h, "OwnerB")
    _, proxy = _party(client, h, "Vertreter")
    contracts = {}
    for no, mea, party in [("01", "400", party_a), ("02", "300", party_a), ("03", "300", party_b)]:
        unit = _unit(client, h, prop["id"], no)
        _ok(
            client.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": keys["MEA"], "value": mea, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        contracts[no] = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": unit,
                    "party_id": party,
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                },
                headers=h,
            ),
            201,
        )["id"]

    base = {"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"}
    assert (
        client.post(f"{H}/meetings", json=base | {"mode": "virtual"}, headers=h).status_code == 422
    )
    assert (
        client.post(f"{H}/meetings", json=base | {"voting_principle": "mea"}, headers=h).status_code
        == 422
    )  # deviation from the head principle needs a documented basis
    results = {}
    for principle in ("head", "mea"):
        body = base | {"voting_principle": principle}
        if principle == "mea":
            body["voting_principle_basis"] = "Teilungserklärung § 10 (Testannahme)"
        meeting = _ok(client.post(f"{H}/meetings", json=body, headers=h), 201)
        assert (
            client.post(
                f"{H}/meetings/{meeting['id']}/invite", json={"invited_at": "2026-06-01"}, headers=h
            ).status_code
            == 422
        )  # no agenda
        item = _ok(
            client.post(
                f"{H}/meetings/{meeting['id']}/agenda",
                json={"title": "Sanierung Dach", "proposal": "Das Dach wird saniert."},
                headers=h,
            ),
            201,
        )
        short = client.post(
            f"{H}/meetings/{meeting['id']}/invite", json={"invited_at": "2026-06-10"}, headers=h
        )
        assert short.status_code == 422
        assert "zu verifizieren" in short.json()["detail"]
        _ok(
            client.post(
                f"{H}/meetings/{meeting['id']}/invite", json={"invited_at": "2026-05-29"}, headers=h
            )
        )
        mid = meeting["id"]
        for no in ("01", "02"):
            _ok(
                client.post(
                    f"{H}/meetings/{mid}/attendance",
                    json={"contract_id": contracts[no], "present": True},
                    headers=h,
                ),
                201,
            )
        assert (
            client.post(
                f"{H}/meetings/{mid}/attendance",
                json={"contract_id": contracts["03"], "proxy_contact_id": proxy["id"]},
                headers=h,
            ).status_code
            == 422
        )  # proxy without text form evidence
        _ok(
            client.post(
                f"{H}/meetings/{mid}/attendance",
                json={
                    "contract_id": contracts["03"],
                    "proxy_contact_id": proxy["id"],
                    "proxy_document_id": _doc(client, h, "vollmacht.pdf"),
                },
                headers=h,
            ),
            201,
        )
        for no, choice in [("01", "yes"), ("02", "yes"), ("03", "no")]:
            _ok(
                client.post(
                    f"{H}/agenda/{item['id']}/votes",
                    json={"contract_id": contracts[no], "choice": choice},
                    headers=h,
                ),
                201,
            )
        assert (
            client.post(
                f"{H}/agenda/{item['id']}/votes",
                json={"contract_id": contracts["01"], "choice": "no"},
                headers=h,
            ).status_code
            == 409
        )
        results[principle] = (
            item["id"],
            _ok(client.get(f"{H}/agenda/{item['id']}/tally", headers=h)),
        )
    head = results["head"][1]
    assert (head["yes"], head["no"], head["proposal"]) == ("1", "1", "negative")
    mea = results["mea"][1]
    assert (mea["yes"], mea["no"], mea["proposal"]) == ("700", "300", "positive")
    item_id = results["mea"][0]
    wrong = {"outcome": "negative", "majority_basis": "einfache Mehrheit der abgegebenen Stimmen"}
    assert client.post(f"{H}/agenda/{item_id}/announce", json=wrong, headers=h).status_code == 409
    res = _ok(
        client.post(
            f"{H}/agenda/{item_id}/announce", json=wrong | {"outcome": "positive"}, headers=h
        ),
        201,
    )
    assert res["status"] == "positive"
    assert (
        client.post(
            f"{H}/agenda/{item_id}/announce", json=wrong | {"outcome": "positive"}, headers=h
        ).status_code
        == 409
    )

    # Circular resolution: missing consent -> negative; all yes -> positive; evidence required.
    circ = {
        "legal_entity_id": hoa,
        "subject": "Hausordnung",
        "wording": "Die Hausordnung wird angepasst.",
        "decided_on": "2026-07-01",
    }
    assert (
        client.post(
            f"{H}/circular-resolutions",
            json=circ | {"consents": {contracts["01"]: "yes"}},
            headers=h,
        ).status_code
        == 422
    )
    evidence = _doc(client, h, "umlauf.pdf")
    partial = _ok(
        client.post(
            f"{H}/circular-resolutions",
            json=circ | {"consents": {contracts["01"]: "yes"}, "evidence_document_id": evidence},
            headers=h,
        ),
        201,
    )
    assert (partial["status"], partial["missing"]) == ("negative", 2)
    full = _ok(
        client.post(
            f"{H}/circular-resolutions",
            json=circ
            | {
                "consents": dict.fromkeys(contracts.values(), "yes"),
                "evidence_document_id": evidence,
            },
            headers=h,
        ),
        201,
    )
    assert full["status"] == "positive"
    numbers = [
        r["number"]
        for r in _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    ]
    assert numbers == [1, 2, 3]

    # Board audit (PÜ06 to PÜ09) with a sample; report separates checked count and value.
    audit = _ok(
        client.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Prüfung Jahresabrechnung 2025",
                "auditor_contact_ids": [proxy["id"]],
            },
            headers=h,
        ),
        201,
    )
    assert audit["population"]["entries"] == 0
    doc = _doc(client, h, "rechnung.pdf")
    items = [
        _ok(
            client.post(
                f"{H}/audits/{audit['id']}/items",
                json={"document_id": doc, "amount": amount},
                headers=h,
            ),
            201,
        )
        for amount in ("120.00", "80.00")
    ]
    _ok(
        client.patch(
            f"/api/v1/hoa/audit-items/{items[0]['id']}", json={"status": "checked"}, headers=h
        )
    )
    q = _ok(
        client.patch(
            f"/api/v1/hoa/audit-items/{items[1]['id']}",
            json={"status": "query", "question": "Leistungszeitraum?"},
            headers=h,
        )
    )
    assert q["version"] == 2
    report = _ok(client.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)
    content = report["content"]
    assert (content["checked_count"], content["checked_value"], content["selected"]) == (
        1,
        "120.00",
        2,
    )
    assert content["open"] == [items[1]["id"]]
    assert "nicht die gesamte Abrechnung" in content["scope_note"]
    again = _ok(client.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)
    assert again["version"] == 2
