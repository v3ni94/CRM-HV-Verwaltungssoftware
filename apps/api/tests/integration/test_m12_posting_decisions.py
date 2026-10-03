"""Learning bookkeeper, steps S0 and S1 (ADR 0014, rule M12-04, plan M12): decision log per
bank transaction behind the tenant switch ``learning_bookkeeper_enabled`` (default off).

Covered with fixed expected values (rule 0.1.8): switch off writes nothing; switch needs
accounting:approve plus tenant_settings:update; snapshot after the import commit, idempotent
per run, refreshed when the facts change; booking closes the round as accepted_unchanged or
modified with a diff; stale proposal id is refused (409 MHVP-BANK-0021); rejection needs a
reason and reopens a round; ignore is recorded and reopenable; reversal with reason code
reaches the bank side through the watermark consumer (counter example row, transaction open
again, rebooking allowed); closed rows are immutable and never deleted (DB guard); tenant and
legal entity separation; rule lifecycle events; concurrency of the snapshot job against a
manual booking. Nothing here posts automatically and no gate opens."""

import asyncio
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.banking.tasks import compute_proposals_once, process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.an16_bulk import bulk_book
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m18_tax_advisor_scope import assign_ledger_scope

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
A = "/api/v1/accounting"
T = "/api/v1/tenant"
BANK = "DE02120300000000202051"
BANK2 = "DE02100500000054540402"
PAYERS = ["DE89370400440532013000", "DE75512108001245126199"]
STRANGER = "DE12500105170648489890"


def _settings(database: Database, redis_url: str) -> Any:
    from pydantic import SecretStr

    # ``ai_inline``: the after-commit hook of the import computes the proposal snapshots in
    # the calling process (no worker in tests), exactly what the Celery task would do.
    return _base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lbk-{RUN}", name=f"Lernbuch {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lbo-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("bkadmin", a, "tenant_admin"),
            ("bkacc", a, "accountant_no_banking"),
            ("bktax", a, "tax_advisor"),
            ("bkcare", a, "caretaker"),
            ("bkother", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _later() -> datetime:
    # The consumer leaves events younger than PROCESS_LAG for the next run.
    return datetime.now(UTC) + timedelta(seconds=30)


def _hoa(client: TestClient, h: dict[str, str], number: str, iban: str) -> dict[str, Any]:
    """HOA property with bank account, ledger, bank ledger account and two owners with
    contracts and IBANs; returns ids and the open receivables (250,00 each)."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Lernhaus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank_id = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": iban,
                "holder": f"GdWE {number}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    contracts = []
    for i, payer in enumerate(PAYERS, start=1):
        contact = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": f"Eig{i}",
                    "last_name": f"L{number}{RUN}",
                    "bank_accounts": [{"iban": payer, "valid_from": "2020-01-01"}],
                },
                headers=h,
            ),
            201,
        )
        party = _ok(
            client.post(
                "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
            ),
            201,
        )
        unit = _unit(client, h, prop["id"], f"0{i}")
        contracts.append(
            _ok(
                client.post(
                    "/api/v1/contracts",
                    json={
                        "kind": "ownership",
                        "unit_id": unit,
                        "party_id": party["id"],
                        "start_date": "2020-01-01",
                        "title_transfer_date": "2020-01-01",
                        "acquisition_kind": "first_acquisition",
                    },
                    headers=h,
                ),
                201,
            )
        )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=h,
        ),
        201,
    )
    debtors = {a["unit_id"]: a["id"] for a in accounts.values() if a["category"] == "debtor"}
    for c in contracts:
        _receivable(client, h, ledger, debtors[c["unit_id"]], accounts["060100"]["id"], c["id"])
    return {
        "hoa": hoa,
        "bank_id": bank_id,
        "iban": iban,
        "ledger": ledger,
        "contracts": contracts,
        "debtors": debtors,
        "income": accounts["060100"]["id"],
        "geldtransit": accounts.get("001360", {}).get("id"),
    }


def _receivable(
    client: TestClient,
    h: dict[str, str],
    ledger: str,
    debtor: str,
    income: str,
    contract_id: str,
    amount: str = "250.00",
    text_: str = "Hausgeld Januar",
) -> str:
    draft = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "receivable",
                "booking_date": "2026-01-01",
                "text": text_,
                "contract_id": contract_id,
                "lines": [
                    {"account_id": debtor, "debit": amount},
                    {"account_id": income, "credit": amount},
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    return str(draft["id"])


def _import(
    client: TestClient, h: dict[str, str], stmt: str, iban: str, entries: list[str]
) -> dict[str, Any]:
    run = _ok(
        client.post(
            f"{B}/imports",
            json={
                "document_id": _upload(
                    client, h, f"{stmt}.xml", _camt(stmt, iban, "0.00", "0.00", entries)
                )
            },
            headers=h,
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    return {"run": run, "txs": txs}


def _decisions(client: TestClient, h: dict[str, str], tx_id: str) -> list[dict[str, Any]]:
    return list(_ok(client.get(f"{B}/transactions/{tx_id}/decisions", headers=h)))


def _events(client: TestClient, h: dict[str, str], event_type: str) -> list[dict[str, Any]]:
    return list(_ok(client.get(f"{T}/events", params={"type": event_type}, headers=h)))


def test_decision_log_behind_switch_and_full_cycle(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "bkadmin"))
    acc = bearer(login(client, world, "bkacc"))
    care = bearer(login(client, world, "bkcare"))
    w = _hoa(client, h, "801", BANK)
    n1, n2 = w["contracts"][0]["number"], w["contracts"][1]["number"]

    # Default off: reading is possible, nothing is written, settings show the flag.
    assert _ok(client.get(f"{B}/learning", headers=h))["enabled"] is False
    assert _ok(client.get(f"{T}/settings", headers=h))["learning_bookkeeper_enabled"] is False
    first = _import(
        client, h, "L-0", BANK, [_ntry("T0", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"HG {n1}")]
    )
    t0 = first["txs"]["T0"]["id"]
    assert _decisions(client, h, t0) == []
    proposals_off = _ok(client.get(f"{B}/transactions/{t0}/posting-proposals", headers=h))
    assert proposals_off["learning"] == {
        "enabled": False,
        "decision_id": None,
        "round": None,
        "features_hash": None,
        "proposals": None,
    }
    # A booking with proposal fields while the switch is off is a plain booking.
    _ok(
        client.post(
            f"{B}/transactions/{t0}/book",
            json={
                "settlements": [
                    {
                        "open_item_id": proposals_off["stage1"][0]["splits"][0]["open_item_id"],
                        "amount": "250.00",
                    }
                ],
                "proposal_id": str(uuid.uuid4()),
                "chosen": 0,
            },
            headers=h,
        ),
        201,
    )
    assert _decisions(client, h, t0) == []

    # Switch: accounting:approve alone (accountant) is not enough, tenant_settings:update
    # is required; the change carries reason and event.
    body = {"enabled": True, "reason": "Datenschutzprüfung im Test simuliert"}
    assert client.put(f"{B}/learning", json=body, headers=acc).status_code == 403
    assert client.put(f"{B}/learning", json=body, headers=care).status_code == 403
    assert client.put(f"{B}/learning", json={"enabled": True}, headers=h).status_code == 422
    assert _ok(client.put(f"{B}/learning", json=body, headers=h)) == {"enabled": True}
    assert _ok(client.get(f"{B}/learning", headers=h))["enabled"] is True
    switched = _events(client, h, "tenant.learning_bookkeeper_changed")
    assert switched
    assert switched[0]["payload"]["reason"] == body["reason"]
    # The banking event consumer positions its watermark on the first pass (older events are
    # history); everything below happens after it.
    positioned = asyncio.run(process_events_once(settings))
    assert positioned["failed"] == 0

    # Import after the switch: the after-commit job snapshots every open transaction.
    second = _import(
        client,
        h,
        "L-1",
        BANK,
        [
            _ntry("T1", "250.00", "CRDT", "2026-01-06", PAYERS[1], f"Hausgeld {n2}"),
            _ntry("T2", "250.00", "CRDT", "2026-01-06", PAYERS[1], "Hausgeld Januar"),
            _ntry("T3", "999.00", "CRDT", "2026-01-07", STRANGER, "Unbekannt"),
        ],
    )
    txs = second["txs"]
    run_id = uuid.UUID(second["run"]["id"])
    t1, t2, t3 = txs["T1"]["id"], txs["T2"]["id"], txs["T3"]["id"]
    rows = _decisions(client, h, t1)
    assert len(rows) == 1
    pending = rows[0]
    assert pending["status"] == "pending"
    assert pending["round"] == 1
    assert pending["level"] == "L0"
    assert pending["legal_entity_id"] == w["hoa"]
    assert pending["best_source"] == "match"
    assert pending["case_kind"] == "full"
    assert len(pending["features_hash"]) == 64
    assert pending["features"]["direction"] == "credit"
    assert "purpose" not in pending["features"]  # minimised
    assert pending["engine_version"]
    assert pending["rule_version"]
    full = next(p for p in pending["proposals"] if p["kind"] == "full")
    shown = _ok(client.get(f"{B}/transactions/{t1}/posting-proposals", headers=h))
    assert shown["learning"]["decision_id"] == pending["id"]
    assert shown["learning"]["round"] == 1
    assert _decisions(client, h, t3)[0]["case_kind"] == "unclear"
    computed_event = _events(client, h, "bank_transaction.booked")
    assert computed_event  # earlier booking of T0, event stream works

    # Idempotent per run: a second computation adds nothing.
    again = asyncio.run(compute_proposals_once(settings, world.tenant_a, run_id))
    assert again == {"checked": 3, "computed": 0, "skipped": 3, "auto_returns": 0}
    assert len(_decisions(client, h, t1)) == 1

    # Refresh when the facts change: a new open item of the second owner changes the hash of
    # every pending snapshot of that ledger; the old round expires, round 2 supersedes it.
    _receivable(
        client,
        h,
        w["ledger"],
        w["debtors"][w["contracts"][1]["unit_id"]],
        w["income"],
        w["contracts"][1]["id"],
        amount="100.00",
        text_="Hausgeld Februar",
    )
    refreshed = asyncio.run(compute_proposals_once(settings, world.tenant_a, run_id))
    assert refreshed["computed"] == 3
    rows = _decisions(client, h, t2)
    assert [r["status"] for r in rows] == ["expired", "pending"]
    assert rows[1]["round"] == 2
    assert rows[1]["supersedes_id"] == rows[0]["id"]
    assert rows[0]["reason"] == "Merkmale geändert, neuer Snapshot"
    stale_id = rows[0]["id"]

    # Accepted unchanged: booking exactly the chosen proposal (T1 full match, round 2).
    rows = _decisions(client, h, t1)
    current = rows[-1]
    full = next(p for p in current["proposals"] if p["kind"] == "full")
    chosen = current["proposals"].index(full)
    booked = _ok(
        client.post(
            f"{B}/transactions/{t1}/book",
            json={
                "settlements": [
                    {"open_item_id": s["open_item_id"], "amount": s["amount"]}
                    for s in full["splits"]
                ],
                "proposal_id": current["id"],
                "chosen": chosen,
                "text": "Hausgeld Februar Eig2",
            },
            headers=h,
        ),
        201,
    )
    rows = _decisions(client, h, t1)
    done = rows[-1]
    assert done["status"] == "accepted_unchanged"
    assert done["chosen_index"] == chosen
    assert done["diff"] == {}
    assert done["journal_entry_id"] == booked["journal_entry_id"]
    assert done["decided_by"] == str(world.users["bkadmin"])
    assert done["final"]["text"] == "Hausgeld Februar Eig2"
    assert done["bulk"] is False
    booked_events = _events(client, h, "bank_transaction.booked")
    mine = next(e for e in booked_events if e["entity_id"] == t1)
    assert mine["payload"]["decision_id"] == done["id"]
    assert mine["payload"]["decision_status"] == "accepted_unchanged"
    assert mine["payload"]["proposal_source"] == "match"
    assert mine["payload"]["discount"] == "0.00"

    # Stale proposal id: the expired round is refused, nothing is booked.
    stale = client.post(
        f"{B}/transactions/{t2}/book",
        json={"settlements": [], "counter_account_id": w["income"], "proposal_id": stale_id},
        headers=h,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "MHVP-BANK-0021"
    assert client.get(f"{B}/transactions/{t2}", headers=h).status_code in (200, 404)
    assert _decisions(client, h, t2)[-1]["status"] == "pending"

    # Rejection needs a reason of at least three characters; it closes the round as rejected
    # and opens the next one; the transaction stays open. The caretaker may not decide.
    current = _decisions(client, h, t3)[-1]
    short = client.post(f"{B}/transactions/{t3}/reject", json={"reason": "ab"}, headers=h)
    assert short.status_code == 422
    assert (
        client.post(
            f"{B}/transactions/{t3}/reject", json={"reason": "Zahler unbekannt"}, headers=care
        ).status_code
        == 403
    )
    rejected = _ok(
        client.post(
            f"{B}/transactions/{t3}/reject",
            json={"reason": "Zahler unbekannt, Rückfrage läuft", "proposal_id": current["id"]},
            headers=h,
        )
    )
    assert rejected["status"] == "rejected"
    assert rejected["reason"] == "Zahler unbekannt, Rückfrage läuft"
    rows = _decisions(client, h, t3)
    assert [r["status"] for r in rows] == ["expired", "rejected", "pending"]
    assert rows[-1]["round"] == 3
    assert txs["T3"]["status"] == "new"
    listed = {t["id"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    assert listed[t3]["status"] == "new"
    rejected_events = _events(client, h, "bank_transaction.proposal_rejected")
    assert rejected_events[0]["payload"]["decision_id"] == rejected["id"]

    # Ignore with reason is recorded and reopenable; reopening takes a new snapshot.
    ignored = _ok(
        client.post(
            f"{B}/transactions/{t3}/ignore",
            json={"decision": "ignore", "reason": "Fehlbuchung der Bank"},
            headers=h,
        )
    )
    assert ignored["status"] == "ignored"
    rows = _decisions(client, h, t3)
    assert rows[-1]["status"] == "ignored"
    assert rows[-1]["reason"] == "Fehlbuchung der Bank"
    # The read is gated like the writes: with the switch off the log is not visible, the
    # rows stay stored and reappear when switched on.
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Lesesperre"}, headers=h))
    assert _decisions(client, h, t3) == []
    _ok(client.put(f"{B}/learning", json={"enabled": True, "reason": "wieder an"}, headers=h))
    assert len(_decisions(client, h, t3)) == len(rows)
    assert (
        client.post(f"{B}/transactions/{t3}/reopen", json={"reason": "x"}, headers=h).status_code
        == 422
    )
    reopened = _ok(
        client.post(
            f"{B}/transactions/{t3}/reopen", json={"reason": "Doch echter Eingang"}, headers=h
        )
    )
    assert reopened["status"] == "new"
    rows = _decisions(client, h, t3)
    assert rows[-1]["status"] == "pending"
    assert rows[-1]["round"] == 4
    assert (
        client.post(
            f"{B}/transactions/{t3}/reopen", json={"reason": "noch einmal"}, headers=h
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{B}/transactions/{t1}/reopen", json={"reason": "gebucht"}, headers=h
        ).status_code
        == 409
    )

    # Modified: T2 (payer IBAN only, no exact open amount left) is booked against an income
    # account instead of the unclear proposal; the diff names the counter account.
    current = _decisions(client, h, t2)[-1]
    best_index = max(
        range(len(current["proposals"])), key=lambda i: current["proposals"][i]["confidence"]
    )
    modified = _ok(
        client.post(
            f"{B}/transactions/{t2}/book",
            json={
                "settlements": [],
                "counter_account_id": w["income"],
                "proposal_id": current["id"],
            },
            headers=h,
        ),
        201,
    )
    rows = _decisions(client, h, t2)
    assert rows[-1]["status"] == "modified"
    assert rows[-1]["chosen_index"] == best_index
    assert rows[-1]["journal_entry_id"] == modified["journal_entry_id"]
    assert rows[-1]["diff"]["counter_account_number"] == {"proposed": None, "final": "060100"}
    assert rows[-1]["final"]["counter_account_number"] == "060100"

    # Reversal with reason code: the accounting side records the code, the bank side learns
    # it through the watermark consumer (counter example, transaction open again).
    reversal = _ok(
        client.post(
            f"{A}/ledgers/{w['ledger']}/entries/{booked['journal_entry_id']}/reverse",
            json={"reason": "Falscher Posten gewählt", "reason_code": "wrong_assignment"},
            headers=h,
        ),
        201,
    )
    assert reversal["reversal_reason_code"] == "wrong_assignment"
    reversed_events = _events(client, h, "journal_entry.reversed")
    assert reversed_events[0]["payload"]["reason_code"] == "wrong_assignment"
    assert reversed_events[0]["payload"]["bank_transaction_id"] == t1
    bad_code = client.post(
        f"{A}/ledgers/{w['ledger']}/entries/{modified['journal_entry_id']}/reverse",
        json={"reason": "Test", "reason_code": "steuerlich"},
        headers=h,
    )
    assert bad_code.status_code == 422
    consumed = asyncio.run(process_events_once(settings, now=_later()))
    assert consumed["failed"] == 0
    assert consumed["handled"] >= 1
    rows = _decisions(client, h, t1)
    statuses = [r["status"] for r in rows]
    assert "reversed" in statuses
    counter = next(r for r in rows if r["status"] == "reversed")
    assert counter["supersedes_id"] == done["id"]
    assert counter["journal_entry_id"] == reversal["id"]
    assert counter["reason"].startswith("wrong_assignment:")
    assert rows[-1]["status"] == "pending"  # bookable again, fresh snapshot
    listed = {t["id"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    assert listed[t1]["status"] == "new"
    assert listed[t1]["journal_entry_id"] == booked["journal_entry_id"]  # history stays
    posted_reversed = _events(client, h, "bank_transaction.posting_reversed")
    assert posted_reversed[0]["entity_id"] == t1
    assert posted_reversed[0]["payload"]["reason_code"] == "wrong_assignment"
    assert posted_reversed[0]["payload"]["decision_ids"] == [counter["id"]]
    # Idempotent: a third run neither repeats the counter example nor reopens anything.
    asyncio.run(process_events_once(settings, now=_later()))
    assert [r["status"] for r in _decisions(client, h, t1)].count("reversed") == 1
    # Correction: the transaction is booked again (Storno plus Neubuchung, B03).
    rebooked = _ok(
        client.post(
            f"{B}/transactions/{t1}/book",
            json={"settlements": [], "counter_account_id": w["income"]},
            headers=h,
        ),
        201,
    )
    assert rebooked["journal_entry_id"] != booked["journal_entry_id"]
    rows = _decisions(client, h, t1)
    assert rows[-1]["status"] == "modified"
    assert rows[-1]["journal_entry_id"] == rebooked["journal_entry_id"]
    assert _ok(client.get(f"{A}/ledgers/{w['ledger']}/checks", headers=h))["ok"] is True

    # Closed rows are immutable and never deleted (DB guard, B03), pending rows stay pending.
    still_pending = _decisions(client, h, t3)[-1]
    assert still_pending["status"] == "pending"
    _assert_guard(database, world.tenant_a, done["id"], still_pending["id"])

    # Tenant separation: the other tenant sees nothing and keeps its own switch off.
    other = bearer(login(client, world, "bkother", tenant_id=world.tenant_b))
    assert client.get(f"{B}/transactions/{t1}/decisions", headers=other).status_code == 404
    assert (
        client.post(
            f"{B}/transactions/{t1}/reject", json={"reason": "fremd"}, headers=other
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{B}/learning", headers=other))["enabled"] is False

    # Legal entity separation: a second HOA with its own ledger and an approved rule; the
    # rule never appears in the proposals of the first HOA, and the tax advisor scoped to the
    # second HOA cannot read the decisions of the first (404, never 403).
    w2 = _hoa(client, h, "802", BANK2)
    rule = _ok(
        client.post(
            f"{B}/rules",
            json={
                "name": "Hausgeld 802",
                "legal_entity_id": w2["hoa"],
                "purpose_regex": "Hausgeld",
                "account_id": w2["income"],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=acc))
    third = _import(
        client,
        h,
        "L-2",
        BANK,
        [_ntry("T5", "250.00", "CRDT", "2026-01-08", STRANGER, "Hausgeld ohne Nummer")],
    )
    t5 = third["txs"]["T5"]["id"]
    snapshot = _decisions(client, h, t5)[-1]
    assert snapshot["legal_entity_id"] == w["hoa"]
    assert all(p.get("rule_id") != rule["id"] for p in snapshot["proposals"])
    assert rule["id"] not in snapshot["features"]["rule_ids"]
    fourth = _import(
        client,
        h,
        "L-3",
        BANK2,
        [_ntry("T6", "250.00", "CRDT", "2026-01-08", STRANGER, "Hausgeld ohne Nummer")],
    )
    t6 = fourth["txs"]["T6"]["id"]
    snapshot2 = _decisions(client, h, t6)[-1]
    assert snapshot2["legal_entity_id"] == w2["hoa"]
    assert rule["id"] in snapshot2["features"]["rule_ids"]
    assert any(p.get("rule_id") == rule["id"] for p in snapshot2["proposals"])
    tax = bearer(login(client, world, "bktax"))
    assert client.get(f"{B}/transactions/{t5}/decisions", headers=tax).status_code == 404
    assign_ledger_scope(client, h, world.users["bktax"], w2["ledger"])
    tax = bearer(login(client, world, "bktax"))
    assert client.get(f"{B}/transactions/{t5}/decisions", headers=tax).status_code == 404
    assert (
        _ok(client.get(f"{B}/transactions/{t6}/decisions", headers=tax))[-1]["id"]
        == snapshot2["id"]
    )

    # Rule lifecycle events (S0): proposed, approved, disabled.
    proposed = _events(client, h, "bank_rule.proposed")
    assert proposed[0]["entity_id"] == rule["id"]
    assert proposed[0]["payload"]["origin"] == "manual"
    approved = _events(client, h, "bank_rule.approved")
    assert approved[0]["entity_id"] == rule["id"]
    assert approved[0]["payload"]["approval_state"] == "approved"
    _ok(client.post(f"{B}/rules/{rule['id']}/disable", headers=h))
    disabled = _events(client, h, "bank_rule.disabled")
    assert disabled[0]["payload"] == {
        "approval_state": "disabled",
        "legal_entity_id": w2["hoa"],
        "before": "approved",
    }

    # Bulk confirmation is recorded with the bulk marker (lower evidence weight).
    bulk = _ok(
        bulk_book(
            client,
            h,
            {
                "preview": False,
                "items": [
                    {"transaction_id": t5, "settlements": [], "counter_account_id": w["income"]}
                ],
            },
        )
    )
    assert bulk["results"][0]["ok"] is True
    assert _decisions(client, h, t5)[-1]["bulk"] is True

    # Switching off stops writing and gates the read; existing rows stay stored and are
    # visible again once switched on.
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Test Ende"}, headers=h))
    fifth = _import(
        client, h, "L-4", BANK, [_ntry("T7", "10.00", "CRDT", "2026-01-09", STRANGER, "Rest")]
    )
    assert _decisions(client, h, fifth["txs"]["T7"]["id"]) == []
    assert _decisions(client, h, t1) == []
    _ok(client.put(f"{B}/learning", json={"enabled": True, "reason": "Nachweis"}, headers=h))
    assert len(_decisions(client, h, t1)) >= 4
    assert _decisions(client, h, fifth["txs"]["T7"]["id"]) == []
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Test Ende"}, headers=h))


def _assert_guard(
    database: Database, tenant_id: uuid.UUID, closed_id: str, pending_id: str
) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(database.app_url)
    try:
        for statement in (
            "UPDATE posting_decision SET reason = 'geändert' WHERE id = :id",
            "UPDATE posting_decision SET proposals = '[]'::jsonb WHERE id = :id",
            "DELETE FROM posting_decision WHERE id = :id",
        ):
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
                )
                with pytest.raises(Exception, match="posting decision"):
                    conn.execute(text(statement), {"id": closed_id})
        for statement, message in (
            ("UPDATE posting_decision SET reason = 'x' WHERE id = :id", "stays pending"),
            (
                "UPDATE posting_decision SET status = 'rejected', proposals = '[]'::jsonb "
                "WHERE id = :id",
                "snapshot is immutable",
            ),
        ):
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
                )
                with pytest.raises(Exception, match=message):
                    conn.execute(text(statement), {"id": pending_id})
    finally:
        engine.dispose()


def test_snapshot_job_against_manual_booking(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """The import job and a person work on the same transactions at the same time: at most
    one pending row per transaction, a booked transaction never keeps a pending row, and the
    booking is recorded once. Nothing is posted twice (B02, B08)."""
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "bkadmin"))
    _ok(client.put(f"{B}/learning", json={"enabled": True, "reason": "Nebenläufigkeit"}, headers=h))
    w = _hoa(client, h, "803", "DE02300209000106531065")
    n1 = w["contracts"][0]["number"]
    entries = [
        _ntry(f"C{i}", "1.00", "CRDT", "2026-01-10", STRANGER, f"Teil {i} {n1}")
        for i in range(1, 25)
    ]
    imported = _import(client, h, "L-C", w["iban"], entries)
    run_id = uuid.UUID(imported["run"]["id"])
    ids = [imported["txs"][f"C{i}"]["id"] for i in range(1, 25)]
    # The inline hook already snapshotted this run; expire all rows by changing the facts so
    # the job below has real work while the person books.
    _receivable(
        client,
        h,
        w["ledger"],
        w["debtors"][w["contracts"][0]["unit_id"]],
        w["income"],
        w["contracts"][0]["id"],
        amount="24.00",
        text_="Nachzahlung",
    )
    results: dict[str, Any] = {}
    barrier = threading.Barrier(2)

    def job() -> None:
        barrier.wait()
        results["job"] = asyncio.run(compute_proposals_once(settings, world.tenant_a, run_id))

    def person() -> None:
        barrier.wait()
        booked = []
        for tx_id in ids:
            response = client.post(
                f"{B}/transactions/{tx_id}/book",
                json={"settlements": [], "counter_account_id": w["income"]},
                headers=h,
            )
            booked.append(response.status_code)
        results["person"] = booked

    threads = [threading.Thread(target=job), threading.Thread(target=person)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert results["person"] == [201] * len(ids)
    assert results["job"]["checked"] <= len(ids)
    for tx_id in ids:
        rows = _decisions(client, h, tx_id)
        assert sum(r["status"] == "pending" for r in rows) == 0, rows
        closed = [r for r in rows if r["status"] in ("modified", "accepted_unchanged")]
        assert len(closed) == 1, rows
        assert closed[0]["journal_entry_id"] is not None
    listed = {t["id"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    assert all(listed[tx_id]["status"] == "booked" for tx_id in ids)
    assert _ok(client.get(f"{A}/ledgers/{w['ledger']}/checks", headers=h))["ok"] is True
    _ok(client.put(f"{B}/learning", json={"enabled": False, "reason": "Test Ende"}, headers=h))
