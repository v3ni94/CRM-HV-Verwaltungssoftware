"""Package U13 (M8-07 rest): deposit and loan single items against the opening balance via the
account kind of the chart of accounts, and undo of the SEPA overview (payment schedule, SEPA
mandate) and of the document index (document links). Expected figures are fixed in the
comments (rule 0.1.8); column headers are invented for the test."""

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
from tests.integration.test_m8_import import BASE, BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import A, _prop
from tests.integration.test_q08_import_history import IBAN_FOREIGN, _map, _ok, _run, _setup

pytestmark = pytest.mark.integration
M = "/api/v1/imports/migration"
HISTORY = f"{BASE}/history"
IBAN_DEPOSIT = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u13-{RUN}", name=f"U13 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u13b-{RUN}", name=f"U13b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "u13admin": (a, "tenant_admin"),
            "u13reader": (a, "read_only"),
            "u13other": (b, "tenant_admin"),
        }
        for name, (tenant, role) in specs.items():
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


def _apply(
    c: TestClient,
    h: dict[str, str],
    report: str,
    rows: list[list[Any]],
    columns: dict[str, str],
    name: str,
    **maps: Any,
) -> tuple[str, dict[str, Any]]:
    """Stage, validate and apply; returns the import run id and the apply report."""
    source = _stage(c, h, report, name, _xlsx(rows), XLSX)
    mapping = _map(c, h, report, columns, **maps)
    _ok(
        c.post(
            f"{BASE}/files/{source['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        )
    )
    applied = _ok(c.post(f"{BASE}/files/{source['id']}/apply", headers=h), 201)
    run_id = applied.get("import_run_id") or applied["report"]["import_run_id"]
    return run_id, applied["report"]["apply"]


SEPA_COLS = {
    "property_number": "Objekt",
    "unit_number": "Einheit",
    "contact_external_id": "Kontakt",
    "kind": "Vertragsart",
    "interval": "Intervall",
    "due_day": "Tag",
    "valid_from": "Ab",
    "mandate_reference": "Mandat",
    "creditor_id": "Gläubiger",
    "signed_at": "Unterschrift",
    "iban": "IBAN",
    "evidence_document_id": "Nachweis",
}
SEPA_HEAD = list(SEPA_COLS.values())
SEPA_MAPS = {"kind": {"E": "ownership"}, "interval": {"quartalsweise": "quarterly"}}


def test_deposit_and_loan_against_opening_balance(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "u13admin"))
    other = bearer(login(client, world, "u13other"))
    # Rental property 883: deposits belong to the landlord's segregated account (6.9.1).
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    prop = _prop(client, h, "883", "rental")
    landlord = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Viktor", "last_name": f"Vermieter{RUN}"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": landlord["id"]}]}, headers=h
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": party["id"], "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    entities = _ok(client.get(f"/api/v1/properties/{prop['id']}/legal-entities", headers=h))
    owner = next(e["id"] for e in entities if e["kind"] == "rental_owner")
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={
                "legal_entity_id": owner,
                "template_id": template,
                "migration_cutoff": "2026-01-31",
            },
            headers=h,
        ),
        201,
    )["id"]
    # Items: deposit D1 1.500,00 and D2 200,00 (open 1.700,00), loan L1 10.000,00.
    cols = {
        "property_number": "Objekt",
        "kind": "Art",
        "source_item_id": "Posten",
        "original_amount": "Betrag",
    }
    rows: list[list[Any]] = [
        ["Objekt", "Art", "Posten", "Betrag"],
        ["883", "K", "D1", "1.500,00"],
        ["883", "K", "D2", "200,00"],
        ["883", "D", "L1", "10.000,00"],
    ]
    items = _run(client, h, "open_items", rows, cols, kind={"K": "deposit", "D": "loan"})
    assert items["counts"] == {"created": 3}
    accounts = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    loan = next(a for a in accounts if a["category"] == "loan")
    cash = next(a for a in accounts if a["category"] == "cash")
    check_url = f"{HISTORY}/open-items/balance-check"
    ob_url = f"{M}/ledgers/{ledger}/opening-balances"
    # Step 1: no deposit or loan account with a balance line: both stay not comparable.
    first = {
        "cutoff_date": "2026-01-31",
        "lines": [{"kind": "account", "account_id": cash["id"], "amount": "1.00"}],
    }
    _ok(client.put(ob_url, json=first, headers=h))
    check = _ok(client.get(check_url, params={"ledger_id": ledger}, headers=h))
    assert {n["kind"] for n in check["not_comparable"]} == {"deposit", "loan"}
    assert check["groups"] == []
    # Step 2: segregated deposit bank account with its own bank ledger account (asset, line
    # +1.600,00) and the loan account of the chart (liability, line -10.000,00).
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": owner,
                "kind": "deposit",
                "iban": IBAN_DEPOSIT,
                "holder": "Kautionskonto 881",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    deposit_account = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001290",
                "name": "Kautionskonto",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank["id"],
            },
            headers=h,
        ),
        201,
    )
    second = {
        "cutoff_date": "2026-01-31",
        "lines": [
            {"kind": "account", "account_id": cash["id"], "amount": "1.00"},
            {
                "kind": "bank",
                "account_id": deposit_account["id"],
                "amount": "1600.00",
                "property_bank_account_id": bank["id"],
            },
            {"kind": "account", "account_id": loan["id"], "amount": "-10000.00"},
        ],
    }
    response = client.put(ob_url, json=second, headers=h)
    assert response.status_code == 200, response.text
    check = _ok(client.get(check_url, params={"ledger_id": ledger}, headers=h))
    by_group = {g["group"]: g for g in check["groups"]}
    assert check["not_comparable"] == []
    # Loan: items 10.000,00, balance -10.000,00 * -1 (liability) = 10.000,00 -> match.
    assert (by_group["loan"]["status"], by_group["loan"]["difference"]) == ("match", "0.00")
    assert by_group["loan"]["account_basis"] == "loan_category"
    # Deposit: items 1.700,00, balance +1.600,00 (asset) -> difference 100,00.
    assert by_group["deposit"]["items_open_sum"] == "1700.00"
    assert by_group["deposit"]["balance_sum"] == "1600.00"
    assert (by_group["deposit"]["status"], by_group["deposit"]["difference"]) == (
        "deviation",
        "100.00",
    )
    assert check["all_match"] is False
    assert client.get(check_url, params={"ledger_id": ledger}, headers=other).status_code == 404


def test_undo_sepa_overview_and_document_index(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "u13admin"))
    reader = bearer(login(client, world, "u13reader"))
    other = bearer(login(client, world, "u13other"))
    contract_id = _setup(client, h)["contract"]["id"]
    evidence = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("mandat.pdf", b"%PDF-1.4 mandat u13", "application/pdf")},
            headers=h,
        ),
        201,
    )
    reference = f"U13-{RUN}"[:35]
    run1, report1 = _apply(
        client,
        h,
        "sepa_overview",
        [
            SEPA_HEAD,
            [
                "881",
                "01",
                "K881",
                "E",
                "quartalsweise",
                "5",
                "01.01.2026",
                reference,
                "DE98ZZZ09999999999",
                "02.01.2020",
                IBAN_FOREIGN,
                evidence["id"],
            ],
        ],
        SEPA_COLS,
        "sepa1.xlsx",
        **SEPA_MAPS,
    )
    assert report1["counts"] == {"created": 1}
    run2, report2 = _apply(
        client,
        h,
        "sepa_overview",
        [SEPA_HEAD, ["881", "01", "K881", "E", "quartalsweise", "3", "01.04.2026"] + [None] * 5],
        SEPA_COLS,
        "sepa2.xlsx",
        **SEPA_MAPS,
    )
    assert report2["counts"] == {"created": 1}

    def contract() -> Any:
        return _ok(client.get(f"/api/v1/contracts/{contract_id}", headers=h))

    assert [(s["due_day"], s["valid_to"]) for s in contract()["schedules"]] in (
        [(5, "2026-03-31"), (3, None)],
        [(3, None), (5, "2026-03-31")],
    )
    # Permissions and tenant separation of the undo.
    assert client.post(f"/api/v1/imports/{run1}/undo", headers=reader).status_code == 403
    assert client.post(f"/api/v1/imports/{run1}/undo", headers=other).status_code == 404
    # Undo of run 1: the schedule stays (later schedule of run 2), the mandate is removed and
    # the contract loses reference and direct debit flag.
    undone1 = _ok(client.post(f"/api/v1/imports/{run1}/undo", headers=h))
    kept = {i["entity_type"]: i["kept_reason"] for i in undone1["items"] if not i["undone"]}
    assert kept == {"payment_schedule": "späterer Zahlungsplan vorhanden"}
    assert {i["entity_type"] for i in undone1["items"] if i["undone"]} == {"sepa_mandate"}
    assert _ok(client.get("/api/v1/sepa-mandates", headers=h)) == []
    after = contract()
    assert (after["sepa_mandate_id"], after["direct_debit"]) == (None, False)
    # Undo of run 2: its schedule goes, the schedule of run 1 is open again (valid_to None).
    _ok(client.post(f"/api/v1/imports/{run2}/undo", headers=h))
    assert [(s["due_day"], s["valid_to"]) for s in contract()["schedules"]] == [(5, None)]

    # Document index: the links of the run go, the DMS document itself stays.
    document = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("u13vertrag.pdf", b"%PDF-1.4 vertrag u13", "application/pdf")},
            headers=h,
        ),
        201,
    )
    run3, report3 = _apply(
        client,
        h,
        "document_index",
        [["Objekt", "Datei", "Einheit"], ["881", "u13vertrag.pdf", "01"]],
        {"property_number": "Objekt", "document_ref": "Datei", "unit_number": "Einheit"},
        "docs.xlsx",
    )
    assert report3["counts"] == {"created": 1}
    links = _ok(client.get(f"/api/v1/documents/{document['id']}", headers=h))["links"]
    assert {link["entity_type"] for link in links} == {"property", "unit"}
    undone3 = _ok(client.post(f"/api/v1/imports/{run3}/undo", headers=h))
    assert [i["entity_type"] for i in undone3["items"] if i["undone"]] == [
        "document_link",
        "document_link",
    ]
    assert _ok(client.get(f"/api/v1/documents/{document['id']}", headers=h))["links"] == []
