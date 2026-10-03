"""AL02 (GAI-612 rest of AK10, rule 0.1.8): second independent tests for the annex D cases
D29, D32, D33 and D35 to D38. Each test uses its own scenario and its own predefined expected
values (computation in the docstring), not the numbers of the first test. Own test world with
the prefix ``al02-RUN``; only helper functions of other modules are reused, never their worlds."""

import asyncio
import json
from collections.abc import Iterator
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
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _upload
from tests.integration.test_m15_payments import PROVIDER, PROVIDER2, _link_contact, _twin_user

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
T = "/api/v1/tenant"
OWN = "DE12500105170648489890"


class _OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"al02-{RUN}", name=f"AL02 A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("al02admin", "tenant_admin"),
            ("al02acc", "accountant_banking"),
            ("al02approver", "tenant_admin"),
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
    return response.json() if response.content else None


def _ownership(c: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    return dict(
        _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": unit,
                    "party_id": party,
                    "start_date": "2021-03-01",
                    "title_transfer_date": "2021-03-01",
                    "acquisition_kind": "first_acquisition",
                },
                headers=h,
            ),
            201,
        )
    )


def _text_doc(c: TestClient, h: dict[str, str], title: str, entity: str, entity_id: str) -> str:
    links = json.dumps([{"entity_type": entity, "entity_id": entity_id}])
    doc = _ok(
        c.post(
            "/api/v1/documents",
            data={"title": title, "links": links},
            files={"file": (f"{title}.txt", title.encode(), "text/plain")},
            headers=h,
        ),
        201,
    )
    _ok(c.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": ["owner"]}, headers=h))
    return str(doc["id"])


def _pdf(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, f"%PDF-1.4 {name}".encode(), "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _portal_owner(
    c: TestClient, h: dict[str, str], world: World, name: str, party: str
) -> dict[str, str]:
    contact = _ok(c.get(f"/api/v1/parties/{party}", headers=h))["members"][0]["contact_id"]
    inv = _ok(
        c.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return bearer(login(c, world, name))


def _hoa(c: TestClient, h: dict[str, str], number: str, name: str) -> tuple[dict[str, Any], str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": name, "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    return prop, next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")


def _ledger(c: TestClient, h: dict[str, str], hoa: str) -> tuple[str, dict[str, str]]:
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    return str(ledger), acc


@pytest.mark.annex_d("D29")
def test_al02_second_owner_reads_gdwe_minutes_beyond_own_unit(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D29 second test: owner of unit 02 (the first test used unit 01) of a three unit
    community. Two GdWE documents (Gesamtabrechnung, Vertrag Hausmeister) are linked to the
    legal entity only, not to unit 02 or its contract. Expected: both listed and downloadable
    (content equals the title), no redaction note. The contract file of owner 03 and a GdWE
    document of a second community stay hidden (not listed, download 404)."""
    c, _ = clients
    h = bearer(login(c, world, "al02admin"))
    prop, hoa = _hoa(c, h, "291", f"AL02 D29 WEG {RUN}")
    _, other_hoa = _hoa(c, h, "292", f"AL02 D29 Fremd {RUN}")
    parties = {}
    contracts = {}
    for no in ("01", "02", "03"):
        unit = _unit(c, h, prop["id"], no)
        parties[no], _ = _party(c, h, f"AL02Eig{no}")
        contracts[no] = _ownership(c, h, unit, parties[no])
    titles = {
        "gesamt": f"Gesamtabrechnung 2025 {RUN}",
        "hausmeister": f"Hausmeistervertrag GdWE {RUN}",
        "eig03": f"Eigentuemerakte 03 {RUN}",
        "fremd": f"Beschluss Fremd-WEG {RUN}",
    }
    docs = {
        "gesamt": _text_doc(c, h, titles["gesamt"], "legal_entity", hoa),
        "hausmeister": _text_doc(c, h, titles["hausmeister"], "legal_entity", hoa),
        "eig03": _text_doc(c, h, titles["eig03"], "contract", contracts["03"]["id"]),
        "fremd": _text_doc(c, h, titles["fremd"], "legal_entity", other_hoa),
    }
    owner02 = _portal_owner(c, h, world, "al02owner02", parties["02"])
    listed = {d["id"] for d in _ok(c.get(f"{P}/documents", headers=owner02))}
    assert {docs["gesamt"], docs["hausmeister"]} <= listed
    assert docs["eig03"] not in listed
    assert docs["fremd"] not in listed
    for kind in ("gesamt", "hausmeister"):
        response = c.get(f"{P}/documents/{docs[kind]}/download", headers=owner02)
        assert response.status_code == 200, response.text
        assert response.content == titles[kind].encode()
        assert "X-Redaction-Note" not in response.headers
    for kind in ("eig03", "fremd"):
        assert c.get(f"{P}/documents/{docs[kind]}/download", headers=owner02).status_code == 404


@pytest.mark.annex_d("D32", "D33")
def test_al02_board_sample_three_positions_one_changed(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D32/D33 second test: three positions 45,50 and 310,25 (checked) and 64,25 (open).
    Report 1: checked 2 / 45,50 + 310,25 = 355,75; unchecked 1 / 64,25; selected 3; restricted
    status because of the open position, never a full audit claim. Then the invoice behind
    310,25 changes (net 320,00). Expected: that position outdated, the 45,50 position stays
    checked; report 2: checked 1 / 45,50, outdated = [position 2], status restricted by the
    change (no green overall status)."""
    c, _ = clients
    h = bearer(login(c, world, "al02admin"))
    _, hoa = _hoa(c, h, "321", f"AL02 D32 WEG {RUN}")
    ledger, acc = _ledger(c, h, hoa)
    _, auditor = _party(c, h, "AL02Beirat")
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"AL02 Gartenbau {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    bodies = []
    for no, amount in (("1", "45.50"), ("2", "310.25"), ("3", "64.25")):
        body = {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": f"AL02-D32-{no}",
            "invoice_date": "2025-09-15",
            "net": amount,
            "vat": "0.00",
            "gross": amount,
            "document_id": _pdf(c, h, f"al02-beleg-{no}.pdf"),
            "lines": [{"account_id": acc["040300"], "net": amount}],
        }
        body["id"] = _ok(c.post(f"{A}/invoices", json=body, headers=h), 201)["id"]
        bodies.append(body)
    audit = _ok(
        c.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Beiratsstichprobe AL02",
                "auditor_contact_ids": [auditor["id"]],
            },
            headers=h,
        ),
        201,
    )
    items = [
        _ok(
            c.post(
                f"{H}/audits/{audit['id']}/items",
                json={"document_id": b["document_id"], "amount": b["gross"]},
                headers=h,
            ),
            201,
        )
        for b in bodies
    ]
    for item in items[:2]:
        _ok(c.patch(f"{H}/audit-items/{item['id']}", json={"status": "checked"}, headers=h))
    first = _ok(c.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)["content"]
    assert (first["checked_count"], first["checked_value"]) == (2, "355.75")
    assert (first["unchecked_count"], first["unchecked_value"]) == (1, "64.25")
    assert first["selected"] == 3
    assert first["open"] == [items[2]["id"]]
    assert first["outdated"] == []
    assert "nicht die gesamte Abrechnung" in first["scope_note"]
    assert first["overall_status"].startswith("eingeschränkt")

    payload = {k: v for k, v in bodies[1].items() if k != "id"}
    changed = _ok(
        c.put(
            f"{A}/invoices/{bodies[1]['id']}",
            json=payload | {"net": "320.00", "gross": "320.00"},
            headers=h,
        )
    )
    assert changed["version"] == 2
    detail = _ok(c.get(f"{H}/audits/{audit['id']}", headers=h))
    status = {i["id"]: i["status"] for i in detail["items"]}
    assert status == {items[0]["id"]: "checked", items[1]["id"]: "outdated", items[2]["id"]: "open"}
    assert detail["outdated_reasons"] == {items[1]["id"]: "Rechnung nach Prüfung geändert"}
    assert detail["overall_status"] == "eingeschränkt: Positionen nach Prüfung geändert"
    second = _ok(c.post(f"{H}/audits/{audit['id']}/reports", json={}, headers=h), 201)
    assert second["version"] == 2
    c2 = second["content"]
    assert (c2["checked_count"], c2["checked_value"]) == (1, "45.50")
    assert c2["outdated"] == [items[1]["id"]]
    assert c2["overall_status"] == "eingeschränkt: Positionen nach Prüfung geändert"


def _debit(ref: str, amount: str, e2e: str) -> str:
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-03-10</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef><NtryDtls><TxDtls><Refs><EndToEndId>{e2e}</EndToEndId></Refs>
<RltdPties><Cdtr><Nm>Dienstleister</Nm></Cdtr><CdtrAcct><Id><IBAN>{PROVIDER}</IBAN></Id></CdtrAcct></RltdPties>
<RmtInf><Ustrd>Zahlung</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def _credit(ref: str, amount: str) -> str:
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-03-13</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef><NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
<RltdPties><Dbtr><Nm>Dienstleister</Nm></Dbtr><DbtrAcct><Id><IBAN>{PROVIDER}</IBAN></Id></DbtrAcct></RltdPties>
<RmtInf><Ustrd>Rueckgabe</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


@pytest.mark.annex_d("D35", "D36", "D37", "D38")
def test_al02_payment_iban_first_twin_first_partial_then_return(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """D35 to D38 second test with own numbers: invoice 750,00 and invoice 480,00.
    D35: the IBAN is changed first (the first test changed the amount first), then the amount
    to 700,00: each change after the full release sets the order back to draft, 0 approvals.
    D36: the twin account approves first (the first test let the original approve first);
    the original account of the same person is refused (MHVP-GATE-0002), approvals stay 1.
    D37: the 480,00 order is rejected: open items stay [480,00, 750,00]. The 750,00 order is
    executed with 250,00 only: open 750 - 250 = 500,00 -> [480,00, 500,00].
    D38: the 250,00 come back: reversal of the payment posting, open again [480,00, 750,00]."""
    client, gated = clients
    h = bearer(login(client, world, "al02admin"))
    acc_user = bearer(login(client, world, "al02acc"))
    prop, hoa = _hoa(client, h, "351", f"AL02 D35 WEG {RUN}")
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE AL02",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    ledger, _ = _ledger(client, h, hoa)
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
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AL02 Dienst {RUN} GmbH",
                "bank_accounts": [
                    {"iban": PROVIDER, "valid_from": "2020-01-01"},
                    {"iban": PROVIDER2, "valid_from": "2020-01-01"},
                ],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, bearer(login(client, world, "al02approver")), provider)

    def invoice(number: str, gross: str) -> str:
        body = {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": number,
            "invoice_date": "2026-03-01",
            "due_date": "2026-03-20",
            "service_from": "2026-02-01",
            "net": gross,
            "vat": "0.00",
            "gross": gross,
            "payee_iban": PROVIDER,
            "lines": [{"account_id": acc["040300"], "net": gross}],
        }
        inv = _ok(client.post(f"{A}/invoices", json=body, headers=h), 201)["id"]
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
        return str(inv)

    def new_order(inv: str) -> dict[str, Any]:
        return dict(
            _ok(
                client.post(
                    f"{B}/payment-orders",
                    json={
                        "invoice_id": inv,
                        "property_bank_account_id": bank,
                        "execution_date": "2026-03-09",
                    },
                    headers=h,
                ),
                201,
            )
        )

    def approve(order_id: str, headers: dict[str, str]) -> Any:
        return client.post(f"{B}/payment-orders/{order_id}/approve", headers=headers)

    def remaining() -> list[Decimal]:
        rows = _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h
            )
        )
        return sorted(Decimal(i["remaining"]) for i in rows)

    inv_a, inv_b = invoice("AL02-D35-A", "750.00"), invoice("AL02-D35-B", "480.00")
    assert remaining() == [Decimal("480.00"), Decimal("750.00")]

    # D35: IBAN first, then the amount; each change voids the full release.
    order = new_order(inv_a)
    _ok(approve(order["id"], h))
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"
    patched = _ok(
        client.patch(
            f"{B}/payment-orders/{order['id']}", json={"counterpart_iban": PROVIDER2}, headers=h
        )
    )
    assert (patched["status"], patched["approvals"]) == ("draft", 0)
    _ok(approve(order["id"], h))
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"
    patched = _ok(
        client.patch(f"{B}/payment-orders/{order['id']}", json={"amount": "700.00"}, headers=h)
    )
    assert (patched["status"], patched["approvals"], patched["amount"]) == ("draft", 0, "700.00")
    voided = [
        e["payload"]["fields"]
        for e in _ok(
            client.get(
                f"{T}/events",
                params={"type": "payment_order.approvals_invalidated", "page_size": 200},
                headers=h,
            )
        )
        if e["entity_id"] == order["id"]
    ]
    assert sorted(tuple(f) for f in voided) == [("amount",), ("counterpart_iban",)]

    # D36: twin account approves first, the original account of the same person is refused.
    asyncio.run(_twin_user(_settings(database, redis_url), world, "al02twin", "tenant_admin"))
    person = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Zwilling", "last_name": f"AL02 {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    _link_contact(world, "al02admin", person)
    _link_contact(world, "al02twin", person)
    twin = bearer(login(client, world, "al02twin"))
    assert _ok(approve(order["id"], twin))["approvals"] == 1
    refused = approve(order["id"], h)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-GATE-0002"
    drafts = _ok(client.get(f"{B}/payment-orders", params={"status": "draft"}, headers=h))
    assert next(o for o in drafts if o["id"] == order["id"])["approvals"] == 1
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"

    # D37 (a): the 480,00 order is rejected; nothing is settled.
    gh = bearer(login(gated, world, "al02acc"))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    ob = new_order(inv_b)
    _ok(approve(ob["id"], twin))
    _ok(approve(ob["id"], acc_user))
    batch_b = _ok(
        gated.post(f"{B}/payment-batches", json={"order_ids": [ob["id"]]}, headers=gh), 201
    )
    rejected = _ok(
        gated.post(
            f"{B}/payment-batches/{batch_b['id']}/bank-status",
            json={"status": "rejected", "reason": "AM04 Deckung"},
            headers=gh,
        )
    )
    assert rejected[0]["status"] == "rejected"
    assert remaining() == [Decimal("480.00"), Decimal("750.00")]

    # D37 (b): the 700,00 order of invoice A is executed with 250,00 only.
    batch_a = _ok(
        gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh), 201
    )
    _ok(
        gated.post(
            f"{B}/payment-batches/{batch_a['id']}/bank-status",
            json={"status": "submitted"},
            headers=gh,
        )
    )
    stmt = _camt(
        f"AL02-{RUN}-1",
        OWN,
        "3000.00",
        "2750.00",
        [_debit("AL02-P1", "250.00", order["end_to_end_id"])],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "al02-1.xml", stmt)}, headers=h
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    part = _ok(
        gated.post(
            f"{B}/payment-batches/{batch_a['id']}/bank-status",
            json={
                "status": "executed",
                "bank_transaction_id": txs["AL02-P1"]["id"],
                "reason": "Teilausführung",
            },
            headers=gh,
        )
    )
    assert (part[0]["status"], part[0]["executed_amount"]) == ("partially_executed", "250.00")
    assert remaining() == [Decimal("480.00"), Decimal("500.00")]

    # D38: the 250,00 come back; the payment posting is reversed, the payable open again.
    stmt2 = _camt(f"AL02-{RUN}-2", OWN, "2750.00", "3000.00", [_credit("AL02-R1", "250.00")])
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "al02-2.xml", stmt2)}, headers=h
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    returned = _ok(
        gated.post(
            f"{B}/payment-batches/{batch_a['id']}/bank-status",
            json={
                "status": "returned",
                "reason": "Empfänger unbekannt",
                "bank_transaction_id": txs["AL02-R1"]["id"],
            },
            headers=gh,
        )
    )
    assert returned[0]["status"] == "returned"
    assert remaining() == [Decimal("480.00"), Decimal("750.00")]
    original = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries/{part[0]['journal_entry_id']}", headers=h)
    )
    assert original["status"] == "posted"
    assert original["reversed_by_id"] is not None
    reversal = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries/{original['reversed_by_id']}", headers=h)
    )
    assert (reversal["kind"], reversal["reverses_id"]) == ("reversal", original["id"])
    assert [(ln["account_id"], ln["debit"], ln["credit"]) for ln in reversal["lines"]] == [
        (ln["account_id"], ln["credit"], ln["debit"]) for ln in original["lines"]
    ]
