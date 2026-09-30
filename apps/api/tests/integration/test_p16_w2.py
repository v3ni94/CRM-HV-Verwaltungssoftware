"""Package P16 (wave 2): parties, notes and tags of contacts (M3-01, M3-02, M3-04), bank
accounts, service providers, VAT history, meter photo, image gallery (M4-01 to M4-06),
contract custom fields, payment and schedule corrections, deposits, SEPA lifecycle
(M5-01 to M5-07). Tenant separation, permission and validation for every new endpoint."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.contracts.mandates import expire_due_mandates, mark_mandate_used
from mhvp.contracts.models import MandateSequence, MandateStatus, SepaMandate
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import IBAN, _party, _payment, _property, _unit
from tests.integration.test_m6_documents import BUCKET, _pdf, _settings, _upload

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p16a-{RUN}", name=f"P16 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p16b-{RUN}", name=f"P16 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p16admin", a, "tenant_admin"),
            ("p16reader", a, "read_only"),
            ("p16approver", a, "tenant_admin"),
            ("p16other", b, "tenant_admin"),
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
    return response.json() if response.content else None


def _heads(
    client: TestClient, world: World
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    return (
        bearer(login(client, world, "p16admin")),
        bearer(login(client, world, "p16reader")),
        bearer(login(client, world, "p16other")),
    )


def _contact(c: TestClient, h: dict[str, str], name: str, **extra: Any) -> dict[str, Any]:
    body = {"kind": "person", "first_name": name, "last_name": f"P16{RUN}", **extra}
    return _ok(c.post("/api/v1/contacts", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _doc(c: TestClient, h: dict[str, str], text: str) -> str:
    return str(_ok(_upload(c, h, f"{text}.pdf", _pdf(text), "application/pdf"), 201)["id"])


# M3-01 parties ------------------------------------------------------------------------


def test_party_patch_and_delete(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    a, b, c = (_contact(client, h, n) for n in ("Anna", "Bert", "Clara"))
    party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": a["id"]}]}, headers=h),
        201,
    )
    url = f"/api/v1/parties/{party['id']}"
    changed = _ok(
        client.patch(
            url,
            json={
                "name": "Familie P16",
                "members": [
                    {"contact_id": a["id"], "role": "primary", "share_percent": "50"},
                    {"contact_id": b["id"], "role": "co_party", "share_percent": "50"},
                ],
            },
            headers=h,
        )
    )
    assert changed["name"] == "Familie P16"
    assert {m["contact_id"] for m in changed["members"]} == {a["id"], b["id"]}
    replaced = _ok(client.patch(url, json={"members": [{"contact_id": c["id"]}]}, headers=h))
    assert [m["contact_id"] for m in replaced["members"]] == [c["id"]]
    # Validation, permission, tenant separation.
    dup = {"members": [{"contact_id": c["id"]}, {"contact_id": c["id"]}]}
    assert client.patch(url, json=dup, headers=h).status_code == 422
    over = {
        "members": [
            {"contact_id": c["id"], "share_percent": "60"},
            {"contact_id": a["id"], "share_percent": "60"},
        ]
    }
    assert client.patch(url, json=over, headers=h).status_code == 422
    assert client.patch(url, json={"members": []}, headers=h).status_code == 422
    assert client.patch(url, json={"name": "x"}, headers=reader).status_code == 403
    assert client.patch(url, json={"name": "x"}, headers=other).status_code == 404
    assert client.delete(url, headers=reader).status_code == 403
    assert client.delete(url, headers=other).status_code == 404
    _ok(client.delete(url, headers=h), 204)
    assert client.get(url, headers=h).status_code == 404


def test_party_in_use_cannot_be_deleted(client: TestClient, world: World) -> None:
    h, _, _ = _heads(client, world)
    prop = _property(client, h, "761", "rental")
    unit = _unit(client, h, prop["id"], "01")
    tenant, _ = _party(client, h, "Mieter")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    body = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": "2026-01-01"}
    _ok(client.post("/api/v1/contracts", json=body, headers=h), 201)
    res = client.delete(f"/api/v1/parties/{tenant}", headers=h)
    assert res.status_code == 409, res.text
    assert client.get(f"/api/v1/parties/{tenant}", headers=h).status_code == 200


# M3-02 notes, M3-04 tags --------------------------------------------------------------


def test_notes_patch_delete(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    contact = _contact(client, h, "Notiz")
    base = f"/api/v1/contacts/{contact['id']}/notes"
    note = _ok(
        client.post(base, json={"body": "erster Text", "category": "allgemein"}, headers=h), 201
    )
    url = f"{base}/{note['id']}"
    out = _ok(client.patch(url, json={"pinned": True, "category": "wichtig"}, headers=h))
    assert out["pinned"] is True
    assert out["category"] == "wichtig"
    assert out["body"] == "erster Text"
    assert _ok(client.patch(url, json={"body": "neuer Text"}, headers=h))["body"] == "neuer Text"
    assert client.patch(url, json={"body": ""}, headers=h).status_code == 422
    assert client.patch(url, json={"body": None}, headers=h).status_code == 422
    assert client.patch(url, json={"pinned": True}, headers=reader).status_code == 403
    assert client.patch(url, json={"pinned": True}, headers=other).status_code == 404
    assert client.delete(url, headers=reader).status_code == 403
    assert client.delete(url, headers=other).status_code == 404
    other_contact = _contact(client, h, "Andere")
    wrong = f"/api/v1/contacts/{other_contact['id']}/notes/{note['id']}"
    assert client.delete(wrong, headers=h).status_code == 404
    _ok(client.delete(url, headers=h), 204)
    assert _ok(client.get(base, headers=h)) == []


def test_tag_administration(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    t_a, t_b = f"vip{RUN}", f"vip-alt{RUN}"
    _contact(client, h, "Tag1", tags=[t_a, t_b])
    c2 = _contact(client, h, "Tag2", tags=[t_b])
    tags = {t["name"]: t for t in _ok(client.get("/api/v1/contact-tags", headers=h))}
    assert tags[t_a]["contacts"] == 1
    assert tags[t_b]["contacts"] == 2
    assert client.get("/api/v1/contact-tags", headers=other).json() == []
    a_id, b_id = tags[t_a]["id"], tags[t_b]["id"]
    # Rename: duplicate name conflicts, free name works.
    assert (
        client.patch(f"/api/v1/contact-tags/{a_id}", json={"name": t_b}, headers=h).status_code
        == 409
    )
    renamed = _ok(
        client.patch(f"/api/v1/contact-tags/{a_id}", json={"name": f"gold{RUN}"}, headers=h)
    )
    assert renamed["name"] == f"gold{RUN}"
    assert renamed["contacts"] == 1
    assert (
        client.patch(f"/api/v1/contact-tags/{a_id}", json={"name": "  "}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/contact-tags/{a_id}", json={"name": "x"}, headers=reader).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/contact-tags/{a_id}", json={"name": "x"}, headers=other).status_code
        == 404
    )
    # Merge gold into vip-alt: c1 is on both, counts stay 2 without duplicate links.
    assert (
        client.post(
            f"/api/v1/contact-tags/{a_id}/merge", json={"target_id": a_id}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/contact-tags/{a_id}/merge", json={"target_id": b_id}, headers=other
        ).status_code
        == 404
    )
    merged = _ok(
        client.post(f"/api/v1/contact-tags/{a_id}/merge", json={"target_id": b_id}, headers=h)
    )
    assert merged["contacts"] == 2
    assert a_id not in {t["id"] for t in _ok(client.get("/api/v1/contact-tags", headers=h))}
    assert client.delete(f"/api/v1/contact-tags/{b_id}", headers=reader).status_code == 403
    _ok(client.delete(f"/api/v1/contact-tags/{b_id}", headers=h), 204)
    assert _ok(client.get(f"/api/v1/contacts/{c2['id']}", headers=h))["tags"] == []


# M4 properties ------------------------------------------------------------------------


def test_bank_account_and_provider_maintenance(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "762", "name": "Objekt 762", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    pid = prop["id"]
    entity = prop["legal_entities"][0]["id"]
    account = _ok(
        client.post(
            f"/api/v1/properties/{pid}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "hoa",
                "iban": IBAN,
                "holder": "WEG 762",
                "valid_from": "2026-01-01",
                "is_default": True,
            },
            headers=h,
        ),
        201,
    )
    url = f"/api/v1/properties/{pid}/bank-accounts/{account['id']}"
    out = _ok(
        client.patch(
            url,
            json={"bank_name": "Testbank", "notes": "Umzug", "valid_to": "2026-06-30"},
            headers=h,
        )
    )
    assert out["bank_name"] == "Testbank"
    assert out["valid_to"] == "2026-06-30"
    assert out["is_default"] is False  # an ended account is no payment target
    assert out["iban_masked"] == account["iban_masked"]
    assert client.patch(url, json={"valid_to": "2025-12-31"}, headers=h).status_code == 422
    assert client.patch(url, json={"iban": IBAN}, headers=h).status_code == 422
    assert client.patch(url, json={"bic": "xx"}, headers=h).status_code == 422
    assert client.patch(url, json={"holder": None}, headers=h).status_code == 422
    assert (
        client.patch(url, json={"bank_connection_id": str(uuid.uuid4())}, headers=h).status_code
        == 404
    )
    assert client.patch(url, json={"notes": "x"}, headers=reader).status_code == 403
    assert client.patch(url, json={"notes": "x"}, headers=other).status_code == 404
    wrong_prop = f"/api/v1/properties/{uuid.uuid4()}/bank-accounts/{account['id']}"
    assert client.patch(wrong_prop, json={"notes": "x"}, headers=h).status_code == 404

    person = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "last_name": f"Dienst{RUN}",
                "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )
    provider = _ok(
        client.post(
            f"/api/v1/properties/{pid}/service-providers",
            json={
                "contact_id": person["id"],
                "contract_type_code": "caretaker",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    purl = f"/api/v1/properties/{pid}/service-providers/{provider['id']}"
    done = _ok(
        client.patch(
            purl,
            json={"valid_to": "2026-12-31", "notice_period": "3m", "notes": "gekündigt"},
            headers=h,
        )
    )
    assert done["valid_to"] == "2026-12-31"
    assert done["notice_period"] == "3m"
    assert client.patch(purl, json={"valid_to": "2025-01-01"}, headers=h).status_code == 422
    foreign = _contact(client, h, "Fremdkonto")
    assert (
        client.patch(
            purl, json={"contact_bank_account_id": str(uuid.uuid4())}, headers=h
        ).status_code
        == 404
    )
    assert client.patch(purl, json={"categories": None}, headers=h).status_code == 422
    assert client.patch(purl, json={"notes": "x"}, headers=reader).status_code == 403
    assert client.patch(purl, json={"notes": "x"}, headers=other).status_code == 404
    assert foreign["id"]


def test_vat_history_meter_photo_and_images(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "763", "name": "Objekt 763", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    pid = prop["id"]
    unit = _unit(client, h, pid, "01")
    for start, end, option in (
        ("2026-01-01", "2026-06-30", "none"),
        ("2026-07-01", None, "commercial_full_vat"),
    ):
        _ok(
            client.post(
                f"/api/v1/units/{unit}/vat-options",
                json={
                    "option": option,
                    "occupant": "vacancy",
                    "valid_from": start,
                    "valid_to": end,
                },
                headers=h,
            ),
            201,
        )
    history = _ok(client.get(f"/api/v1/units/{unit}/vat-options", headers=reader))
    assert [r["valid_from"] for r in history] == ["2026-07-01", "2026-01-01"]
    assert client.get(f"/api/v1/units/{unit}/vat-options", headers=other).status_code == 404
    assert client.get(f"/api/v1/units/{uuid.uuid4()}/vat-options", headers=h).status_code == 404

    doc = _doc(client, h, "Zaehlerfoto")
    meter = _ok(
        client.post(
            f"/api/v1/properties/{pid}/meters",
            json={"meter_type_code": "cold_water", "number": "KW-P16", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    reading = _ok(
        client.post(
            f"/api/v1/meters/{meter['id']}/readings",
            json={"read_at": "2026-02-01", "value": "10", "photo_document_id": doc},
            headers=h,
        ),
        201,
    )
    assert reading["photo_document_id"] == doc
    assert (
        _ok(client.get(f"/api/v1/meters/{meter['id']}/readings", headers=h))[0]["photo_document_id"]
        == doc
    )
    missing = {"read_at": "2026-03-01", "value": "11", "photo_document_id": str(uuid.uuid4())}
    assert (
        client.post(f"/api/v1/meters/{meter['id']}/readings", json=missing, headers=h).status_code
        == 422
    )

    # Image gallery: PATCH keeps the order, unknown or duplicate documents are refused.
    img2 = _doc(client, h, "Bild2")
    out = _ok(client.patch(f"/api/v1/properties/{pid}", json={"images": [img2, doc]}, headers=h))
    assert out["images"] == [img2, doc]
    assert _ok(client.get(f"/api/v1/properties/{pid}", headers=h))["images"] == [img2, doc]
    assert (
        client.patch(
            f"/api/v1/properties/{pid}", json={"images": [str(uuid.uuid4())]}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/properties/{pid}", json={"images": [doc, doc]}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/properties/{pid}", json={"images": ["x"]}, headers=h).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/properties/{pid}", json={"images": []}, headers=reader).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/properties/{pid}", json={"images": []}, headers=other).status_code
        == 404
    )


# M5 contracts -------------------------------------------------------------------------


def _tenancy(c: TestClient, h: dict[str, str], number: str, **extra: Any) -> dict[str, Any]:
    prop = _property(c, h, number, "rental")
    unit = _unit(c, h, prop["id"], "01")
    tenant, _ = _party(c, h, "Mieter")
    owner, _ = _party(c, h, "Eigentuemer", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    body = {"kind": "tenancy", "unit_id": unit, "party_id": tenant, "start_date": "2026-01-01"}
    return _ok(c.post("/api/v1/contracts", json=body | extra, headers=h), 201)  # type: ignore[no-any-return]


def test_contract_custom_fields(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    key = f"schluessel_{RUN}"
    _ok(
        client.post(
            "/api/v1/custom-fields",
            json={
                "entity_type": "contract",
                "key": key,
                "label": "Schlüsselanzahl",
                "field_type": "integer",
                "min_value": "0",
                "max_value": "20",
            },
            headers=h,
        ),
        201,
    )
    contract = _tenancy(client, h, "764", custom_fields={key: 3})
    assert contract["custom_fields"] == {key: 3}
    url = f"/api/v1/contracts/{contract['id']}/custom-fields"
    assert _ok(client.patch(url, json={"custom_fields": {key: 5}}, headers=h))["custom_fields"] == {
        key: 5
    }
    assert client.patch(url, json={"custom_fields": {key: 99}}, headers=h).status_code == 422
    assert client.patch(url, json={"custom_fields": {"unbekannt": 1}}, headers=h).status_code == 422
    assert client.patch(url, json={"custom_fields": {key: 1}}, headers=reader).status_code == 403
    assert client.patch(url, json={"custom_fields": {key: 1}}, headers=other).status_code == 404
    assert (
        _ok(client.patch(url, json={"custom_fields": {key: None}}, headers=h))["custom_fields"]
        == {}
    )
    bad = _tenancy_bad(client, h)
    assert bad == 422


def _tenancy_bad(c: TestClient, h: dict[str, str]) -> int:
    prop = _property(c, h, "765", "rental")
    unit = _unit(c, h, prop["id"], "01")
    tenant, _ = _party(c, h, "Mieter2")
    body = {
        "kind": "tenancy",
        "unit_id": unit,
        "party_id": tenant,
        "start_date": "2026-01-01",
        "custom_fields": {"nope": 1},
    }
    return c.post("/api/v1/contracts", json=body, headers=h).status_code


def test_payment_and_schedule_correction(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    contract = _tenancy(client, h, "766")
    cid = contract["id"]
    pay = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("500.00", "500.00", "2026-01-01"),
            headers=h,
        ),
        201,
    )
    url = f"/api/v1/contracts/{cid}/payments/{pay['id']}"
    out = _ok(client.patch(url, json={"net": "520.00", "gross": "520.00"}, headers=h))
    assert out["gross"] == "520.00"
    out = _ok(client.patch(url, json={"valid_to": "2026-12-31"}, headers=h))
    assert out["valid_to"] == "2026-12-31"
    assert client.patch(url, json={"gross": "999.00"}, headers=h).status_code == 422  # net mismatch
    assert client.patch(url, json={"valid_to": "2025-12-31"}, headers=h).status_code == 422
    assert client.patch(url, json={"valid_from": "2020-01-01"}, headers=h).status_code == 422
    assert client.patch(url, json={"net": None}, headers=h).status_code == 422
    assert (
        client.patch(url, json={"revenue_account_id": str(uuid.uuid4())}, headers=h).status_code
        == 404
    )
    assert client.patch(url, json={"document_id": str(uuid.uuid4())}, headers=h).status_code == 404
    assert client.patch(url, json={"net": "1.00"}, headers=reader).status_code == 403
    assert client.patch(url, json={"net": "1.00"}, headers=other).status_code == 404
    other_contract = _tenancy(client, h, "767")
    cross = f"/api/v1/contracts/{other_contract['id']}/payments/{pay['id']}"
    assert client.patch(cross, json={"valid_to": "2026-12-31"}, headers=h).status_code == 404

    sched = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/schedules",
            json={"valid_from": "2026-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    surl = f"/api/v1/contracts/{cid}/schedules/{sched['id']}"
    assert _ok(client.patch(surl, json={"due_day": 5}, headers=h))["due_day"] == 5
    assert (
        _ok(client.patch(surl, json={"valid_to": "2026-12-31"}, headers=h))["valid_to"]
        == "2026-12-31"
    )
    assert client.patch(surl, json={"due_day": 40}, headers=h).status_code == 422
    assert client.patch(surl, json={"valid_to": "2025-01-01"}, headers=h).status_code == 422
    assert client.patch(surl, json={"due_day": None}, headers=h).status_code == 422
    assert client.patch(surl, json={"due_day": 4}, headers=reader).status_code == 403
    assert client.patch(surl, json={"due_day": 4}, headers=other).status_code == 404


def test_posted_payment_keeps_financial_content(
    database: Database, redis_url: str, client: TestClient, world: World
) -> None:
    """A payment row used by a posted receivable item refuses financial changes (rule 7)."""
    h, _, _ = _heads(client, world)
    contract = _tenancy(client, h, "768")
    cid = contract["id"]
    pay = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/payments",
            json=_payment("400.00", "400.00", "2026-01-01"),
            headers=h,
        ),
        201,
    )

    async def post_item() -> None:
        from decimal import Decimal

        from mhvp.accounting.models import ItemStatus, ReceivableItem, ReceivableRun, RunStatus

        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                run = ReceivableRun(
                    tenant_id=world.tenant_a,
                    period_month=date(2026, 1, 1),
                    status=RunStatus.POSTED,
                    preview_hash="p16",
                )
                session.add(run)
                await session.flush()
                session.add(
                    ReceivableItem(
                        tenant_id=world.tenant_a,
                        run_id=run.id,
                        contract_id=uuid.UUID(cid),
                        contract_payment_id=uuid.UUID(pay["id"]),
                        period_month=date(2026, 1, 1),
                        payment_type_code="rent",
                        amount=Decimal("400.00"),
                        status=ItemStatus.POSTED,
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(post_item())
    url = f"/api/v1/contracts/{cid}/payments/{pay['id']}"
    assert (
        client.patch(url, json={"net": "410.00", "gross": "410.00"}, headers=h).status_code == 409
    )
    assert client.patch(url, json={"valid_to": "2026-12-31"}, headers=h).status_code == 409
    doc = _doc(client, h, "Mietvertrag")
    assert _ok(client.patch(url, json={"document_id": doc}, headers=h))["net"] == "400.00"


def test_deposit_status_documents_and_limits(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    contract = _tenancy(client, h, "769")
    cid = contract["id"]
    dep = _ok(
        client.post(
            f"/api/v1/contracts/{cid}/deposits",
            json={"kind": "cash", "amount_due": "1500.00", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    assert dep["status"] == "open"
    assert dep["documents"] == []
    url = f"/api/v1/deposits/{dep['id']}"
    doc = _doc(client, h, "Kautionsvertrag")
    out = _ok(
        client.patch(
            url, json={"amount_due": "1200.00", "installments": 3, "documents": [doc]}, headers=h
        )
    )
    assert out["amount_due"] == "1200.00"
    assert out["documents"] == [doc]
    assert client.patch(url, json={"documents": [str(uuid.uuid4())]}, headers=h).status_code == 422
    assert client.patch(url, json={"status": "bogus"}, headers=h).status_code == 422
    assert client.patch(url, json={"amount_due": "0"}, headers=h).status_code == 422
    assert client.patch(url, json={"status": "active"}, headers=reader).status_code == 403
    assert client.patch(url, json={"status": "active"}, headers=other).status_code == 404
    _ok(
        client.post(
            f"{url}/movements",
            json={"date": "2026-02-01", "amount": "400.00", "kind": "payment"},
            headers=h,
        ),
        201,
    )
    assert client.patch(url, json={"amount_due": "1300.00"}, headers=h).status_code == 409
    assert _ok(client.patch(url, json={"status": "active"}, headers=h))["status"] == "active"
    assert _ok(client.patch(url, json={"status": "settled"}, headers=h))["status"] == "settled"
    assert client.patch(url, json={"status": "open"}, headers=h).status_code == 409
    assert client.patch(url, json={"interest_rule": "x"}, headers=h).status_code == 409
    assert _ok(client.patch(url, json={"documents": [doc]}, headers=h))["documents"] == [doc]


# M5-03 / M5-05 SEPA lifecycle ---------------------------------------------------------


def test_sepa_expiry_usage_and_overview(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h, _, _ = _heads(client, world)
    party, contact = _party(client, h, "Sepa", iban=IBAN)
    from tests.integration.conftest import approve_bank_accounts

    approve_bank_accounts(client, bearer(login(client, world, "p16approver")), contact)
    account = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))["bank_accounts"][0][
        "id"
    ]
    doc = _doc(client, h, "Mandat")
    prop = _property(client, h, "770", "rental")
    owner, _ = _party(client, h, "Eigen", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]

    def mandate(ref: str, valid_until: str | None) -> dict[str, Any]:
        body = {
            "party_id": party,
            "legal_entity_id": entity,
            "contact_bank_account_id": account,
            "reference": f"P16-{RUN}-{ref}",
            "creditor_id": "DE98ZZZ09999999999",
            "signed_at": "2025-01-01",
            "type": "core",
            "sequence": "first",
            "valid_until": valid_until,
            "document_id": doc,
        }
        return _ok(client.post("/api/v1/sepa-mandates", json=body, headers=h), 201)  # type: ignore[no-any-return]

    old = mandate("old", "2026-03-31")
    fresh = mandate("new", "2027-12-31")
    listed = _ok(
        client.get("/api/v1/sepa-mandates", params={"expiring_until": "2026-12-31"}, headers=h)
    )
    assert [m["id"] for m in listed] == [old["id"]]
    assert {
        m["id"]
        for m in _ok(client.get("/api/v1/sepa-mandates", params={"unused": "true"}, headers=h))
    } >= {old["id"], fresh["id"]}

    async def run() -> int:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                mandate_row = await session.get(SepaMandate, uuid.UUID(fresh["id"]))
                assert mandate_row is not None
                mark_mandate_used(mandate_row)
                assert mandate_row.sequence is MandateSequence.RECURRING
                assert mandate_row.last_used_at is not None
                return await expire_due_mandates(session, date(2026, 9, 30))
        finally:
            await engine.dispose()

    assert asyncio.run(run()) >= 1
    states = {m["id"]: m for m in _ok(client.get("/api/v1/sepa-mandates", headers=h))}
    assert states[old["id"]]["status"] == MandateStatus.EXPIRED.value
    assert states[fresh["id"]]["status"] == "active"
    assert states[fresh["id"]]["sequence"] == "recurring"
    assert states[fresh["id"]]["last_used_at"]
