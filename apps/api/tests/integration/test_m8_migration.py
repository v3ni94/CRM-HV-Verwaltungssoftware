"""Switch from Immoware24 without parallel operation (6.9.10, D11, M8-03, V9): migration
journal from staged rows, opening balances with four eyes release posted as source
``migration``, reconciliation report per property with zero difference check, switch of the
leading system behind G1. Every expected figure is fixed in the comments (rule 0.1.8).

Synthetic export headers (no statement about real Immoware24 exports, M8-01)."""

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
from tests.integration.test_m8_import import BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import A, _accounts, _prop
from tests.integration.test_m11_banking import IBAN_A, _camt, _upload

pytestmark = pytest.mark.integration
M = "/api/v1/imports/migration"
B = "/api/v1/banking"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mig-{RUN}", name=f"Migration {RUN}")
        b, _ = await services.provision_tenant(
            factory, slug=f"mig2-{RUN}", name=f"Migration2 {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs: dict[str, tuple[bool, list[tuple[Any, str]]]] = {
            "migadmin": (False, [(a, "tenant_admin")]),
            "migacc": (False, [(a, "accountant_no_banking")]),
            "migreader": (False, [(a, "read_only")]),
            "migother": (False, [(b, "tenant_admin")]),
            "migpadmin": (True, []),
            "migpadmin2": (True, [(a, "tenant_admin")]),
        }
        for name, (is_admin, memberships) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            for tenant, role in memberships:
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


def _code(response: Any) -> str:
    return str(response.json().get("code"))


def _hoa(
    c: TestClient, h: dict[str, str], number: str, template: str
) -> tuple[dict[str, Any], str, dict[str, str], str]:
    """Property, HOA ledger, accounts by number and the debtor account of the owner."""
    prop = _prop(c, h, number, "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, prop["id"], "01")
    owner, _ = _party(c, h, f"Eig{number}")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    ledger = _ok(
        c.post(f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template}, headers=h),
        201,
    )
    accounts = _accounts(c, h, ledger["id"])
    debtor = next(n for n in accounts if n.startswith("09") and n not in ("009000", "009999"))
    return prop, ledger["id"], accounts, debtor


def _open_g1(client: TestClient, world: World, template: str) -> None:
    """G1 for tenant A: requested by the platform admin with membership, approved by the other
    platform admin (four eyes), with the released chart of accounts template (V8)."""
    admin = bearer(login(client, world, "migpadmin2"))
    tenant_admin = bearer(login(client, world, "migadmin"))
    _ok(
        client.post(
            f"{A}/templates/{template}/release",
            json={"comment": "Testfreigabe"},
            headers=tenant_admin,
        )
    )
    request_id = _ok(
        client.post(
            "/api/v1/tenant/release-gates/requests",
            json={"gate": "G1", "scope": "Migrationstest", "evidence": "Testfall"},
            headers=admin,
        ),
        201,
    )["id"]
    other = bearer(login(client, world, "migpadmin"))
    _ok(
        client.post(
            f"/api/v1/platform/tenants/{world.tenant_a}/release-gates/requests/{request_id}/approve",
            json={"comment": "geprüft"},
            headers=other,
        )
    )


def test_migration_journal_opening_balances_reconciliation_and_switch(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "migadmin"))
    acc_user = bearer(login(client, world, "migacc"))
    reader = bearer(login(client, world, "migreader"))
    other = bearer(login(client, world, "migother"))
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    prop, ledger, acc, debtor = _hoa(client, h, "861", template)
    _, ledger2, acc2, _ = _hoa(client, h, "862", template)
    bank_account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": next(
                    e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa"
                ),
                "kind": "hoa",
                "iban": IBAN_A,
                "holder": "GdWE 861",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]

    # 1. Migration journal from a staged journal export (year 2026, cut off 31.01.2026).
    #    J1 05.01.: debtor +300,00 / 060100 -300,00 (Hausgeld receivable)
    #    J2 10.01.: 001200 +200,00 / debtor -200,00 (payment)
    #    Row of property 999, row of year 2025 and a row without account are not imported.
    rows: list[list[Any]] = [
        ["Buchungsnummer", "Objekt", "Konto", "Datum", "Betrag", "Buchungstext", "Beleg"],
        ["J1", "861", debtor, "05.01.2026", "300,00", "Hausgeld Januar", "SOLL-01"],
        ["J1", "861", "60100", "05.01.2026", "-300,00", "Hausgeld Januar", "SOLL-01"],
        ["J2", "861", "1200", "10.01.2026", "200,00", "Zahlung Eig861", "KA-1"],
        ["J2", "861", debtor, "10.01.2026", "-200,00", "Zahlung Eig861", "KA-1"],
        ["X1", "999", "1200", "10.01.2026", "1,00", "anderes Objekt", ""],
        ["Y1", "861", "1200", "10.12.2025", "1,00", "Vorjahr", ""],
        ["Z1", "861", "", "10.01.2026", "1,00", "ohne Konto", ""],
    ]
    staged = _stage(client, h, "journal", "journal.xlsx", _xlsx(rows), XLSX)
    body = {"source_file_id": staged["id"], "year": 2026, "year_complete": True}
    assert (
        client.post(f"{M}/ledgers/{ledger}/journal", json=body, headers=reader).status_code == 403
    )
    assert client.post(f"{M}/ledgers/{ledger}/journal", json=body, headers=other).status_code == 404
    imported = _ok(client.post(f"{M}/ledgers/{ledger}/journal", json=body, headers=h))
    assert (imported["imported"], imported["lines"]) == (2, 4)
    assert (imported["other_property"], imported["other_year"], imported["invalid"]) == (1, 1, 1)
    assert imported["debit_total"] == "500.00"
    assert imported["credit_total"] == "500.00"
    assert imported["unbalanced"] == []
    assert imported["unmatched_accounts"] == []
    again = _ok(client.post(f"{M}/ledgers/{ledger}/journal", json=body, headers=h))
    assert (again["imported"], again["existing"]) == (0, 2)
    journal = _ok(client.get(f"{M}/ledgers/{ledger}/journal", headers=h))
    assert journal["summary"]["entries"] == 2
    assert journal["summary"]["year_complete"] is True
    assert journal["entries"][0]["source_entry_id"] == "J1"
    assert journal["entries"][0]["document_ref"] == "SOLL-01"
    assert journal["entries"][0]["reconciled"] is False
    assert client.get(f"{M}/ledgers/{ledger}/journal", headers=other).status_code == 404
    # Never in the live journal: no posted entry of the ledger yet.
    assert _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h)) == []

    # 2. Opening balances as of 31.01.2026 (Immoware24 balance list):
    #    bank 001200 +1.000,00, debtor +100,00, reserve 008000 -250,00
    #    -> net +850,00, counter line 009000 credit 850,00.
    lines = [
        {
            "kind": "bank",
            "account_id": acc["001200"],
            "amount": "1000.00",
            "property_bank_account_id": bank_account,
        },
        {"kind": "debtor", "account_id": acc[debtor], "amount": "100.00"},
        {"kind": "reserve", "account_id": acc["008000"], "amount": "-250.00"},
    ]
    ob_body = {"cutoff_date": "2026-01-31", "note": "Saldenliste 31.01.2026", "lines": lines}
    assert (
        client.put(
            f"{M}/ledgers/{ledger}/opening-balances", json=ob_body, headers=reader
        ).status_code
        == 403
    )
    # Legal entity separation (E01): an account of ledger 862 cannot carry a balance of 861.
    foreign = {
        **ob_body,
        "lines": [{"kind": "bank", "account_id": acc2["001200"], "amount": "1.00"}],
    }
    wrong = client.put(f"{M}/ledgers/{ledger}/opening-balances", json=foreign, headers=h)
    assert wrong.status_code == 422
    assert _code(wrong) == "MHVP-ACC-0004"
    wrong_kind = {
        **ob_body,
        "lines": [{"kind": "debtor", "account_id": acc["001200"], "amount": "1.00"}],
    }
    assert (
        client.put(f"{M}/ledgers/{ledger}/opening-balances", json=wrong_kind, headers=h).status_code
        == 422
    )
    balances = _ok(client.put(f"{M}/ledgers/{ledger}/opening-balances", json=ob_body, headers=h))
    assert balances["status"] == "draft"
    assert balances["total_debit"] == "1100.00"
    assert balances["total_credit"] == "250.00"
    ob = balances["id"]
    assert client.get(f"{M}/opening-balances/{ob}", headers=other).status_code == 404

    # Posting before release and before the cut off date is refused.
    not_released = client.post(f"{M}/opening-balances/{ob}/post", headers=h)
    assert not_released.status_code == 409
    assert _code(not_released) == "MHVP-MIG-0002"
    # Release: same person 403, second person ok.
    same = client.post(f"{M}/opening-balances/{ob}/release", json={}, headers=h)
    assert same.status_code == 403
    assert _code(same) == "MHVP-GATE-0002"
    released = _ok(
        client.post(
            f"{M}/opening-balances/{ob}/release", json={"comment": "geprüft"}, headers=acc_user
        )
    )
    assert released["status"] == "released"
    assert released["released_by"] == str(world.users["migacc"])
    # A released set is immutable.
    assert (
        client.put(f"{M}/ledgers/{ledger}/opening-balances", json=ob_body, headers=h).status_code
        == 409
    )
    no_cutoff = client.post(f"{M}/opening-balances/{ob}/post", headers=h)
    assert no_cutoff.status_code == 409
    assert _code(no_cutoff) == "MHVP-MIG-0001"
    _ok(
        client.put(
            f"{M}/ledgers/{ledger}/cutoff", json={"migration_cutoff": "2026-01-15"}, headers=h
        )
    )
    wrong_date = client.post(f"{M}/opening-balances/{ob}/post", headers=h)
    assert wrong_date.status_code == 409
    assert _code(wrong_date) == "MHVP-MIG-0001"
    _ok(
        client.put(
            f"{M}/ledgers/{ledger}/cutoff", json={"migration_cutoff": "2026-01-31"}, headers=h
        )
    )
    posted = _ok(client.post(f"{M}/opening-balances/{ob}/post", headers=h))
    assert posted["status"] == "posted"
    assert posted["journal_entry_id"]
    entry = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{posted['journal_entry_id']}", headers=h))
    assert (entry["status"], entry["kind"], entry["source"]) == (
        "posted",
        "opening_balance",
        "migration",
    )
    assert entry["booking_date"] == "2026-01-31"
    by_account = {line["account_id"]: line for line in entry["lines"]}
    assert by_account[acc["001200"]]["debit"] == "1000.00"
    assert by_account[acc["008000"]]["credit"] == "250.00"
    assert by_account[acc["009000"]]["credit"] == "850.00"
    # Repeated posting has no second effect (B08); the cut off date is now fixed.
    assert client.post(f"{M}/opening-balances/{ob}/post", headers=h).status_code == 409
    assert (
        client.put(
            f"{M}/ledgers/{ledger}/cutoff", json={"migration_cutoff": "2026-02-28"}, headers=h
        ).status_code
        == 409
    )
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert [(i["account_number"], i["remaining"]) for i in items] == [(debtor, "100.00")]
    assert items[0]["contract_id"] is not None

    # 3. Reconciliation: statement with closing balance 999,99 -> one cent difference blocks.
    doc = _upload(client, h, "s1.xml", _camt("MIG-S1", IBAN_A, "999.99", "999.99", []))
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)
    report = _ok(
        client.post(f"{M}/properties/{prop['id']}/reconciliation", json={}, headers=h), 201
    )
    assert report["as_of"] == "2026-01-31"
    assert report["zero_difference"] is False
    assert report["deviations"] == 1
    assert report["total_difference"] == "0.01"
    bank_line = next(line for line in report["lines"] if line["metric"] == "bankstand")
    assert (bank_line["source"], bank_line["platform"], bank_line["difference"]) == (
        "1000.00",
        "999.99",
        "-0.01",
    )
    assert report["document_id"] is not None
    metrics = {(line["metric"], line["key"]): line for line in report["lines"]}
    assert metrics[("kontosaldo", "001200")]["difference"] == "0.00"
    assert metrics[("debitoren_op", debtor)]["platform"] == "100.00"
    assert metrics[("ruecklage", "008000")]["platform"] == "250.00"
    assert metrics[("journal", "2026")]["deviates"] is False
    pdf = client.get(f"{M}/reconciliation/{report['id']}/pdf", headers=h)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"{M}/reconciliation/{report['id']}", headers=other).status_code == 404

    # 4. Switch: G1 closed -> refused with a message naming G1.
    closed = client.post(f"{M}/ledgers/{ledger}/switch-requests", json={}, headers=h)
    assert closed.status_code == 403
    assert _code(closed) == "MHVP-GATE-0001"
    assert "G1" in closed.json()["detail"]
    assert "Immoware24" in closed.json()["detail"]
    _open_g1(client, world, template)
    blocked = client.post(f"{M}/ledgers/{ledger}/switch-requests", json={}, headers=h)
    assert blocked.status_code == 409
    assert _code(blocked) == "MHVP-MIG-0003"
    assert "0,01 EUR" in blocked.json()["detail"]
    # Corrected statement (closing 1.000,00) -> zero difference -> switch with second person.
    doc2 = _upload(client, h, "s2.xml", _camt("MIG-S2", IBAN_A, "1000.00", "1000.00", []))
    _ok(client.post(f"{B}/imports", json={"document_id": doc2}, headers=h), 201)
    report2 = _ok(
        client.post(f"{M}/properties/{prop['id']}/reconciliation", json={}, headers=h), 201
    )
    assert report2["zero_difference"] is True
    assert report2["deviations"] == 0
    assert report2["total_difference"] == "0.00"
    journal = _ok(client.get(f"{M}/ledgers/{ledger}/journal", headers=h))
    assert all(e["reconciled"] for e in journal["entries"])
    assert len(_ok(client.get(f"{M}/properties/{prop['id']}/reconciliation", headers=h))) == 2
    assert (
        client.post(f"{M}/ledgers/{ledger}/switch-requests", json={}, headers=reader).status_code
        == 403
    )
    request = _ok(
        client.post(
            f"{M}/ledgers/{ledger}/switch-requests", json={"comment": "Nulldifferenz"}, headers=h
        ),
        201,
    )
    assert request["status"] == "requested"
    assert (
        client.post(f"{M}/ledgers/{ledger}/switch-requests", json={}, headers=h).status_code == 409
    )
    same = client.post(f"{M}/switch-requests/{request['id']}/approve", json={}, headers=h)
    assert same.status_code == 403
    assert _code(same) == "MHVP-GATE-0002"
    assert (
        client.post(
            f"{M}/switch-requests/{request['id']}/approve", json={}, headers=other
        ).status_code
        == 404
    )
    approved = _ok(
        client.post(
            f"{M}/switch-requests/{request['id']}/approve", json={"comment": "ok"}, headers=acc_user
        )
    )
    assert approved["status"] == "approved"
    assert approved["decided_by"] == str(world.users["migacc"])
    assert _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))["leading_system"] == "mhvp"
    assert _ok(client.get(f"{A}/ledgers/{ledger2}", headers=h))["leading_system"] == "immoware24"

    # 5. Status per property and tenant separation of the status.
    status = _ok(client.get(f"{M}/status", headers=h))
    row = next(p for p in status if p["property_number"] == "861")
    step = row["ledgers"][0]
    assert (step["journal_imported"], step["opening_balances_entered"], step["released"]) == (
        True,
        True,
        True,
    )
    assert (step["posted"], step["reconciled"], step["switched"]) == (True, True, True)
    assert row["report"]["zero_difference"] is True
    other_row = next(p for p in status if p["property_number"] == "862")
    assert other_row["ledgers"][0]["journal_imported"] is False
    assert other_row["ledgers"][0]["switched"] is False
    assert _ok(client.get(f"{M}/status", headers=other)) == []
    assert client.get(f"{M}/status", headers=reader).status_code == 200


def test_balance_list_csv_import_and_column_configuration(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "migadmin"))
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    _, ledger, acc, debtor = _hoa(client, h, "863", template)
    # Balance list: 1200 +500,00, debtor -20,00 (credit balance stays a debtor line), 8000
    # -100,00, 60100 (revenue) is no balance sheet account -> error, 4711 unknown -> error.
    good = f"Konto;Bezeichnung;Saldo\n1200;Bank;500,00\n{debtor};Eigentümer;-20,00\n8000;Rücklage;-100,00\n"
    bad = good + "60100;Hausgeld;10,00\n4711;Fremd;1,00\n"
    rejected = _ok(
        client.post(
            f"{M}/ledgers/{ledger}/opening-balances/import",
            data={"cutoff_date": "2026-01-31"},
            files={"file": ("salden.csv", bad.encode("utf-8"), "text/csv")},
            headers=h,
        )
    )
    assert rejected["balances"] is None
    assert any("60100" in e and "kein Bestandskonto" in e for e in rejected["errors"])
    assert any("4711" in e for e in rejected["errors"])
    accepted = _ok(
        client.post(
            f"{M}/ledgers/{ledger}/opening-balances/import",
            data={"cutoff_date": "2026-01-31"},
            files={"file": ("salden.csv", good.encode("cp1252"), "text/csv")},
            headers=h,
        )
    )
    assert accepted["errors"] == ["Datei als Windows-1252 (ANSI) gelesen, nicht als UTF-8"]
    balances = accepted["balances"]
    assert balances["entered_via"] == "import"
    assert balances["status"] == "draft"
    assert {
        (line["account_number"], line["kind"], line["amount"]) for line in balances["lines"]
    } == {
        ("001200", "bank", "500.00"),
        (debtor, "debtor", "-20.00"),
        ("008000", "reserve", "-100.00"),
    }
    assert acc["001200"] == next(
        line["account_id"] for line in balances["lines"] if line["kind"] == "bank"
    )

    columns = _ok(client.get(f"{M}/journal-columns", headers=h))
    assert columns["customised"] is False
    assert columns["columns"]["entry_id"] == "Buchungsnummer"
    invalid = client.put(f"{M}/journal-columns", json={"columns": {"entry_id": "Nr"}}, headers=h)
    assert invalid.status_code == 422
    saved = _ok(
        client.put(
            f"{M}/journal-columns",
            json={
                "columns": {
                    "entry_id": "Nr",
                    "property_number": "Objekt",
                    "account_number": "Konto",
                    "booking_date": "Datum",
                    "debit": "S",
                    "credit": "H",
                }
            },
            headers=h,
        )
    )
    assert saved["customised"] is True
    assert saved["columns"]["debit"] == "S"
    assert _ok(client.get(f"{M}/journal-columns", headers=h))["columns"]["entry_id"] == "Nr"
