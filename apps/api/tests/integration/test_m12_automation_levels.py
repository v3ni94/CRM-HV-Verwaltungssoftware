"""Learning bookkeeper, steps S4 to S6 (ADR 0014 addendum, rules M12-05 and M12-06): case
classes and levels with a second person's release, one click acceptance at L1, the runner of
L2 with verifier, fingerprint, review queue and correction by reversal, learned rule
proposals with threshold, contradiction and narrowing, tenant and legal entity separation,
403 without the rights. Fixed expected values (rule 0.1.8); nothing here opens a gate: the
runner posts in the non leading ledger only (operator decision M12-07)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.banking.models import AutoPostingReview, PostingDecision
from mhvp.banking.tasks import levels_refresh_once, process_events_once
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.platform.models import TenantSettings
from tests.integration.af01_switch import seed_auto_posting
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m11_banking import _ntry, _upload
from tests.integration.test_m12_posting_decisions import (
    PAYERS,
    STRANGER,
    _decisions,
    _events,
    _hoa,
    _import,
    _ok,
    _receivable,
    _settings,
)

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
A = "/api/v1/accounting"
BANK_A = "DE02500105170137075030"
BANK_B = "DE02100500000024290661"
BANK_C = "DE02200505501015871393"
BANK_D = "DE02120300000000202051"
OTHER_PAYER = "DE02300606010002474689"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lvl-{RUN}", name=f"Stufen {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lvo-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("lvadmin", a, "tenant_admin"),
            ("lvsecond", a, "tenant_admin"),
            ("lvacc", a, "accountant_no_banking"),
            ("lvcare", a, "caretaker"),
            ("lvother", b, "tenant_admin"),
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


def _db(settings: Any, tenant_id: uuid.UUID, fn: Callable[[Any], Awaitable[Any]]) -> Any:
    """Runs ``fn`` in a tenant transaction (test seed and inspection only)."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> Any:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _set_level(settings: Any, tenant_id: uuid.UUID, case_kind: str, level: str) -> None:
    """Simulates an approved level request (the four eyes path is tested separately)."""

    async def fn(session: Any) -> None:
        row = await session.scalar(select(TenantSettings).with_for_update())
        row.bookkeeping_automation = {**(row.bookkeeping_automation or {}), case_kind: level}

    _db(settings, tenant_id, fn)


def _seed_decisions(
    settings: Any,
    tenant_id: uuid.UUID,
    tx_id: str,
    legal_entity_id: str,
    *,
    unchanged: int,
    modified: int,
) -> None:
    """Closed decisions of a person as ground truth for the eligibility figures."""

    async def fn(session: Any) -> None:
        last = await session.scalar(
            select(PostingDecision.round)
            .where(PostingDecision.bank_transaction_id == uuid.UUID(tx_id))
            .order_by(PostingDecision.round.desc())
            .limit(1)
        )
        round_no = int(last or 0)
        statuses = ["accepted_unchanged"] * unchanged + ["modified"] * modified
        for status in statuses:
            round_no += 1
            session.add(
                PostingDecision(
                    tenant_id=tenant_id,
                    bank_transaction_id=uuid.UUID(tx_id),
                    legal_entity_id=uuid.UUID(legal_entity_id),
                    round=round_no,
                    status=status,
                    engine_version="seed",
                    rule_version="seed",
                    features_hash="0" * 64,
                    features={"amount": "250.00", "direction": "credit"},
                    proposals=[
                        {"source": "match", "kind": "full", "unambiguous": True, "confidence": 0.85}
                    ],
                    case_kind="full",
                    level="L0",
                    decided_by=uuid.uuid4(),
                    decided_at=datetime.now(UTC),
                    final={},
                    diff={} if status == "accepted_unchanged" else {"counter_account_number": {}},
                )
            )
        await session.flush()

    _db(settings, tenant_id, fn)


def _active_rule(
    client: TestClient, h: dict[str, str], second: dict[str, str], hoa: str, **match: Any
) -> str:
    rule = _ok(
        client.post(
            f"{B}/rules",
            json={"name": "Hausgeld Automatik", "legal_entity_id": hoa, **match},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=second))
    evidence = _upload(client, h, "nachweis.xml", b"<nachweis>Testsatz D51</nachweis>")
    _ok(
        client.post(
            f"{B}/rules/{rule['id']}/activate",
            json={"max_amount": "500", "test_evidence_document_id": evidence},
            headers=second,
        )
    )
    return str(rule["id"])


def _switch_on(client: TestClient, h: dict[str, str]) -> None:
    _ok(client.put(f"{B}/learning", json={"enabled": True, "reason": "Test S4 bis S6"}, headers=h))
    seed_auto_posting(client, h)


def test_levels_requests_four_eyes_and_one_click(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lvadmin"))
    second = bearer(login(client, world, "lvsecond"))
    care = bearer(login(client, world, "lvcare"))
    other = bearer(login(client, world, "lvother"))
    _switch_on(client, h)
    w = _hoa(client, h, "821", BANK_A)
    n1 = w["contracts"][0]["number"]

    state = _ok(client.get(f"{B}/automation/levels", headers=h))
    assert state["levels"] == dict.fromkeys(
        [
            "debtor_full",
            "debtor_collective",
            "creditor_invoice",
            "recurring_expense",
            "transfer_pair",
            "excluded",
        ],
        "L0",
    )
    assert state["caps"]["debtor_collective"] == "L1"
    assert state["caps"]["excluded"] == "L0"
    assert client.get(f"{B}/automation/levels", headers=care).status_code == 403

    # One click at L0 is refused; the full dialog stays the way (409 MHVP-BANK-0023).
    imported = _import(
        client,
        h,
        "V-0",
        BANK_A,
        [_ntry("V0", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}")],
    )
    t0 = imported["txs"]["V0"]["id"]
    refused = client.post(f"{B}/transactions/{t0}/accept", json={}, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-BANK-0023"

    # Not eligible: 409 MHVP-BANK-0022 with the missing figures; nothing is stored.
    body = {"case_kind": "debtor_full", "level_to": "L1", "reason": "Test Eignung"}
    early = client.post(f"{B}/automation/level-requests", json=body, headers=h)
    assert early.status_code == 409
    assert early.json()["code"] == "MHVP-BANK-0022"
    assert "n_decided" in early.json()["detail"]
    assert _ok(client.get(f"{B}/automation/levels", headers=h))["requests"] == []

    # Eligible after twenty decisions with one modification (precision 0,95).
    _seed_decisions(settings, world.tenant_a, t0, w["hoa"], unchanged=19, modified=1)
    metrics = _ok(client.get(f"{B}/automation/metrics", headers=h))
    row = next(
        c
        for c in metrics["classes"]
        if c["case_kind"] == "debtor_full" and c["legal_entity_id"] is None
    )
    assert row["n_decided"] == 20
    assert row["precision_manual"] == "0.9500"
    per_entity = next(
        c
        for c in metrics["classes"]
        if c["case_kind"] == "debtor_full" and c["legal_entity_id"] == w["hoa"]
    )
    assert per_entity["n_decided"] == 20
    assert client.post(f"{B}/automation/level-requests", json=body, headers=care).status_code == 403
    request = _ok(client.post(f"{B}/automation/level-requests", json=body, headers=h), 201)
    assert request["status"] == "requested"
    assert request["evidence"]["eligibility"]["n_decided"] == 20
    duplicate = client.post(f"{B}/automation/level-requests", json=body, headers=h)
    assert duplicate.status_code == 409

    # Four eyes: the requester may not approve; another tenant does not see the request.
    own = client.post(f"{B}/automation/level-requests/{request['id']}/approve", json={}, headers=h)
    assert own.status_code == 403
    assert own.json()["code"] == "MHVP-GATE-0002"
    assert (
        client.post(
            f"{B}/automation/level-requests/{request['id']}/approve", json={}, headers=other
        ).status_code
        == 404
    )
    approved = _ok(
        client.post(
            f"{B}/automation/level-requests/{request['id']}/approve",
            json={"comment": "Eignung geprüft"},
            headers=second,
        )
    )
    assert approved["status"] == "approved"
    assert approved["decided_by"] == str(world.users["lvsecond"])
    levels_now = _ok(client.get(f"{B}/automation/levels", headers=h))["levels"]
    assert levels_now["debtor_full"] == "L1"
    changed = _events(client, h, "bookkeeping_level.changed")
    assert changed[0]["payload"] == {
        "case_kind": "debtor_full",
        "level_from": "L0",
        "level_to": "L1",
        "reason": f"Antrag {request['id']} freigegeben",
        "request_id": request["id"],
        "automatic": False,
    }
    assert _ok(client.get("/api/v1/tenant/settings", headers=h))["bookkeeping_automation"] == {
        "debtor_full": "L1"
    }

    # One click at L1: exactly the verified proposal is booked as a manual posting of the
    # person; the decision round closes as accepted_unchanged.
    shown = _ok(client.get(f"{B}/transactions/{t0}/posting-proposals", headers=h))
    accepted = _ok(
        client.post(
            f"{B}/transactions/{t0}/accept",
            json={"proposal_id": shown["learning"]["decision_id"]},
            headers=h,
        ),
        201,
    )
    assert accepted["case_kind"] == "debtor_full"
    assert accepted["level"] == "L1"
    last = next(
        r
        for r in _decisions(client, h, t0)
        if r["journal_entry_id"] == accepted["journal_entry_id"]
    )
    assert last["status"] == "accepted_unchanged"
    assert last["diff"] == {}
    assert last["decided_by"] == str(world.users["lvadmin"])
    assert last["journal_entry_id"] == accepted["journal_entry_id"]
    entry = _ok(
        client.get(f"{A}/ledgers/{w['ledger']}/entries/{accepted['journal_entry_id']}", headers=h)
    )
    assert entry["created_by"] == str(world.users["lvadmin"])
    assert client.post(f"{B}/transactions/{t0}/accept", json={}, headers=h).status_code == 409

    # Lowering is immediate, one person; raising two steps at once is refused.
    lowered = _ok(
        client.put(
            f"{B}/automation/levels",
            json={"case_kind": "debtor_full", "level": "L0", "reason": "Test Absenkung"},
            headers=h,
        )
    )
    assert lowered["debtor_full"] == "L0"
    two_steps = client.post(
        f"{B}/automation/level-requests",
        json={"case_kind": "debtor_full", "level_to": "L2", "reason": "Zwei Stufen"},
        headers=h,
    )
    assert two_steps.status_code == 409
    assert "Nur eine Stufe je Antrag" in two_steps.json()["detail"]

    # The outgoing switch needs tenant_settings:update in addition to accounting:approve.
    acc = bearer(login(client, world, "lvacc"))
    switch = {"enabled": True, "reason": "Test L2b"}
    assert client.put(f"{B}/automation/outgoing", json=switch, headers=acc).status_code == 403
    assert _ok(client.put(f"{B}/automation/outgoing", json=switch, headers=h)) == {"enabled": True}
    assert (
        _ok(client.get(f"{B}/automation/levels", headers=h))["auto_posting_outgoing_enabled"]
        is True
    )
    _ok(
        client.put(
            f"{B}/automation/outgoing", json={"enabled": False, "reason": "zurück"}, headers=h
        )
    )


def test_runner_debtor_full_verifier_review_and_correction(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lvadmin"))
    second = bearer(login(client, world, "lvsecond"))
    care = bearer(login(client, world, "lvcare"))
    other = bearer(login(client, world, "lvother"))
    _switch_on(client, h)
    asyncio.run(process_events_once(settings))  # positions the consumer watermark
    w = _hoa(client, h, "822", BANK_B)
    n1, n2 = w["contracts"][0]["number"], w["contracts"][1]["number"]
    rule_id = _active_rule(client, h, second, w["hoa"], purpose_regex="Hausgeld")

    # Without level L2 the runner books nothing, even with an active rule and automation on.
    first = _import(
        client,
        h,
        "R-1",
        BANK_B,
        [_ntry("R1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}")],
    )
    t1 = first["txs"]["R1"]["id"]
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0
    assert _decisions(client, h, t1)[-1]["status"] == "pending"

    # L2 (simulated approval): the runner books T1 with fingerprint, review item and event.
    _set_level(settings, world.tenant_a, "debtor_full", "L2")
    run = _ok(client.post(f"{B}/auto-post", headers=h))
    assert run["posted"] == 1
    assert run["auto_checked"] == 1
    done = _decisions(client, h, t1)[-1]
    assert done["status"] == "auto_posted"
    assert done["level"] == "L2"
    assert done["decided_by"] is None
    assert len(done["verifier_fingerprint"]) == 64
    assert done["review_due_on"] is not None
    assert done["final"]["settlements"][0]["amount"] == "250.00"
    posted = _events(client, h, "bank_transaction.auto_posted")
    mine = next(e for e in posted if e["entity_id"] == t1)
    assert mine["payload"]["rule_id"] == rule_id
    assert mine["payload"]["verifier_fingerprint"] == done["verifier_fingerprint"]
    assert mine["payload"]["review_kind"] == "daily"
    # AF01 (GAB-08): the shared booking path also emits bank_transaction.booked.
    booked = [e for e in _events(client, h, "bank_transaction.booked") if e["entity_id"] == t1]
    assert [e["payload"]["origin"] for e in booked] == ["auto"]
    assert booked[0]["payload"]["journal_entry_id"] == mine["payload"]["journal_entry_id"]
    reviews = _ok(client.get(f"{B}/auto-posting/reviews", headers=h))
    item = next(r for r in reviews if r["bank_transaction_id"] == t1)
    assert item["status"] == "open"
    assert item["overdue"] is False
    assert item["case_kind"] == "debtor_full"
    assert client.get(f"{B}/auto-posting/reviews", headers=other).json() == []
    tx_row = next(t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["id"] == t1)
    assert tx_row["status"] == "booked"
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # no second effect

    # Verifier refusal: the second owner has January open and pays February only. The
    # amount points at February, the chronology check refuses; the transaction stays open.
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
    second_import = _import(
        client,
        h,
        "R-2",
        BANK_B,
        [_ntry("R2", "100.00", "CRDT", "2026-02-05", PAYERS[1], f"Hausgeld {n2}")],
    )
    t2 = second_import["txs"]["R2"]["id"]
    run = _ok(client.post(f"{B}/auto-post", headers=h))
    assert run["posted"] == 0
    assert run["auto_refused"] == 1
    assert _decisions(client, h, t2)[-1]["status"] == "pending"

    # Overdue review blocks the class: nothing is booked until a person closed the item.
    def overdue(session: Any) -> Any:
        return _overdue(session, item["id"])

    _db(settings, world.tenant_a, overdue)
    third = _import(
        client,
        h,
        "R-3",
        BANK_B,
        [_ntry("R3", "250.00", "CRDT", "2026-02-06", PAYERS[1], f"Hausgeld {n2}")],
    )
    t3 = third["txs"]["R3"]["id"]
    run = _ok(client.post(f"{B}/auto-post", headers=h))
    assert run["posted"] == 0
    assert run["auto_blocked"] >= 1
    assert _ok(client.get(f"{B}/automation/levels", headers=h))["blocked"] == {"debtor_full": 1}
    decision = {"outcome": "ok", "note": "geprüft"}
    assert (
        client.post(
            f"{B}/auto-posting/reviews/{item['id']}", json=decision, headers=care
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{B}/auto-posting/reviews/{item['id']}", json=decision, headers=other
        ).status_code
        == 404
    )
    closed = _ok(client.post(f"{B}/auto-posting/reviews/{item['id']}", json=decision, headers=h))
    assert closed["status"] == "ok"
    assert closed["reviewed_by"] == str(world.users["lvadmin"])
    assert (
        client.post(f"{B}/auto-posting/reviews/{item['id']}", json=decision, headers=h).status_code
        == 409
    )
    # T3 now books (January of owner 2 is still open, so T3 is refused; settle it first).
    _ok(
        client.post(
            f"{B}/transactions/{t2}/book",
            json={
                "settlements": [
                    {
                        "open_item_id": _open_item(client, h, w["ledger"], "100.00"),
                        "amount": "100.00",
                    }
                ]
            },
            headers=h,
        ),
        201,
    )
    run = _ok(client.post(f"{B}/auto-post", headers=h))
    assert run["auto_blocked"] == 0

    # Korrigieren (B03): reversal with reason code plus new posting in one call; the auto
    # posted T1 is corrected against a counter account, the review item is corrected, the
    # consumer writes the counter example and lowers the rule (automation_error).
    corrected = _ok(
        client.post(
            f"{B}/transactions/{t1}/correct",
            json={
                "reason": "Automatik hat den falschen Posten getroffen",
                "reason_code": "automation_error",
                "settlements": [],
                "counter_account_id": w["income"],
            },
            headers=h,
        ),
        201,
    )
    assert corrected["reversal_id"] != corrected["journal_entry_id"]
    reversal = _ok(
        client.get(f"{A}/ledgers/{w['ledger']}/entries/{corrected['reversal_id']}", headers=h)
    )
    assert reversal["kind"] == "reversal"
    assert reversal["reversal_reason_code"] == "automation_error"
    original = _ok(
        client.get(f"{A}/ledgers/{w['ledger']}/entries/{done['journal_entry_id']}", headers=h)
    )
    assert original["reversed_by_id"] == corrected["reversal_id"]
    rows = _decisions(client, h, t1)
    assert rows[-1]["status"] == "modified" or rows[-1]["status"] == "accepted_unchanged"
    assert rows[-1]["decided_by"] == str(world.users["lvadmin"])
    assert rows[-1]["journal_entry_id"] == corrected["journal_entry_id"]
    corrected_events = _events(client, h, "bank_transaction.corrected")
    assert corrected_events[0]["entity_id"] == t1
    assert corrected_events[0]["payload"]["reason_code"] == "automation_error"
    rebooked = [e for e in _events(client, h, "bank_transaction.booked") if e["entity_id"] == t1]
    assert sorted(e["payload"]["origin"] for e in rebooked) == ["auto", "review_correction"]
    processed = asyncio.run(
        process_events_once(settings, now=datetime.now(UTC) + timedelta(seconds=30))
    )
    assert processed["failed"] == 0
    statuses = [r["status"] for r in _decisions(client, h, t1)]
    assert "reversed" in statuses
    rule = next(r for r in _ok(client.get(f"{B}/rules", headers=h)) if r["id"] == rule_id)
    assert rule["approval_state"] == "approved"
    assert rule["contradiction_count"] == 1
    downgraded = _events(client, h, "bank_rule.downgraded")
    assert downgraded[0]["payload"] == {
        "before": "active",
        "after": "approved",
        "reason_code": "automation_error",
        "contradictions": 1,
    }
    assert _ok(client.get(f"{B}/auto-posting/reviews", headers=h)) == [
        r
        for r in _ok(client.get(f"{B}/auto-posting/reviews", headers=h))
        if r["bank_transaction_id"] != t1
    ]
    # The Prüfexport carries the automation tables (rows exist for the legal entity).
    export = _ok(
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": w["ledger"], "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=h,
        ),
        201,
    )
    assert export["id"]
    # Nightly job: only downgrades; the class figures here give no reason to lower.
    refreshed = asyncio.run(levels_refresh_once(settings, today=date(2026, 9, 29)))
    assert refreshed["tenants"] >= 1
    _ok(
        client.put(
            f"{B}/automation/levels",
            json={"case_kind": "debtor_full", "level": "L0", "reason": "Ende"},
            headers=h,
        )
    )
    assert t3


async def _overdue(session: Any, item_id: str) -> None:
    row = await session.get(AutoPostingReview, uuid.UUID(item_id), with_for_update=True)
    row.due_on = datetime.now(UTC).date() - timedelta(days=3)


def _open_item(client: TestClient, h: dict[str, str], ledger: str, remaining: str) -> str:
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
    )
    return str(next(i["id"] for i in items if i["remaining"] == remaining))


def test_rule_proposals_threshold_contradiction_and_four_eyes(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lvadmin"))
    second = bearer(login(client, world, "lvsecond"))
    care = bearer(login(client, world, "lvcare"))
    other = bearer(login(client, world, "lvother"))
    _switch_on(client, h)
    w = _hoa(client, h, "823", BANK_C)
    assert settings

    def book(ref: str, day: str, payer: str, amount: str, account: str) -> str:
        imported = _import(
            client,
            h,
            f"P-{ref}",
            BANK_C,
            [_ntry(ref, amount, "CRDT", day, payer, f"Sonderumlage {ref}")],
        )
        tx_id = imported["txs"][ref]["id"]
        _ok(
            client.post(
                f"{B}/transactions/{tx_id}/book",
                json={"settlements": [], "counter_account_id": account},
                headers=h,
            ),
            201,
        )
        return str(tx_id)

    # Two identical decisions: below the recurring threshold (3), no proposal yet.
    book("S1", "2026-01-10", STRANGER, "80.00", w["income"])
    book("S2", "2026-02-10", STRANGER, "80.00", w["income"])
    assert _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h)) == []
    # Third identical decision (same counterparty, same amount): proposal with evidence.
    book("S3", "2026-03-10", STRANGER, "80.00", w["income"])
    proposals = _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h))
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["recurring"] is True
    assert proposal["threshold"] == 3
    assert proposal["evidence_count"] == "3.0"
    assert proposal["amount_min"] == "80.00"
    assert proposal["amount_max"] == "80.00"
    assert proposal["has_iban_key"] is True
    assert proposal["purpose_tokens"] == ["sonderumlage"]
    assert len(proposal["evidence"]["decision_ids"]) == 3
    assert proposal["legal_entity_id"] == w["hoa"]
    assert client.get(f"{B}/rule-proposals", headers=other).json() == []
    assert client.get(f"{B}/rule-proposals", headers=care).status_code == 403
    created = _events(client, h, "bank_rule_proposal.created")
    assert created[0]["entity_id"] == proposal["id"]

    # Widening is refused (422 MHVP-BANK-0024); narrowing creates the rule as proposed by
    # the accepting person, who may not approve it (four eyes); a second person may.
    widened = client.post(
        f"{B}/rule-proposals/{proposal['id']}/accept",
        json={"amount_max": "500.00"},
        headers=h,
    )
    assert widened.status_code == 422
    assert widened.json()["code"] == "MHVP-BANK-0024"
    assert (
        client.post(
            f"{B}/rule-proposals/{proposal['id']}/accept", json={}, headers=care
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{B}/rule-proposals/{proposal['id']}/accept", json={}, headers=other
        ).status_code
        == 404
    )
    rule = _ok(
        client.post(
            f"{B}/rule-proposals/{proposal['id']}/accept",
            json={"name": "Sonderumlage Zahler X", "purpose_tokens": ["sonderumlage", "umlage"]},
            headers=h,
        ),
        201,
    )
    assert rule["approval_state"] == "proposed"
    assert rule["learned_from_proposal_id"] == proposal["id"]
    assert rule["match"]["purpose_keywords"] == ["sonderumlage", "umlage"]
    assert rule["match"]["amount_min"] == "80.00"
    assert rule["match"]["amount_max"] == "80.00"
    assert rule["match"]["counterpart_iban_fingerprint"]
    assert rule["action"] == {"kind": "posting", "account_id": w["income"]}
    assert rule["created_by"] == str(world.users["lvadmin"])
    assert client.post(f"{B}/rules/{rule['id']}/approve", headers=h).status_code == 403
    approved = _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=second))
    assert approved["approval_state"] == "approved"
    accepted = _ok(client.get(f"{B}/rule-proposals", params={"status": "accepted"}, headers=h))
    assert accepted[0]["rule_id"] == rule["id"]
    # Nothing was booked by the proposal or the rule: every posting above is a manual one.
    booked = _ok(client.get(f"{B}/transactions", params={"status": "booked"}, headers=h))
    assert all(t["journal_entry_id"] for t in booked)
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0

    # Contradiction withdraws: another payer books three times, then against another account.
    book("K1", "2026-01-11", OTHER_PAYER, "45.00", w["income"])
    book("K2", "2026-02-11", OTHER_PAYER, "45.00", w["income"])
    book("K3", "2026-03-11", OTHER_PAYER, "45.00", w["income"])
    open_now = _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h))
    assert len(open_now) == 1
    withdrawn_id = open_now[0]["id"]
    reserve = next(
        a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{w['ledger']}/accounts", headers=h))
        if a["number"] == "060200"
    )
    book("K4", "2026-04-11", OTHER_PAYER, "45.00", reserve)
    assert _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h)) == []
    withdrawn = _ok(client.get(f"{B}/rule-proposals", params={"status": "withdrawn"}, headers=h))
    assert withdrawn[0]["id"] == withdrawn_id
    assert withdrawn[0]["reason"] == "Anderes Konto gewählt"

    # Rejection with reason: proposed again only at twice the evidence.
    book("Z1", "2026-01-12", PAYERS[0], "30.00", w["income"])
    book("Z2", "2026-02-12", PAYERS[0], "30.00", w["income"])
    book("Z3", "2026-03-12", PAYERS[0], "30.00", w["income"])
    z = _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h))
    assert len(z) == 1
    rejected = _ok(
        client.post(
            f"{B}/rule-proposals/{z[0]['id']}/reject",
            json={"reason": "Einmalige Zahlungen"},
            headers=h,
        )
    )
    assert rejected["status"] == "rejected"
    book("Z4", "2026-04-12", PAYERS[0], "30.00", w["income"])
    book("Z5", "2026-05-12", PAYERS[0], "30.00", w["income"])
    assert _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h)) == []
    book("Z6", "2026-06-12", PAYERS[0], "30.00", w["income"])
    again = _ok(client.get(f"{B}/rule-proposals", params={"status": "proposed"}, headers=h))
    assert len(again) == 1
    assert again[0]["evidence_count"] == "6.0"


def test_exclusion_returns_clarification_and_retention(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Completion of the automation (ADR 0014 addendum 2): an automatic posting without
    completed review is excluded from dunning, settlement proposal and direct debit; a
    return opens a review item of kind ``return`` and counts a contradiction; the B05
    clarification row with ticket, list, 403 and tenant separation; the retention run
    anonymises instead of deleting and the guard still forbids every delete."""
    from decimal import Decimal

    from sqlalchemy import delete as sa_delete
    from sqlalchemy import update as sa_update
    from sqlalchemy.exc import DBAPIError

    from mhvp.accounting import direct_debit, dunning, settlement
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import JournalEntry, Ledger
    from mhvp.banking import clarifications, features, review
    from mhvp.banking.models import BankClarification, BankRule, BankTransaction
    from mhvp.banking.tasks import learning_retention_once
    from mhvp.core.problems import ProblemError
    from mhvp.tickets.models import Ticket

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "lvadmin"))
    second = bearer(login(client, world, "lvsecond"))
    care = bearer(login(client, world, "lvcare"))
    other = bearer(login(client, world, "lvother"))
    _switch_on(client, h)
    w = _hoa(client, h, "824", BANK_D)
    n1 = w["contracts"][0]["number"]
    rule_id = _active_rule(client, h, second, w["hoa"], purpose_regex="Hausgeld")
    _set_level(settings, world.tenant_a, "debtor_full", "L2")
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": [{"level": 1, "min_days_overdue": 10, "text": "Zahlungserinnerung"}],
                "threshold_amount": "20.00",
            },
            headers=h,
        )
    )
    _ok(
        client.put(
            f"{A}/direct-debits/creditor-ids/legal-entities/{w['hoa']}",
            json={"sepa_creditor_id": "DE98ZZZ09999999999"},
            headers=h,
        )
    )
    first = _import(
        client,
        h,
        "X-1",
        BANK_D,
        [_ntry("X1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}")],
    )
    t1 = first["txs"]["X1"]["id"]
    # The import's after-commit job already ran the runner at L2 (the manual call is idle).
    _ok(client.post(f"{B}/auto-post", headers=h))
    done = _decisions(client, h, t1)[-1]
    assert done["status"] == "auto_posted"
    entry_id = uuid.UUID(done["journal_entry_id"])
    debtor_account = uuid.UUID(w["debtors"][w["contracts"][0]["unit_id"]])
    # A second receivable of owner 1 (February) stays open and is overdue at the run date.
    _receivable(
        client,
        h,
        w["ledger"],
        w["debtors"][w["contracts"][0]["unit_id"]],
        w["income"],
        w["contracts"][0]["id"],
        amount="300.00",
        text_="Hausgeld Februar",
    )
    ledger_id = uuid.UUID(w["ledger"])

    async def flagged(session: Any) -> bool:
        entry = await session.get(JournalEntry, entry_id)
        return bool(entry.auto_review_pending)

    assert _db(settings, world.tenant_a, flagged) is True

    # (1) Exclusion while the review is open: dunning excludes the debtor with the reason,
    # the settlement proposal refuses with 409, the direct debit selection blocks the item.
    async def dunning_reasons(session: Any) -> dict[str, str]:
        run = await dunning.preview(
            session, tenant_id=world.tenant_a, user_id=None, run_date=date(2026, 3, 20)
        )
        from mhvp.accounting.models import DunningCase

        rows = await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))
        return {str(c.debtor_account_id): f"{c.status}|{c.reason}" for c in rows}

    reasons = _db(settings, world.tenant_a, dunning_reasons)
    assert reasons[str(debtor_account)] == f"excluded|{acc.UNREVIEWED_AUTO_REASON}"

    async def proposal(session: Any) -> str:
        ledger = await session.get(Ledger, ledger_id)
        try:
            await settlement.items_for(session, ledger, debtor_account, date(2026, 3, 20))
        except ProblemError as exc:
            return f"{exc.status} {exc.error.code}"
        return "ok"

    assert _db(settings, world.tenant_a, proposal) == "409 MHVP-BANK-0026"

    async def debit_reasons(session: Any) -> list[str | None]:
        ledger = await session.get(Ledger, ledger_id)
        sel = await direct_debit.select_due(
            session, ledger=ledger, collection_date=date(2026, 3, 20)
        )
        return [c.block_reason for c in sel.candidates]

    # Owner 1 (February, flagged) is blocked with the reason; owner 2 keeps its own reason.
    assert sorted(_db(settings, world.tenant_a, debit_reasons)) == [
        acc.UNREVIEWED_AUTO_REASON,
        "kein SEPA-Mandat der Vertragspartei",
    ]

    # Review closed as ok: the flag is cleared and the runs see the debtor again.
    item = next(
        r
        for r in _ok(client.get(f"{B}/auto-posting/reviews", headers=h))
        if r["bank_transaction_id"] == t1
    )
    assert item["return_transaction_id"] is None
    _ok(client.post(f"{B}/auto-posting/reviews/{item['id']}", json={"outcome": "ok"}, headers=h))
    assert _db(settings, world.tenant_a, flagged) is False
    assert _db(settings, world.tenant_a, proposal) == "ok"
    assert acc.UNREVIEWED_AUTO_REASON not in _db(settings, world.tenant_a, debit_reasons)
    reasons = _db(settings, world.tenant_a, dunning_reasons)
    assert reasons[str(debtor_account)].startswith("excluded|Buchungskreis nicht führend")

    # (2) Return: the bank returns the payment (purpose "Rücklastschrift", opposite amount,
    # same payer) -> review item of kind return on the automatic posting, flag set again,
    # contradiction counted on the rule, event emitted; idempotent on a second run.
    second_import = _import(
        client,
        h,
        "X-2",
        BANK_D,
        [_ntry("X2", "250.00", "DBIT", "2026-01-12", PAYERS[0], f"Rücklastschrift Hausgeld {n1}")],
    )
    t2 = second_import["txs"]["X2"]["id"]

    async def returns(session: Any) -> int:
        rows = await review.register_returns(
            session, tenant_id=world.tenant_a, today=date(2026, 1, 12)
        )
        return len(rows)

    assert len(_events(client, h, "auto_posting_review.return_opened")) == 1

    # The import job registered the return already; a second run is idempotent.
    assert _db(settings, world.tenant_a, returns) == 0
    assert _db(settings, world.tenant_a, flagged) is True
    ret_item = next(
        r
        for r in _ok(client.get(f"{B}/auto-posting/reviews", headers=h))
        if r["bank_transaction_id"] == t1
    )
    assert ret_item["kind"] == "return"
    assert ret_item["return_transaction_id"] == t2
    from mhvp.workspace.services import local_today

    assert ret_item["due_on"] == review.next_working_day(local_today()).isoformat()
    rule = next(r for r in _ok(client.get(f"{B}/rules", headers=h)) if r["id"] == rule_id)
    assert rule["contradiction_count"] == 1
    assert rule["approval_state"] == "active"  # a return lowers nothing by itself (B03)
    opened = _events(client, h, "auto_posting_review.return_opened")
    assert opened[0]["payload"]["return_transaction_id"] == t2
    assert opened[0]["payload"]["rule_id"] == rule_id
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # the return stays L0
    assert _decisions(client, h, t2)[-1]["status"] == "pending"

    # (3) B05 clarification row of the return movement (unposted): ticket, list, 403,
    # tenant separation, decision with reason, verifier evidence and lock warning.
    async def open_clarification(session: Any) -> dict[str, Any]:
        tx = await session.get(BankTransaction, uuid.UUID(t2))
        row, created = await clarifications.ensure_open(
            session, tx, tenant_id=world.tenant_a, reasons=["Unbelegte Bankbewegung"], rule_id=None
        )
        again, created_again = await clarifications.ensure_open(
            session, tx, tenant_id=world.tenant_a, reasons=["x"], rule_id=None
        )
        ticket = await session.get(Ticket, row.ticket_id)
        return {
            "id": str(row.id),
            "created": created,
            "again": created_again and again.id != row.id,
            "ticket_title": ticket.title if ticket else None,
        }

    opened_row = _db(settings, world.tenant_a, open_clarification)
    assert opened_row["created"] is True
    assert opened_row["again"] is False
    assert opened_row["ticket_title"].startswith("Beleg fehlt: Bankbewegung 12.01.2026 -250.00 EUR")
    listed = _ok(client.get(f"{B}/clarifications", params={"ledger_id": w["ledger"]}, headers=h))
    assert [r["id"] for r in listed] == [opened_row["id"]]
    assert listed[0]["status"] == "open"
    assert listed[0]["amount"] == "-250.00"
    assert listed[0]["ticket_id"] is not None
    assert client.get(f"{B}/clarifications", headers=other).json() == []
    assert (
        client.post(
            f"{B}/clarifications/{opened_row['id']}",
            json={"status": "no_document_required", "reason": "Rückläufer"},
            headers=care,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{B}/clarifications/{opened_row['id']}",
            json={"status": "no_document_required", "reason": "x"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{B}/clarifications/{opened_row['id']}",
            json={"status": "no_document_required"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{B}/clarifications/{opened_row['id']}", json={"status": "resolved"}, headers=h
        ).status_code
        == 422
    )
    locked = _ok(
        client.post(f"{A}/ledgers/{w['ledger']}/lock", json={"until": "2026-01-31"}, headers=h)
    )
    assert locked["unclarified_bank_movements"] == 1
    decided = _ok(
        client.post(
            f"{B}/clarifications/{opened_row['id']}",
            json={
                "status": "no_document_required",
                "reason": "Rücklastschrift der Bank, kein Fremdbeleg",
            },
            headers=h,
        )
    )
    assert decided["status"] == "no_document_required"
    assert decided["decided_by"] == str(world.users["lvadmin"])
    assert _ok(client.get(f"{B}/clarifications", headers=h)) == []
    assert [
        r["status"]
        for r in _ok(client.get(f"{B}/clarifications", params={"open_only": "false"}, headers=h))
    ] == ["no_document_required"]
    events = _events(client, h, "bank_clarification.decided")
    assert events[0]["payload"]["after"] == "no_document_required"

    async def evidence(session: Any) -> Any:
        tx = await session.get(BankTransaction, uuid.UUID(t2))
        collected = await features.collect(session, tx)
        return collected.tx["clarification"], collected.summary()["clarification_status"]

    assert _db(settings, world.tenant_a, evidence) == (
        {"status": "no_document_required", "document_id": None, "decided_by_person": True},
        "no_document_required",
    )

    # (4) Retention: a closed decision older than 24 months is anonymised (fingerprint and
    # proposal text gone, outcome kept), a delete is still refused by the guard, a second
    # change of the anonymised row is refused too.
    async def age_decision(session: Any) -> str:
        # A closed row is immutable (created_at included), so an old closed decision is
        # inserted as it would have been written 27 months ago.
        row = PostingDecision(
            tenant_id=world.tenant_a,
            bank_transaction_id=uuid.UUID(t1),
            legal_entity_id=uuid.UUID(w["hoa"]),
            round=99,
            status="accepted_unchanged",
            engine_version="seed",
            rule_version="seed",
            features_hash="1" * 64,
            features={"amount": "250.00", "counterpart_iban_fingerprint": "f" * 64},
            proposals=[
                {
                    "source": "match",
                    "kind": "full",
                    "unambiguous": True,
                    "confidence": 0.85,
                    "splits": [{"open_item_id": "oi", "amount": "250.00"}],
                    "reasoning": ["Vertragsnummer im Verwendungszweck"],
                }
            ],
            case_kind="full",
            level="L0",
            decided_by=world.users["lvadmin"],
            decided_at=datetime(2024, 6, 1, tzinfo=UTC),
            journal_entry_id=entry_id,
            final={"settlements": [{"open_item_id": "oi", "amount": "250.00"}]},
            diff={},
            created_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        session.add(row)
        await session.flush()
        return str(row.id)

    decision_id = _db(settings, world.tenant_a, age_decision)
    report = asyncio.run(learning_retention_once(settings, now=datetime(2026, 9, 29, tzinfo=UTC)))
    assert report["decisions"] >= 1
    assert report["errors"] == []

    async def inspect(session: Any) -> dict[str, Any]:
        row = await session.get(PostingDecision, uuid.UUID(decision_id))
        out = {
            "status": row.status,
            "fingerprint": row.features.get("counterpart_iban_fingerprint"),
            "proposal_keys": sorted(row.proposals[0].keys()) if row.proposals else [],
            "anonymised": row.anonymised_at is not None,
            "entry": row.journal_entry_id == entry_id,
            "final": row.final["settlements"][0]["amount"],
        }
        nested = await session.begin_nested()
        try:
            await session.execute(sa_delete(PostingDecision).where(PostingDecision.id == row.id))
            out["delete"] = "allowed"
        except DBAPIError:
            out["delete"] = "refused"
        await nested.rollback()
        nested = await session.begin_nested()
        try:
            await session.execute(
                sa_update(PostingDecision)
                .where(PostingDecision.id == row.id)
                .values(reason="geändert")
            )
            out["rewrite"] = "allowed"
        except DBAPIError:
            out["rewrite"] = "refused"
        await nested.rollback()
        return out

    state = _db(settings, world.tenant_a, inspect)
    assert state["status"] == "accepted_unchanged"
    assert state["fingerprint"] is None
    assert state["anonymised"] is True
    assert state["entry"] is True
    assert state["final"] == "250.00"
    assert "reasoning" not in state["proposal_keys"]
    assert "splits" in state["proposal_keys"]
    assert state["delete"] == "refused"
    assert state["rewrite"] == "refused"
    assert Decimal(listed[0]["amount"]) == Decimal("-250.00")
    assert isinstance(BankRule, type)
    assert isinstance(BankClarification, type)
    _ok(
        client.put(
            f"{B}/automation/levels",
            json={"case_kind": "debtor_full", "level": "L0", "reason": "Ende"},
            headers=h,
        )
    )
