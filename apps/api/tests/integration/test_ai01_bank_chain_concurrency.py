"""AI01 (GAH-102, GAH-105, GAH-201): statement chain check in the bank reconciliation, number
range rule of 7.2 on new ledger accounts, and concurrency of money flows (B08, rule 9):
parallel import of the same statement file, parallel import of overlapping statements of one
account (as two fetches of the same account deliver them) and parallel submission of one
payment batch. Synthetic data only, no network."""

import asyncio
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"


class _OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


def _iban(account: int, blz: str = "37040044") -> str:
    """Synthetic, checksum valid German IBAN (mod 97), never a real account."""
    bban = f"{blz}{account:010d}"
    digits = "".join(str(int(c, 36)) for c in f"{bban}DE00")
    return f"DE{98 - int(digits) % 97:02d}{bban}"


PAYER = _iban(9_101_003)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ai01-{RUN}", name=f"AI01 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai01b-{RUN}", name=f"AI01b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ai01admin", "tenant_admin", a),
            ("ai01acc", "accountant_banking", a),
            ("ai01appr", "tenant_admin", a),
            ("ai01other", "tenant_admin", b),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=_OpenG1G2())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ntry(ref: str, amount: str, ind: str, day: str) -> str:
    party = "Dbtr" if ind == "CRDT" else "Cdtr"
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt><AcctSvcrRef>{ref}</AcctSvcrRef>
<NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
<RltdPties><{party}><Nm>Zahler</Nm></{party}><{party}Acct><Id><IBAN>{PAYER}</IBAN></Id></{party}Acct></RltdPties>
<RmtInf><Ustrd>Hausgeld</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def _camt(
    stmt_id: str, iban: str, period: tuple[str, str], balances: tuple[str, str], entries: list[str]
) -> bytes:
    start, end = period
    opening, closing = balances
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>
<GrpHdr><MsgId>M-{stmt_id}</MsgId><CreDtTm>{end}T08:00:00</CreDtTm></GrpHdr>
<Stmt><Id>{stmt_id}</Id><FrToDt><FrDtTm>{start}T00:00:00</FrDtTm><ToDtTm>{end}T23:59:59</ToDtTm></FrToDt>
<Acct><Id><IBAN>{iban}</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{opening}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>{start}</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{closing}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>{end}</Dt></Dt></Bal>
{"".join(entries)}</Stmt></BkToCstmrStmt></Document>""".encode()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "application/xml")}, headers=h),
            201,
        )["id"]
    )


def _property(c: TestClient, h: dict[str, str], number: str) -> tuple[str, str, dict[str, str]]:
    """Each property gets its own IBANs (an import is routed by the IBAN of the statement)."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AI01 Haus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    banks = {}
    for role, kind, offset in [("own", "hoa", 1), ("other", "reserve", 2)]:
        iban = _iban(9_100_000 + int(number) * 10 + offset)
        banks[f"{role}_iban"] = iban
        banks[role] = _ok(
            c.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": kind,
                    "iban": iban,
                    "bic": "BYLADEM1001",
                    "holder": "GdWE AI01",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
    return prop["id"], hoa, banks


def test_statement_chain_status_in_reconciliation(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """GAH-102. Expected values: January 1.000,00 + 100,00 = 1.100,00 (ok, first); February
    opens with 1.150,00 against 1.100,00 (break 50,00) and closes 1.150,00 + 50,00 = 1.200,00;
    April follows February with March missing (gap 01.03. to 31.03.)."""
    client, _ = clients
    h = bearer(login(client, world, "ai01admin"))
    _, _, banks = _property(client, h, "911")
    for sid, period, bal, entries in [
        ("AI01-1", ("2026-01-01", "2026-01-31"), ("1000.00", "1100.00"), ["R1", "100.00"]),
        ("AI01-2", ("2026-02-01", "2026-02-28"), ("1150.00", "1200.00"), ["R2", "50.00"]),
        ("AI01-4", ("2026-04-01", "2026-04-30"), ("1200.00", "1210.00"), ["R4", "10.00"]),
    ]:
        data = _camt(
            sid, banks["own_iban"], period, bal, [_ntry(entries[0], entries[1], "CRDT", period[0])]
        )
        _ok(
            client.post(
                f"{B}/imports", json={"document_id": _upload(client, h, sid, data)}, headers=h
            ),
            201,
        )
    rec = _ok(client.get(f"{B}/accounts/{banks['own']}/reconciliation", headers=h))
    assert [r["statement_ref"] for r in rec] == ["AI01-1", "AI01-2", "AI01-4"]
    assert [r["status"] for r in rec] == ["ok", "ok", "ok"]
    assert [r["chain_status"] for r in rec] == ["first", "break", "ok"]
    assert Decimal(rec[1]["chain_difference"]) == Decimal("50.00")
    assert [r["period_status"] for r in rec] == ["first", "ok", "gap"]
    assert (rec[2]["gap_from"], rec[2]["gap_to"]) == ("2026-03-01", "2026-03-31")

    # Another tenant sees nothing (RLS), unknown account 404.
    ho = bearer(login(client, world, "ai01other"))
    assert client.get(f"{B}/accounts/{banks['own']}/reconciliation", headers=ho).status_code == 404


def test_account_number_range_rule(clients: tuple[TestClient, TestClient], world: World) -> None:
    """GAH-105: cost account in the bank range and a bank link on a reserve account are
    refused with MHVP-ACC-0032; bank, cash, transit and technical stay allowed."""
    client, _ = clients
    h = bearer(login(client, world, "ai01admin"))
    _, hoa, banks = _property(client, h, "912")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    url = f"{A}/ledgers/{ledger}/accounts"
    bad = client.post(
        url,
        json={"number": "001500", "name": "x", "category": "cost", "type": "expense"},
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "MHVP-ACC-0032"
    link = client.post(
        url,
        json={
            "number": "008100",
            "name": "Rücklage",
            "category": "reserve",
            "type": "liability",
            "property_bank_account_id": banks["other"],
        },
        headers=h,
    )
    assert link.status_code == 422, link.text
    assert link.json()["code"] == "MHVP-ACC-0032"
    ok = _ok(
        client.post(
            url,
            json={
                "number": "001210",
                "name": "Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": banks["own"],
            },
            headers=h,
        ),
        201,
    )
    assert ok["range_warning"] is None
    _ok(
        client.post(
            url,
            json={
                "number": "001360",
                "name": "Geldtransit",
                "category": "transit",
                "type": "asset",
            },
            headers=h,
        ),
        201,
    )
    listed = _ok(client.get(url, headers=h))
    assert all(a["range_warning"] is None for a in listed)  # default chart is clean
    bad_schema = client.post(
        url, json={"number": "12", "name": "x", "category": "bank", "type": "asset"}, headers=h
    )
    assert bad_schema.status_code == 422


def test_parallel_import_of_the_same_file_and_overlapping_fetches(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """GAH-201 (B08): the same statement file imported twice at the same time, and two
    overlapping statements of one account (as two parallel fetches deliver them), keep each
    bank transaction exactly once. Expected: 3 transactions of 100,00, 200,00 and 300,00,
    sum 600,00."""
    client, _ = clients
    h = bearer(login(client, world, "ai01admin"))
    _, _, banks = _property(client, h, "913")
    entries = [
        _ntry("P-1", "100.00", "CRDT", "2026-05-02"),
        _ntry("P-2", "200.00", "CRDT", "2026-05-03"),
    ]
    data = _camt(
        "AI01-P", banks["own_iban"], ("2026-05-01", "2026-05-31"), ("0.00", "300.00"), entries
    )
    doc = _upload(client, h, "p.xml", data)
    overlap = _camt(
        "AI01-Q",
        banks["own_iban"],
        ("2026-05-01", "2026-05-31"),
        ("0.00", "600.00"),
        [*entries, _ntry("P-3", "300.00", "CRDT", "2026-05-04")],
    )
    doc_q = _upload(client, h, "q.xml", overlap)
    settings = _settings(database, redis_url)

    def run_import(document_id: str) -> tuple[int, str]:
        with TestClient(create_app(settings)) as own:
            r = own.post(f"{B}/imports", json={"document_id": document_id}, headers=h)
            return r.status_code, r.text

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run_import, [doc, doc, doc_q]))
    codes = [c for c, _ in results]
    assert all(c in (201, 409) for c in codes), results
    assert 201 in codes
    # A refused parallel import (409 "wird gerade parallel importiert") is retried afterwards,
    # as the operator or the next fetch would do; the retry adds only what is new.
    for document_id, code in zip([doc, doc, doc_q], codes, strict=True):
        if code == 409:
            _ok(client.post(f"{B}/imports", json={"document_id": document_id}, headers=h), 201)
    txs = _ok(client.get(f"{B}/transactions", params={"bank_account_id": banks["own"]}, headers=h))
    amounts = sorted(Decimal(t["amount"]) for t in txs)
    assert amounts == [Decimal("100.00"), Decimal("200.00"), Decimal("300.00")], (codes, amounts)
    assert sum(amounts) == Decimal("600.00")


def test_parallel_submission_of_one_payment_batch(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """GAH-201 (8.2, B08): two simultaneous submissions of the same batch give exactly one
    transfer to the bank (one 200, one 409 MHVP-BANK-0018); the order is submitted once."""
    client, gated = clients
    h = bearer(login(client, world, "ai01admin"))
    acc_user = bearer(login(client, world, "ai01acc"))
    approver = bearer(login(client, world, "ai01appr"))
    _, hoa, banks = _property(client, h, "914")
    bank = banks["own"]
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )
    gh = bearer(login(gated, world, "ai01acc"))
    gh_admin = bearer(login(gated, world, "ai01admin"))
    _ok(
        gated.post(
            f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh_admin
        )
    )
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AI01 Dienst {RUN} GmbH",
                "bank_accounts": [{"iban": _iban(9_101_010), "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, approver, provider)
    inv = _ok(
        client.post(
            f"{A}/invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider,
                "number": "AI01-1",
                "invoice_date": "2026-02-01",
                "due_date": "2026-02-20",
                "service_from": "2026-01-01",
                "net": "123.45",
                "vat": "0.00",
                "gross": "123.45",
                "payee_iban": _iban(9_101_010),
                "lines": [{"account_id": acc["040300"], "net": "123.45"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    for step in ("completeness", "factual", "arithmetic_tax"):
        _ok(
            client.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": "ok", "reason": "geprüft"},
                headers=h,
            ),
            201,
        )
    _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
    _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-05",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(client.post(f"{B}/payment-orders/{order}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{order}/approve", headers=acc_user))
    batch = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [order]}, headers=gh), 201)
    assert gated.get(f"{B}/payment-batches/{batch['id']}/file", headers=gh).status_code == 200

    def submit(ref: str) -> tuple[int, Any]:
        with TestClient(
            create_app(_settings(database, redis_url), release_gate_resolver=_OpenG1G2())
        ) as own:
            r = own.post(
                f"{B}/payment-batches/{batch['id']}/submit", json={"reference": ref}, headers=gh
            )
            return r.status_code, r.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["AI01 Protokoll 1", "AI01 Protokoll 2"]))
    codes = sorted(c for c, _ in results)
    assert codes == [200, 409], results
    refused = next(json.loads(b) for c, b in results if c == 409)
    assert refused["code"] == "MHVP-BANK-0018"
    detail = _ok(client.get(f"{B}/payment-batches/{batch['id']}", headers=h))
    assert detail["status"] == "submitted"
    statuses = [
        o["status"] for o in _ok(client.get(f"{B}/payment-orders", headers=h)) if o["id"] == order
    ]
    assert statuses == ["submitted"]
    # Reader without banking right of another tenant: 404 (RLS).
    ho = bearer(login(client, world, "ai01other"))
    assert client.get(f"{B}/payment-batches/{batch['id']}", headers=ho).status_code == 404
