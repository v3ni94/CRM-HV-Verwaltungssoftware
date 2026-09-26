"""M11-finapi Stage 3: invoice to bank transaction matching, payment proposal (draft only,
gate G2 stays closed, never initiates), ticket "Als Rechnung zuordnen" with Drive year-folder
filing via a fake Drive store (no real network)."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any, cast

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
T = "/api/v1"
KNOWN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"im-{RUN}", name=f"Match {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("im-admin", "tenant_admin"),
            ("im-acc", "accountant_no_banking"),
            ("im-approver", "tenant_admin"),
        ]:
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


def _ntry(ref: str, amount: str, ind: str, day: str, iban: str, purpose: str) -> str:
    party = "Dbtr" if ind == "CRDT" else "Cdtr"
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt><AcctSvcrRef>{ref}</AcctSvcrRef>
<NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
<RltdPties><{party}><Nm>Zahlungsempfänger</Nm></{party}><{party}Acct><Id><IBAN>{iban}</IBAN></Id></{party}Acct></RltdPties>
<RmtInf><Ustrd>{purpose}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def _camt(stmt_id: str, iban: str, opening: str, closing: str, entries: list[str]) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>
<GrpHdr><MsgId>M-{stmt_id}</MsgId><CreDtTm>2026-02-01T08:00:00</CreDtTm></GrpHdr>
<Stmt><Id>{stmt_id}</Id><Acct><Id><IBAN>{iban}</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{opening}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">{closing}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-31</Dt></Dt></Bal>
{"".join(entries)}</Stmt></BkToCstmrStmt></Document>""".encode()


def _upload(
    c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str = "application/xml"
) -> str:
    return str(
        _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h), 201)["id"]
    )


def _review_all(c: TestClient, h: dict[str, str], inv: str) -> Any:
    out = None
    for step in ("completeness", "factual", "arithmetic_tax"):
        out = _ok(
            c.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": "ok", "reason": f"{step} geprüft"},
                headers=h,
            ),
            201,
        )
    return out


def _bank_iban(number: str) -> str:
    """A distinct, checksum-valid DE IBAN per test property (mod-97, ISO 7064): file import
    matches a statement's account purely by IBAN (`mhvp.banking.services.import_file`), so
    reusing one IBAN across tests would silently attribute a transaction to the wrong
    property's bank account."""
    bban = f"030000000000{number:>06}"
    rearranged = bban + "DE00"
    digits = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - (int(digits) % 97)
    return f"DE{check:02d}{bban}"


def _setup_property_and_ledger(
    client: TestClient, h: dict[str, str], number: str
) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": "Rechnungshaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    iban = _bank_iban(number)
    bank_account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": iban,
                "holder": "GdWE Rechnungshaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    return {
        "property": prop,
        "hoa": hoa,
        "ledger": ledger,
        "bank_account": bank_account,
        "iban": iban,
    }


def _post_invoice(
    client: TestClient,
    h_creator: dict[str, str],
    h_releaser: dict[str, str],
    ledger: str,
    number: str,
    h_approver: dict[str, str],
) -> dict[str, Any]:
    """Full M14 flow (see test_m14_invoices): create, review, release (by a second person),
    post -- so the resulting invoice is `PostingStatus.POSTED`, the precondition for
    `mhvp.banking.invoice_matching.match_invoice`."""
    acc = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h_creator))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Handwerker {number} GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h_creator,
        ),
        201,
    )["id"]
    # M5-01: the provider IBAN counts as master data only after a second person released it.
    approve_bank_accounts(client, h_approver, provider)
    body = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": number,
        "invoice_date": "2026-02-01",
        "due_date": "2026-02-15",
        "service_from": "2026-01-01",
        "service_to": "2026-01-31",
        "net": "1000.00",
        "vat": "190.00",
        "gross": "1190.00",
        "payee_iban": KNOWN,
        "order_reference": "AUF-2026-01",
        "lines": [
            {
                "account_id": acc["040100"],
                "net": "1000.00",
                "vat_percent": "19",
                "vat": "190.00",
                "text": "Handwerkerleistung",
            }
        ],
    }
    inv = _ok(client.post(f"{A}/invoices", json=body, headers=h_creator), 201)
    _review_all(client, h_creator, inv["id"])
    _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=h_releaser))
    return cast(
        dict[str, Any], _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h_creator))
    )


def test_match_by_amount_and_invoice_number(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "im-admin"))
    acc = bearer(login(client, world, "im-acc"))
    setup = _setup_property_and_ledger(client, h, "901")
    inv = _post_invoice(
        client, h, acc, setup["ledger"], "R-900", bearer(login(client, world, "im-approver"))
    )

    camt = _camt(
        "S-INV-1",
        setup["iban"],
        "5000.00",
        "3810.00",
        [_ntry("REF-INV-1", "1190.00", "DBIT", "2026-02-10", KNOWN, "Zahlung Rechnung R-900")],
    )
    doc = _upload(client, h, "auszug.xml", camt)
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)

    result = _ok(client.post(f"{B}/invoice-matching/{inv['id']}/match", headers=h))
    assert len(result["matches"]) == 1
    assert result["matches"][0]["match_basis"] == "amount_and_number"
    assert result["proposal"] is None

    # Reading the links back gives the same one, and a repeated match call is idempotent
    # (no duplicate link for the same transaction).
    again = _ok(client.post(f"{B}/invoice-matching/{inv['id']}/match", headers=h))
    assert len(again["matches"]) == 1
    read_back = _ok(client.get(f"{B}/invoice-matching/{inv['id']}", headers=h))
    assert len(read_back) == 1
    assert read_back[0]["id"] == result["matches"][0]["id"]


def test_match_by_amount_and_iban_without_number_in_purpose(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "im-admin"))
    acc = bearer(login(client, world, "im-acc"))
    setup = _setup_property_and_ledger(client, h, "905")
    inv = _post_invoice(
        client, h, acc, setup["ledger"], "R-904", bearer(login(client, world, "im-approver"))
    )

    camt = _camt(
        "S-INV-2",
        setup["iban"],
        "5000.00",
        "3810.00",
        [_ntry("REF-INV-2", "1190.00", "DBIT", "2026-02-11", KNOWN, "Handwerkerrechnung Februar")],
    )
    doc = _upload(client, h, "auszug2.xml", camt)
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)

    result = _ok(client.post(f"{B}/invoice-matching/{inv['id']}/match", headers=h))
    assert len(result["matches"]) == 1
    assert result["matches"][0]["match_basis"] == "amount_and_iban"


def test_unmatched_invoice_creates_draft_proposal_never_initiates(
    client: TestClient, world: World
) -> None:
    """Core Stage 3 guarantee: when nothing matches, a payment PROPOSAL is a draft
    `PaymentOrder` only ("vorbereitet, nicht ausgeführt"); no provider/bank is ever asked to
    pay (gate G2 stays closed: `mhvp.banking.invoice_matching.propose_payment` only calls the
    existing `payments.order_from_invoice`, which never exports or submits)."""
    h = bearer(login(client, world, "im-admin"))
    acc = bearer(login(client, world, "im-acc"))
    setup = _setup_property_and_ledger(client, h, "902")
    inv = _post_invoice(
        client, h, acc, setup["ledger"], "R-901", bearer(login(client, world, "im-approver"))
    )

    without_body = _ok(client.post(f"{B}/invoice-matching/{inv['id']}/match", headers=h))
    assert without_body["matches"] == []
    assert without_body["proposal"] is None
    assert "Zahlungsvorschlag" in without_body["proposal_note"]

    with_body = _ok(
        client.post(
            f"{B}/invoice-matching/{inv['id']}/match",
            json={
                "bank_account_id": setup["bank_account"],
                "execution_date": "2026-02-20",
            },
            headers=h,
        )
    )
    assert with_body["proposal"] is not None
    assert with_body["proposal"]["status"] == "draft"
    assert with_body["proposal_note"] == "vorbereitet, nicht ausgeführt"

    orders = _ok(client.get(f"{B}/payment-orders", params={"status": "draft"}, headers=h))
    assert any(o["invoice_id"] == inv["id"] for o in orders)
    # Never anything beyond draft: no export/approve call happened in this flow, so the batch
    # list stays empty and G2's submit/export path was never reached.
    assert all(o["status"] == "draft" for o in orders if o["invoice_id"] == inv["id"])


def test_get_invoice_matches_starts_empty(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "im-admin"))
    acc = bearer(login(client, world, "im-acc"))
    setup = _setup_property_and_ledger(client, h, "903")
    inv = _post_invoice(
        client, h, acc, setup["ledger"], "R-902", bearer(login(client, world, "im-approver"))
    )
    matches = _ok(client.get(f"{B}/invoice-matching/{inv['id']}", headers=h))
    assert matches == []


def test_attach_invoice_to_ticket_files_into_drive_year_folder(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fake Drive store (no real network): the ticket becomes category "invoice" and the
    invoice's original document is filed under "<Objektordner>/<Jahr>"."""
    from mhvp.documents import property_filing as pf

    calls: list[dict[str, Any]] = []

    class _Result:
        ref = "fake-drive-file-id-1"

    class FakeDriveStore:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def file_in_property_year_folder(self, data: bytes, meta: Any, year: int) -> Any:
            calls.append({"year": year, "property_folder": meta.property_folder, "size": len(data)})
            return _Result()

    monkeypatch.setattr(pf, "GoogleDriveStore", FakeDriveStore)

    h = bearer(login(client, world, "im-admin"))
    acc = bearer(login(client, world, "im-acc"))
    setup = _setup_property_and_ledger(client, h, "904")

    # Original document uploaded and set on the invoice before release (payment-relevant
    # fields do not include document_id, so this does not void the release/reviews below).
    doc_id = _upload(
        client, h, "rechnung.pdf", b"%PDF-1.4 fake invoice pdf", mime="application/pdf"
    )
    acc_map = {
        a["number"]: a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{setup['ledger']}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": "Handwerker R-903 GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, bearer(login(client, world, "im-approver")), provider)
    body = {
        "ledger_id": setup["ledger"],
        "provider_contact_id": provider,
        "number": "R-903",
        "invoice_date": "2026-02-01",
        "due_date": "2026-02-15",
        "service_from": "2026-01-01",
        "service_to": "2026-01-31",
        "net": "1000.00",
        "vat": "190.00",
        "gross": "1190.00",
        "payee_iban": KNOWN,
        "order_reference": "AUF-2026-01",
        "document_id": doc_id,
        "lines": [
            {
                "account_id": acc_map["040100"],
                "net": "1000.00",
                "vat_percent": "19",
                "vat": "190.00",
                "text": "Handwerkerleistung",
            }
        ],
    }
    inv = _ok(client.post(f"{A}/invoices", json=body, headers=h), 201)
    _review_all(client, h, inv["id"])
    _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=acc))
    inv = _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h))

    ticket = _ok(
        client.post(
            f"{T}/tickets",
            json={
                "property_id": setup["property"]["id"],
                "title": "Rechnung Handwerker",
                "public_description": "Rechnung zur Prüfung",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.put(
            "/api/v1/dms-connections/google_drive",
            json={
                "enabled": True,
                "options": {"root_folder_id": "root-1", "client_id": "cid"},
                "secret": json.dumps({"client_secret": "sec", "refresh_token": "ref"}),
            },
            headers=h,
        )
    )
    attached = _ok(
        client.post(
            f"{T}/tickets/{ticket['id']}/attach-invoice", json={"invoice_id": inv["id"]}, headers=h
        )
    )
    assert attached["category"] == "invoice"
    assert len(calls) == 1
    assert calls[0]["year"] == 2026

    # Idempotent: a repeated attach does not re-upload.
    _ok(
        client.post(
            f"{T}/tickets/{ticket['id']}/attach-invoice", json={"invoice_id": inv["id"]}, headers=h
        )
    )
    assert len(calls) == 1
