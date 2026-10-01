"""M17-01 to M17-08: interim statement, draft editing, results per contract with cost
breakdown, access per tenant, difference report, Belegeinsicht and result entries as drafts
behind G3. Expected values by hand: one let unit (WFL 60, whole year 2025), Gartenpflege
120,00 EUR, no advances -> costs 120,00, balance 120,00 (Nachzahlung). New version with
Gartenpflege 150,00 -> costs 150,00, delta +30,00."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_operating_costs import OpenG3, _rental_world, _statement

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
S = "/api/v1/statements"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bk17r-{RUN}", name=f"BKR {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"bk17rb-{RUN}", name=f"BKRB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m17radmin", a, "tenant_admin"),
            ("m17racc", a, "accountant_no_banking"),
            ("m17rread", a, "read_only"),
            ("m17rother", b, "tenant_admin"),
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


async def _evidence_document(settings: Any, tenant: Any) -> str:
    """Document row as evidence of the deadline exception (no object storage needed)."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
            doc = Document(
                tenant_id=tenant,
                title="Nachweis Messdienst",
                filename="nachweis.pdf",
                mime_type="application/pdf",
                size=10,
                sha256="e" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref-deadline",
                text_status=TextStatus.NONE,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(doc)
            await session.flush()
            return str(doc.id)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _item(w: dict[str, Any], amount: str = "120.00") -> dict[str, Any]:
    return {
        "label": "Gartenpflege",
        "amount": amount,
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "§ 4 Mietvertrag, Nr. 10 BetrKV",
    }


def test_m17_04_interim_needs_purpose_and_m17_08_draft_editing(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "m17radmin"))
    w = _rental_world(client, h, "871")
    half = {"ledger_id": w["ledger"], "period_from": "2025-01-01", "period_to": "2025-06-30"}
    assert client.post(S, json=half, headers=h).status_code == 422  # not twelve months
    assert client.post(S, json=half | {"interim": True}, headers=h).status_code == 422
    st = _ok(
        client.post(
            S,
            json=half
            | {
                "interim": True,
                "purpose": "Auszug des Mieters, Zwischenabrechnung vereinbart",
                "include_heating": False,
                "settings": {"text_credit": "Guthaben wird erstattet.", "bundled": True},
            },
            headers=h,
        ),
        201,
    )
    assert (st["interim"], st["include_heating"]) == (True, False)
    assert st["settings"] == {"text_credit": "Guthaben wird erstattet.", "bundled": True}
    # Header change in draft: whole year again, interim switched off, purpose kept.
    patched = _ok(
        client.patch(
            f"{S}/{st['id']}",
            json={
                "period_to": "2025-12-31",
                "interim": False,
                "settings": {"format": "pdf_bundle"},
            },
            headers=h,
        )
    )
    assert (patched["period_to"], patched["interim"]) == ("2025-12-31", False)
    assert patched["settings"]["format"] == "pdf_bundle"
    assert patched["settings"]["bundled"] is True
    bad = client.patch(f"{S}/{st['id']}", json={"settings": {"format": "docx"}}, headers=h)
    assert bad.status_code == 422

    item = _ok(client.post(f"{S}/{st['id']}/cost-items", json=_item(w), headers=h), 201)
    second = _ok(client.post(f"{S}/{st['id']}/cost-items", json=_item(w, "10.00"), headers=h), 201)
    _ok(client.put(f"{S}/{st['id']}/cost-items/{item['id']}", json=_item(w, "90.00"), headers=h))
    assert client.delete(f"{S}/{st['id']}/cost-items/{second['id']}", headers=h).status_code == 204
    items = _ok(client.get(f"{S}/{st['id']}", headers=h))["cost_items"]
    assert [(i["label"], i["amount"]) for i in items] == [("Gartenpflege", "90.00")]
    # Validation, permission and tenant separation.
    assert (
        client.put(
            f"{S}/{st['id']}/cost-items/{item['id']}", json=_item(w, "-1.00"), headers=h
        ).status_code
        == 422
    )
    reader = bearer(login(client, world, "m17rread"))
    assert (
        client.put(
            f"{S}/{st['id']}/cost-items/{item['id']}", json=_item(w), headers=reader
        ).status_code
        == 403
    )
    assert client.patch(f"{S}/{st['id']}", json={}, headers=reader).status_code == 403
    other = bearer(login(client, world, "m17rother"))
    assert (
        client.put(
            f"{S}/{st['id']}/cost-items/{item['id']}", json=_item(w), headers=other
        ).status_code
        == 404
    )
    assert client.get(f"{S}/{st['id']}/results", headers=other).status_code == 404
    # After the calculation the draft is frozen: changes only via a new version.
    _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    assert (
        client.put(f"{S}/{st['id']}/cost-items/{item['id']}", json=_item(w), headers=h).status_code
        == 409
    )
    assert client.delete(f"{S}/{st['id']}/cost-items/{item['id']}", headers=h).status_code == 409
    assert client.patch(f"{S}/{st['id']}", json={}, headers=h).status_code == 409


def test_m17_02_03_05_06_results_access_diff_inspection(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "m17radmin"))
    acc_user = bearer(login(client, world, "m17racc"))
    w = _rental_world(client, h, "872")
    st = _statement(client, h, w["ledger"])
    _ok(client.post(f"{S}/{st['id']}/cost-items", json=_item(w), headers=h), 201)
    _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    (row,) = _ok(client.get(f"{S}/{st['id']}/results", headers=h))
    contract = w["contract"]["id"]
    assert (row["contract_id"], row["costs"], row["balance"]) == (contract, "120.00", "120.00")
    (line,) = row["lines"]
    assert (line["label"], line["total"], line["allocation_key"], line["share"]) == (
        "Gartenpflege",
        "120.00",
        "WFL",
        "120.00",
    )
    assert row["delivered_at"] is None
    assert row["objection_deadline_orientation"] is None

    delivery = {
        "delivery_method": "registered_mail",
        "delivered_at": "2099-01-15",
        "evidence": "Einwurf-Einschreiben, Sendungsnummer im Postausgangsbuch",
    }
    url = f"{S}/{st['id']}/results/{contract}/delivery"
    assert client.put(url, json=delivery, headers=h).status_code == 409  # not yet approved
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    assert client.put(url, json=delivery | {"evidence": ""}, headers=h).status_code == 422
    early = client.put(url, json=delivery | {"delivered_at": "2020-01-01"}, headers=h)
    assert early.status_code == 422, early.text
    reader = bearer(login(client, world, "m17rread"))
    assert client.put(url, json=delivery, headers=reader).status_code == 403
    stored = _ok(client.put(url, json=delivery, headers=h))
    assert (stored["delivered_at"], stored["delivery_method"]) == ("2099-01-15", "registered_mail")
    assert stored["objection_deadline_orientation"] == "2100-01-15"
    unknown = f"{S}/{st['id']}/results/{w['unit']}/delivery"
    assert client.put(unknown, json=delivery, headers=h).status_code == 404

    # Belegeinsicht: request, provision with redaction note, objection, close.
    base = f"{S}/{st['id']}/inspections"
    req = {"contract_id": contract, "requested_at": "2099-02-01", "channel": "email"}
    assert client.post(base, json=req | {"channel": "fax"}, headers=h).status_code == 422
    assert client.post(base, json=req, headers=reader).status_code == 403
    ins = _ok(client.post(base, json=req | {"scope": "Gartenpflege Rechnungen"}, headers=h), 201)
    assert ins["status"] == "requested"
    iurl = f"{base}/{ins['id']}"
    assert client.patch(iurl, json={"close": True}, headers=h).status_code == 409
    assert client.patch(iurl, json={"provision": "electronic"}, headers=h).status_code == 422
    provided = _ok(
        client.patch(
            iurl,
            json={
                "provision": "electronic",
                "provided_at": "2099-02-05",
                "redaction_note": "Namen Dritter auf Seite 2 geschwärzt, Original unverändert",
            },
            headers=h,
        )
    )
    assert (provided["status"], provided["provision"]) == ("provided", "electronic")
    assert (
        client.patch(iurl, json={"objection_received_at": "2099-03-01"}, headers=h).status_code
        == 422
    )
    closed = _ok(
        client.patch(
            iurl,
            json={
                "objection_received_at": "2099-03-01",
                "objection_text": "Gartenpflege zu hoch",
                "close": True,
            },
            headers=h,
        )
    )
    assert (closed["status"], closed["objection_text"]) == ("closed", "Gartenpflege zu hoch")
    assert [i["id"] for i in _ok(client.get(base, headers=reader))] == [ins["id"]]

    # Difference report: new version with 150,00 instead of 120,00.
    assert client.get(f"{S}/{st['id']}/diff", headers=h).status_code == 409
    new = _ok(client.post(f"{S}/{st['id']}/new-version", headers=h), 201)
    (old_item,) = _ok(client.get(f"{S}/{new['id']}", headers=h))["cost_items"]
    _ok(
        client.put(
            f"{S}/{new['id']}/cost-items/{old_item['id']}", json=_item(w, "150.00"), headers=h
        )
    )
    assert client.get(f"{S}/{new['id']}/diff", headers=h).status_code == 409  # not calculated
    _ok(client.post(f"{S}/{new['id']}/calculate", headers=h))
    report = _ok(client.get(f"{S}/{new['id']}/diff", headers=h))
    (tenant,) = report["tenants"]
    assert tenant["status"] == "changed"
    assert tenant["costs"] == {"old": "120.00", "new": "150.00", "delta": "30.00"}
    assert tenant["balance"]["delta"] == "30.00"
    assert report["positions"] == [
        {"label": "Gartenpflege", "old": "120.00", "new": "150.00", "delta": "30.00"}
    ]


def test_m17_01_result_entries_are_drafts_behind_g3(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m17radmin"))
    # The M17-01 allocation basis lock (AE17, default on) is covered by its own tests; this
    # world records no allocation agreements, so it is switched off for this tenant only.
    assert (
        client.put(
            "/api/v1/billing/allocation-basis-setting", json={"block_output": False}, headers=h
        ).status_code
        == 200
    )
    acc_user = bearer(login(client, world, "m17racc"))
    w = _rental_world(client, h, "873")
    ledger = w["ledger"]
    result_account = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "060900",
                "name": "Abrechnungsergebnis BK",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "statement_result", "account_id": result_account},
            headers=h,
        )
    )
    st = _statement(client, h, ledger)
    # A recorded exception keeps the test independent of the day it runs (A04 lock).
    exception = "Verzögerung durch Messdienst, Nachweis Schreiben vom 10.12.2026"
    text_only = _ok(
        client.patch(f"{S}/{st['id']}", json={"deadline_exception": exception}, headers=h)
    )
    # GA06-04: the reason alone does not release a late claim; evidence document required.
    assert text_only["deadline_exception_effective"] is False
    assert text_only["deadline_exception_set_by"] is not None
    unknown = {"deadline_exception_document_id": "00000000-0000-7000-8000-000000000000"}
    assert client.patch(f"{S}/{st['id']}", json=unknown, headers=h).status_code == 422
    evidence = asyncio.run(_evidence_document(_settings(database, redis_url), world.tenant_a))
    with_doc = _ok(
        client.patch(
            f"{S}/{st['id']}", json={"deadline_exception_document_id": evidence}, headers=h
        )
    )
    assert with_doc["deadline_exception_effective"] is True
    assert with_doc["deadline_exception_document_id"] == evidence
    _ok(client.post(f"{S}/{st['id']}/cost-items", json=_item(w), headers=h), 201)
    _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    body = {"booking_date": "2026-10-15", "due_date": "2026-11-15"}
    closed = client.post(f"{S}/{st['id']}/result-entries", json=body, headers=acc_user)
    assert closed.status_code == 403, closed.text
    assert closed.json()["code"] == "MHVP-GATE-0001"
    gh = bearer(login(gated, world, "m17racc"))
    early = gated.post(f"{S}/{st['id']}/result-entries", json=body, headers=gh)
    assert early.status_code == 409  # only from status due
    _ok(
        gated.post(
            f"{S}/{st['id']}/transition",
            json={"target": "issued", "delivered_at": "2099-01-15"},
            headers=gh,
        )
    )
    # The due transition is gated as well (M17-01).
    due_closed = client.post(f"{S}/{st['id']}/transition", json={"target": "due"}, headers=acc_user)
    assert due_closed.status_code == 403
    _ok(gated.post(f"{S}/{st['id']}/transition", json={"target": "due"}, headers=gh))
    no_posting = gated.post(f"{S}/{st['id']}/transition", json={"target": "posted"}, headers=gh)
    assert no_posting.status_code == 409  # drafts missing
    created = _ok(gated.post(f"{S}/{st['id']}/result-entries", json=body, headers=gh), 201)
    (entry_id,) = created["entry_ids"]
    again = _ok(gated.post(f"{S}/{st['id']}/result-entries", json=body, headers=gh), 201)
    assert again["entry_ids"] == [entry_id]  # idempotent
    entry = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))
    assert (entry["status"], entry["kind"], entry["source"]) == (
        "draft",
        "statement_result",
        "statement",
    )
    lines = sorted((ln["debit"], ln["credit"]) for ln in entry["lines"])
    assert lines == [("0.00", "120.00"), ("120.00", "0.00")]
    still_draft = gated.post(f"{S}/{st['id']}/transition", json={"target": "posted"}, headers=gh)
    assert still_draft.status_code == 409
    assert "Entwurf" in still_draft.json()["detail"]
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{entry_id}/post", headers=h))
    posted = _ok(gated.post(f"{S}/{st['id']}/transition", json={"target": "posted"}, headers=gh))
    assert posted["status"] == "posted"
    locked = _ok(gated.post(f"{S}/{st['id']}/transition", json={"target": "locked"}, headers=gh))
    assert locked["status"] == "locked"
    assert locked["locked_at"]
