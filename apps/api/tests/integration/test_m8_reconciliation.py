"""A68 (13.1, M8-03): daily reconciliation report of the parallel operation. Synthetic staging
rows (invented headers, no statement about real Immoware24 exports) against posted platform
figures; every expected difference is recomputed by hand in the comments (rule 0.1.8).
Read and compare only: the report changes no posting, open item or bank figure."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.imports.tasks import report_all_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import A, _book, _entry, _hoa_ledger, _line
from tests.integration.test_m11_banking import IBAN_A, PAYER, _camt, _ntry, _upload

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/reconciliation-reports"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rc-{RUN}", name=f"Abgleich {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rc2-{RUN}", name=f"Abgleich2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m8radmin", a, "tenant_admin"),
            ("m8rreader", a, "read_only"),
            ("m8rother", b, "tenant_admin"),
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


def _by(lines: list[dict[str, Any]], prop: str, metric: str, key: str | None = None) -> Any:
    found = [
        line
        for line in lines
        if line["property_number"] == prop and line["metric"] == metric and line["key"] == key
    ]
    assert len(found) == 1, (prop, metric, key, found)
    return found[0]


def test_reconciliation_report_differences_csv_permissions_and_tenants(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "m8radmin"))

    # Platform figures (tenant A), all as of 31.01.2026:
    #   receivable 05.01.: debtor 300,00 / Hausgeld 060100 300,00 -> open receivable 300,00
    #   payment 10.01.:    bank 001200 200,00 / debtor 200,00, settles 200,00 -> open 100,00
    #   reserve 15.01.:    Zuführung 030000 100,00 / Erhaltungsrücklage 008000 100,00
    # Balances (debit minus credit): 001200 +200,00, debtor +100,00, 008000 -100,00,
    # 060100 -300,00, 030000 +100,00. Reserve as credit balance: 100,00.
    ledger, acc, debtor = _hoa_ledger(client, h, "851")
    debtor_number = next(n for n, i in acc.items() if i == debtor)
    _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-01-05",
            [_line(debtor, "300.00"), _line(acc["060100"], "0", "300.00")],
        ),
    )
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-01-10",
            [_line(acc["001200"], "200.00"), _line(debtor, "0", "200.00")],
            settlements=[{"open_item_id": item[0]["id"], "amount": "200.00"}],
        ),
    )
    _book(
        client,
        h,
        ledger,
        _entry(
            "custom",
            "2026-01-15",
            [_line(acc["030000"], "100.00"), _line(acc["008000"], "0", "100.00")],
        ),
    )
    # Bank: statement closing 10.200,00 on 31.01.2026 with one credit of 200,00 on 10.01.
    prop_id = _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))["property_id"]
    hoa = next(
        e["id"]
        for e in _ok(client.get(f"/api/v1/properties/{prop_id}", headers=h))["legal_entities"]
        if e["kind"] == "hoa"
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop_id}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": IBAN_A,
                "holder": "GdWE 851",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    camt = _camt(
        "RC-851",
        IBAN_A,
        "10000.00",
        "10200.00",
        [_ntry("RC-1", "200.00", "CRDT", "2026-01-10", PAYER, "Hausgeld")],
    )
    _ok(
        client.post(
            "/api/v1/banking/imports",
            json={"document_id": _upload(client, h, "rc.xml", camt)},
            headers=h,
        ),
        201,
    )

    # Source rows (staged only, M8-03). Journal, signed amount, debit positive:
    #   851/1200 +200,00 (= platform), 851/debtor +300,00 -200,00 (= 100,00 = platform),
    #   851/8000 -100,00 (= platform), 851/60100 -310,00 (platform -300,00: difference +10,00),
    #   851/4711 +5,00 (unknown account), 851/1200 +50,00 on 05.02. (after as_of, ignored),
    #   999/1200 +1,00 (property missing), one row without property (warning).
    journal = _stage(
        client,
        h,
        "journal",
        "journal.xlsx",
        _xlsx(
            [
                ["Objekt", "Konto", "Datum", "Betrag"],
                ["851", "1200", "10.01.2026", "200,00"],
                ["851", debtor_number, "05.01.2026", "300,00"],
                ["851", debtor_number, "10.01.2026", "-200,00"],
                ["851", "8000", "15.01.2026", "-100,00"],
                ["851", "60100", "05.01.2026", "-310,00"],
                ["851", "4711", "05.01.2026", "5,00"],
                ["851", "1200", "05.02.2026", "50,00"],
                ["999", "1200", "05.01.2026", "1,00"],
                [None, "1200", "05.01.2026", "1,00"],
            ]
        ),
        XLSX,
    )
    # Bank rows: credit 200,00 on 10.01. (balance 10.200,00), debit 50,00 on 12.01. (balance
    # 10.150,00). Source balance = last balance 10.150,00, platform statement 10.200,00:
    # difference +50,00. Credits 10.01. to 12.01.: source 200,00, platform 200,00.
    bank = _stage(
        client,
        h,
        "bank_transactions",
        "bank.xlsx",
        _xlsx(
            [
                ["Objekt", "IBAN", "Datum", "Betrag", "Saldo"],
                ["851", IBAN_A, "10.01.2026", "200,00", "10.200,00"],
                ["851", IBAN_A, "12.01.2026", "-50,00", "10.150,00"],
            ]
        ),
        XLSX,
    )

    report = _ok(client.post(BASE, json={"as_of": "2026-01-31"}, headers=h), 201)
    assert report["as_of"] == "2026-01-31"
    assert report["trigger"] == "manual"
    assert {s["id"] for s in report["sources"]} == {journal["id"], bank["id"]}
    assert report["counts"] == {
        "journal": 7,
        "bank_transactions": 2,
        "invalid": 1,
        "after_as_of": 1,
    }
    assert len(report["warnings"]) == 1
    assert "Objektnummer fehlt" in report["warnings"][0]
    lines = report["lines"]
    assert _by(lines, "851", "kontosaldo", "001200") == {
        "property_number": "851",
        "metric": "kontosaldo",
        "key": "001200",
        "source": "200.00",
        "platform": "200.00",
        "difference": "0.00",
        "deviates": False,
        "hint": None,
    }
    assert _by(lines, "851", "kontosaldo", debtor_number)["difference"] == "0.00"
    assert _by(lines, "851", "kontosaldo", "008000")["difference"] == "0.00"
    hausgeld = _by(lines, "851", "kontosaldo", "060100")
    assert (hausgeld["source"], hausgeld["platform"], hausgeld["difference"]) == (
        "-310.00",
        "-300.00",
        "10.00",
    )
    assert hausgeld["deviates"] is True
    unknown = _by(lines, "851", "kontosaldo", "004711")
    assert unknown["platform"] is None
    assert "Kontoart unbekannt" in unknown["hint"]
    only_platform = _by(lines, "851", "kontosaldo", "030000")
    assert (only_platform["source"], only_platform["platform"]) == (None, "100.00")
    assert only_platform["hint"] == "Konto nicht in der Quelle"
    assert _by(lines, "851", "kontosaldo", "001200")["deviates"] is False
    debitoren = _by(lines, "851", "debitoren_op")
    assert (debitoren["source"], debitoren["platform"], debitoren["deviates"]) == (
        "100.00",
        "100.00",
        False,
    )
    assert "1 Quellkonto" in debitoren["hint"]
    assert _by(lines, "851", "kreditoren_op")["difference"] == "0.00"
    reserve = _by(lines, "851", "ruecklage")
    assert (reserve["source"], reserve["platform"]) == ("100.00", "100.00")
    bankstand = _by(lines, "851", "bankstand", IBAN_A[-4:])
    assert (bankstand["source"], bankstand["platform"], bankstand["difference"]) == (
        "10150.00",
        "10200.00",
        "50.00",
    )
    zahlungen = _by(lines, "851", "zahlungen", IBAN_A[-4:])
    assert (zahlungen["source"], zahlungen["platform"], zahlungen["deviates"]) == (
        "200.00",
        "200.00",
        False,
    )
    missing = _by(lines, "999", "kontosaldo", "001200")
    assert missing["hint"] == "Objekt nicht auf der Plattform"
    assert missing["platform"] is None
    # Deviations: 004711, 060100, 030000, bankstand, 999/001200 = 5 of 12 lines.
    assert report["totals"] == {
        "properties": 2,
        "compared": 12,
        "deviations": 5,
        "missing_on_platform": 1,
    }
    assert [p["number"] for p in report["properties"]] == ["851", "999"]
    assert report["properties"][1] == {
        "number": "999",
        "name": None,
        "on_platform": False,
        "compared": 1,
        "deviations": 1,
    }

    # Nothing was changed on the platform by the report (read only).
    after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert Decimal(after[0]["remaining"]) == Decimal("100.00")

    # CSV: semicolon, German amounts, UTF-8 BOM.
    csv_response = client.get(f"{BASE}/{report['id']}/csv", headers=h)
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert 'filename="abgleich-2026-01-31.csv"' in csv_response.headers["content-disposition"]
    text = csv_response.content.decode("utf-8-sig")
    rows = text.splitlines()
    assert rows[0] == "Objekt;Kennzahl;Schlüssel;Quelle;Plattform;Differenz;Abweichung;Hinweis"
    assert "851;kontosaldo;060100;-310,00;-300,00;10,00;ja;" in rows
    assert f"851;bankstand;{IBAN_A[-4:]};10.150,00;10.200,00;50,00;ja;" in rows
    assert "999;kontosaldo;001200;1,00;;;ja;Objekt nicht auf der Plattform" in rows

    # Stored as import run, listed with the reconciliation source.
    listed = _ok(client.get(BASE, headers=h))
    assert [r["id"] for r in listed] == [report["id"]]
    assert listed[0]["totals"]["deviations"] == 5
    runs = _ok(client.get("/api/v1/imports", headers=h))
    assert next(r for r in runs if r["id"] == report["id"])["source"] == "immoware24:reconciliation"
    assert _ok(client.get(f"{BASE}/{report['id']}", headers=h))["lines"] == lines
    # An ordinary import run is not a reconciliation report.
    assert client.get(f"{BASE}/{journal['id']}", headers=h).status_code == 404

    # Permissions: reading is allowed, creating needs ai:create.
    reader = bearer(login(client, world, "m8rreader"))
    assert _ok(client.get(BASE, headers=reader))[0]["id"] == report["id"]
    assert client.post(BASE, json={}, headers=reader).status_code == 403
    assert client.put(f"{BASE}/columns", json={"columns": {}}, headers=reader).status_code == 403

    # Tenant separation: tenant B sees nothing and has no rows to compare.
    other = bearer(login(client, world, "m8rother", tenant_id=world.tenant_b))
    assert _ok(client.get(BASE, headers=other)) == []
    assert client.get(f"{BASE}/{report['id']}", headers=other).status_code == 404
    assert client.get(f"{BASE}/{report['id']}/csv", headers=other).status_code == 404
    assert client.post(BASE, json={}, headers=other).status_code == 422
    assert (
        client.post(BASE, json={"source_file_ids": [journal["id"]]}, headers=other).status_code
        == 404
    )

    # Column configuration: defaults, validation, custom mapping used by the next report.
    columns = _ok(client.get(f"{BASE}/columns", headers=h))
    assert columns["customised"] is False
    assert columns["columns"]["journal"]["account_number"] == "Konto"
    assert (
        client.put(
            f"{BASE}/columns", json={"columns": {"journal": {"foo": "x"}}}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{BASE}/columns",
            json={"columns": {"journal": {"property_number": "Objekt"}}},
            headers=h,
        ).status_code
        == 422
    )
    custom = _ok(
        client.put(
            f"{BASE}/columns",
            json={
                "columns": {
                    "journal": {
                        "property_number": "Objekt",
                        "account_number": "Konto",
                        "booking_date": "Datum",
                        "debit": "Betrag",
                    }
                }
            },
            headers=h,
        )
    )
    assert custom["customised"] is True
    assert custom["columns"]["journal"] == {
        "property_number": "Objekt",
        "account_number": "Konto",
        "booking_date": "Datum",
        "debit": "Betrag",
    }
    assert custom["columns"]["bank_transactions"] == columns["defaults"]["bank_transactions"]
    # With "Betrag" read as debit only: debtor 300,00 + (-200,00) = 100,00 stays, but 060100
    # is now +(-310,00) = -310,00 read as debit, i.e. unchanged sign; 1200 unchanged. The
    # configuration is applied (report carries it).
    second = _ok(
        client.post(
            BASE, json={"as_of": "2026-01-31", "source_file_ids": [journal["id"]]}, headers=h
        ),
        201,
    )
    assert second["columns"]["journal"]["debit"] == "Betrag"
    assert [s["id"] for s in second["sources"]] == [journal["id"]]
    assert all(line["metric"] not in ("bankstand", "zahlungen") for line in second["lines"])

    # Beat job: one report per active tenant with staged rows; tenant B is skipped.
    totals = asyncio.run(report_all_once(_settings(database, redis_url)))
    assert totals["ran"] >= 1
    assert totals["skipped"] >= 1
    assert totals["failed"] == 0
    latest = _ok(client.get(BASE, headers=h))[0]
    assert latest["trigger"] == "beat"
    assert latest["totals"]["properties"] == 2
    assert _ok(client.get(BASE, headers=other)) == []
