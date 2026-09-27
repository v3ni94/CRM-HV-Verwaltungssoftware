"""Hotfix 1.35.2 (7.9.2 PÜ06, PÜ07; A52): an audit engagement and its items reference only
records of the engagement's own community.

The board portal releases the statement's cost items and the receipts behind the audit items to
external board members (``mhvp.portal.board``). Creating the engagement therefore refuses a
statement of another community, and adding an item refuses a booking of another community, an
unposted booking, a booking outside the engagement period and a receipt that is neither the
booking's own receipt nor the receipt of an invoice or booking of the community. The value of
an item is the booked figure (debit total of the booking, gross of the invoice); a different
client amount is refused. The CRM picker (candidate list, then the existing POST) keeps working.
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
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m10_ledger import _accounts, _book, _entry, _line
from tests.integration.test_m21_board_portal import (
    _doc,
    _engagement,
    _hoa,
    _ledger_with_invoice,
    _ok,
)

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
ACC = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"hx-{RUN}", name=f"Prüfung {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"hx2-{RUN}", name=f"Prüfung B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("hxadmin", a, "tenant_admin"),
            ("hxadmin_b", b, "tenant_admin"),
            ("hxtax", a, "tax_advisor"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=[role],
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


def _community(
    client: TestClient, h: dict[str, str], number: str
) -> tuple[str, dict[str, Any], str, dict[str, str], str]:
    """Community with ledger, one incoming invoice (gross 120,00) and its receipt."""
    hoa, _, board = _hoa(client, h, number)
    invoice_doc = _doc(client, h, f"rechnung-{number}.pdf", f"%PDF-1.4 {number}".encode())
    _, invoice = _ledger_with_invoice(client, h, hoa, number, invoice_doc)
    ledger = str(invoice["ledger_id"])
    return hoa, board, ledger, _accounts(client, h, ledger), invoice_doc


def _expense(acc: dict[str, str], day: str, amount: str, **extra: Any) -> dict[str, Any]:
    return _entry(
        "custom",
        day,
        [_line(acc["040300"], amount), _line(acc["001200"], "0", amount)],
        **extra,
    )


def _item(client: TestClient, h: dict[str, str], engagement: str, body: dict[str, Any]) -> Any:
    return client.post(f"{H}/audits/{engagement}/items", json=body, headers=h)


def _refused(response: Any, fragment: str) -> None:
    assert response.status_code == 422, response.text
    assert fragment in response.json()["detail"], response.text


def test_engagement_refuses_statement_of_another_community(
    client: TestClient, world: World
) -> None:
    """PÜ06: the statement of community 912 cannot be attached to an engagement of community
    911 (its cost items would be released to the board of 911). The own statement passes the
    community check and only fails because it is not calculated yet."""
    h = bearer(login(client, world, "hxadmin"))
    hoa_a, board_a, ledger_a, _, _ = _community(client, h, "911")
    _, _, ledger_b, _, _ = _community(client, h, "912")
    statement_a = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger_a, "year": 2025}, headers=h), 201
    )["id"]
    statement_b = _ok(
        client.post(f"{H}/statements", json={"ledger_id": ledger_b, "year": 2025}, headers=h), 201
    )["id"]
    body = {
        "legal_entity_id": hoa_a,
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "purpose": "Stichprobe Jahresabrechnung 2025 (Hotfix)",
        "auditor_contact_ids": [board_a["id"]],
    }
    _refused(
        client.post(f"{H}/audits", json=body | {"statement_id": statement_b}, headers=h),
        "Gemeinschaft des Prüfauftrags",
    )
    own = client.post(f"{H}/audits", json=body | {"statement_id": statement_a}, headers=h)
    assert own.status_code == 409, own.text
    assert own.json()["detail"] == "Abrechnung nicht berechnet."
    # Tenant B finds neither the statement nor the community of tenant A.
    hb = bearer(login(client, world, "hxadmin_b", tenant_id=world.tenant_b))
    foreign = client.post(f"{H}/audits", json=body | {"statement_id": statement_a}, headers=hb)
    assert foreign.status_code == 404, foreign.text


def test_item_refuses_foreign_unposted_and_out_of_period_bookings(
    client: TestClient, world: World
) -> None:
    """PÜ07: only a posted booking of the engagement's community inside the engagement period
    becomes an audit item; the amount is the booked debit total, a different client amount is
    refused. The CRM picker path (candidate list, then POST with the candidate) still works."""
    h = bearer(login(client, world, "hxadmin"))
    hoa_a, board_a, ledger_a, acc_a, _ = _community(client, h, "913")
    _, _, ledger_b, acc_b, _ = _community(client, h, "914")
    entry_doc = _doc(client, h, "beleg-913.pdf", b"%PDF-1.4 beleg 913")
    in_period = _book(
        client, h, ledger_a, _expense(acc_a, "2025-06-01", "120.00", document_id=entry_doc)
    )
    before_period = _book(client, h, ledger_a, _expense(acc_a, "2024-12-15", "50.00"))
    draft = _ok(
        client.post(
            f"{ACC}/ledgers/{ledger_a}/entries",
            json=_expense(acc_a, "2025-07-01", "70.00"),
            headers=h,
        ),
        201,
    )
    foreign = _book(client, h, ledger_b, _expense(acc_b, "2025-06-01", "90.00"))
    engagement = _engagement(client, h, hoa_a, board_a["id"])

    _refused(
        _item(client, h, engagement, {"journal_entry_id": foreign["id"], "amount": "90.00"}),
        "Gemeinschaft des Prüfauftrags",
    )
    _refused(
        _item(client, h, engagement, {"journal_entry_id": draft["id"], "amount": "70.00"}),
        "keine Entwürfe",
    )
    _refused(
        _item(client, h, engagement, {"journal_entry_id": before_period["id"], "amount": "50.00"}),
        "außerhalb des Prüfzeitraums",
    )
    _refused(
        _item(client, h, engagement, {"journal_entry_id": in_period["id"], "amount": "999.00"}),
        "gebuchten Betrag 120,00 EUR",
    )
    # A receipt that is not the booking's own receipt is refused together with the booking.
    unrelated = _doc(client, h, "fremd-913.pdf", b"%PDF-1.4 fremd")
    _refused(
        _item(
            client,
            h,
            engagement,
            {"journal_entry_id": in_period["id"], "document_id": unrelated, "amount": "120.00"},
        ),
        "nicht zu dieser Buchung",
    )

    # Happy path of the CRM picker: the candidate is posted unchanged.
    candidates = _ok(client.get(f"{H}/audits/{engagement}/candidates", headers=h))["items"]
    assert [c["journal_entry_id"] for c in candidates] == [in_period["id"]]
    candidate = candidates[0]
    item = _ok(
        _item(
            client,
            h,
            engagement,
            {
                "journal_entry_id": candidate["journal_entry_id"],
                "document_id": candidate["document_id"],
                "amount": candidate["amount"],
            },
        ),
        201,
    )
    assert (item["journal_entry_id"], item["document_id"], item["amount"]) == (
        in_period["id"],
        entry_doc,
        "120.00",
    )
    # Without a client amount the booked figure is taken.
    derived = _ok(_item(client, h, engagement, {"journal_entry_id": in_period["id"]}), 201)
    assert derived["amount"] == "120.00"
    detail = _ok(client.get(f"{H}/audits/{engagement}", headers=h))
    assert [i["id"] for i in detail["items"]] == [item["id"], derived["id"]]

    # Tenant B reaches neither the engagement nor the booking of tenant A.
    hb = bearer(login(client, world, "hxadmin_b", tenant_id=world.tenant_b))
    assert _item(client, hb, engagement, {"journal_entry_id": in_period["id"]}).status_code == 404


def test_item_refuses_receipt_outside_the_community(client: TestClient, world: World) -> None:
    """PÜ07: a receipt without booking must be the receipt of an invoice or booking of the
    engagement's community; an unrelated upload and the invoice receipt of another community
    are refused and never reach the board. The amount is the invoice gross."""
    h = bearer(login(client, world, "hxadmin"))
    hoa_a, board_a, _, _, invoice_doc_a = _community(client, h, "915")
    _, _, _, _, invoice_doc_b = _community(client, h, "916")
    unrelated = _doc(client, h, "mietvertrag-915.pdf", b"%PDF-1.4 mietvertrag")
    engagement = _engagement(client, h, hoa_a, board_a["id"])

    _refused(
        _item(client, h, engagement, {"document_id": unrelated, "amount": "10.00"}),
        "keiner Rechnung oder Buchung",
    )
    _refused(
        _item(client, h, engagement, {"document_id": invoice_doc_b, "amount": "120.00"}),
        "keiner Rechnung oder Buchung",
    )
    _refused(
        _item(client, h, engagement, {"document_id": invoice_doc_a, "amount": "1.00"}),
        "gebuchten Betrag 120,00 EUR",
    )
    item = _ok(
        _item(client, h, engagement, {"document_id": invoice_doc_a, "amount": "120.00"}), 201
    )
    assert (item["document_id"], item["amount"]) == (invoice_doc_a, "120.00")
    derived = _ok(_item(client, h, engagement, {"document_id": invoice_doc_a}), 201)
    assert derived["amount"] == "120.00"
    detail = _ok(client.get(f"{H}/audits/{engagement}", headers=h))
    assert {i["document_id"] for i in detail["items"]} == {invoice_doc_a}
    assert _item(client, h, engagement, {"amount": "1.00"}).status_code == 422


def test_scoped_member_reads_only_audits_of_its_communities(
    client: TestClient, world: World
) -> None:
    """A37, M18-05: a tax advisor limited to community 921 has accounting:read and so reaches
    GET /hoa/audits/{id}; the engagement of community 922 answers 404 (review 27.09.2026)."""
    from tests.integration.test_m18_tax_advisor_scope import _membership_id

    h = bearer(login(client, world, "hxadmin"))
    hoa_a, board_a, _, _, _ = _community(client, h, "921")
    hoa_b, board_b, _, _, _ = _community(client, h, "922")

    def engagement(hoa: str, board: dict[str, Any]) -> str:
        body = {
            "legal_entity_id": hoa,
            "period_from": "2025-01-01",
            "period_to": "2025-12-31",
            "purpose": "Stichprobe Bereichsprüfung (Hotfix)",
            "auditor_contact_ids": [board["id"]],
        }
        return str(_ok(client.post(f"{H}/audits", json=body, headers=h), 201)["id"])

    eng_a, eng_b = engagement(hoa_a, board_a), engagement(hoa_b, board_b)
    tax_member = _membership_id(client, h, world.users["hxtax"])
    scoped = client.put(
        f"/api/v1/tenant/members/{tax_member}/legal-entities",
        json={"legal_entity_ids": [hoa_a]},
        headers=h,
    )
    assert scoped.status_code == 204, scoped.text
    tax = bearer(login(client, world, "hxtax"))
    assert client.get(f"{H}/audits/{eng_a}", headers=tax).status_code == 200
    assert client.get(f"{H}/audits/{eng_b}", headers=tax).status_code == 404
