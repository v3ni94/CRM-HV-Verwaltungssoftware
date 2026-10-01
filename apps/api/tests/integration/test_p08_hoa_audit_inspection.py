"""P08 (M25-02, M25-03, M25-05, M25-07, M25-08) and acceptance cases SD-05, SD-06, SD-07.

Expected values by hand: one receipt of 120,00 EUR booked on the community ledger; the filter
bounds 100,00 and 200,00 include and exclude it; two real changes of an item give exactly two
history rows, a repeated identical patch gives none; a report version can be confirmed once;
a package with ``valid_days`` is retrievable until revoked, afterwards 409."""

import asyncio
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_a61_inspection import _doc as _a61_doc
from tests.integration.test_a61_inspection import _world
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_board_portal import _doc, _hoa, _ledger_with_invoice

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
INS = f"{H}/inspection-requests"


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "p08", "p08admin", "p08reader"))


@pytest.fixture(scope="module")
def other_world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "p08b", "p08other"))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_audit_filters_history_confirmation_and_authorization(
    client: TestClient, world: World, other_world: World
) -> None:
    h = bearer(login(client, world, "p08admin"))
    hr = bearer(login(client, world, "p08reader"))
    ho = bearer(login(client, other_world, "p08other"))
    hoa, _, board = _hoa(client, h, "951")
    doc = _doc(client, h, "rechnung-p08.pdf", b"%PDF-1.4 p08")
    _ledger_with_invoice(client, h, hoa, "951", doc)
    eng = _ok(
        client.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Stichprobe P08",
                "auditor_contact_ids": [board["id"]],
                "authorization_text": "Beiratsauftrag laut Protokoll vom 12.03.2026",
                "data_as_of": "2026-03-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    item = _ok(
        client.post(
            f"{H}/audits/{eng}/items",
            json={"document_id": doc, "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    # M25-08: authorization and data cut-off are stored and shown.
    detail = _ok(client.get(f"{H}/audits/{eng}", headers=h))
    assert detail["authorization_text"].startswith("Beiratsauftrag")
    assert detail["data_as_of"] == "2026-03-01"

    # M25-02: filters by amount, missing receipt, risk note and item status.
    def ids(**params: Any) -> list[str]:
        body = _ok(client.get(f"{H}/audits/{eng}", params=params, headers=h))
        return [i["id"] for i in body["items"]]

    assert ids(min_amount="100.00", max_amount="200.00") == [item["id"]]
    assert ids(min_amount="120.01") == []
    assert ids(missing_document="true") == []
    assert ids(missing_document="false") == [item["id"]]
    assert ids(has_risk="true") == []
    assert ids(has_risk="false") == [item["id"]]
    assert (
        client.get(f"{H}/audits/{eng}", params={"item_status": "x"}, headers=h).status_code == 422
    )

    # M25-05: every real change is one history row, a repeated value none.
    iid = item["id"]
    p1 = _ok(
        client.patch(
            f"{H}/audit-items/{iid}",
            json={"question": "Wofür?", "risk_note": "Betrag ohne Auftrag"},
            headers=h,
        )
    )
    assert p1["version"] == 2
    assert ids(has_risk="true") == [iid]
    p2 = _ok(client.patch(f"{H}/audit-items/{iid}", json={"answer": "Gartenpflege"}, headers=h))
    assert p2["version"] == 3
    same = _ok(client.patch(f"{H}/audit-items/{iid}", json={"answer": "Gartenpflege"}, headers=h))
    assert same["version"] == 3
    history = _ok(client.get(f"{H}/audit-items/{iid}/history", headers=h))
    assert [e["item_version"] for e in history] == [2, 3]
    assert history[0]["changes"]["question"] == {"old": None, "new": "Wofür?"}
    assert history[1]["changes"]["answer"] == {"old": None, "new": "Gartenpflege"}
    assert history[1]["actor_user_id"] == str(world.users["p08admin"])
    _ok(client.patch(f"{H}/audit-items/{iid}", json={"answer": "Gartenpflege 2025"}, headers=h))
    assert _ok(client.get(f"{H}/audit-items/{iid}/history", headers=h))[2]["changes"]["answer"] == {
        "old": "Gartenpflege",
        "new": "Gartenpflege 2025",
    }
    assert client.get(f"{H}/audit-items/{iid}/history", headers=ho).status_code == 404
    assert client.patch(f"{H}/audit-items/{iid}", json={"note": "x"}, headers=hr).status_code == 403

    # M25-03: confirm exactly one report version, once; no resolution arises (PÜ09).
    report = _ok(client.post(f"{H}/audits/{eng}/reports", json={"findings": "ok"}, headers=h), 201)
    assert report["content"]["authorization_text"].startswith("Beiratsauftrag")
    assert report["content"]["data_as_of"] == "2026-03-01"
    url = f"{H}/audits/{eng}/reports/{report['version']}/confirm"
    body = {"confirmed_by_name": "Erika Beirat", "note": "Kenntnis genommen"}
    assert client.post(url, json=body, headers=hr).status_code == 403
    assert client.post(url, json=body, headers=ho).status_code == 404
    assert client.post(url, json={"confirmed_by_name": "E"}, headers=h).status_code == 422
    done = _ok(client.post(url, json=body, headers=h))
    assert done["confirmed_by_name"] == "Erika Beirat"
    assert done["confirmed_at"]
    assert client.post(url, json=body, headers=h).status_code == 409
    assert (
        client.post(f"{H}/audits/{eng}/reports/99/confirm", json=body, headers=h).status_code == 404
    )
    assert _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h)) == []
    assert _ok(client.get(f"{H}/audits/{eng}", headers=h))["status"] == "open"

    # SD-06 (W13): the audit exists without a board account and is no resolution: neither the
    # report nor its confirmation creates an entry in the resolution collection (asserted above).
    assert _ok(client.get(f"{H}/audits/{eng}", headers=h))["overall_status"]


def _released_request(
    client: TestClient, h: dict[str, str], number: str
) -> tuple[str, str, str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG Einsicht {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    _, applicant = _party(client, h, f"Eigentuemer{number}")
    req = _ok(
        client.post(
            INS,
            json={
                "legal_entity_id": hoa,
                "applicant_contact_id": applicant["id"],
                "requested_on": "2026-09-20",
                "scope_kinds": ["statement"],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{INS}/{req['id']}/transition", json={"status": "released"}, headers=h))
    d1 = _a61_doc(
        client, h, f"abrechnung-{number}.pdf", b"%PDF-1.4 a" + number.encode(), hoa, owner=True
    )
    return hoa, str(req["id"]), d1, str(prop["id"])


def test_package_expiry_and_revocation_sd07(
    client: TestClient, world: World, other_world: World
) -> None:
    """SD-07 (PÜ13): request, scope, release, notification of the question, package, actual
    retrieval and answer are in the trail; a read only retrieval is no acknowledgement (status
    stays provided); an expired or revoked package is no longer retrievable (old links)."""
    h = bearer(login(client, world, "p08admin"))
    hr = bearer(login(client, world, "p08reader"))
    ho = bearer(login(client, other_world, "p08other"))
    _, rid, d1, _ = _released_request(client, h, "952")
    assert (
        client.post(
            f"{INS}/{rid}/package", json={"document_ids": [d1], "valid_days": 0}, headers=h
        ).status_code
        == 422
    )
    pack = _ok(
        client.post(
            f"{INS}/{rid}/package", json={"document_ids": [d1], "valid_days": 14}, headers=h
        )
    )
    detail = _ok(client.get(f"{INS}/{rid}", headers=h))
    assert detail["package_expires_at"] is not None
    _ok(client.post(f"{INS}/{rid}/notes", json={"text": "Welche Belege fehlen?"}, headers=h), 201)
    _ok(client.post(f"{INS}/{rid}/notes", json={"text": "Keine, vollständig."}, headers=h), 201)
    _ok(
        client.post(
            f"{INS}/{rid}/transition",
            json={"status": "provided", "delivery_kind": "portal"},
            headers=h,
        )
    )
    got = client.get(f"{INS}/{rid}/package", headers=hr)  # read only: records, no status change
    assert got.status_code == 200
    assert hashlib.sha256(got.content).hexdigest() == pack["sha256"]
    mid = _ok(client.get(f"{INS}/{rid}", headers=h))
    assert mid["status"] == "provided", "a retrieval by a reader is no acknowledgement"
    assert [e["kind"] for e in mid["events"]] == [
        "status",
        "status",
        "package",
        "note",
        "note",
        "status",
        "notified",  # M25-07: the notification is its own event after "provided"
        "retrieval",
    ]
    assert not [e for e in mid["events"] if e["to_status"] in ("acknowledged", "accepted")]

    # Revocation: reason required, reader forbidden, other tenant 404, then 409 on retrieval.
    assert client.post(f"{INS}/{rid}/revoke", json={"text": "x"}, headers=hr).status_code == 403
    assert client.post(f"{INS}/{rid}/revoke", json={"text": "x"}, headers=ho).status_code == 404
    assert client.post(f"{INS}/{rid}/revoke", json={"text": ""}, headers=h).status_code == 422
    revoked = _ok(client.post(f"{INS}/{rid}/revoke", json={"text": "Eigentümerwechsel"}, headers=h))
    assert revoked["events"][-1]["kind"] == "revoked"
    assert client.get(f"{INS}/{rid}/package", headers=h).status_code == 409
    # A new package without expiry makes it retrievable again (management decision).
    _ok(client.post(f"{INS}/{rid}/package", json={"document_ids": [d1]}, headers=h))
    assert client.get(f"{INS}/{rid}/package", headers=h).status_code == 200
    # No package yet: revoke refused.
    _, rid2, _, _ = _released_request(client, h, "953")
    assert client.post(f"{INS}/{rid2}/revoke", json={"text": "x"}, headers=h).status_code == 409


def test_package_index_outside_portal_sd05(client: TestClient, world: World) -> None:
    """SD-05 (PÜ12): a package with index and verifiable file references can be produced
    without the portal (data medium); the index lists the SHA-256 per document, sorted by file
    name; a document of another community is refused by name."""
    h = bearer(login(client, world, "p08admin"))
    hoa, rid, d1, _ = _released_request(client, h, "954")
    other_hoa, _, d_foreign, _ = _released_request(client, h, "955")
    refused = client.post(f"{INS}/{rid}/package", json={"document_ids": [d1, d_foreign]}, headers=h)
    assert refused.status_code == 422
    assert "nicht dem Objekt zugeordnet" in refused.json()["detail"]
    assert other_hoa != hoa
    pack = _ok(client.post(f"{INS}/{rid}/package", json={"document_ids": [d1]}, headers=h))
    _ok(
        client.post(
            f"{INS}/{rid}/transition",
            json={"status": "provided", "delivery_kind": "data_medium"},
            headers=h,
        )
    )
    data = client.get(f"{INS}/{rid}/package", headers=h).content
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        index = json.loads(zf.read("index.json"))
        assert [e["sha256"] for e in index] == [pack["entries"][0]["sha256"]]
        assert "index.csv" in zf.namelist()


# Q09 (M25-07): notification event and owner check ---------------------------------------


def _owner_request(
    client: TestClient, h: dict[str, str], number: str, requested_on: str
) -> tuple[str, str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG Owner {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party, applicant = _party(client, h, f"Antragsteller{number}")
    unit = _unit(client, h, prop["id"], "01")
    _ok(
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
    )
    req: dict[str, Any] = _ok(
        client.post(
            INS,
            json={
                "legal_entity_id": hoa,
                "applicant_contact_id": applicant["id"],
                "requested_on": requested_on,
                "scope_kinds": ["statement"],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{INS}/{req['id']}/transition", json={"status": "released"}, headers=h))
    doc = _a61_doc(
        client, h, f"abrechnung-{number}.pdf", b"%PDF-1.4 o" + number.encode(), hoa, owner=True
    )
    return str(req["id"]), doc, hoa


def test_owner_check_changed_and_unchanged(
    client: TestClient,
    world: World,
    other_world: World,
) -> None:
    h = bearer(login(client, world, "p08admin"))
    hr = bearer(login(client, world, "p08reader"))
    ho = bearer(login(client, other_world, "p08other"))
    rid, doc, _ = _owner_request(client, h, "961", "2019-06-01")
    _ok(
        client.post(
            f"{INS}/{rid}/package", json={"document_ids": [doc], "valid_days": 14}, headers=h
        )
    )
    provided = _ok(
        client.post(
            f"{INS}/{rid}/transition",
            json={"status": "provided", "delivery_kind": "portal"},
            headers=h,
        )
    )
    kinds = [e["kind"] for e in provided["events"]]
    assert kinds[-2:] == ["status", "notified"]
    assert "Benachrichtigung" in provided["events"][-1]["note"]
    assert "gültig bis" in provided["events"][-1]["note"]

    checked = _ok(client.post(f"{INS}/{rid}/owner-check", headers=h))
    assert (checked["owner_on_request_date"], checked["owner_today"]) == (False, True)
    assert checked["ownership_changed"] is True
    assert checked["package_active"] is True
    assert "Widerruf" in checked["recommendation"]
    trail = _ok(client.get(f"{INS}/{rid}", headers=h))["events"]
    assert trail[-1]["kind"] == "owner_check"

    same, _, _ = _owner_request(client, h, "962", "2021-06-01")
    unchanged = _ok(client.post(f"{INS}/{same}/owner-check", headers=h))
    assert unchanged["ownership_changed"] is False
    assert unchanged["package_active"] is False
    assert unchanged["recommendation"] == "Eigentümerstellung unverändert."

    # Authorization and tenant separation: reader 403, other tenant 404.
    assert client.post(f"{INS}/{rid}/owner-check", headers=hr).status_code == 403
    assert client.post(f"{INS}/{rid}/owner-check", headers=ho).status_code == 404
