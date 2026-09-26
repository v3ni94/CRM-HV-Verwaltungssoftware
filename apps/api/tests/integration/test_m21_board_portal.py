"""A52 (7.9.2 PÜ07, PÜ08; D32, D33; docs/rules/M21-07.md): portal role board with audit room.

The board member reads the engagement, its positions and only the receipts released through
the positions, records notes and questions, and the management answers traceably. The board
never posts, releases or changes a statement (no CRM right), sees no engagement of another
community and nothing of another tenant; a foreign engagement answers 404 without a hint. A
position changed after the check is shown outdated to the board as well (D33).
"""

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
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m10_ledger import _accounts, _book, _entry, _line

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
ACC = "/api/v1/accounting"
P = "/api/v1/portal"
B = "/api/v1/portal/board"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bd-{RUN}", name=f"Beirat {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"bd2-{RUN}", name=f"Beirat B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("bdadmin", a), ("bdadmin_b", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


def _doc(c: TestClient, h: dict[str, str], name: str, content: bytes) -> str:
    files = {"file": (name, content, "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _hoa(client: TestClient, h: dict[str, str], number: str) -> tuple[str, str, dict[str, Any]]:
    """Community with one owner (unit 01) and a board contact (person, no contract)."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG Beirat {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party, _ = _party(client, h, f"Eig{number}")
    unit = _unit(client, h, prop["id"], "01")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    _, board = _party(client, h, f"Beirat{number}")
    return hoa, str(prop["id"]), board


def _ledger_with_invoice(
    client: TestClient, h: dict[str, str], hoa: str, number: str, document_id: str
) -> tuple[str, dict[str, Any]]:
    template = _ok(client.post(f"{ACC}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{ACC}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{ACC}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Gärtner {number} {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    body = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": f"BD-{number}",
        "invoice_date": "2025-06-01",
        "net": "120.00",
        "vat": "0.00",
        "gross": "120.00",
        "document_id": document_id,
        "lines": [{"account_id": acc["040300"], "net": "120.00"}],
    }
    invoice = _ok(client.post(f"{ACC}/invoices", json=body, headers=h), 201)
    return str(invoice["id"]), body


def _engagement(client: TestClient, h: dict[str, str], hoa: str, board_contact: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/audits",
                json={
                    "legal_entity_id": hoa,
                    "period_from": "2025-01-01",
                    "period_to": "2025-12-31",
                    "purpose": "Stichprobe Jahresabrechnung 2025 (A52)",
                    "auditor_contact_ids": [board_contact],
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def _board_login(
    client: TestClient, h: dict[str, str], world: World, name: str, engagement: str, contact: str
) -> dict[str, str]:
    created = _ok(
        client.post(
            f"{H}/audit-engagements/{engagement}/board-access",
            json={"contact_id": contact, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    assert created["invitation_token"]
    _ok(
        client.post(
            f"{P}/invitations/accept",
            json={"token": created["invitation_token"], "password": PASSWORD},
        )
    )
    return bearer(login(client, world, name))


def test_board_reads_positions_and_released_receipts_only_and_never_posts(
    client: TestClient, world: World
) -> None:
    """PÜ07/PÜ08, D32: the board sees the engagement with its positions and exactly the receipts
    behind the positions (the item document and the invoice document of the booked entry), opens
    them (read receipt as indication only), and holds no CRM right: no booking, no release, no
    change of the statement. A receipt of the community outside the engagement stays hidden."""
    h = bearer(login(client, world, "bdadmin"))
    hoa, _, board = _hoa(client, h, "901")
    doc_item = _doc(client, h, "rechnung-garten.pdf", b"%PDF-1.4 garten")
    doc_other = _doc(client, h, "rechnung-dach.pdf", b"%PDF-1.4 dach")
    _ledger_with_invoice(client, h, hoa, "901", doc_item)
    engagement = _engagement(client, h, hoa, board["id"])
    # The board access requires the contact to be listed as auditor of the engagement.
    stranger = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Fremd", "last_name": f"Kontakt{RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    assert (
        client.post(
            f"{H}/audit-engagements/{engagement}/board-access",
            json={"contact_id": stranger, "email": world.email("x901"), "display_name": "x"},
            headers=h,
        ).status_code
        == 422
    )
    item = _ok(
        client.post(
            f"{H}/audits/{engagement}/items",
            json={"document_id": doc_item, "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    bh = _board_login(client, h, world, "bd901", engagement, board["id"])

    me = _ok(client.get(f"{P}/me", headers=bh))
    assert me["roles"] == ["board"]
    engagements = _ok(client.get(f"{B}/engagements", headers=bh))
    assert [e["id"] for e in engagements] == [engagement]
    assert engagements[0]["legal_entity_name"]
    detail = _ok(client.get(f"{B}/engagements/{engagement}", headers=bh))
    assert [p["id"] for p in detail["positions"]] == [item["id"]]
    assert detail["positions"][0]["status"] == "open"
    assert detail["overall_status"].startswith("eingeschränkt")  # D32: no full audit claim
    assert {d["id"] for d in detail["documents"]} == {doc_item}
    assert "Indiz" in detail["read_receipt_note"]

    opened = client.get(f"{B}/engagements/{engagement}/documents/{doc_item}", headers=bh)
    assert opened.status_code == 200, opened.text
    assert opened.content == b"%PDF-1.4 garten"
    assert (
        client.get(f"{B}/engagements/{engagement}/documents/{doc_other}", headers=bh).status_code
        == 404
    )
    # The general portal document list does not widen the scope of the board role.
    assert client.get(f"{P}/documents/{doc_item}/download", headers=bh).status_code == 404
    # D34/PÜ13: the retrieval is recorded as an indication, visible to the management.
    receipts = _ok(client.get(f"/api/v1/documents/{doc_item}/portal-read-receipts", headers=h))
    assert [r["kind"] for r in receipts["items"]] == ["opened"]

    # No booking, no release, no change of the statement or the audit by the board role.
    forbidden = [
        ("post", f"{ACC}/ledgers/{engagement}/entries", {}),
        ("post", f"{H}/statements", {"ledger_id": engagement, "year": 2025}),
        ("patch", f"{H}/audit-items/{item['id']}", {"status": "checked"}),
        ("post", f"{H}/audits/{engagement}/reports", {}),
        ("get", f"{H}/audits/{engagement}", None),
        ("get", "/api/v1/contacts", None),
    ]
    for method, path, body in forbidden:
        response = getattr(client, method)(path, headers=bh, **({"json": body} if body else {}))
        assert response.status_code == 403, (method, path, response.text)


def test_board_question_answered_by_management_and_position_outdated_after_change(
    client: TestClient, world: World
) -> None:
    """PÜ08: note and question per position; the answer of the management is traceable on the
    question itself (author, time) and cannot be given twice. D33: an invoice changed after the
    check marks the position outdated for the board as well."""
    h = bearer(login(client, world, "bdadmin"))
    hoa, _, board = _hoa(client, h, "902")
    doc = _doc(client, h, "rechnung-902.pdf", b"%PDF-1.4 902")
    invoice, body = _ledger_with_invoice(client, h, hoa, "902", doc)
    engagement = _engagement(client, h, hoa, board["id"])
    item = _ok(
        client.post(
            f"{H}/audits/{engagement}/items",
            json={"document_id": doc, "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{H}/audit-items/{item['id']}", json={"status": "checked"}, headers=h))
    bh = _board_login(client, h, world, "bd902", engagement, board["id"])

    note = _ok(
        client.post(
            f"{B}/engagements/{engagement}/notes",
            json={
                "kind": "note",
                "text": "Beleg und Leistung stimmig.",
                "audit_item_id": item["id"],
            },
            headers=bh,
        ),
        201,
    )
    assert note["kind"] == "note"
    question = _ok(
        client.post(
            f"{B}/engagements/{engagement}/notes",
            json={"kind": "question", "text": "Warum ohne Angebot?", "audit_item_id": item["id"]},
            headers=bh,
        ),
        201,
    )
    # A position of a different engagement is refused.
    other_engagement = _engagement(client, h, hoa, board["id"])
    other_item = _ok(
        client.post(f"{H}/audits/{other_engagement}/items", json={"document_id": doc}, headers=h),
        201,
    )
    assert (
        client.post(
            f"{B}/engagements/{engagement}/notes",
            json={"kind": "question", "text": "x", "audit_item_id": other_item["id"]},
            headers=bh,
        ).status_code
        == 422
    )
    section = _ok(client.get(f"{H}/audit-engagements/{engagement}/board", headers=h))
    assert [n["kind"] for n in section["notes"]] == ["note", "question"]
    assert [a["account_status"] for a in section["access"]] == ["active"]
    answered = _ok(
        client.post(
            f"{H}/audit-engagements/{engagement}/notes/{question['id']}/answer",
            json={"answer": "Angebot lag unter der Wertgrenze der Gemeinschaftsordnung."},
            headers=h,
        )
    )
    assert answered["kind"] == "answered"
    assert answered["answered_at"]
    assert answered["text"] == "Warum ohne Angebot?"  # question kept, never overwritten
    assert (
        client.post(
            f"{H}/audit-engagements/{engagement}/notes/{question['id']}/answer",
            json={"answer": "nochmal"},
            headers=h,
        ).status_code
        == 409
    )
    detail = _ok(client.get(f"{B}/engagements/{engagement}", headers=bh))
    assert [n["kind"] for n in detail["notes"]] == ["note", "answered"]
    assert detail["notes"][1]["answer"].startswith("Angebot lag")
    assert detail["positions"][0]["status"] == "checked"

    # D33: the invoice behind the checked position gets a new version after the check.
    _ok(
        client.put(
            f"{ACC}/invoices/{invoice}", json=body | {"net": "150.00", "gross": "150.00"}, headers=h
        )
    )
    detail = _ok(client.get(f"{B}/engagements/{engagement}", headers=bh))
    assert detail["positions"][0]["status"] == "outdated"
    assert detail["positions"][0]["outdated_reason"] == "Rechnung nach Prüfung geändert"
    assert detail["overall_status"] == "eingeschränkt: Positionen nach Prüfung geändert"

    # Revocation ends the access; the notes stay with the engagement.
    access_id = section["access"][0]["id"]
    revoked = _ok(
        client.post(
            f"{H}/audit-engagements/{engagement}/board-access/{access_id}/revoke", headers=h
        )
    )
    assert revoked["revoked_at"]
    assert client.get(f"{B}/engagements/{engagement}", headers=bh).status_code == 404
    assert (
        len(_ok(client.get(f"{H}/audit-engagements/{engagement}/board", headers=h))["notes"]) == 2
    )


def test_board_sees_only_own_community_and_tenant(client: TestClient, world: World) -> None:
    """Separation: a board member of community 903 reaches nothing of community 904 (same
    tenant), an owner without board access has no audit room, and the administrator of tenant B
    finds neither the engagement nor its board section (RLS, ADR 0002)."""
    h = bearer(login(client, world, "bdadmin"))
    hoa_a, _, board_a = _hoa(client, h, "903")
    hoa_b, _, board_b = _hoa(client, h, "904")
    doc_b = _doc(client, h, "rechnung-904.pdf", b"%PDF-1.4 904")
    eng_a = _engagement(client, h, hoa_a, board_a["id"])
    eng_b = _engagement(client, h, hoa_b, board_b["id"])
    _ok(client.post(f"{H}/audits/{eng_b}/items", json={"document_id": doc_b}, headers=h), 201)
    bh_a = _board_login(client, h, world, "bd903", eng_a, board_a["id"])
    bh_b = _board_login(client, h, world, "bd904", eng_b, board_b["id"])

    assert [e["id"] for e in _ok(client.get(f"{B}/engagements", headers=bh_a))] == [eng_a]
    assert client.get(f"{B}/engagements/{eng_b}", headers=bh_a).status_code == 404
    assert client.get(f"{B}/engagements/{eng_b}/documents/{doc_b}", headers=bh_a).status_code == 404
    assert (
        client.post(
            f"{B}/engagements/{eng_b}/notes", json={"text": "fremd"}, headers=bh_a
        ).status_code
        == 404
    )
    assert client.get(f"{B}/engagements/{eng_b}/documents/{doc_b}", headers=bh_b).status_code == 200

    # The same board access twice is refused; a second engagement of the same community reuses
    # the existing portal account without a new invitation.
    assert (
        client.post(
            f"{H}/audit-engagements/{eng_a}/board-access",
            json={"contact_id": board_a["id"]},
            headers=h,
        ).status_code
        == 409
    )
    eng_a2 = _engagement(client, h, hoa_a, board_a["id"])
    again = _ok(
        client.post(
            f"{H}/audit-engagements/{eng_a2}/board-access",
            json={"contact_id": board_a["id"]},
            headers=h,
        ),
        201,
    )
    assert again["invitation_token"] is None
    assert {e["id"] for e in _ok(client.get(f"{B}/engagements", headers=bh_a))} == {eng_a, eng_a2}

    # Owner of community 903 without board access: no audit room at all.
    owner_contact = _ok(client.get("/api/v1/contacts", params={"q": "Eig903"}, headers=h))
    assert owner_contact["items"], owner_contact
    inv = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={
                "contact_id": owner_contact["items"][0]["id"],
                "email": world.email("owner903"),
                "display_name": "owner903",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    oh = bearer(login(client, world, "owner903"))
    assert "board" not in _ok(client.get(f"{P}/me", headers=oh))["roles"]
    assert _ok(client.get(f"{B}/engagements", headers=oh)) == []
    assert client.get(f"{B}/engagements/{eng_a}", headers=oh).status_code == 404

    # Tenant B: nothing of tenant A is reachable, not even the CRM board section.
    hb = bearer(login(client, world, "bdadmin_b", tenant_id=world.tenant_b))
    assert client.get(f"{H}/audit-engagements/{eng_a}/board", headers=hb).status_code == 404
    assert (
        client.post(
            f"{H}/audit-engagements/{eng_a}/board-access",
            json={"contact_id": board_a["id"]},
            headers=hb,
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{H}/audits", params={"legal_entity_id": hoa_a}, headers=hb)) == []


def test_a76_a77_board_filters_positions_and_records_statement_on_report(
    client: TestClient, world: World
) -> None:
    """A77 (PÜ08): the board filters the positions of its audit room by account, vendor, booking
    date and text server side; the filter options list only accounts and vendors of the
    positions. A76 (PÜ09): the board records its statement on a report version in the portal;
    the text lands like the CRM entry in ``audit_report.content.board_statement`` with the
    recording portal account and a history, without any release effect. Board access of another
    community, a report of another engagement and tenant B all answer 404."""
    h = bearer(login(client, world, "bdadmin"))
    hoa, _, board = _hoa(client, h, "905")
    doc = _doc(client, h, "rechnung-905.pdf", b"%PDF-1.4 905")
    _, invoice = _ledger_with_invoice(client, h, hoa, "905", doc)
    ledger = str(invoice["ledger_id"])
    vendor = str(invoice["provider_contact_id"])
    acc = _accounts(client, h, ledger)
    cleaning = _book(
        client,
        h,
        ledger,
        _entry(
            "custom",
            "2025-06-01",
            [_line(acc["040300"], "120.00"), _line(acc["001200"], "0", "120.00")],
            document_id=doc,
            text="Reinigung Juni",
        ),
    )
    garden = _book(
        client,
        h,
        ledger,
        _entry(
            "custom",
            "2025-09-15",
            [_line(acc["040400"], "80.00"), _line(acc["001200"], "0", "80.00")],
            text="Gartenpflege September",
        ),
    )
    engagement = _engagement(client, h, hoa, board["id"])
    item_cleaning = _ok(
        client.post(
            f"{H}/audits/{engagement}/items",
            json={"journal_entry_id": cleaning["id"], "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    item_garden = _ok(
        client.post(
            f"{H}/audits/{engagement}/items",
            json={"journal_entry_id": garden["id"], "amount": "80.00"},
            headers=h,
        ),
        201,
    )
    bh = _board_login(client, h, world, "bd905", engagement, board["id"])
    base = f"{B}/engagements/{engagement}"

    # Unfiltered: both positions with accounts and vendor; options from the positions only.
    detail = _ok(client.get(base, headers=bh))
    assert [p["id"] for p in detail["positions"]] == [item_cleaning["id"], item_garden["id"]]
    assert detail["positions_total"] == 2
    assert detail["positions"][0]["vendor_contact_id"] == vendor
    assert detail["positions"][0]["vendor_name"].startswith("Gärtner 905")
    assert {a["number"] for a in detail["positions"][0]["accounts"]} == {"040300", "001200"}
    assert detail["positions"][1]["vendor_contact_id"] is None
    assert {a["number"] for a in detail["filter_options"]["accounts"]} == {
        "040300",
        "040400",
        "001200",
    }
    assert [v["id"] for v in detail["filter_options"]["vendors"]] == [vendor]
    assert detail["filter"]["account_id"] is None

    by_account = _ok(client.get(base, params={"account_id": acc["040400"]}, headers=bh))
    assert [p["id"] for p in by_account["positions"]] == [item_garden["id"]]
    assert by_account["positions_total"] == 2
    assert by_account["filter"]["account_id"] == acc["040400"]
    by_vendor = _ok(client.get(base, params={"vendor_contact_id": vendor}, headers=bh))
    assert [p["id"] for p in by_vendor["positions"]] == [item_cleaning["id"]]
    # Receipts follow the filtered positions; the invoice document belongs to the cleaning.
    assert {d["id"] for d in by_vendor["documents"]} == {doc}
    assert by_account["documents"] == []
    by_date = _ok(
        client.get(base, params={"date_from": "2025-09-01", "date_to": "2025-09-30"}, headers=bh)
    )
    assert [p["id"] for p in by_date["positions"]] == [item_garden["id"]]
    by_text = _ok(client.get(base, params={"q": "reinigung"}, headers=bh))
    assert [p["id"] for p in by_text["positions"]] == [item_cleaning["id"]]
    none = _ok(client.get(base, params={"account_id": acc["040400"], "q": "reinigung"}, headers=bh))
    assert none["positions"] == []
    assert none["overall_status"] == detail["overall_status"]  # status never depends on filter
    assert (
        client.get(
            base, params={"date_from": "2025-12-01", "date_to": "2025-11-01"}, headers=bh
        ).status_code
        == 422
    )

    # Reports: none yet, then one version created in the CRM; the board sees no position ids.
    assert _ok(client.get(f"{base}/reports", headers=bh)) == []
    report = _ok(
        client.post(
            f"{H}/audits/{engagement}/reports",
            json={"findings": "Stichprobe ohne Beanstandung", "recommendation": "Entlastung"},
            headers=h,
        ),
        201,
    )
    reports = _ok(client.get(f"{base}/reports", headers=bh))
    assert [r["id"] for r in reports] == [report["id"]]
    assert reports[0]["version"] == 1
    assert reports[0]["board_statement"] is None
    assert reports[0]["content"]["findings"] == "Stichprobe ohne Beanstandung"
    assert "open" not in reports[0]["content"]
    assert "snapshot_hash" not in reports[0]["content"]

    statement = f"{base}/reports/{report['id']}/statement"
    assert client.post(statement, json={"text": "   "}, headers=bh).status_code == 422
    first = _ok(
        client.post(
            statement, json={"text": "Der Beirat nimmt den Bericht zur Kenntnis."}, headers=bh
        )
    )
    assert first["board_statement"]["text"] == "Der Beirat nimmt den Bericht zur Kenntnis."
    assert first["board_statement"]["recorded_at"]
    assert first["board_statement"]["source"] == "portal"
    me = _ok(client.get(f"{P}/me", headers=bh))
    assert me["roles"] == ["board"]
    second = _ok(client.post(statement, json={"text": "Ergänzung des Beirats."}, headers=bh))
    assert second["board_statement"]["text"] == "Ergänzung des Beirats."
    assert [s["text"] for s in second["board_statement_history"]] == [
        "Der Beirat nimmt den Bericht zur Kenntnis."
    ]
    # Stored like the CRM entry: the CRM report list shows the same statement with the account.
    crm = _ok(client.get(f"{H}/audits/{engagement}/reports", headers=h))
    assert crm[0]["board_statement"]["text"] == "Ergänzung des Beirats."
    assert crm[0]["board_statement"]["recorded_by_account"]
    assert crm[0]["content"]["findings"] == "Stichprobe ohne Beanstandung"
    assert crm[0]["version"] == 1
    # No release effect: engagement and positions unchanged.
    assert _ok(client.get(f"{H}/audits/{engagement}", headers=h))["status"] == "open"
    assert _ok(client.get(base, headers=bh))["positions"][0]["status"] == "open"

    # Separation: a report of another engagement is 404 through this engagement; a board member
    # of another community and the administrator of tenant B reach nothing.
    hoa_other, _, board_other = _hoa(client, h, "906")
    eng_other = _engagement(client, h, hoa_other, board_other["id"])
    report_other = _ok(
        client.post(f"{H}/audits/{eng_other}/reports", json={"findings": "x"}, headers=h), 201
    )
    assert (
        client.post(
            f"{base}/reports/{report_other['id']}/statement", json={"text": "x"}, headers=bh
        ).status_code
        == 404
    )
    bh_other = _board_login(client, h, world, "bd906", eng_other, board_other["id"])
    assert client.get(f"{base}/reports", headers=bh_other).status_code == 404
    assert (
        client.get(base, params={"vendor_contact_id": vendor}, headers=bh_other).status_code == 404
    )
    assert client.post(statement, json={"text": "fremd"}, headers=bh_other).status_code == 404
    hb = bearer(login(client, world, "bdadmin_b", tenant_id=world.tenant_b))
    assert client.get(f"{base}/reports", headers=hb).status_code in (403, 404)
    assert client.post(statement, json={"text": "fremd"}, headers=hb).status_code in (403, 404)
