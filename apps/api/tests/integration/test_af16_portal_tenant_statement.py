"""AF16 (GAC-02): tenant portal view of the released operating cost statement.

Expected values by hand: tenant 1 has costs of 300,00 EUR (Grundsteuer 200,00 EUR plus Wasser
100,00 EUR of his contract), advances paid 250,00 EUR, balance 50,00 EUR additional payment.
Visible only for the own contract, only for an issued statement, only with the tenant switch
on and G3 open; otherwise the list is empty with a note and detail/PDF answer 403. A foreign
contract or a draft statement answers 404. Explanations without approved text block show the
placeholder. Detail and PDF write read receipts."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.portal.tenant_statements import DISABLED_NOTE, GATE_NOTE, PLACEHOLDER
from tests.integration.conftest import Database
from tests.integration.test_a61_inspection import _world
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal/tenant-statements"
PA = "/api/v1/portal-admin"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "af16", "af16admin", "af16reader"))


@pytest.fixture(scope="module")
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _run(database: Database, redis_url: str, world: World, fn: Any) -> Any:
    async def go() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _statements(
    database: Database,
    redis_url: str,
    world: World,
    *,
    entity: str,
    prop: str,
    c1: str,
    c2: str,
    doc: str,
) -> tuple[UUID, UUID]:
    from mhvp.accounting.models import Ledger
    from mhvp.billing.models import (
        Statement,
        StatementKind,
        StatementResult,
        StatementSnapshot,
    )
    from mhvp.billing.status import StatementStatus

    async def fn(session: Any) -> tuple[UUID, UUID]:
        ledger = await session.scalar(select(Ledger).where(Ledger.legal_entity_id == UUID(entity)))
        if ledger is None:
            ledger = Ledger(
                tenant_id=world.tenant_a,
                legal_entity_id=UUID(entity),
                property_id=UUID(prop),
                name="AF16 Ledger",
            )
            session.add(ledger)
            await session.flush()
        ids = []
        for status in (StatementStatus.ISSUED, StatementStatus.CALCULATED):
            st = Statement(
                tenant_id=world.tenant_a,
                kind=StatementKind.OPERATING_COSTS,
                ledger_id=ledger.id,
                property_id=UUID(prop),
                period_from=date(2025, 1, 1),
                period_to=date(2025, 12, 31),
                status=status,
            )
            session.add(st)
            await session.flush()
            snap = StatementSnapshot(
                tenant_id=world.tenant_a,
                statement_id=st.id,
                rule_version="af16",
                hash="b" * 64,
                inputs={
                    "positions": [
                        {
                            "label": "Grundsteuer",
                            "amount": "400.00",
                            "basis": "Wohnfläche",
                            "allocation_key": {"code": "wfl", "name": "Wohnfläche"},
                            "split": {f"contract:{c1}": "200.00", f"contract:{c2}": "200.00"},
                        },
                        {
                            "label": "Wasser",
                            "amount": "250.00",
                            "basis": "Verbrauch",
                            "split": {f"contract:{c1}": "100.00", f"contract:{c2}": "150.00"},
                        },
                    ]
                },
                results={
                    "results": [
                        {
                            "contract_id": c1,
                            "unit_number": "01",
                            "costs": "300.00",
                            "advances_paid": "250.00",
                            "balance": "50.00",
                        },
                        {
                            "contract_id": c2,
                            "unit_number": "02",
                            "costs": "350.00",
                            "advances_paid": "400.00",
                            "balance": "-50.00",
                        },
                    ]
                },
            )
            session.add(snap)
            await session.flush()
            st.snapshot_id = snap.id
            for cid, document in ((c1, UUID(doc)), (c2, None)):
                session.add(
                    StatementResult(
                        tenant_id=world.tenant_a,
                        statement_id=st.id,
                        contract_id=UUID(cid),
                        document_id=document,
                    )
                )
            await session.flush()
            ids.append(st.id)
        return ids[0], ids[1]

    return _run(database, redis_url, world, fn)  # type: ignore[no-any-return]


def test_tenant_statement_scope_switch_and_gate(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, open_ = clients
    h = bearer(login(open_, world, "af16admin"))
    prop = _ok(
        open_.post(
            "/api/v1/properties",
            json={"number": "161", "name": "Miete AF16", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(open_, h, "EigAF16", "company")
    entity = _ok(
        open_.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    contracts = []
    tenants = []
    for number in ("01", "02"):
        unit = _unit(open_, h, prop["id"], number)
        party, _ = _party(open_, h, f"MieterAF16{number}")
        contracts.append(
            _ok(
                open_.post(
                    "/api/v1/contracts",
                    json={
                        "kind": "tenancy",
                        "unit_id": unit,
                        "party_id": party,
                        "start_date": "2024-01-01",
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
        tenants.append(party)
    files = {"file": ("bk.pdf", b"%PDF-1.4 af16", "application/pdf")}
    doc = str(_ok(open_.post("/api/v1/documents", files=files, headers=h), 201)["id"])
    issued, draft = _statements(
        database, redis_url, world, entity=entity, prop=prop["id"],
        c1=contracts[0], c2=contracts[1], doc=doc,
    )  # fmt: skip
    t1 = _portal_user(open_, h, world, "af16t1", _contact_of(open_, h, tenants[0]))
    t2 = _portal_user(open_, h, world, "af16t2", _contact_of(open_, h, tenants[1]))
    detail = f"{P}/{issued}/contracts/{contracts[0]}"

    # Switch off (default): empty with note, detail locked.
    off = _ok(open_.get(P, headers=t1))
    assert off == {"items": [], "available": False, "note": DISABLED_NOTE}
    assert open_.get(detail, headers=t1).status_code == 403
    assert open_.get(P, params={"x": "1"}, headers=t1).status_code == 422

    reader = bearer(login(open_, world, "af16reader"))
    assert (
        open_.patch(
            f"{PA}/features", json={"tenant_statement_enabled": True}, headers=reader
        ).status_code
        == 403
    )
    _ok(open_.patch(f"{PA}/features", json={"tenant_statement_enabled": True}, headers=h))

    # G3 closed: empty with note, detail and PDF 403.
    assert _ok(closed.get(P, headers=t1))["note"] == GATE_NOTE
    assert _ok(closed.get(P, headers=t1))["items"] == []
    assert closed.get(detail, headers=t1).status_code == 403
    assert closed.get(f"{detail}/pdf", headers=t1).status_code == 403

    # G3 open: only the issued statement of the own contract.
    listed = _ok(open_.get(P, headers=t1))
    assert listed["available"] is True
    assert [(i["statement_id"], i["contract_id"]) for i in listed["items"]] == [
        (str(issued), contracts[0])
    ]
    assert listed["items"][0]["balance"] == "50.00"
    assert listed["items"][0]["has_pdf"] is True

    body = _ok(open_.get(detail, headers=t1))
    assert body["costs"] == "300.00"
    assert body["advances_paid"] == "250.00"
    assert [(p["label"], p["own_share"]) for p in body["positions"]] == [
        ("Grundsteuer", "200.00"),
        ("Wasser", "100.00"),
    ]
    assert body["positions"][0]["allocation_key"] == "Wohnfläche"
    assert set(body["explanations"]) == {"key", "consumption", "advance", "balance"}
    assert all(
        e["released"] is False and e["text"] == PLACEHOLDER for e in body["explanations"].values()
    )
    assert body["read_receipt"] is not None

    # Foreign contract, foreign statement, draft and unknown ids: 404.
    assert open_.get(f"{P}/{issued}/contracts/{contracts[1]}", headers=t1).status_code == 404
    assert open_.get(f"{P}/{draft}/contracts/{contracts[0]}", headers=t1).status_code == 404
    assert open_.get(f"{P}/{uuid.uuid4()}/contracts/{contracts[0]}", headers=t1).status_code == 404
    assert open_.get(f"{detail}/pdf", headers=t2).status_code == 404
    # Tenant 2 sees his own row without PDF.
    other = _ok(open_.get(P, headers=t2))["items"]
    assert [(i["contract_id"], i["balance"], i["has_pdf"]) for i in other] == [
        (contracts[1], "-50.00", False)
    ]
    assert open_.get(f"{P}/{issued}/contracts/{contracts[1]}/pdf", headers=t2).status_code == 404

    pdf = open_.get(f"{detail}/pdf", headers=t1)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content == b"%PDF-1.4 af16"
    receipts = _ok(open_.get(f"/api/v1/documents/{doc}/portal-read-receipts", headers=h))
    kinds = sorted(r["kind"] for r in receipts["items"])
    assert kinds == ["downloaded", "opened"]

    # A staff session is no portal account.
    assert open_.get(P, headers=h).status_code in (401, 403)
