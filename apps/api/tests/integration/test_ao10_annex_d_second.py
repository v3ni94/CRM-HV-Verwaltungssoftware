"""AO10 (GAK-402, rule 0.1.8): second independent tests for the annex D cases D04, D17, D31,
D34, D47 and D55 (the guard in tests/unit/test_aj19_test_guards.py keeps its single test list
empty).

Own world (tenant slug and user names with the prefix ``ao10``), other inputs and another path
than the first tests of the cases. Every expected value is derived by hand in the docstring or
in a comment before it is asserted, never read back from the code. No gate is opened; the
productive flags stay off and no ledger becomes leading."""

import asyncio
import csv
import hashlib
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import func, select

from mhvp.accounting.audit_export import BOM
from mhvp.documents import deletion_journal as dj
from mhvp.documents.blobs import BlobStore
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_annex_d_gaps import (
    _entries,
    _hoa,
    _line,
    _trial_balance,
    _txs,
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _payment, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m9_restore_replay import (
    _events,
    _factory,
    _restore,
    _snapshot,
)
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m21_portal import _contact_of, _doc, _portal_user

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
D = "/api/v1/documents"
# Synthetic IBANs with a valid check digit (no real data).
IBAN_REV = "DE22100100105555555555"
IBAN_OPS = "DE72100100106666666666"
USERS = (
    ("ao10admin", "tenant_admin"),
    ("ao10second", "tenant_admin"),
    ("ao10acc", "accountant_no_banking"),
)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ao10-{RUN}", name=f"AO10 Anhang D {RUN}"
        )
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in USERS:
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


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int | None = None) -> Any:
    """Expects ``status``; without it any of 200 and 201 (the routes differ in the code)."""
    ok = (status,) if status else (200, 201)
    assert response.status_code in ok, response.text
    return response.json() if response.content else None


@pytest.mark.annex_d("D04")
def test_d04_second_incoming_half_first_with_other_amounts(
    client: TestClient, world: World
) -> None:
    """D04, second path: the community holds 5.000,00 on bank A and 2.500,00 on bank B (the
    reserve account). The transfer of 750,00 runs from B to A. The statement of B (outgoing)
    is imported first, that of A (incoming) second. Expected by hand: A 5.000,00 + 750,00 =
    5.750,00, B 2.500,00 - 750,00 = 1.750,00, total 7.500,00 before and after. The pair is
    recognised at the second import; booking the INCOMING half (A) against bank B posts the
    pair once; booking the outgoing half afterwards is refused (409) and moves nothing. No
    cost, revenue or reserve account moves, no open item exists, G1 stays closed."""
    h = bearer(login(client, world, "ao10admin"))
    acc_user = bearer(login(client, world, "ao10acc"))
    w = _hoa(client, h, "904", [(IBAN_REV, "hoa", "001210"), (IBAN_OPS, "reserve", "001211")])
    bank_a, bank_b = w["ledger_banks"][IBAN_REV], w["ledger_banks"][IBAN_OPS]
    opening = _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/entries",
            json={
                "kind": "opening_balance",
                "booking_date": "2026-01-01",
                "text": "Anfangsbestand AO10",
                "lines": [
                    _line(bank_a, "5000.00"),
                    _line(bank_b, "2500.00"),
                    _line(w["accounts"]["009000"]["id"], "0", "7500.00"),
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{w['ledger']}/entries/{opening['id']}/approve", headers=acc_user))
    _ok(client.post(f"{A}/ledgers/{w['ledger']}/entries/{opening['id']}/post", headers=h))
    file_b = _camt(
        "1004-B",
        IBAN_OPS,
        "2500.00",
        "1750.00",
        [_ntry("1004-B1", "750.00", "DBIT", "2026-01-12", IBAN_REV, "Umbuchung Reserve")],
    )
    file_a = _camt(
        "1004-A",
        IBAN_REV,
        "5000.00",
        "5750.00",
        [_ntry("1004-A1", "750.00", "CRDT", "2026-01-13", IBAN_OPS, "Umbuchung Reserve")],
    )
    run_b = _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "b.xml", file_b)}, headers=h
        ),
        201,
    )
    run_a = _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "a.xml", file_a)}, headers=h
        ),
        201,
    )
    assert (run_b["counts"]["transfers"], run_a["counts"]["transfers"]) == (0, 1)
    (out,) = _txs(client, h, w["bank_ids"][IBAN_OPS])
    (into,) = _txs(client, h, w["bank_ids"][IBAN_REV])
    assert (out["transfer_pair_id"], into["transfer_pair_id"]) == (into["id"], out["id"])

    _ok(
        client.post(
            f"{B}/transactions/{into['id']}/book", json={"counter_account_id": bank_b}, headers=h
        ),
        201,
    )
    second = client.post(
        f"{B}/transactions/{out['id']}/book", json={"counter_account_id": bank_a}, headers=h
    )
    assert second.status_code == 409, second.text

    tb = _trial_balance(client, h, w["ledger"])
    by = {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}
    assert (by["001210"], by["001211"]) == (Decimal("5750.00"), Decimal("1750.00"))
    assert by["001210"] + by["001211"] == Decimal("7500.00")
    assert not {a["category"] for a in tb["accounts"] if Decimal(a["balance"]) != 0} & {
        "cost",
        "revenue",
        "reserve",
    }
    posted = sorted(e["kind"] for e in _entries(client, h, w["ledger"]) if e["status"] == "posted")
    assert posted == ["bank_transfer", "opening_balance"]
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{w['ledger']}/open-items", params={"as_of": "2026-12-31"}, headers=h
            )
        )
        == []
    )
    for iban in (IBAN_REV, IBAN_OPS):
        rec = _ok(client.get(f"{B}/accounts/{w['bank_ids'][iban]}/reconciliation", headers=h))
        assert [Decimal(r["statement_difference"]) for r in rec] == [Decimal("0.00")]
    gate = client.post(
        f"{A}/ledgers/{w['ledger']}/leading", json={"leading_system": "mhvp"}, headers=h
    )
    assert gate.status_code == 403
    assert gate.json()["code"] == "MHVP-GATE-0001"


def _property(c: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AO10 Haus {number}", "management_type": kind},
            headers=h,
        ),
        201,
    )


def _ownership(c: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
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


@pytest.mark.annex_d("D17")
def test_d17_second_company_with_two_units_and_unequal_co_owners(
    client: TestClient, world: World
) -> None:
    """D17, second path with other figures. Party P (a company) owns units 11 and 12 with
    250,00 hoa fee each. Party Q (two persons, 60/40) owns unit 13 with 175,00, party R
    (one person) owns unit 14 with 100,00. Expected by hand: four ownership contracts and four
    distinct debtor accounts (per party and unit, not per person); one receivable per
    contract: 250,00 + 250,00 + 175,00 + 100,00 = 775,00 in four open items, none per co owner.
    Head principle: P votes yes with both units, Q yes, R no. Heads: P 1, Q 1, R 1, so
    yes 2 : no 1, positive (counting per unit would give 3 : 1, per person 4 : 1 or more).
    P voting yes on unit 11 and no on unit 12 is inconsistent (409)."""
    h = bearer(login(client, world, "ao10admin"))
    weg = _property(client, h, "917", "hoa")
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    party_p, _ = _party(client, h, "Firma", "company")
    first = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Clara", "last_name": f"Quart{RUN}"},
            headers=h,
        ),
        201,
    )
    second = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Dirk", "last_name": f"Quart{RUN}"},
            headers=h,
        ),
        201,
    )
    party_q = _ok(
        client.post(
            "/api/v1/parties",
            json={
                "members": [
                    {"contact_id": first["id"], "share_percent": "60"},
                    {"contact_id": second["id"], "role": "co_party", "share_percent": "40"},
                ]
            },
            headers=h,
        ),
        201,
    )
    party_r, _ = _party(client, h, "Rudi")
    plan = [("11", party_p, "250.00"), ("12", party_p, "250.00")]
    plan += [("13", str(party_q["id"]), "175.00"), ("14", party_r, "100.00")]
    contracts: dict[str, dict[str, Any]] = {}
    for no, party, amount in plan:
        contracts[no] = _ownership(client, h, _unit(client, h, weg["id"], no), party)
        _ok(
            client.post(
                f"/api/v1/contracts/{contracts[no]['id']}/payments",
                json=_payment(amount, amount, "2020-01-01", "hoa_fee"),
                headers=h,
            )
        )
        _ok(
            client.post(
                f"/api/v1/contracts/{contracts[no]['id']}/schedules",
                json={"valid_from": "2020-01-01", "due_day": 3},
                headers=h,
            )
        )
    assert len({c["debtor_account"]["id"] for c in contracts.values()}) == 4
    assert contracts["11"]["party_id"] == contracts["12"]["party_id"] == party_p

    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": accounts["060100"]},
            headers=h,
        )
    )
    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-04-01", "scope": "property", "scope_id": weg["id"]},
            headers=h,
        )
    )
    assert run["totals"]["ready"] == {"count": 4, "amount": "775.00"}
    _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-04-30"}, headers=h)
    )
    assert sorted(i["contract_id"] for i in items) == sorted(c["id"] for c in contracts.values())
    assert sum(Decimal(i["remaining"]) for i in items) == Decimal("775.00")

    meeting = _ok(
        client.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2026-07-04T10:00:00+02:00",
                "voting_principle": "head",
            },
            headers=h,
        )
    )
    mid = meeting["id"]
    items_by = {}
    for key, title in (("ok", "Hofsanierung"), ("split", "Zaun")):
        items_by[key] = _ok(
            client.post(
                f"{H}/meetings/{mid}/agenda",
                json={"title": title, "proposal": f"{title} wird beschlossen."},
                headers=h,
            )
        )
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-06-10"}, headers=h))
    for no in contracts:
        _ok(
            client.post(
                f"{H}/meetings/{mid}/attendance",
                json={"contract_id": contracts[no]["id"], "present": True},
                headers=h,
            )
        )

    def vote(item: str, no: str, choice: str) -> None:
        _ok(
            client.post(
                f"{H}/agenda/{item}/votes",
                json={"contract_id": contracts[no]["id"], "choice": choice},
                headers=h,
            )
        )

    for no, choice in [("11", "yes"), ("12", "yes"), ("13", "yes"), ("14", "no")]:
        vote(items_by["ok"]["id"], no, choice)
    tally = _ok(client.get(f"{H}/agenda/{items_by['ok']['id']}/tally", headers=h))
    assert (tally["yes"], tally["no"], tally["principle"]) == ("2", "1", "head")
    assert tally["proposal"] == "positive"
    for no, choice in [("11", "yes"), ("12", "no"), ("13", "yes"), ("14", "no")]:
        vote(items_by["split"]["id"], no, choice)
    refused = client.get(f"{H}/agenda/{items_by['split']['id']}/tally", headers=h)
    assert refused.status_code == 409, refused.text


@pytest.mark.annex_d("D31")
def test_d31_second_each_tenant_gets_only_the_own_released_version(
    client: TestClient, world: World
) -> None:
    """D31, second path: a heating bill with third party data stays on the property (original,
    visible for nobody in the portal). Two redacted versions are released, one linked to the
    contract of tenant X, one to that of tenant Y (each linked to the original with role
    generated). Expected by hand: X sees exactly 1 document (its own version, with the
    redaction note), Y sees exactly 1 (its own), 2 released documents exist and 2 tenants,
    so 1 + 1 = 2 and no document appears for both. Neither tenant can read or download the
    original (404 in the portal, 403 in the CRM read path), and the other tenant's version
    is not downloadable either (404): no blanket refusal, no blanket release."""
    h = bearer(login(client, world, "ao10admin"))
    rental = _property(client, h, "931", "rental")
    landlord, _ = _party(client, h, "Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    users: dict[str, dict[str, str]] = {}
    contracts: dict[str, dict[str, Any]] = {}
    for tag, unit_no in (("x", "A"), ("y", "B")):
        party, _ = _party(client, h, f"Mieter{tag.upper()}")
        contracts[tag] = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": _unit(client, h, rental["id"], unit_no),
                    "party_id": party,
                    "start_date": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )
        users[tag] = _portal_user(client, h, world, f"ao10t{tag}", _contact_of(client, h, party))
    titles = {
        "orig": f"AO10 Heizkostenrechnung {RUN}",
        "x": f"AO10 Heizkostenrechnung X geschwaerzt {RUN}",
        "y": f"AO10 Heizkostenrechnung Y geschwaerzt {RUN}",
    }
    orig = _doc(client, h, titles["orig"], "property", rental["id"], ["tenant"])
    released = {
        tag: _doc(client, h, titles[tag], "contract", contracts[tag]["id"], ["tenant"])
        for tag in ("x", "y")
    }
    for doc in released.values():
        _ok(
            client.post(
                f"{D}/{doc}/links",
                json={"entity_type": "document", "entity_id": orig, "role": "generated"},
                headers=h,
            ),
            201,
        )
    listed = {
        tag: {d["id"]: d for d in _ok(client.get(f"{P}/documents", headers=users[tag]))}
        for tag in ("x", "y")
    }
    assert [set(listed[t]) for t in ("x", "y")] == [{released["x"]}, {released["y"]}]
    assert len(listed["x"]) + len(listed["y"]) == 2
    for tag in ("x", "y"):
        other = "y" if tag == "x" else "x"
        assert listed[tag][released[tag]]["redaction_note"]
        own = client.get(f"{P}/documents/{released[tag]}/download", headers=users[tag])
        assert own.status_code == 200, own.text
        assert own.content == titles[tag].encode()
        assert own.headers["X-Redaction-Note"]
        assert (
            client.get(f"{P}/documents/{released[other]}/download", headers=users[tag]).status_code
            == 404
        )
        assert client.get(f"{P}/documents/{orig}/download", headers=users[tag]).status_code == 404
        assert client.get(f"{D}/{orig}", headers=users[tag]).status_code == 403
    # The management still sees the original and the link of each version to it.
    for doc in released.values():
        links = _ok(client.get(f"{D}/{doc}", headers=h))["links"]
        assert any(
            link["entity_type"] == "document" and link["entity_id"] == orig for link in links
        )


async def _count(settings: Any, world: World, model: Any, *where: Any) -> int:
    from mhvp.core.db.tenancy import tenant_transaction

    engine, factory = _factory(settings)
    try:
        async with tenant_transaction(factory, world.tenant_a) as session:
            return int(
                await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
            )
    finally:
        await engine.dispose()


@pytest.mark.annex_d("D34")
def test_d34_second_two_owners_receipts_are_per_account_and_no_dispatch(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """D34, second path with two owners and a GdWE document. Owner 1 opens the document once
    and downloads it once; owner 2 only lists. Expected by hand: 1 open + 1 download = 2
    read receipts, all with owner 1's contact, none for owner 2 (listing writes nothing), so
    the total is 2 and owner 2's count is 0. No dispatch row exists for the document (a
    read receipt is no delivery, no Zugang) and the document stays visible to owners only."""
    from mhvp.communication.models import Dispatch
    from mhvp.portal.models import PortalReadReceipt

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "ao10admin"))
    weg = _property(client, h, "934", "hoa")
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    parties = []
    for no in ("01", "02"):
        party, _ = _party(client, h, f"Leser{no}")
        _ownership(client, h, _unit(client, h, weg["id"], no), party)
        parties.append(party)
    document = _doc(client, h, "AO10 Einladung ETV", "legal_entity", hoa, ["owner"])
    contacts = [_contact_of(client, h, p) for p in parties]
    owner1 = _portal_user(client, h, world, "ao10owner1", contacts[0])
    owner2 = _portal_user(client, h, world, "ao10owner2", contacts[1])
    path = f"{D}/{document}/portal-read-receipts"

    assert document in {d["id"] for d in _ok(client.get(f"{P}/documents", headers=owner2))}
    assert _ok(client.get(path, headers=h))["items"] == []
    _ok(client.get(f"{P}/documents/{document}", headers=owner1))
    assert client.get(f"{P}/documents/{document}/download", headers=owner1).status_code == 200
    out = _ok(client.get(path, headers=h))
    assert sorted(r["kind"] for r in out["items"]) == ["downloaded", "opened"]
    assert {r["contact_id"] for r in out["items"]} == {contacts[0]}
    assert "Keine Zustellung" in out["note"]
    assert (
        asyncio.run(
            _count(
                settings,
                world,
                PortalReadReceipt,
                PortalReadReceipt.document_id == uuid.UUID(document),
            )
        )
        == 2
    )
    assert (
        asyncio.run(_count(settings, world, Dispatch, Dispatch.document_id == uuid.UUID(document)))
        == 0
    )
    assert _ok(client.get(f"{D}/{document}", headers=h))["visibility"] == ["owner"]


@pytest.mark.annex_d("D47")
def test_d47_second_hold_set_after_the_restore_keeps_the_evidence(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """D47, second path: the document is deleted lawfully (no hold at backup time, retention
    ended 31.12.2020). The restore brings it back. Only AFTER the restore a deletion hold is
    set (a new proceeding). Expected by hand: the journal holds exactly 1 deletion entry; the
    dry run reports 0 x would_delete and 1 x kept_hold; the real replay deletes nothing, the
    document and its blob stay unchanged (same bytes, same SHA-256), and the refusal is
    recorded as an event marked as replay. A journal filtered to a foreign tenant id holds 0
    entries (tenant separation of the export)."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "ao10admin"))
    second = bearer(login(client, world, "ao10second"))
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"ao10_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )["id"]
    _ok(client.post(f"/api/v1/retention-profiles/{profile}/release", headers=second))
    started = datetime.now(UTC) - timedelta(minutes=1)
    data = b"AO10 Beleg spaeter unter Sperre"
    doc = _ok(client.post(D, files={"file": ("ao10.txt", data, "text/plain")}, headers=h), 201)
    _ok(
        client.patch(
            f"{D}/{doc['id']}",
            json={"retention_profile_id": profile, "retention_until": "2020-12-31"},
            headers=h,
        )
    )
    row = asyncio.run(_snapshot(settings, world, doc["id"]))
    assert row["retention_hold_reason"] is None
    assert client.delete(f"{D}/{doc['id']}", headers=h).status_code == 204

    engine, factory = _factory(settings)
    try:
        journal = asyncio.run(
            dj.export_journal(factory, since=started, tenant_ids=[world.tenant_a])
        )
        foreign = asyncio.run(dj.export_journal(factory, since=started, tenant_ids=[uuid.uuid4()]))
    finally:
        asyncio.run(engine.dispose())
    assert foreign["entries"] == []
    mine = [e for e in journal["entries"] if e["document_id"] == doc["id"]]
    assert [e["type"] for e in mine] == ["document.deleted"]

    asyncio.run(_restore(settings, world, row, data))
    _ok(client.post(f"{D}/{doc['id']}/hold", json={"reason": "Neues Verfahren AO10"}, headers=h))
    engine, factory = _factory(settings)
    try:
        store = BlobStore(settings)
        dry = asyncio.run(dj.replay_journal(factory, journal, store, apply=False))
        assert dry.counts.get(dj.OUTCOME_WOULD_DELETE, 0) == 0
        assert dry.counts[dj.OUTCOME_KEPT_HOLD] == 1
        report = asyncio.run(dj.replay_journal(factory, journal, store, apply=True))
    finally:
        asyncio.run(engine.dispose())
    result = next(r for r in report.results if r.document_id == doc["id"])
    assert result.outcome == dj.OUTCOME_KEPT_HOLD
    assert "Neues Verfahren AO10" in (result.reason or "")
    assert client.get(f"{D}/{doc['id']}", headers=h).status_code == 200
    assert BlobStore(settings).get(row["storage_ref"]) == data
    assert hashlib.sha256(data).hexdigest() == row["sha256"]
    refusals = asyncio.run(_events(settings, world, "document.deletion_refused"))
    assert refusals[-1].payload["replay"] is True
    assert str(refusals[-1].entity_id) == doc["id"]


def _table(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = zf.read(name).decode("utf-8")
    assert text.startswith(BOM), name
    return list(csv.DictReader(io.StringIO(text.removeprefix(BOM)), delimiter=";"))


def _amount(text: str) -> Decimal:
    return Decimal(text.replace(".", "").replace(",", "."))


@pytest.mark.annex_d("D55")
def test_d55_second_export_is_recomputable_from_the_files(client: TestClient, world: World) -> None:
    """D55, second path, analysis of the export. Postings of a small ledger: opening balance
    on 01.01.2026 (001200 debit 8.000,00, 001201 debit 12.000,00, 009000 credit 20.000,00),
    receivable on 02.05.2026 (debtor debit 300,00 / 060100 credit 300,00), a custom entry on
    10.06.2026 (060100 debit 45,50 / 001200 credit 45,50) and its reversal on 15.06.2026
    (001200 debit 45,50 / 060100 credit 45,50). Expected by hand: 4 entries numbered 1 to 4,
    9 lines; debit total 20.000,00 + 300,00 + 45,50 + 45,50 = 20.391,00 equals the credit
    total; 001200 ends at 8.000,00 - 45,50 + 45,50 = 8.000,00, 001201 at 12.000,00. The
    ledger API shows the same balances. Period 01.06.2026 to 30.06.2026 keeps 2 entries
    (numbers 3 and 4), the opening balances stay; the reversal relation names 3 and 4; the
    only approval is the opening balance; every file hash of the index matches."""
    h = bearer(login(client, world, "ao10admin"))
    acc_user = bearer(login(client, world, "ao10acc"))
    prop = _property(client, h, "955", "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    owner, _ = _party(client, h, "Pruefer")
    _ownership(client, h, _unit(client, h, prop["id"], "01"), owner)  # creates a debtor account
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    debtor = next(a["id"] for a in acc.values() if a["category"] == "debtor")

    def book(body: dict[str, Any]) -> dict[str, Any]:
        draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
        if body["kind"] == "opening_balance":
            _ok(
                client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=acc_user)
            )
        return _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]

    opening = book(
        {
            "kind": "opening_balance",
            "booking_date": "2026-01-01",
            "text": "Anfangsbestand AO10",
            "lines": [
                _line(acc["001200"]["id"], "8000.00"),
                _line(acc["001201"]["id"], "12000.00"),
                _line(acc["009000"]["id"], "0", "20000.00"),
            ],
        }
    )
    book(
        {
            "kind": "receivable",
            "booking_date": "2026-05-02",
            "due_date": "2026-05-04",
            "text": "Hausgeld Mai",
            "lines": [_line(debtor, "300.00"), _line(acc["060100"]["id"], "0", "300.00")],
        }
    )
    custom = book(
        {
            "kind": "custom",
            "booking_date": "2026-06-10",
            "text": "Doppelt erfasst",
            "lines": [
                _line(acc["060100"]["id"], "45.50"),
                _line(acc["001200"]["id"], "0", "45.50"),
            ],
        }
    )
    reversal = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{custom['id']}/reverse",
            json={"reason": "Doppelt erfasst", "booking_date": "2026-06-15"},
            headers=h,
        ),
        201,
    )

    def export(period_from: str, period_to: str) -> tuple[dict[str, Any], bytes]:
        run = _ok(
            client.post(
                f"{A}/audit-exports",
                json={"ledger_id": ledger, "period_from": period_from, "period_to": period_to},
                headers=h,
            ),
            201,
        )
        data = client.get(f"{A}/audit-exports/{run['id']}/download", headers=h).content
        assert hashlib.sha256(data).hexdigest() == run["sha256"]
        return run, data

    _, data = export("2026-01-01", "2026-12-31")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        entries = _table(zf, "buchungen.csv")
        lines = _table(zf, "buchungszeilen.csv")
        assert [r["Nummer"] for r in entries] == ["1", "2", "3", "4"]
        assert len(lines) == 9
        debit = sum(_amount(r["Soll"]) for r in lines)
        credit = sum(_amount(r["Haben"]) for r in lines)
        assert debit == credit == Decimal("20391.00")
        net: dict[str, Decimal] = {}
        for r in lines:
            net[r["Kontonummer"]] = (
                net.get(r["Kontonummer"], Decimal(0)) + _amount(r["Soll"]) - _amount(r["Haben"])
            )
        assert net["001200"] == Decimal("8000.00")
        assert net["001201"] == Decimal("12000.00")
        tb = {
            a["number"]: Decimal(a["balance"])
            for a in _trial_balance(client, h, ledger)["accounts"]
        }
        assert (tb["001200"], tb["001201"]) == (net["001200"], net["001201"])
        storno = _table(zf, "storno_beziehungen.csv")
        assert [
            (r["Original-ID"], r["Storno-ID"], r["Original-Nummer"], r["Storno-Nummer"])
            for r in storno
        ] == [(custom["id"], reversal["id"], "3", "4")]
        approvals = _table(zf, "freigaben.csv")
        assert [(r["Objekt-ID"], r["Person"]) for r in approvals] == [
            (opening["id"], str(world.users["ao10acc"]))
        ]
        index = {e["file"]: e["sha256"] for e in json.loads(zf.read("index.json"))["files"]}
        for name, digest in index.items():
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest, name

    _, june = export("2026-06-01", "2026-06-30")
    with zipfile.ZipFile(io.BytesIO(june)) as zf:
        assert [r["Nummer"] for r in _table(zf, "buchungen.csv")] == ["3", "4"]
        assert len(_table(zf, "eroeffnungsbestaende.csv")) == 3
