"""Package Q08 (M8-02, M8-03, M8-04, M8-06, M8-07) with synthetic exports: SEPA overview,
chart of accounts, historical bank transactions with journal assignment, document index,
historical tickets and open items. Every expected figure is fixed in the comments (rule 0.1.8).
Column headers are invented for the test and make no statement about real Immoware24 exports
(13.1, M8-01 stays open)."""

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
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BASE, BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import A, _accounts, _prop
from tests.integration.test_m11_banking import IBAN_A

pytestmark = pytest.mark.integration
M = "/api/v1/imports/migration"
HISTORY = f"{BASE}/history"
IBAN_FOREIGN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q08-{RUN}", name=f"Q08 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q08b-{RUN}", name=f"Q08b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "q8admin": (a, "tenant_admin"),
            "q8reader": (a, "read_only"),
            "q8other": (b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _map(
    c: TestClient, h: dict[str, str], report: str, columns: dict[str, str], **maps: Any
) -> Any:
    return _ok(
        c.post(
            f"{BASE}/mappings",
            json={
                "report_type": report,
                "name": f"Q08 {report}",
                "columns": columns,
                "value_maps": maps,
            },
            headers=h,
        ),
        201,
    )


def _run(
    c: TestClient,
    h: dict[str, str],
    report: str,
    rows: list[list[Any]],
    columns: dict[str, str],
    *,
    name: str = "export.xlsx",
    **maps: Any,
) -> dict[str, Any]:
    """Stage, validate, test run (rolled back) and apply; returns the apply report."""
    source = _stage(c, h, report, name, _xlsx(rows), XLSX)
    mapping = _map(c, h, report, columns, **maps)
    _ok(
        c.post(
            f"{BASE}/files/{source['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        )
    )
    dry = _ok(c.post(f"{BASE}/files/{source['id']}/test-run", headers=h))
    applied = _ok(c.post(f"{BASE}/files/{source['id']}/apply", headers=h), 201)
    assert dry["counts"] == applied["report"]["apply"]["counts"]  # the test run shows the result
    return applied["report"]["apply"]  # type: ignore[no-any-return]


def _setup(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    """Property 881 (HOA) with ledger (cut off 31.01.2026), owner contact K881 with IBAN,
    ownership contract and the HOA bank account."""
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)["id"]
    prop = _prop(c, h, "881", "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, prop["id"], "01")
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Erika",
                "last_name": f"Eigner{RUN}",
                "external_ids": {"immoware24": "K881"},
                "bank_accounts": [{"iban": IBAN_FOREIGN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    contract = _ok(
        c.post(
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
    ledger = _ok(
        c.post(
            f"{A}/ledgers",
            json={
                "legal_entity_id": hoa,
                "template_id": template,
                "migration_cutoff": "2026-01-31",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": IBAN_A,
                "holder": "GdWE 881",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    return {"prop": prop, "ledger": ledger["id"], "contract": contract, "unit": unit}


def test_fields_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q8admin"))
    reader = bearer(login(client, world, "q8reader"))
    fields = _ok(client.get(f"{BASE}/fields", headers=h))
    required = {
        rt: {f["name"] for f in fields[rt] if f["required"]}
        for rt in (
            "sepa_overview",
            "chart_of_accounts",
            "bank_history",
            "document_index",
            "ticket_history",
            "open_items",
        )
    }
    assert required["chart_of_accounts"] == {
        "property_number",
        "number",
        "name",
        "category",
        "account_type",
    }
    assert required["open_items"] == {
        "property_number",
        "kind",
        "source_item_id",
        "original_amount",
    }
    assert "due_day" in required["sepa_overview"]
    # Unknown target field in a template: 422; missing required field: 422 at validation.
    bad = client.post(
        f"{BASE}/mappings",
        json={"report_type": "open_items", "name": "x", "columns": {"erfunden": "A"}},
        headers=h,
    )
    assert bad.status_code == 422
    source = _stage(
        client, h, "open_items", "p.xlsx", _xlsx([["Objekt", "Posten"], ["881", "P1"]]), XLSX
    )
    incomplete = _map(client, h, "open_items", {"property_number": "Objekt"})
    response = client.post(
        f"{BASE}/files/{source['id']}/validate", json={"mapping_id": incomplete["id"]}, headers=h
    )
    assert response.status_code == 422
    assert "Pflichtfelder ohne Zuordnung" in response.text
    assert client.post(f"{BASE}/files/{source['id']}/apply", headers=reader).status_code == 403
    assert client.post(f"{BASE}/files/{source['id']}/test-run", headers=reader).status_code == 403


def test_q08_history_imports(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q8admin"))
    reader = bearer(login(client, world, "q8reader"))
    other = bearer(login(client, world, "q8other"))
    ctx = _setup(client, h)
    ledger = ctx["ledger"]
    acc_rows = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    existing = next(a for a in acc_rows if a["number"] == "001200")
    accounts = _accounts(client, h, ledger)
    debtor = next(n for n in accounts if n.startswith("09") and n not in ("009000", "009999"))

    # M8-03 chart of accounts: 001200 as in the ledger (unchanged), 001200 style clash with
    # another name (conflict), a new account 99 -> 000099 (created, review status entwurf),
    # unknown object and unknown category (invalid).
    chart_cols = {
        "property_number": "Objekt",
        "number": "Konto",
        "name": "Bezeichnung",
        "category": "Kategorie",
        "account_type": "Art",
    }
    chart_rows: list[list[Any]] = [
        ["Objekt", "Konto", "Bezeichnung", "Kategorie", "Art"],
        ["881", "1200", existing["name"], existing["category"], existing["type"]],
        ["881", "8000", "Anderer Name", existing["category"], existing["type"]],
        ["881", "99", "Testkonto Altsystem", "Kosten", "Aufwand"],
        ["999", "99", "Fremd", "Kosten", "Aufwand"],
        ["881", "98", "Ohne Kategorie", "unbekannt", "Aufwand"],
    ]
    maps = {"category": {"Kosten": "cost"}, "account_type": {"Aufwand": "expense"}}
    chart = _run(client, h, "chart_of_accounts", chart_rows, chart_cols, **maps)
    # 8000 exists in the default template: name differs -> conflict; object 999 is invalid at
    # apply; the unknown category stays invalid at validation and is not applied at all.
    assert chart["counts"] == {"created": 1, "unchanged": 1, "conflict": 1, "invalid": 1}
    created = next(
        a
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["number"] == "000099"
    )
    assert created["name"] == "Testkonto Altsystem"
    again = _run(client, h, "chart_of_accounts", chart_rows, chart_cols, name="again.xlsx", **maps)
    assert again["counts"] == {"unchanged": 2, "conflict": 1, "invalid": 1}  # idempotent

    # M8-07 open items (ledger of 881, cut off 31.01.2026):
    #   R1 receivable due 05.01.2026 300,00 paid 100,00 -> open 200,00
    #   R2 receivable due 05.02.2026 300,00 paid 0 -> open 300,00
    #   C1 credit 50,00, D1 deposit 1.500,00, B1 reserve 2.000,50, L1 loan 10.000,00,
    #   S1 special levy due 01.03.2026 4.000,00 paid 1.000,00 -> open 3.000,00
    # Invalid: paid above original, receivable without due date, open amount not matching.
    oi_cols = {
        "property_number": "Objekt",
        "kind": "Art",
        "source_item_id": "Posten",
        "unit_number": "Einheit",
        "contact_external_id": "Kontakt",
        "original_due_date": "Fällig",
        "original_amount": "Betrag",
        "paid_amount": "Bezahlt",
        "open_amount": "Offen",
        "resolution_ref": "Beschluss",
    }
    oi_rows: list[list[Any]] = [
        [
            "Objekt",
            "Art",
            "Posten",
            "Einheit",
            "Kontakt",
            "Fällig",
            "Betrag",
            "Bezahlt",
            "Offen",
            "Beschluss",
        ],
        ["881", "F", "R1", "01", "K881", "05.01.2026", "300,00", "100,00", "200,00", None],
        ["881", "F", "R2", "01", "K881", "05.02.2026", "300,00", None, None, None],
        ["881", "G", "C1", "01", "K881", None, "50,00", None, None, None],
        ["881", "K", "D1", "01", "K881", None, "1.500,00", None, None, None],
        ["881", "R", "B1", None, None, None, "2.000,50", None, None, None],
        ["881", "D", "L1", None, None, None, "10.000,00", None, None, None],
        ["881", "S", "S1", "01", "K881", "01.03.2026", "4.000,00", "1.000,00", None, "TOP 5 v2"],
        ["881", "F", "E1", "01", "K881", "05.01.2026", "10,00", "20,00", None, None],
        ["881", "F", "E2", "01", "K881", None, "10,00", None, None, None],
        ["881", "F", "E3", "01", "K881", "05.01.2026", "10,00", "4,00", "7,00", None],
    ]
    kind_map = {
        "F": "receivable",
        "G": "credit",
        "K": "deposit",
        "R": "reserve",
        "D": "loan",
        "S": "special_levy",
    }
    items = _run(client, h, "open_items", oi_rows, oi_cols, kind=kind_map)
    assert items["counts"] == {"created": 7, "invalid": 3}
    assert items["sums"]["created_amount"] == "18150.50"  # 300+300+50+1500+2000,50+10000+4000
    assert items["sums"]["source_amount"] == "18180.50"  # plus E1, E2, E3 (10,00 each)
    messages = " ".join(m for p in items["problems"] for m in p["messages"])
    assert "übersteigt" in messages
    assert "Ursprungsfälligkeit fehlt" in messages
    assert "erwartet 6.00" in messages or "erwartet 6" in messages
    summary = _ok(
        client.get(f"{HISTORY}/open-items/summary", params={"ledger_id": ledger}, headers=h)
    )
    kinds = summary["kinds"]
    assert kinds["receivable"] == {
        "count": 2,
        "original": "600.00",
        "paid": "100.00",
        "open": "500.00",
    }
    assert kinds["special_levy"]["open"] == "3000.00"
    assert kinds["reserve"]["open"] == "2000.50"
    listed = _ok(client.get(f"{HISTORY}/open-items", params={"kind": "receivable"}, headers=h))
    assert [i["source_item_id"] for i in listed] == ["R1", "R2"]
    assert listed[0]["original_due_date"] == "2026-01-05"
    repeat = _run(client, h, "open_items", oi_rows, oi_cols, name="again.xlsx", kind=kind_map)
    assert repeat["counts"] == {"unchanged": 7, "invalid": 3}
    # RLS and permissions: other tenant gets 404 / empty; changed values are a conflict.
    assert (
        client.get(
            f"{HISTORY}/open-items/summary", params={"ledger_id": ledger}, headers=other
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{HISTORY}/open-items", headers=other)) == []
    assert client.get(f"{HISTORY}/open-items", headers=reader).status_code == 200
    changed = [
        oi_rows[0],
        ["881", "F", "R1", "01", "K881", "05.01.2026", "301,00", "100,00", None, None],
    ]
    conflict = _run(client, h, "open_items", changed, oi_cols, name="c.xlsx", kind=kind_map)
    assert conflict["counts"] == {"conflict": 1}

    # M8-04 journal of the ledger (J2 booked) and historical bank transactions.
    _ok(
        client.post(
            f"{M}/ledgers/{ledger}/journal",
            json={
                "source_file_id": _stage(
                    client,
                    h,
                    "journal",
                    "journal.xlsx",
                    _xlsx(
                        [
                            [
                                "Buchungsnummer",
                                "Objekt",
                                "Konto",
                                "Datum",
                                "Betrag",
                                "Buchungstext",
                                "Beleg",
                            ],
                            ["J2", "881", "1200", "10.01.2026", "200,00", "Zahlung", "KA-1"],
                            ["J2", "881", debtor, "10.01.2026", "-200,00", "Zahlung", "KA-1"],
                        ]
                    ),
                    XLSX,
                )["id"],
                "year": 2026,
                "year_complete": False,
            },
            headers=h,
        )
    )
    bank_cols = {
        "property_number": "Objekt",
        "iban": "IBAN",
        "booking_date": "Datum",
        "amount": "Betrag",
        "purpose": "Zweck",
        "bank_reference": "Referenz",
        "journal_entry_id": "Buchung",
    }
    bank_rows: list[list[Any]] = [
        ["Objekt", "IBAN", "Datum", "Betrag", "Zweck", "Referenz", "Buchung"],
        ["881", IBAN_A, "10.01.2026", "200,00", "Zahlung Eigner", None, "J2"],
        ["881", IBAN_A, "10.01.2026", "200,00", "Zahlung Eigner", None, None],
        ["881", IBAN_A, "12.01.2026", "-75,50", "Reparatur", "REF3", "J9"],
        ["881", IBAN_A, "15.02.2026", "10,00", "nach Stichtag", None, None],
        ["881", IBAN_FOREIGN, "10.01.2026", "10,00", "fremdes Konto", None, None],
    ]
    bank = _run(client, h, "bank_history", bank_rows, bank_cols)
    # Two equal payments without reference stay two transactions (D05), one with reference.
    assert bank["counts"] == {"created": 3, "invalid": 2}
    assert bank["sums"]["created_amount"] == "324.50"  # 200,00 + 200,00 - 75,50
    account_id = _ok(
        client.get(f"/api/v1/properties/{ctx['prop']['id']}/bank-accounts", headers=h)
    )[0]["id"]
    txs = _ok(
        client.get(
            "/api/v1/banking/transactions", params={"bank_account_id": account_id}, headers=h
        )
    )
    assert len(txs) == 3
    assert {t["status"] for t in txs} == {"ignored"}  # history: never matched or posted
    assert _ok(client.get(f"{A}/ledgers/{ledger}/entries", headers=h)) == []  # no live posting
    links = _ok(client.get(f"{HISTORY}/bank-links", headers=h))
    assert len(links) == 2  # J2 found, J9 not yet imported
    open_links = _ok(client.get(f"{HISTORY}/bank-links", params={"open_only": True}, headers=h))
    assert [link["source_entry_id"] for link in open_links] == ["J9"]
    bank_again = _run(client, h, "bank_history", bank_rows, bank_cols, name="again.xlsx")
    assert bank_again["counts"] == {"unchanged": 3, "invalid": 2}
    assert (
        len(
            _ok(
                client.get(
                    "/api/v1/banking/transactions",
                    params={"bank_account_id": account_id},
                    headers=h,
                )
            )
        )
        == 3
    )
    assert _ok(client.get(f"{HISTORY}/bank-links", headers=other)) == []

    # M8-02 SEPA overview: quarterly on day 5 from 01.01.2026 with complete mandate evidence.
    evidence = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("mandat.pdf", b"%PDF-1.4 mandat", "application/pdf")},
            headers=h,
        ),
        201,
    )
    sepa_cols = {
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
    head = [
        "Objekt",
        "Einheit",
        "Kontakt",
        "Vertragsart",
        "Intervall",
        "Tag",
        "Ab",
        "Mandat",
        "Gläubiger",
        "Unterschrift",
        "IBAN",
        "Nachweis",
    ]
    sepa_rows: list[list[Any]] = [
        head,
        [
            "881",
            "01",
            "K881",
            "E",
            "quartalsweise",
            "5",
            "01.01.2026",
            f"M881-{RUN}"[:35],
            "DE98ZZZ09999999999",
            "02.01.2020",
            IBAN_FOREIGN,
            evidence["id"],
        ],
        [
            "881",
            "02",
            "K881",
            "E",
            "quartalsweise",
            "5",
            "01.01.2026",
            None,
            None,
            None,
            None,
            None,
        ],
        ["881", "01", "K881", "E", "monatlich", "40", "01.01.2026", None, None, None, None, None],
    ]
    sepa_maps = {
        "kind": {"E": "ownership"},
        "interval": {"quartalsweise": "quarterly", "monatlich": "monthly"},
    }
    sepa = _run(client, h, "sepa_overview", sepa_rows, sepa_cols, **sepa_maps)
    assert sepa["counts"] == {"created": 1, "invalid": 2}  # unit 02 missing, day 40
    contract = _ok(client.get(f"/api/v1/contracts/{ctx['contract']['id']}", headers=h))
    assert [(s["interval"], s["due_day"]) for s in contract["schedules"]] == [("quarterly", 5)]
    assert contract["direct_debit"] is True
    assert contract["sepa_mandate_id"] is not None
    mandates = _ok(client.get("/api/v1/sepa-mandates", headers=h))
    assert [m["reference"] for m in mandates] == [f"M881-{RUN}"[:35]]
    sepa_again = _run(
        client, h, "sepa_overview", sepa_rows, sepa_cols, name="again.xlsx", **sepa_maps
    )
    assert sepa_again["counts"] == {"unchanged": 1, "invalid": 2}
    assert len(_ok(client.get("/api/v1/sepa-mandates", headers=h))) == 1
    # Without evidence document the schedule is created but no mandate (note in the report).
    no_evidence = [
        head,
        [
            "881",
            "01",
            "K881",
            "E",
            "monatlich",
            "3",
            "01.04.2026",
            "M2",
            "DE98ZZZ09999999999",
            "02.01.2020",
            IBAN_FOREIGN,
            None,
        ],
    ]
    partial = _run(client, h, "sepa_overview", no_evidence, sepa_cols, name="n.xlsx", **sepa_maps)
    assert partial["counts"] == {"created": 1}
    assert "Mandat nicht angelegt" in partial["problems"][0]["messages"][0]
    assert len(_ok(client.get("/api/v1/sepa-mandates", headers=h))) == 1

    # M8-06 document index: the contract document of the DMS gets object and contract links.
    contract_doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("vertrag881.pdf", b"%PDF-1.4 vertrag", "application/pdf")},
            headers=h,
        ),
        201,
    )
    doc_cols = {
        "property_number": "Objekt",
        "document_ref": "Datei",
        "unit_number": "Einheit",
        "contract_ref": "Vertrag",
    }
    doc_rows: list[list[Any]] = [
        ["Objekt", "Datei", "Einheit", "Vertrag"],
        ["881", "vertrag881.pdf", "01", ctx["contract"]["number"]],
        ["881", "gibtesnicht.pdf", None, None],
    ]
    docs = _run(client, h, "document_index", doc_rows, doc_cols)
    assert docs["counts"] == {"created": 1, "invalid": 1}
    links = _ok(client.get(f"/api/v1/documents/{contract_doc['id']}", headers=h))["links"]
    assert {(link["entity_type"], link["role"]) for link in links} == {
        ("property", "attachment"),
        ("unit", "attachment"),
        ("contract", "attachment"),
    }
    docs_again = _run(client, h, "document_index", doc_rows, doc_cols, name="again.xlsx")
    assert docs_again["counts"] == {"unchanged": 1, "invalid": 1}

    # M8-06 historical tickets: read only; closing before opening is invalid.
    ticket_cols = {
        "source_ticket_id": "Nr",
        "property_number": "Objekt",
        "unit_number": "Einheit",
        "title": "Betreff",
        "status_text": "Status",
        "created_on": "Angelegt",
        "closed_on": "Erledigt",
    }
    ticket_rows: list[list[Any]] = [
        ["Nr", "Objekt", "Einheit", "Betreff", "Status", "Angelegt", "Erledigt"],
        ["T-1", "881", "01", "Heizung ausgefallen", "erledigt", "03.11.2025", "05.11.2025"],
        ["T-2", "881", None, "Wasserschaden", "offen", "10.12.2025", None],
        ["T-3", "881", None, "Falsch", "offen", "10.12.2025", "01.12.2025"],
    ]
    tickets = _run(client, h, "ticket_history", ticket_rows, ticket_cols)
    assert tickets["counts"] == {"created": 2, "invalid": 1}
    listed_tickets = _ok(
        client.get(f"{HISTORY}/tickets", params={"property_id": ctx["prop"]["id"]}, headers=reader)
    )
    assert [t["source_ticket_id"] for t in listed_tickets] == ["T-2", "T-1"]
    assert _ok(client.get(f"{HISTORY}/tickets", headers=other)) == []
    live = _ok(client.get("/api/v1/tickets", headers=h))
    assert all(
        t.get("title") != "Heizung ausgefallen"
        for t in (live if isinstance(live, list) else live.get("items", []))
    )
