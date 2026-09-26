"""A72 to A74 (Restpunkte Welle 6): CRM views of the board audit, portal form submissions and
provider appointment proposals.

* A72 (7.9.2 PÜ07 to PÜ09): candidate bookings for audit items with filters by account,
  vendor and date, the list of reports and the board statement on a report (text only, no
  release effect).
* A73 (A56): submissions per portal form template for the CRM with the ticket created.
* A74 (A58): appointment proposals of a work order with status and confirmed appointment.

Each endpoint: happy path, permission (portal users have no CRM right), tenant separation.
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
from tests.integration.test_a55_a58_portal_attachments import _rental, _tenancy
from tests.integration.test_a56_portal_forms import _template
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m10_ledger import _accounts, _book, _entry, _line
from tests.integration.test_m21_board_portal import (
    _board_login,
    _doc,
    _engagement,
    _hoa,
    _ledger_with_invoice,
)
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"w6a-{RUN}", name=f"W6 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"w6b-{RUN}", name=f"W6 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("w6admin", a), ("w6admin_b", b)):
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


def test_a72_audit_candidates_reports_and_board_statement(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w6admin"))
    hb = bearer(login(client, world, "w6admin_b"))
    hoa, _, board = _hoa(client, h, "972")
    doc = _doc(client, h, "rechnung-972.pdf", b"%PDF-1.4 972")
    _, invoice = _ledger_with_invoice(client, h, hoa, "972", doc)
    ledger = str(invoice["ledger_id"])
    vendor = str(invoice["provider_contact_id"])
    acc = _accounts(client, h, ledger)
    # Two posted bookings: the cleaning invoice (with document, so with vendor) in June and a
    # garden booking without document in September; a draft never appears.
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
    _ok(
        client.post(
            f"/api/v1/accounting/ledgers/{ledger}/entries",
            json=_entry(
                "custom",
                "2025-10-01",
                [_line(acc["040400"], "10.00"), _line(acc["001200"], "0", "10.00")],
            ),
            headers=h,
        ),
        201,
    )
    engagement = _engagement(client, h, hoa, board["id"])

    base = f"{H}/audits/{engagement}/candidates"
    all_ = _ok(client.get(base, headers=h))
    assert (all_["period_from"], all_["period_to"]) == ("2025-01-01", "2025-12-31")
    assert (all_["total"], all_["truncated"]) == (2, False)
    assert [c["journal_entry_id"] for c in all_["items"]] == [cleaning["id"], garden["id"]]
    first = all_["items"][0]
    assert first["amount"] == "120.00"
    assert first["vendor_contact_id"] == vendor
    assert first["invoice_number"] == "BD-972"
    assert {a["number"] for a in first["accounts"]} == {"040300", "001200"}
    assert first["selected"] is False
    assert all_["items"][1]["vendor_contact_id"] is None
    # Filters: account, vendor, date, text.
    by_account = _ok(client.get(base, params={"account_id": acc["040400"]}, headers=h))
    assert [c["journal_entry_id"] for c in by_account["items"]] == [garden["id"]]
    by_vendor = _ok(client.get(base, params={"vendor_contact_id": vendor}, headers=h))
    assert [c["journal_entry_id"] for c in by_vendor["items"]] == [cleaning["id"]]
    by_date = _ok(client.get(base, params={"date_from": "2025-09-01"}, headers=h))
    assert [c["journal_entry_id"] for c in by_date["items"]] == [garden["id"]]
    assert by_date["period_from"] == "2025-09-01"
    by_text = _ok(client.get(base, params={"q": "garten"}, headers=h))
    assert [c["journal_entry_id"] for c in by_text["items"]] == [garden["id"]]
    assert (
        client.get(
            base, params={"date_from": "2025-12-01", "date_to": "2025-11-01"}, headers=h
        ).status_code
        == 422
    )
    # The selection stays the existing endpoint; the candidate is then flagged.
    _ok(
        client.post(
            f"{H}/audits/{engagement}/items",
            json={"journal_entry_id": cleaning["id"], "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    flagged = {
        c["journal_entry_id"]: c["selected"] for c in _ok(client.get(base, headers=h))["items"]
    }
    assert flagged == {cleaning["id"]: True, garden["id"]: False}

    # Reports and the board statement (text only, no release effect).
    assert _ok(client.get(f"{H}/audits/{engagement}/reports", headers=h)) == []
    report = _ok(
        client.post(
            f"{H}/audits/{engagement}/reports",
            json={"findings": "Stichprobe ohne Beanstandung"},
            headers=h,
        ),
        201,
    )
    reports = _ok(client.get(f"{H}/audits/{engagement}/reports", headers=h))
    assert [r["id"] for r in reports] == [report["id"]]
    assert reports[0]["board_statement"] is None
    assert reports[0]["content"]["findings"] == "Stichprobe ohne Beanstandung"
    statement = f"{H}/audit-reports/{report['id']}/board-statement"
    assert client.post(statement, json={"statement": " "}, headers=h).status_code == 422
    first_statement = _ok(
        client.post(
            statement, json={"statement": "Der Beirat nimmt den Bericht zur Kenntnis."}, headers=h
        )
    )
    assert (
        first_statement["board_statement"]["text"] == "Der Beirat nimmt den Bericht zur Kenntnis."
    )
    assert first_statement["board_statement"]["recorded_at"]
    second = _ok(client.post(statement, json={"statement": "Ergänzung des Beirats."}, headers=h))
    assert second["board_statement"]["text"] == "Ergänzung des Beirats."
    assert [s["text"] for s in second["content"]["board_statement_history"]] == [
        "Der Beirat nimmt den Bericht zur Kenntnis."
    ]
    # Report figures and the engagement status are untouched by a statement.
    assert second["content"]["findings"] == "Stichprobe ohne Beanstandung"
    assert second["version"] == 1
    assert _ok(client.get(f"{H}/audits/{engagement}", headers=h))["status"] == "open"

    # Tenant separation and permission: tenant B sees nothing, the board portal user holds no
    # CRM right.
    assert client.get(base, headers=hb).status_code == 404
    assert client.get(f"{H}/audits/{engagement}/reports", headers=hb).status_code == 404
    assert client.post(statement, json={"statement": "x"}, headers=hb).status_code == 404
    bh = _board_login(client, h, world, "w6board", engagement, board["id"])
    assert client.get(base, headers=bh).status_code == 403
    assert client.get(f"{H}/audits/{engagement}/reports", headers=bh).status_code == 403
    assert client.post(statement, json={"statement": "x"}, headers=bh).status_code == 403


def test_a73_form_submissions_listed_per_template(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w6admin"))
    hb = bearer(login(client, world, "w6admin_b"))
    template = _template(
        client,
        h,
        "Kontaktformular W6",
        "all",
        fields=[{"key": "anliegen", "label": "Anliegen", "type": "text", "required": True}],
    )
    empty = _ok(client.get(f"{PA}/forms/{template['id']}/submissions", headers=h))
    assert empty == []
    prop_id, _ = _rental(client, h, "973")
    tenancy = _tenancy(client, h, prop_id, "A")
    contact = _contact_of(client, h, tenancy["party_id"])
    ta = _portal_user(client, h, world, "w6tenant", contact)
    submitted = [
        _ok(
            client.post(
                f"{P}/forms/{template['id']}/submissions",
                json={"values": {"anliegen": text}, "unit_id": tenancy["unit_id"]},
                headers=ta,
            ),
            201,
        )
        for text in ("Bitte um Rückruf", "Zweite Anfrage")
    ]
    rows = _ok(client.get(f"{PA}/forms/{template['id']}/submissions", headers=h))
    # Newest first, with account, contact name and the ticket for the link.
    assert [r["id"] for r in rows] == [s["id"] for s in reversed(submitted)]
    assert rows[0]["ticket_id"] == submitted[1]["ticket_id"]
    assert rows[0]["ticket_number"] == submitted[1]["ticket_number"]
    assert rows[0]["ticket_status"] == submitted[1]["status"]
    assert rows[0]["contact_id"] == contact
    assert rows[0]["contact_name"]
    assert rows[0]["account_status"] == "active"
    assert rows[0]["unit_id"] == tenancy["unit_id"]
    assert rows[0]["created_at"]
    assert "values" not in rows[0]
    # Tenant B: not found; the portal user: no CRM right; unknown template: not found.
    assert client.get(f"{PA}/forms/{template['id']}/submissions", headers=hb).status_code == 404
    assert client.get(f"{PA}/forms/{template['id']}/submissions", headers=ta).status_code == 403
    assert (
        client.get(
            f"{PA}/forms/01920000-0000-7000-8000-000000000001/submissions", headers=h
        ).status_code
        == 404
    )


def test_a74_work_order_proposals_visible_in_crm(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w6admin"))
    hb = bearer(login(client, world, "w6admin_b"))
    prop_id, _ = _rental(client, h, "974")
    tenancy = _tenancy(client, h, prop_id, "A")
    ta = _portal_user(client, h, world, "w6resident", _contact_of(client, h, tenancy["party_id"]))
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Dach W6 {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    pv = _portal_user(client, h, world, "w6provider", provider)
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Dach undicht", "description": "Tropft", "unit_id": tenancy["unit_id"]},
            headers=ta,
        ),
        201,
    )
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": prop_id,
                "provider_contact_id": provider,
                "description": "Ziegel ersetzen",
            },
            headers=h,
        ),
        201,
    )
    oid = order["id"]
    crm = f"/api/v1/work-orders/{oid}/appointment-proposals"
    none_yet = _ok(client.get(crm, headers=h))
    assert none_yet["proposals"] == []
    assert (none_yet["scheduled_at"], none_yet["open_count"]) == (None, 0)
    assert none_yet["confirmed_proposal_id"] is None
    for status in ("requested", "approved"):
        _ok(client.post(f"/api/v1/work-orders/{oid}/steps", json={"status": status}, headers=h))
    first = _ok(
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={"proposals": [{"starts_at": "2026-10-01T09:00:00Z"}]},
            headers=pv,
        ),
        201,
    )
    proposals = _ok(
        client.post(
            f"{P}/work-orders/{oid}/appointment-proposals",
            json={
                "proposals": [
                    {"starts_at": "2026-10-05T09:00:00Z"},
                    {"starts_at": "2026-10-06T14:00:00Z", "note": "nachmittags"},
                ]
            },
            headers=pv,
        ),
        201,
    )
    open_ = _ok(client.get(crm, headers=h))
    assert (open_["open_count"], open_["confirmed_proposal_id"]) == (2, None)
    by_id = {p["id"]: p for p in open_["proposals"]}
    assert by_id[first[0]["id"]]["status"] == "superseded"
    assert by_id[proposals[1]["id"]]["note"] == "nachmittags"
    assert by_id[proposals[1]["id"]]["proposed_by_contact_id"] == provider
    chosen = proposals[1]["id"]
    _ok(client.post(f"{P}/work-orders/{oid}/appointment-proposals/{chosen}/accept", headers=ta))
    confirmed = _ok(client.get(crm, headers=h))
    assert confirmed["confirmed_proposal_id"] == chosen
    assert confirmed["scheduled_at"] == "2026-10-06T14:00:00Z"
    assert confirmed["open_count"] == 0
    assert confirmed["status"] == "scheduled"
    statuses = {p["id"]: p["status"] for p in confirmed["proposals"]}
    assert (statuses[chosen], statuses[proposals[0]["id"]]) == ("accepted", "declined")
    assert confirmed["ticket_id"] == ticket["id"]
    # Tenant B: not found; portal users (resident, provider): no CRM right.
    assert client.get(crm, headers=hb).status_code == 404
    assert client.get(crm, headers=ta).status_code == 403
    assert client.get(crm, headers=pv).status_code == 403
