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
ACC = "/api/v1/accounting"


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
    meetings = _ok(client.get(f"{H}/meetings", params={"legal_entity_id": hoa}, headers=h))
    assert len(meetings) == 2
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
    mid_mea = next(m["id"] for m in meetings if m["voting_principle"] == "mea")
    detail = _ok(client.get(f"{H}/meetings/{mid_mea}", headers=h))
    assert (detail["represented"], detail["proxies"]) == (3, 1)
    assert detail["agenda"][0]["resolution"]["status"] == "positive"
    members = _ok(client.get(f"{H}/meetings/{mid_mea}/members", headers=h))
    assert [(m["unit_number"], m["present"], m["proxy"]) for m in members] == [
        ("01", True, False),
        ("02", True, False),
        ("03", False, True),
    ]
    assert members[2]["votes"] == {detail["agenda"][0]["id"]: "no"}
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

    # M25-01 rule set (decided 24.09.2026). Test rule, not a legal statement: MEA principle,
    # more than 2/3 of votes cast and at least half of all MEA. A yes 700, B no 300 ->
    # 0.7000 > 0.6667 and 0.7000 >= 0.5 -> positive. A unanimity rule fails because of B.
    rule = _ok(
        client.post(
            f"{H}/majority-rules",
            json={
                "legal_entity_id": hoa,
                "label": "Testregel qualifiziert",
                "principle": "mea",
                "share_of_votes_cast": "0.66666667",
                "min_mea_share_of_all": "0.5",
                "source": "Teilungserklärung § 12 (Testannahme)",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    allrule = _ok(
        client.post(
            f"{H}/majority-rules",
            json={
                "legal_entity_id": hoa,
                "label": "Testregel allstimmig",
                "principle": "head",
                "unanimous": True,
                "source": "Vereinbarung (Testannahme)",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    assert (
        client.post(
            f"{H}/majority-rules",
            json={
                "legal_entity_id": hoa,
                "label": "ohne Schwelle",
                "principle": "head",
                "source": "x y z",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ).status_code
        == 422
    )
    m3 = _ok(client.post(f"{H}/meetings", json=base, headers=h), 201)
    items3 = [
        _ok(
            client.post(
                f"{H}/meetings/{m3['id']}/agenda",
                json={"title": title, "rule_id": rid},
                headers=h,
            ),
            201,
        )
        for title, rid in [("Aufzug", rule["id"]), ("Gartennutzung", allrule["id"])]
    ]
    _ok(
        client.post(f"{H}/meetings/{m3['id']}/invite", json={"invited_at": "2026-05-29"}, headers=h)
    )
    for no in ("01", "02", "03"):
        _ok(
            client.post(
                f"{H}/meetings/{m3['id']}/attendance",
                json={"contract_id": contracts[no], "present": True},
                headers=h,
            ),
            201,
        )
    for item in items3:
        for no, choice in [("01", "yes"), ("02", "yes"), ("03", "no")]:
            _ok(
                client.post(
                    f"{H}/agenda/{item['id']}/votes",
                    json={"contract_id": contracts[no], "choice": choice},
                    headers=h,
                ),
                201,
            )
    q = _ok(client.get(f"{H}/agenda/{items3[0]['id']}/tally", headers=h))
    assert (q["principle"], q["yes"], q["no"], q["proposal"]) == ("mea", "700", "300", "positive")
    assert q["checks"]["share_of_votes_cast"] == {"value": "0.7000", "passed": True}
    assert q["checks"]["mea_share_of_all"] == {"value": "0.7000", "passed": True}
    assert q["rule"]["source"].startswith("Teilungserklärung")
    u = _ok(client.get(f"{H}/agenda/{items3[1]['id']}/tally", headers=h))
    assert (u["proposal"], u["checks"]["unanimous"]["passed"]) == ("negative", False)
    rules = _ok(client.get(f"{H}/majority-rules", params={"legal_entity_id": hoa}, headers=h))
    assert {r["label"] for r in rules} == {"Testregel qualifiziert", "Testregel allstimmig"}


def _hoa_with_owners(
    client: TestClient, h: dict[str, str], number: str
) -> tuple[str, str, dict[str, str], dict[str, Any]]:
    """Property with two owners (units 01 and 02, one each) for the D cases below."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG D-Fall {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    contracts: dict[str, str] = {}
    for no in ("01", "02"):
        party, _ = _party(client, h, f"D{number}{no}")
        unit = _unit(client, h, prop["id"], no)
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
    _, auditor = _party(client, h, f"Beirat{number}")
    return str(prop["id"]), hoa, contracts, auditor


def test_d32_d33_audit_sample_report_and_invoice_change_after_check(
    client: TestClient, world: World
) -> None:
    """D32 (PÜ09): the report shows count and value of the actually checked positions separately
    from the selected and unchecked ones and never claims a full audit. D33: an invoice changed
    after the board checked its document marks that position outdated; the report and the audit
    detail no longer show an unchanged green overall status. Expected values by hand: items
    120,00 (checked) and 80,00 (open): checked 1 / 120,00, unchecked 1 / 80,00, selected 2."""
    h = bearer(login(client, world, "m25admin"))
    _, hoa, _, auditor = _hoa_with_owners(client, h, "752")
    template = _ok(client.post(f"{ACC}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{ACC}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{ACC}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Dachdecker {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    doc_checked = _doc(client, h, "rechnung-dach.pdf")
    doc_open = _doc(client, h, "rechnung-garten.pdf")
    invoice_body = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": "D33-1",
        "invoice_date": "2025-06-01",
        "net": "120.00",
        "vat": "0.00",
        "gross": "120.00",
        "document_id": doc_checked,
        "lines": [{"account_id": acc["040300"], "net": "120.00"}],
    }
    invoice = _ok(client.post(f"{ACC}/invoices", json=invoice_body, headers=h), 201)["id"]

    audit = _ok(
        client.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Stichprobe Jahresabrechnung 2025 (D32)",
                "auditor_contact_ids": [auditor["id"]],
            },
            headers=h,
        ),
        201,
    )
    items = [
        _ok(
            client.post(
                f"{H}/audits/{audit['id']}/items",
                json={"document_id": doc, "amount": amount},
                headers=h,
            ),
            201,
        )
        for doc, amount in [(doc_checked, "120.00"), (doc_open, "80.00")]
    ]
    _ok(
        client.patch(
            f"{H}/audit-items/{items[0]['id']}",
            json={"status": "checked", "note": "Beleg und Leistung stimmig"},
            headers=h,
        )
    )
    # D32: checked count and value separate from selected and unchecked; no full audit claim.
    report = _ok(client.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)
    c = report["content"]
    assert (c["checked_count"], c["checked_value"]) == (1, "120.00")
    assert (c["unchecked_count"], c["unchecked_value"]) == (1, "80.00")
    assert (c["selected"], c["population_entries"]) == (2, 0)
    assert c["open"] == [items[1]["id"]]
    assert c["outdated"] == []
    assert c["outdated_reasons"] == {}
    assert "nicht die gesamte Abrechnung" in c["scope_note"]
    assert c["overall_status"].startswith("eingeschränkt: offene Positionen")
    detail = _ok(client.get(f"{H}/audits/{audit['id']}", headers=h))
    assert [i["status"] for i in detail["items"]] == ["checked", "open"]

    # D33: the invoice behind the checked document gets a new version after the check.
    changed = _ok(
        client.put(
            f"{ACC}/invoices/{invoice}",
            json=invoice_body | {"net": "150.00", "gross": "150.00"},
            headers=h,
        )
    )
    assert changed["version"] == 2
    detail = _ok(client.get(f"{H}/audits/{audit['id']}", headers=h))
    assert detail["outdated_reasons"] == {items[0]["id"]: "Rechnung nach Prüfung geändert"}
    by_id = {i["id"]: i for i in detail["items"]}
    assert (by_id[items[0]["id"]]["status"], by_id[items[0]["id"]]["version"]) == ("outdated", 3)
    assert by_id[items[1]["id"]]["status"] == "open"  # untouched document stays as it was
    assert detail["overall_status"] == "eingeschränkt: Positionen nach Prüfung geändert"
    # The outdated position is no longer worked on in place; a new check is a new position.
    assert (
        client.patch(
            f"{H}/audit-items/{items[0]['id']}", json={"status": "checked"}, headers=h
        ).status_code
        == 409
    )
    second = _ok(client.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)
    c2 = second["content"]
    assert second["version"] == 2
    assert (c2["checked_count"], c2["checked_value"]) == (0, "0.00")
    assert c2["outdated"] == [items[0]["id"]]
    assert c2["overall_status"] == "eingeschränkt: Positionen nach Prüfung geändert"


def test_d53_virtual_meeting_needs_basis_and_documents_disruption(
    client: TestClient, world: World
) -> None:
    """D53: a virtual meeting is refused without a positive basis resolution (a negative circular
    resolution is no basis); a result announced against the tally is refused; a technical
    disruption is documented as an event, blocks votes and announcements until the documented
    resumption, and stays visible on the meeting instead of a silently successful video call."""
    h = bearer(login(client, world, "m25admin"))
    _, hoa, contracts, _ = _hoa_with_owners(client, h, "753")
    evidence = _doc(client, h, "umlauf-virtuell.pdf")
    circ = {
        "legal_entity_id": hoa,
        "subject": "Virtuelle Versammlungen",
        "wording": "Versammlungen können rein virtuell stattfinden.",
        "decided_on": "2026-03-01",
        "evidence_document_id": evidence,
    }
    negative = _ok(
        client.post(
            f"{H}/circular-resolutions",
            json=circ | {"consents": {contracts["01"]: "yes", contracts["02"]: "no"}},
            headers=h,
        ),
        201,
    )
    assert negative["status"] == "negative"
    positive = _ok(
        client.post(
            f"{H}/circular-resolutions",
            json=circ | {"consents": dict.fromkeys(contracts.values(), "yes")},
            headers=h,
        ),
        201,
    )
    assert positive["status"] == "positive"

    base = {"legal_entity_id": hoa, "scheduled_at": "2026-08-20T18:00:00+02:00", "mode": "virtual"}
    for body in (base, base | {"virtual_basis_resolution_id": negative["id"]}):
        refused = client.post(f"{H}/meetings", json=body, headers=h)
        assert refused.status_code == 422, refused.text
        assert "Beschlussgrundlage" in refused.json()["detail"]
    meeting = _ok(
        client.post(
            f"{H}/meetings", json=base | {"virtual_basis_resolution_id": positive["id"]}, headers=h
        ),
        201,
    )
    mid = meeting["id"]
    assert meeting["mode"] == "virtual"
    item = _ok(
        client.post(
            f"{H}/meetings/{mid}/agenda",
            json={
                "title": "Wirtschaftsplan 2027",
                "proposal": "Der Wirtschaftsplan wird beschlossen.",
            },
            headers=h,
        ),
        201,
    )
    # A disruption before the meeting is opened has no meeting to disrupt.
    early = {
        "description": "Konferenzsystem nicht erreichbar",
        "occurred_at": "2026-08-20T18:05:00+02:00",
    }
    assert client.post(f"{H}/meetings/{mid}/disruptions", json=early, headers=h).status_code == 409
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-07-20"}, headers=h))
    for no in ("01", "02"):
        _ok(
            client.post(
                f"{H}/meetings/{mid}/attendance",
                json={"contract_id": contracts[no], "present": True, "online": True},
                headers=h,
            ),
            201,
        )
    _ok(
        client.post(
            f"{H}/agenda/{item['id']}/votes",
            json={"contract_id": contracts["01"], "choice": "yes"},
            headers=h,
        ),
        201,
    )

    # Disruption: documented, meeting marked disrupted, votes and announcements blocked.
    disrupted = _ok(
        client.post(
            f"{H}/meetings/{mid}/disruptions",
            json=early | {"affected_contract_ids": [contracts["02"]]},
            headers=h,
        ),
        201,
    )
    assert disrupted["status"] == "disrupted"
    blocked_vote = client.post(
        f"{H}/agenda/{item['id']}/votes",
        json={"contract_id": contracts["02"], "choice": "no"},
        headers=h,
    )
    assert blocked_vote.status_code == 409
    assert "gestört" in blocked_vote.json()["detail"]
    blocked_announce = client.post(
        f"{H}/agenda/{item['id']}/announce",
        json={"outcome": "positive", "majority_basis": "einfache Mehrheit"},
        headers=h,
    )
    assert blocked_announce.status_code == 409
    assert (
        client.post(f"{H}/meetings/{mid}/disruptions", json=early, headers=h).status_code == 409
    )  # a second open disruption is not stacked on the first
    resumed = _ok(
        client.post(
            f"{H}/meetings/{mid}/disruptions",
            json={
                "description": "Verbindung wiederhergestellt, Anwesenheit erneut festgestellt",
                "occurred_at": "2026-08-20T18:20:00+02:00",
                "resolved": True,
            },
            headers=h,
        ),
        201,
    )
    assert resumed["status"] == "held"
    _ok(
        client.post(
            f"{H}/agenda/{item['id']}/votes",
            json={"contract_id": contracts["02"], "choice": "no"},
            headers=h,
        ),
        201,
    )
    # Head principle, 1 yes : 1 no -> negative; announcing "positive" is refused (wrong majority).
    tally = _ok(client.get(f"{H}/agenda/{item['id']}/tally", headers=h))
    assert (tally["yes"], tally["no"], tally["proposal"]) == ("1", "1", "negative")
    wrong = client.post(
        f"{H}/agenda/{item['id']}/announce",
        json={"outcome": "positive", "majority_basis": "einfache Mehrheit"},
        headers=h,
    )
    assert wrong.status_code == 409
    _ok(
        client.post(
            f"{H}/agenda/{item['id']}/announce",
            json={"outcome": "negative", "majority_basis": "einfache Mehrheit"},
            headers=h,
        ),
        201,
    )
    detail = _ok(client.get(f"{H}/meetings/{mid}", headers=h))
    assert detail["status"] == "held"
    assert [(d["resolved"], d["affected_contract_ids"]) for d in detail["disruptions"]] == [
        (False, [contracts["02"]]),
        (True, []),
    ]
    assert detail["disruptions"][0]["description"] == "Konferenzsystem nicht erreichbar"
    # A presence meeting has no technical disruption to document.
    presence = _ok(
        client.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2026-09-20T18:00:00+02:00"},
            headers=h,
        ),
        201,
    )
    assert (
        client.post(f"{H}/meetings/{presence['id']}/disruptions", json=early, headers=h).status_code
        == 422
    )
