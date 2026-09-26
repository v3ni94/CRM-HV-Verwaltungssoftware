"""M11 acceptance with synthetic CAMT.053 files (no real bank data): re-import has no additional
effect, two real identical payments stay two (D05), internal transfer is paired and not income
(D04), statement and ledger reconciliation (B09), possible duplicates without bank reference go
to review, unknown accounts are refused, connectors without contract report not configured."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking.tasks import sync_all_once
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
IBAN_A = "DE02120300000000202051"
IBAN_B = "DE89370400440532013000"
PAYER = "DE75512108001245126199"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bk-{RUN}", name=f"Bank {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m11admin", "tenant_admin"), ("m11clerk", "clerk_no_accounting")]:
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


def _ntry(ref: str | None, amount: str, ind: str, day: str, iban: str, purpose: str) -> str:
    party = "Dbtr" if ind == "CRDT" else "Cdtr"
    ref_xml = f"<AcctSvcrRef>{ref}</AcctSvcrRef>" if ref else ""
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt>{ref_xml}
<NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
<RltdPties><{party}><Nm>Zahler</Nm></{party}><{party}Acct><Id><IBAN>{iban}</IBAN></Id></{party}Acct></RltdPties>
<RmtInf><Ustrd>{purpose}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def _camt(stmt_id: str, iban: str, opening: str, closing: str, entries: list[str]) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>
<GrpHdr><MsgId>M-{stmt_id}</MsgId><CreDtTm>2026-02-01T08:00:00</CreDtTm></GrpHdr>
<Stmt><Id>{stmt_id}</Id><Acct><Id><IBAN>{iban}</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{opening}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{closing}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-31</Dt></Dt></Bal>
{"".join(entries)}</Stmt></BkToCstmrStmt></Document>""".encode()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "application/xml")}, headers=h),
            201,
        )["id"]
    )


def test_camt_import_identity_transfer_and_reconciliation(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "m11admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "711", "name": "Bankhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    accounts = {}
    for iban, kind in [(IBAN_A, "hoa"), (IBAN_B, "reserve")]:
        accounts[iban] = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": kind,
                    "iban": iban,
                    "holder": "GdWE Bankhaus",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]

    # D05: two real payments of 400,00 with distinct bank references; D04 transfer A -> B.
    file_a = _camt(
        "S-A-1",
        IBAN_A,
        "10000.00",
        "9800.00",
        [
            _ntry("REF-1", "400.00", "CRDT", "2026-01-05", PAYER, "Hausgeld Januar"),
            _ntry("REF-2", "400.00", "CRDT", "2026-01-05", PAYER, "Hausgeld Januar"),
            _ntry("REF-3", "1000.00", "DBIT", "2026-01-10", IBAN_B, "Umbuchung Rücklage"),
        ],
    )
    doc_a = _upload(client, h, "a.xml", file_a)
    run = _ok(client.post(f"{B}/imports", json={"document_id": doc_a}, headers=h), 201)
    assert run["counts"]["new"] == 3
    assert run["counts"]["possible_duplicates"] == 1
    again = _ok(client.post(f"{B}/imports", json={"document_id": doc_a}, headers=h), 201)
    assert again["counts"]["new"] == 0
    assert again["counts"]["duplicates"] == 3
    txs = _ok(
        client.get(f"{B}/transactions", params={"bank_account_id": accounts[IBAN_A]}, headers=h)
    )
    credits = [Decimal(t["amount"]) for t in txs if Decimal(t["amount"]) > 0]
    assert sum(credits) == Decimal("800.00")  # neither 400,00 nor 1.600,00
    assert all(t["status"] == "new" for t in txs)
    assert txs[0]["counterpart_iban_suffix"] == PAYER[-4:]

    file_b = _camt(
        "S-B-1",
        IBAN_B,
        "20000.00",
        "21000.00",
        [_ntry("REF-B1", "1000.00", "CRDT", "2026-01-11", IBAN_A, "Umbuchung Rücklage")],
    )
    run_b = _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "b.xml", file_b)}, headers=h
        ),
        201,
    )
    assert run_b["counts"]["transfers"] == 1
    out = next(t for t in txs if t["amount"] == "-1000.00")
    paired = _ok(
        client.get(f"{B}/transactions", params={"bank_account_id": accounts[IBAN_B]}, headers=h)
    )[0]
    assert paired["transfer_pair_id"] == out["id"]

    # Without bank reference a hash match is kept for review, never dropped.
    no_ref = _camt(
        "S-A-2",
        IBAN_A,
        "9800.00",
        "10200.00",
        [
            _ntry(None, "200.00", "CRDT", "2026-01-20", PAYER, "Nachzahlung"),
            _ntry(None, "200.00", "CRDT", "2026-01-20", PAYER, "Nachzahlung"),
        ],
    )
    run_c = _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "c.xml", no_ref)}, headers=h
        ),
        201,
    )
    assert run_c["counts"]["new"] == 2
    review = _ok(client.get(f"{B}/transactions", params={"status": "needs_review"}, headers=h))
    assert len(review) == 1
    kept = _ok(
        client.post(
            f"{B}/transactions/{review[0]['id']}/review",
            json={"decision": "keep", "reason": "zwei Zahlungen laut Auszug"},
            headers=h,
        )
    )
    assert kept["status"] == "new"
    assert (
        client.post(
            f"{B}/transactions/{review[0]['id']}/review",
            json={"decision": "keep", "reason": "nochmal"},
            headers=h,
        ).status_code
        == 409
    )

    # B09: statement balances: 10.000 + 400 + 400 - 1.000 = 9.800; 9.800 + 400 = 10.200.
    rec = _ok(client.get(f"{B}/accounts/{accounts[IBAN_A]}/reconciliation", headers=h))
    assert [Decimal(r["statement_difference"]) for r in rec] == [Decimal("0.00"), Decimal("0.00")]
    wrong = _camt(
        "S-B-2",
        IBAN_B,
        "21000.00",
        "21500.00",
        [_ntry("REF-B2", "100.00", "CRDT", "2026-01-25", PAYER, "x")],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "d.xml", wrong)}, headers=h
        ),
        201,
    )
    rec_b = _ok(client.get(f"{B}/accounts/{accounts[IBAN_B]}/reconciliation", headers=h))
    assert Decimal(rec_b[-1]["statement_difference"]) == Decimal("400.00")  # shown, not booked away

    # Ledger comparison when the bank account is linked to a ledger account.
    template = _ok(client.post("/api/v1/accounting/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            "/api/v1/accounting/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/accounting/ledgers/{ledger['id']}/accounts",
            json={
                "number": "001210",
                "name": "Bank A",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": accounts[IBAN_A],
            },
            headers=h,
        ),
        201,
    )
    rec2 = _ok(client.get(f"{B}/accounts/{accounts[IBAN_A]}/reconciliation", headers=h))
    assert Decimal(rec2[0]["ledger_balance"]) == Decimal("0")
    assert Decimal(rec2[0]["ledger_difference"]) == Decimal("9800.00")

    # Unknown account and invalid files are refused.
    foreign = _camt("S-X", "DE02500105170137075030", "0", "0", [])
    bad = client.post(
        f"{B}/imports", json={"document_id": _upload(client, h, "x.xml", foreign)}, headers=h
    )
    assert bad.status_code == 422
    junk = client.post(
        f"{B}/imports",
        json={"document_id": _upload(client, h, "j.xml", b"<a>kein camt</a>")},
        headers=h,
    )
    assert junk.status_code == 422

    # Connectors without contract: not configured, credentials never returned.
    conn = _ok(
        client.post(
            f"{B}/connections",
            json={
                "connector": "ebics",
                "bank_name": "Hausbank",
                "credentials": "geheim",
                "consent_valid_until": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    assert conn["status"] == "not_configured"
    assert conn["has_credentials"] is True
    assert "credentials" not in conn
    result = asyncio.run(sync_all_once(_settings(database, redis_url)))
    assert result["not_configured"] >= 1
    assert result["consent_warnings"] >= 1
    runs = _ok(client.get(f"{B}/runs", headers=h))
    assert any(r["source"] == "ebics" and r["errors"] for r in runs)

    clerk = bearer(login(client, world, "m11clerk"))
    assert client.get(f"{B}/transactions", headers=clerk).status_code == 403


# A28 (M11-02): MT940 upload on the same import path as CAMT.053 -----------------------------

IBAN_MT = "DE91100000000123456789"


def _mt940(statement_no: str, iban: str, opening: str, closing: str, lines: list[str]) -> bytes:
    body = "\r\n".join(lines)
    return (
        f":20:STARTUMSE\r\n:25:{iban}\r\n:28C:{statement_no}\r\n:60F:C260131EUR{opening}\r\n"
        f"{body}\r\n:62F:C260228EUR{closing}\r\n-\r\n"
    ).encode("latin-1")


def _line61(day: str, dc: str, amount: str, purpose: str, bank_ref: str | None = None) -> str:
    ref = f"//{bank_ref}" if bank_ref else ""
    # value date 26MMDD, entry date MMDD, D/C, funds code R, amount with comma, type NTRF
    return (
        f":61:26{day}{day}{dc}R{amount}NTRFNONREF{ref}\r\n"
        f":86:166?00SEPA-GUTSCHRIFT?20EREF+E-{day}?21SVWZ+{purpose}?30COBADEFFXXX?31{PAYER}"
        "?32Maria Muster?33mann"
    )


async def _second_tenant(settings: Any) -> World:
    """Own tenant with its own administrator for the tenant separation check."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        b, _ = await services.provision_tenant(factory, slug=f"bk2-{RUN}", name=f"Bank B {RUN}")
        world = World(tenant_a=b, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m11adminb"), display_name="b", password=PASSWORD
        )
        world.users["m11adminb"] = uid
        await services.add_member(
            factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_b(database: Database, redis_url: str) -> World:
    return asyncio.run(_second_tenant(_settings(database, redis_url)))


def test_mt940_import_reimport_and_tenant_separation(
    client: TestClient, world: World, world_b: World
) -> None:
    h = bearer(login(client, world, "m11admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "712", "name": "Swifthaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": IBAN_MT,
                "holder": "GdWE Swifthaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]

    # Two real identical payments (D05): one with a bank reference, one without (derived).
    file_1 = _mt940(
        "00020/001",
        IBAN_MT,
        "1000,00",
        "1700,00",
        [
            _line61("0203", "C", "400,00", "Hausgeld Februar", "BR-MT-1"),
            _line61("0203", "C", "400,00", "Hausgeld Februar"),
            _line61("0210", "D", "100,00", "Entgelt"),
        ],
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("auszug.sta", file_1, "text/plain")},
            headers=h,
        ),
        201,
    )["id"]
    run = _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)
    assert run["source"] == "file:mt940"
    assert run["counts"]["new"] == 3
    assert run["counts"]["statements"] == 1
    assert run["counts"]["possible_duplicates"] == 1  # hash hint only, both are kept
    txs = _ok(client.get(f"{B}/transactions", params={"bank_account_id": account}, headers=h))
    assert sorted(Decimal(t["amount"]) for t in txs) == [
        Decimal("-100.00"),
        Decimal("400.00"),
        Decimal("400.00"),
    ]
    assert all(t["status"] == "new" for t in txs)  # references present: nothing for review
    credit = next(t for t in txs if t["amount"] == "400.00" and t["purpose"] == "Hausgeld Februar")
    assert credit["counterpart_name"] == "Maria Mustermann"
    assert credit["counterpart_iban_suffix"] == PAYER[-4:]
    assert credit["end_to_end_id"] == "E-0203"

    # Re-import of the same file: no additional effect (B08, D05).
    again = _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)
    assert again["counts"]["new"] == 0
    assert again["counts"]["duplicates"] == 3
    assert again["counts"]["statements"] == 0
    rec = _ok(client.get(f"{B}/accounts/{account}/reconciliation", headers=h))
    assert [Decimal(r["statement_difference"]) for r in rec] == [Decimal("0.00")]

    # Content based detection: an MT940 uploaded with an .xml name is still parsed as MT940,
    # a non MT940 text file with .sta name is refused with a German message.
    file_2 = _mt940(
        "00021/001",
        IBAN_MT,
        "1700,00",
        "1750,00",
        [_line61("0220", "C", "50,00", "Nachzahlung", "BR-MT-2")],
    )
    doc_2 = _upload(client, h, "auszug.xml", file_2)
    assert (
        _ok(client.post(f"{B}/imports", json={"document_id": doc_2}, headers=h), 201)["counts"][
            "new"
        ]
        == 1
    )
    junk = client.post(
        f"{B}/imports",
        json={
            "document_id": _ok(
                client.post(
                    "/api/v1/documents",
                    files={"file": ("k.sta", b"kein auszug", "text/plain")},
                    headers=h,
                ),
                201,
            )["id"]
        },
        headers=h,
    )
    assert junk.status_code == 422
    assert "MT940" in junk.json()["detail"]

    # Tenant separation: the other tenant neither sees the document nor the transactions.
    hb = bearer(login(client, world_b, "m11adminb"))
    assert client.post(f"{B}/imports", json={"document_id": doc}, headers=hb).status_code == 404
    assert (
        _ok(client.get(f"{B}/transactions", params={"bank_account_id": account}, headers=hb)) == []
    )
    assert client.get(f"{B}/accounts/{account}/reconciliation", headers=hb).status_code == 404
