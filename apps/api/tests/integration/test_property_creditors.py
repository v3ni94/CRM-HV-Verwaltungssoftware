"""Creditors per property (rule M11-08): link, trade, unlink, filter, contact section,
"Kreditor anlegen" from a bank transaction (contact with role dienstleister, IBAN pending for
four eyes, link to the property of the account), idempotent backfill from booked postings,
permissions (403) and tenant separation. Expected values are fixed (rule 0.1.8)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
P = "/api/v1/properties"
IBAN_HOA = "DE02120300000000202051"
IBAN_HOA_2 = "DE02100500000054540402"
IBAN_HOA_3 = "DE02500105170137075030"
IBAN_PLUMBER = "DE75512108001245126199"
IBAN_OWNER = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cr-{RUN}", name=f"Kreditor {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"crb-{RUN}", name=f"Kreditor B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("cradmin", a, "tenant_admin"),
            ("crviewer", a, "read_only"),
            ("crcaretaker", a, "caretaker"),
            ("crother", b, "tenant_admin"),
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


def _property_with_account(
    client: TestClient, h: dict[str, str], number: str, iban: str
) -> tuple[str, str]:
    prop = _ok(
        client.post(
            P,
            json={"number": number, "name": f"Objekt {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    account = _ok(
        client.post(
            f"{P}/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": iban,
                "holder": f"GdWE {number}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    return str(prop["id"]), str(account)


def _company(client: TestClient, h: dict[str, str], name: str, **extra: Any) -> str:
    body = {"kind": "company", "company_name": name, "bank_accounts": [], **extra}
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _import(
    client: TestClient, h: dict[str, str], stmt: str, iban: str, entries: list[str]
) -> None:
    doc = _upload(client, h, f"{stmt}.xml", _camt(stmt, iban, "5000.00", "4000.00", entries))
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)


def test_link_edit_filter_unlink_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cradmin"))
    viewer = bearer(login(client, world, "crviewer"))
    caretaker = bearer(login(client, world, "crcaretaker"))
    prop_id, _ = _property_with_account(client, h, "901", IBAN_HOA_2)
    plumber = _company(
        client,
        h,
        f"Rohr frei GmbH {RUN}",
        phones=[{"label": "work", "number": "+4921731234567"}],
        emails=[{"email": f"rohr.{RUN}@example.org"}],
    )
    electrician = _company(client, h, f"Blitz Elektro {RUN}", roles=["dienstleister"])

    # The link adds the creditor role where it is missing and keeps the contact otherwise.
    row = _ok(
        client.post(
            f"{P}/{prop_id}/creditors",
            json={"contact_id": plumber, "trade": "Sanitär", "since": "2024-03-01"},
            headers=h,
        ),
        201,
    )
    assert row["source"] == "manual"
    assert row["trade"] == "Sanitär"
    assert row["since"] == "2024-03-01"
    assert row["contact_roles"] == ["dienstleister"]
    assert row["phone"] == "+4921731234567"
    assert row["email"] == f"rohr.{RUN}@example.org"
    assert row["last_invoice_date"] is None
    assert row["open_invoice_amount"] is None
    assert row["work_orders_count"] == 0
    # Idempotent: a second link of the same contact returns the same row.
    again = _ok(
        client.post(f"{P}/{prop_id}/creditors", json={"contact_id": plumber}, headers=h), 201
    )
    assert again["id"] == row["id"]
    _ok(
        client.post(
            f"{P}/{prop_id}/creditors",
            json={"contact_id": electrician, "trade": "Elektro"},
            headers=h,
        ),
        201,
    )

    listed = _ok(client.get(f"{P}/{prop_id}/creditors", headers=viewer))
    assert [r["trade"] for r in listed] == ["Elektro", "Sanitär"]
    filtered = _ok(client.get(f"{P}/{prop_id}/creditors", params={"trade": "sanitär"}, headers=h))
    assert [r["contact_id"] for r in filtered] == [plumber]

    edited = _ok(
        client.patch(
            f"{P}/{prop_id}/creditors/{row['id']}", json={"trade": "Heizung und Sanitär"}, headers=h
        )
    )
    assert edited["trade"] == "Heizung und Sanitär"

    # Contact page: properties as creditor.
    mine = _ok(client.get(f"/api/v1/contacts/{plumber}/creditor-properties", headers=viewer))
    assert [(m["property_id"], m["trade"]) for m in mine] == [(prop_id, "Heizung und Sanitär")]

    # properties:read reads, properties:update writes; read_only and caretaker cannot write.
    for headers in (viewer, caretaker):
        assert (
            client.post(
                f"{P}/{prop_id}/creditors", json={"contact_id": plumber}, headers=headers
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"{P}/{prop_id}/creditors/{row['id']}", json={"trade": "x"}, headers=headers
            ).status_code
            == 403
        )
        assert (
            client.delete(f"{P}/{prop_id}/creditors/{row['id']}", headers=headers).status_code
            == 403
        )
    assert client.get(f"{P}/{prop_id}/creditors", headers=caretaker).status_code == 200

    assert client.delete(f"{P}/{prop_id}/creditors/{row['id']}", headers=h).status_code == 204
    assert [r["contact_id"] for r in _ok(client.get(f"{P}/{prop_id}/creditors", headers=h))] == [
        electrician
    ]
    # Unlinking leaves the contact untouched.
    assert client.get(f"/api/v1/contacts/{plumber}", headers=h).status_code == 200
    assert client.delete(f"{P}/{prop_id}/creditors/{row['id']}", headers=h).status_code == 404


def test_creditor_from_transaction_and_backfill(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cradmin"))
    viewer = bearer(login(client, world, "crviewer"))
    prop_id, account_id = _property_with_account(client, h, "902", IBAN_HOA)
    _import(
        client,
        h,
        f"S-CR-{RUN}",
        IBAN_HOA,
        [
            _ntry("REF-CR-1", "250.00", "DBIT", "2026-01-12", IBAN_PLUMBER, "Rechnung 4711"),
            _ntry("REF-CR-2", "80.00", "DBIT", "2026-01-20", IBAN_OWNER, "Guthaben Abrechnung"),
        ],
    )
    txs = _ok(client.get(f"{B}/transactions", params={"bank_account_id": account_id}, headers=h))
    by_ref = {t["bank_reference"]: t for t in txs}
    tx_plumber = by_ref["REF-CR-1"]
    tx_owner = by_ref["REF-CR-2"]

    lookup = _ok(
        client.get(f"{B}/transactions/{tx_plumber['id']}/counterparty-contact", headers=viewer)
    )
    assert lookup["contact_id"] is None
    assert lookup["property_id"] == prop_id
    assert lookup["counterpart_name"] == "Zahler"
    assert lookup["has_counterpart_iban"] is True

    # read_only has no contacts:create.
    assert (
        client.post(
            f"{B}/transactions/{tx_plumber['id']}/creditor-contact", json={}, headers=viewer
        ).status_code
        == 403
    )
    created = _ok(
        client.post(
            f"{B}/transactions/{tx_plumber['id']}/creditor-contact",
            json={"name": f"Zahler Sanitär {RUN}", "trade": "Sanitär"},
            headers=h,
        ),
        201,
    )
    assert created["created"] is True
    assert created["display_name"] == f"Zahler Sanitär {RUN}"
    assert created["property_id"] == prop_id
    assert created["link_id"] is not None
    assert created["bank_account_pending"] is True
    contact = _ok(client.get(f"/api/v1/contacts/{created['contact_id']}", headers=h))
    assert contact["kind"] == "company"
    assert contact["roles"] == ["dienstleister"]
    # The IBAN from the transaction is never released here: pending for a second person.
    assert [a["approval_status"] for a in contact["bank_accounts"]] == ["pending"]
    assert contact["bank_accounts"][0]["iban_masked"].endswith(IBAN_PLUMBER[-4:])
    listed = _ok(client.get(f"{P}/{prop_id}/creditors", headers=h))
    assert [(r["contact_id"], r["source"], r["since"], r["trade"]) for r in listed] == [
        (created["contact_id"], "proposal", "2026-01-12", "Sanitär")
    ]

    # Second call: the counterparty is known by IBAN now, nothing is created twice.
    lookup = _ok(client.get(f"{B}/transactions/{tx_plumber['id']}/counterparty-contact", headers=h))
    assert lookup == {
        **lookup,
        "contact_id": created["contact_id"],
        "basis": "iban",
        "is_creditor": True,
        "linked_to_property": True,
    }
    second = _ok(
        client.post(f"{B}/transactions/{tx_plumber['id']}/creditor-contact", json={}, headers=h),
        201,
    )
    assert second["created"] is False
    assert second["contact_id"] == created["contact_id"]

    # Backfill: only booked outgoing postings to a contact with the creditor role count; an
    # owner refund (contact without the role) is no creditor relation.
    owner = _company(
        client,
        h,
        f"Eigentümer Guthaben {RUN}",
        bank_accounts=[{"iban": IBAN_OWNER, "valid_from": "2020-01-01"}],
    )
    assert (
        client.delete(f"{P}/{prop_id}/creditors/{created['link_id']}", headers=h).status_code == 204
    )
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        conn.execute(
            text("UPDATE bank_transaction SET status = 'booked' WHERE id IN (:a, :b)"),
            {"a": tx_plumber["id"], "b": tx_owner["id"]},
        )
    engine.dispose()
    assert (
        client.post("/api/v1/properties/creditors/backfill", json={}, headers=viewer).status_code
        == 403
    )
    first = _ok(
        client.post(
            "/api/v1/properties/creditors/backfill", json={"property_id": prop_id}, headers=h
        )
    )
    assert first["created"] == 1
    again = _ok(client.post("/api/v1/properties/creditors/backfill", json={}, headers=h))
    assert again["created"] == 0
    rows = _ok(client.get(f"{P}/{prop_id}/creditors", headers=h))
    assert [(r["contact_id"], r["source"], r["since"]) for r in rows] == [
        (created["contact_id"], "backfill", "2026-01-12")
    ]
    assert owner not in {r["contact_id"] for r in rows}


def test_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cradmin"))
    other = bearer(login(client, world, "crother"))
    prop_id, account_id = _property_with_account(client, h, "903", IBAN_HOA_3)
    contact = _company(client, h, f"Fremd Dach {RUN}")
    row = _ok(client.post(f"{P}/{prop_id}/creditors", json={"contact_id": contact}, headers=h), 201)
    assert client.get(f"{P}/{prop_id}/creditors", headers=other).status_code == 404
    assert (
        client.post(
            f"{P}/{prop_id}/creditors", json={"contact_id": contact}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{P}/{prop_id}/creditors/{row['id']}", json={"trade": "x"}, headers=other
        ).status_code
        == 404
    )
    assert client.delete(f"{P}/{prop_id}/creditors/{row['id']}", headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/contacts/{contact}/creditor-properties", headers=other).status_code
        == 404
    )
    _import(
        client,
        h,
        f"S-SEP-{RUN}",
        IBAN_HOA_3,
        [_ntry("REF-SEP", "10.00", "DBIT", "2026-02-02", IBAN_PLUMBER, "x")],
    )
    tx = _ok(client.get(f"{B}/transactions", params={"bank_account_id": account_id}, headers=h))[0]
    assert (
        client.get(f"{B}/transactions/{tx['id']}/counterparty-contact", headers=other).status_code
        == 404
    )
    assert (
        client.post(
            f"{B}/transactions/{tx['id']}/creditor-contact", json={}, headers=other
        ).status_code
        == 404
    )
    assert _ok(client.post("/api/v1/properties/creditors/backfill", json={}, headers=other)) == {
        "scanned": 0,
        "created": 0,
    }
