"""AN20 (GAK-401, GAK-402, rule 0.1.8): second independent tests for the annex D cases D50,
D51, D53, D54, D56 and D58, which were named by one test only or by none (guard in
tests/unit/test_aj19_test_guards.py now covers D01 to D58).

Each test states its expected values by hand in the docstring before the run. Own world
(tenant slug and user names with the prefix ``an20``), other inputs and another path than the
first test of the case. No gate is opened; the productive flags stay off."""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.auth.permissions import READ_ALL
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_annex_d_money import (
    _accounts,
    _bank_account,
    _entry,
    _invoice,
    _ledger_account,
    _provider,
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m25_meeting import _doc, _hoa_with_owners

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
# Synthetic IBANs with a valid check digit (no real data).
RENT_IBAN = "DE02500105170137075030"
DEPOSIT_IBAN_1 = "DE27100777770209299700"
DEPOSIT_IBAN_2 = "DE02120300000000202051"
USERS = (
    ("an20admin", "tenant_admin"),
    ("an20second", "tenant_admin"),
    ("an20acc", "accountant_banking"),
    ("an20approver", "tenant_admin"),
    ("an20reader", "read_only"),
)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"an20-{RUN}", name=f"AN20 Anhang D {RUN}"
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _hoa_property(client: TestClient, h: dict[str, str], number: str) -> tuple[str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AN20 Haus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    return str(prop["id"]), next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")


@pytest.mark.annex_d("D50")
def test_d50_second_reader_and_read_key_cannot_change_money(
    client: TestClient, world: World
) -> None:
    """D50, second path: a ledger with one draft entry of 100,00. The read only role and an
    API key with only read scopes try to book a new entry (POST entries), to post the draft
    (POST .../post), to start a receivable run and to run the automatic bank posting.
    Expected: every call is 403 (code MHVP-AUTH-0003), afterwards the ledger still holds
    exactly 1 entry, still a draft, and the trial balance of both accounts is 0,00 (a draft
    does not move balances). The administrator posts the same draft successfully."""
    h = bearer(login(client, world, "an20admin"))
    reader = bearer(login(client, world, "an20reader"))
    key = _ok(
        client.post(
            "/api/v1/tenant/api-keys",
            json={"name": f"an20-read-{uuid.uuid4().hex[:6]}", "scopes": sorted(READ_ALL)},
            headers=h,
        ),
        201,
    )["key"]
    key_h = {"X-API-Key": key}
    prop, entity = _hoa_property(client, h, "850")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = _accounts(client, h, ledger)
    first, second = sorted(acc)[:2]
    lines = [
        {"account_id": acc[first], "debit": "100.00"},
        {"account_id": acc[second], "credit": "100.00"},
    ]
    body = {"kind": "custom", "booking_date": "2026-03-02", "text": "D50 Entwurf", "lines": lines}
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)

    attempts = [
        ("POST", f"{A}/ledgers/{ledger}/entries", body),
        ("POST", f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", None),
        (
            "POST",
            f"{A}/receivable-runs",
            {"period_month": "2026-03-01", "scope": "property", "scope_id": prop},
        ),
        ("POST", f"{B}/auto-post", None),
    ]
    for label, headers in (("reader", reader), ("read key", key_h)):
        for method, path, payload in attempts:
            response = client.request(method, path, json=payload, headers=headers)
            assert response.status_code == 403, f"{label} {path}: {response.text}"
            assert response.json()["code"] == "MHVP-AUTH-0003", f"{label} {path}"

    entries = _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h))
    assert [(e["id"], e["status"]) for e in entries] == [(draft["id"], "draft")]
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h)
    )
    assert {Decimal(a["balance"]) for a in tb["accounts"]} <= {Decimal("0.00")}
    posted = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    assert posted["status"] == "posted"


@pytest.mark.annex_d("D51")
def test_d51_second_four_eyes_majority_rule_and_disabled_bank_rule(
    client: TestClient, world: World
) -> None:
    """D51, second path: with the four eyes switch on, a majority rule typed in by one person
    stays a draft; the creator cannot release it (refused), a second administrator can.
    A bank posting rule that was proposed, released and then disabled can no longer be
    activated (409, a disabled rule never turns productive by itself) and keeps the state
    ``disabled``. Expected: approval_status draft -> (self release 4xx) -> approved; bank rule
    state proposed -> approved -> disabled, activation after disabling 409."""
    h = bearer(login(client, world, "an20admin"))
    second = bearer(login(client, world, "an20second"))
    _, hoa = _hoa_property(client, h, "851")
    _ok(client.put(f"{H}/majority-rule-four-eyes", json={"enabled": True}, headers=h))
    try:
        rule = _ok(
            client.post(
                f"{H}/majority-rules",
                json={
                    "legal_entity_id": hoa,
                    "label": "Einstimmigkeit nach Annahme",
                    "principle": "head",
                    "unanimous": True,
                    "valid_from": "2026-01-01",
                    "source": "Gemeinschaftsordnung (Testannahme AN20)",
                },
                headers=h,
            ),
            201,
        )
        assert rule["approval_status"] == "draft"
        own = client.post(f"{H}/majority-rules/{rule['id']}/approve", headers=h)
        assert 400 <= own.status_code < 500, own.text
        approved = _ok(client.post(f"{H}/majority-rules/{rule['id']}/approve", headers=second))
        assert approved["approval_status"] == "approved"
        assert approved["approved_by"] != approved["created_by"]
    finally:
        _ok(client.put(f"{H}/majority-rule-four-eyes", json={"enabled": False}, headers=h))

    bank_rule = _ok(
        client.post(
            f"{B}/rules",
            json={"name": "AN20 Regel", "legal_entity_id": hoa, "name_contains": "Umlage"},
            headers=h,
        ),
        201,
    )
    assert bank_rule["approval_state"] == "proposed"
    assert client.post(f"{B}/rules/{bank_rule['id']}/approve", headers=h).status_code == 403
    _ok(client.post(f"{B}/rules/{bank_rule['id']}/approve", headers=second))
    disabled = _ok(client.post(f"{B}/rules/{bank_rule['id']}/disable", headers=h))
    assert disabled["approval_state"] == "disabled"
    evidence = _doc(client, h, "testlauf-an20.pdf")
    again = client.post(
        f"{B}/rules/{bank_rule['id']}/activate",
        json={"max_amount": "100.00", "test_evidence_document_id": evidence},
        headers=second,
    )
    assert again.status_code == 409, again.text
    states = {r["id"]: r["approval_state"] for r in _ok(client.get(f"{B}/rules", headers=h))}
    assert states[bank_rule["id"]] == "disabled"


@pytest.mark.annex_d("D53")
def test_d53_second_foreign_basis_expired_basis_and_wrong_majority(
    client: TestClient, world: World
) -> None:
    """D53, second path, two owners with one vote each (head principle). A basis resolution of
    another community is refused (MHVP-HOA-0004); a basis valid only until 01.08.2026 does
    not carry a meeting on 20.08.2026 (422); with a valid basis (until 30.06.2028) the
    meeting opens. Both owners vote yes: tally 2 : 0, proposal positive. An open technical
    disruption blocks the announcement (409); after the documented resumption the wrong
    outcome negative is refused (409) and positive is recorded (201)."""
    h = bearer(login(client, world, "an20admin"))
    _, hoa, contracts, _ = _hoa_with_owners(client, h, "853")
    _, other_hoa, other_contracts, _ = _hoa_with_owners(client, h, "854")
    _ok(
        client.put(
            f"{H}/meeting-settings",
            json={"invitation_weeks": 3, "virtual_meetings_enabled": True},
            headers=h,
        )
    )

    def circular(entity: str, owners: dict[str, str]) -> str:
        return str(
            _ok(
                client.post(
                    f"{H}/circular-resolutions",
                    json={
                        "legal_entity_id": entity,
                        "subject": "Virtuelle Versammlungen",
                        "wording": "Versammlungen können rein virtuell stattfinden.",
                        "decided_on": "2026-03-01",
                        "evidence_document_id": _doc(client, h, f"umlauf-{entity[:6]}.pdf"),
                        "consents": dict.fromkeys(owners.values(), "yes"),
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    own_basis = circular(hoa, contracts)
    foreign_basis = circular(other_hoa, other_contracts)
    base = {"legal_entity_id": hoa, "scheduled_at": "2026-08-20T18:00:00+02:00", "mode": "virtual"}
    for basis in (
        {"virtual_basis_resolution_id": foreign_basis, "virtual_basis_valid_until": "2028-06-30"},
        {"virtual_basis_resolution_id": own_basis, "virtual_basis_valid_until": "2026-08-01"},
    ):
        refused = client.post(f"{H}/meetings", json=base | basis, headers=h)
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "MHVP-HOA-0004"
    meeting = _ok(
        client.post(
            f"{H}/meetings",
            json=base
            | {"virtual_basis_resolution_id": own_basis, "virtual_basis_valid_until": "2028-06-30"},
            headers=h,
        ),
        201,
    )
    mid = meeting["id"]
    item = _ok(
        client.post(
            f"{H}/meetings/{mid}/agenda",
            json={"title": "Dachsanierung", "proposal": "Die Dachsanierung wird beschlossen."},
            headers=h,
        ),
        201,
    )
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
                json={"contract_id": contracts[no], "choice": "yes"},
                headers=h,
            ),
            201,
        )
    tally = _ok(client.get(f"{H}/agenda/{item['id']}/tally", headers=h))
    assert (tally["yes"], tally["no"], tally["proposal"]) == ("2", "0", "positive")
    disruption = {
        "description": "Tonausfall im Konferenzsystem",
        "occurred_at": "2026-08-20T19:10:00+02:00",
    }
    disrupted = _ok(client.post(f"{H}/meetings/{mid}/disruptions", json=disruption, headers=h), 201)
    assert disrupted["status"] == "disrupted"
    announce = {"outcome": "positive", "majority_basis": "einfache Mehrheit"}
    assert (
        client.post(f"{H}/agenda/{item['id']}/announce", json=announce, headers=h).status_code
        == 409
    )
    resumed = _ok(
        client.post(
            f"{H}/meetings/{mid}/disruptions",
            json={
                "description": "Ton wieder da, Anwesenheit erneut festgestellt",
                "occurred_at": "2026-08-20T19:25:00+02:00",
                "resolved": True,
            },
            headers=h,
        ),
        201,
    )
    assert resumed["status"] == "held"
    wrong = client.post(
        f"{H}/agenda/{item['id']}/announce", json=announce | {"outcome": "negative"}, headers=h
    )
    assert wrong.status_code == 409, wrong.text
    _ok(client.post(f"{H}/agenda/{item['id']}/announce", json=announce, headers=h), 201)
    detail = _ok(client.get(f"{H}/meetings/{mid}", headers=h))
    assert [d["resolved"] for d in detail["disruptions"]] == [False, True]


@pytest.mark.annex_d("D54")
def test_d54_second_contest_and_annulment_delete_nothing(client: TestClient, world: World) -> None:
    """D54, second path without statement: a positive resolution is contested with a court
    note, later annulled. Expected: the resolution stays in the collection each time (count 1,
    same id), the status follows the change (contested, annulled) and the court note is kept;
    there is no delete route (404 or 405); an unknown status is refused (422). The legal state
    and any follow up are never replaced by silent removal."""
    h = bearer(login(client, world, "an20admin"))
    _, hoa = _hoa_property(client, h, "855")
    rid = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2026-06-15",
                "subject": "Fassadenanstrich",
                "wording": "Die Fassade wird gestrichen.",
                "status": "positive",
            },
            headers=h,
        ),
        201,
    )["id"]

    def collection() -> list[dict[str, Any]]:
        return _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))  # type: ignore[no-any-return]

    _ok(
        client.patch(
            f"{H}/resolutions/{rid}",
            json={"status": "contested", "court_notes": "Anfechtungsklage eingegangen"},
            headers=h,
        )
    )
    rows = collection()
    assert [(r["id"], r["status"], r["court_notes"]) for r in rows] == [
        (rid, "contested", "Anfechtungsklage eingegangen")
    ]
    assert client.delete(f"{H}/resolutions/{rid}", headers=h).status_code in (404, 405)
    assert (
        client.patch(f"{H}/resolutions/{rid}", json={"status": "weg"}, headers=h).status_code == 422
    )
    _ok(client.patch(f"{H}/resolutions/{rid}", json={"status": "annulled"}, headers=h))
    rows = collection()
    assert [(r["id"], r["status"], r["court_notes"]) for r in rows] == [
        (rid, "annulled", "Anfechtungsklage eingegangen")
    ]


@pytest.mark.annex_d("D56")
def test_d56_second_two_deposit_accounts_and_cut_off_date(client: TestClient, world: World) -> None:
    """D56, second path. Rent account 3.000,00 booked 02.03.2026; deposit accounts 1.200,00
    and 800,00 booked 10.03.2026 against the deposit liability 070000. Expected liquidity at
    31.03.2026: free funds 3.000,00, segregated deposits 1.200,00 + 800,00 = 2.000,00 (never
    5.000,00); at 05.03.2026 (before the deposits): free 3.000,00, segregated 0,00. An invoice
    of 750,00 cannot be paid from the second deposit account (422, Kautionskonto) but from the
    rent account (order 750,00)."""
    h = bearer(login(client, world, "an20admin"))
    acc_user = bearer(login(client, world, "an20acc"))
    approver = bearer(login(client, world, "an20approver"))
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "856", "name": "Miethaus AN20", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Bestand AN20 {RUN} GmbH"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h),
        201,
    )
    entity = _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": party["id"], "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    rent_bank = _bank_account(client, h, rental["id"], entity, "rent", RENT_IBAN, "Miete")
    dep1 = _bank_account(client, h, rental["id"], entity, "deposit", DEPOSIT_IBAN_1, "Kaution 1")
    dep2 = _bank_account(client, h, rental["id"], entity, "deposit", DEPOSIT_IBAN_2, "Kaution 2")
    assert (rent_bank["segregated"], dep1["segregated"], dep2["segregated"]) == (False, True, True)
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    rent_acc = _ledger_account(
        client, h, ledger, "001210", "Mietkonto", property_bank_account_id=rent_bank["id"]
    )
    dep1_acc = _ledger_account(
        client, h, ledger, "001220", "Kautionskonto 1", property_bank_account_id=dep1["id"]
    )
    dep2_acc = _ledger_account(
        client, h, ledger, "001230", "Kautionskonto 2", property_bank_account_id=dep2["id"]
    )

    def account(number: str, name: str, category: str, kind: str) -> str:
        return str(
            _ok(
                client.post(
                    f"{A}/ledgers/{ledger}/accounts",
                    json={"number": number, "name": name, "category": category, "type": kind},
                    headers=h,
                ),
                201,
            )["id"]
        )

    liability = account("070000", "Kautionsverbindlichkeiten", "technical", "liability")
    revenue = account("080100", "Mieterträge", "revenue", "income")
    _entry(
        client, h, ledger, "2026-03-02", "Mieteingang",
        [{"account_id": rent_acc, "debit": "3000.00"}, {"account_id": revenue, "credit": "3000.00"}],
    )  # fmt: skip
    for day, acc, amount in (
        ("2026-03-10", dep1_acc, "1200.00"),
        ("2026-03-10", dep2_acc, "800.00"),
    ):
        _entry(
            client, h, ledger, day, "Kaution",
            [{"account_id": acc, "debit": amount}, {"account_id": liability, "credit": amount}],
        )  # fmt: skip

    def liquidity(as_of: str) -> dict[str, Any]:
        return _ok(  # type: ignore[no-any-return]
            client.get(f"{A}/ledgers/{ledger}/liquidity", params={"as_of": as_of}, headers=h)
        )

    after = liquidity("2026-03-31")
    assert Decimal(after["free_funds"]) == Decimal("3000.00")
    assert Decimal(after["segregated_deposits"]) == Decimal("2000.00")
    before = liquidity("2026-03-05")
    assert Decimal(before["free_funds"]) == Decimal("3000.00")
    assert Decimal(before["segregated_deposits"]) == Decimal("0.00")

    provider = _provider(client, h, approver, "Dienst AN20")
    cost_account = next(
        a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["category"] == "cost"
    )
    inv = _invoice(client, h, acc_user, ledger, provider, cost_account, "AN20-1", "750.00")
    refused = client.post(
        f"{B}/payment-orders",
        json={
            "invoice_id": inv,
            "property_bank_account_id": dep2["id"],
            "execution_date": "2026-04-05",
        },
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    assert "Kautionskonto" in refused.json()["detail"]
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv,
                "property_bank_account_id": rent_bank["id"],
                "execution_date": "2026-04-05",
            },
            headers=h,
        ),
        201,
    )
    assert order["amount"] == "750.00"


@pytest.mark.annex_d("D58")
def test_d58_second_two_sev_owners_with_vat(client: TestClient, world: World) -> None:
    """D58, second path: four apartments, SEV owner X holds units 01 and 02, SEV owner Y unit
    03, unit 04 belongs to a plain owner; fee 30,00 per apartment with 19 % VAT. Expected by
    hand: community fee (no debtor) 4 x 30,00 = 120,00 net, VAT 22,80, gross 142,80, debtor
    entity kind hoa; fee for X 2 x 30,00 = 60,00, VAT 11,40, gross 71,40, kind sev_owner; fee
    for Y 30,00, VAT 5,70, gross 35,70; every payee is the manager, never a party."""
    h = bearer(login(client, world, "an20admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "858", "name": "SEV-Haus AN20", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    owner_x, _ = _party(client, h, "SEVX")
    owner_y, _ = _party(client, h, "SEVY")
    plain, _ = _party(client, h, "Normal")
    ownership = {
        "kind": "ownership",
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
    }
    units: dict[str, str] = {}
    for number, party, sev in (
        ("01", owner_x, True),
        ("02", owner_x, True),
        ("03", owner_y, True),
        ("04", plain, False),
    ):
        units[number] = _unit(client, h, prop["id"], number)
        contract = _ok(
            client.post(
                "/api/v1/contracts",
                json=ownership
                | {"unit_id": units[number], "party_id": party}
                | ({"sev_enabled": True} if sev else {}),
                headers=h,
            ),
            201,
        )
        assert (contract["sev_fee_debtor_party_id"] == party) is sev

    # The SEV owner's own ledger entity arises with the first tenancy in its SEV unit.
    for number in ("01", "03"):
        tenant, _ = _party(client, h, f"Mieter{number}")
        _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": units[number],
                    "party_id": tenant,
                    "start_date": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )

    fee_body = {
        "property_id": prop["id"],
        "start_date": "2026-01-01",
        "vat_percent": "19",
        "amounts_per_unit_type": {"apartment": "30.00"},
    }

    def preview(extra: dict[str, Any]) -> dict[str, Any]:
        fee = _ok(client.post(f"{A}/admin-fees", json=fee_body | extra, headers=h), 201)
        return _ok(  # type: ignore[no-any-return]
            client.get(f"{A}/admin-fees/{fee['id']}/invoice-preview", headers=h)
        )

    community = preview({})
    assert (community["net"], community["vat"], community["gross"]) == ("120.00", "22.80", "142.80")
    assert community["debtor_legal_entity_kind"] == "hoa"
    assert community["invoice_debtor_party_id"] is None
    x = preview({"invoice_debtor_party_id": owner_x})
    assert (x["net"], x["vat"], x["gross"]) == ("60.00", "11.40", "71.40")
    assert x["lines"] == [
        {"unit_type": "apartment", "count": 2, "rate": "30.00", "amount": "60.00"}
    ]
    assert x["debtor_legal_entity_kind"] == "sev_owner"
    y = preview({"invoice_debtor_party_id": owner_y})
    assert (y["net"], y["vat"], y["gross"]) == ("30.00", "5.70", "35.70")
    assert y["debtor_legal_entity_id"] != x["debtor_legal_entity_id"]
    for draft in (community, x, y):
        assert (draft["payee_role"], draft["payee_party_id"]) == ("manager", None)
