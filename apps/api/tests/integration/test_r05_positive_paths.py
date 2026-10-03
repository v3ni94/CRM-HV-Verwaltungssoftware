"""R05 (Q09/Q10 remainders): positive paths and the tenant default for inspection packages.

Expected values by hand: a statement snapshot with one unit (cost share 100,00 EUR) is shown
to the owner of exactly that unit once it is issued and G4 is open, as PDF; before issue, with
G4 closed, for a foreign owner or a foreign unit it never is. The position context of a booked
invoice of 120,00 EUR shows invoice, order, payment of 120,00 EUR and the allocation key of the
cost item. The portal receipt search runs in the database: "100%" matches only the literal
percent sign; the tenant default of 14 days sets the expiry of a package without own period."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
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
from tests.integration.conftest import Database
from tests.integration.test_a61_inspection import _world
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m10_ledger import _accounts, _book, _entry, _line
from tests.integration.test_m21_board_portal import (
    _board_login,
    _doc,
    _ledger_with_invoice,
)
from tests.integration.test_m21_portal import _contact_of, _portal_user

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
TS = "/api/v1/tenant/settings"
ACC = "/api/v1/accounting"
P = "/api/v1/portal"
B = "/api/v1/portal/board"


class OpenG4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G4


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "r05", "r05admin", "r05reader"))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
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


def _community(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    """Community with one owner (unit 01), a board contact and a ledger with default accounts."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG R05 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party, _ = _party(c, h, f"EigR05{number}")
    unit = _unit(c, h, prop["id"], "01")
    _ok(
        c.post(
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
    _, board = _party(c, h, f"BeiR05{number}")
    return {
        "hoa": hoa,
        "property": str(prop["id"]),
        "party": party,
        "unit": unit,
        "board": board,
    }


def _ledger_of(database: Database, redis_url: str, world: World, hoa: str) -> UUID:
    from mhvp.accounting.models import Ledger

    async def fn(session: Any) -> UUID:
        return UUID(
            str(await session.scalar(select(Ledger.id).where(Ledger.legal_entity_id == UUID(hoa))))
        )

    return _run(database, redis_url, world, fn)  # type: ignore[no-any-return]


def _statement(
    database: Database,
    redis_url: str,
    world: World,
    ledger_id: UUID,
    unit: str,
    status: str,
    year: int,
) -> UUID:
    from mhvp.billing.status import StatementStatus
    from mhvp.hoa.models import HoaStatement

    snapshot = {
        "positions": [{"label": "Gartenpflege", "amount": "100.00", "basis": "GO", "split": {}}],
        "total_costs": "100.00",
        "reserve": {"opening": "0.00", "closing": "0.00"},
        "units": [
            {
                "unit_id": unit,
                "unit_number": "01",
                "cost_share": "100.00",
                "advances_resolved": "80.00",
                "advances_paid": "80.00",
                "arrears": "0.00",
                "result": "20.00",
                "reserve_due": "0.00",
                "reserve_paid": "0.00",
            }
        ],
    }

    async def fn(session: Any) -> UUID:
        resolution_id: UUID | None = None
        if status in {"resolved", "issued", "due", "posted", "locked"}:
            # ck_hoa_statement_resolved_needs_resolution (0462, AP05): a resolved statement
            # always references its resolution.
            from mhvp.accounting.models import Ledger
            from mhvp.hoa.models import Resolution

            ledger = await session.get(Ledger, ledger_id)
            res = Resolution(
                tenant_id=world.tenant_a,
                legal_entity_id=ledger.legal_entity_id,
                number=year,
                decided_on=date(year + 1, 6, 1),
                subject="Jahresabrechnung",
                wording="Die Jahresabrechnung wird beschlossen.",
                status="positive",
                subject_type="hoa_statement",
            )
            session.add(res)
            await session.flush()
            resolution_id = res.id
        row = HoaStatement(
            tenant_id=world.tenant_a,
            ledger_id=ledger_id,
            year=year,
            status=StatementStatus(status),
            snapshot=snapshot,
            snapshot_hash="a" * 64,
            resolution_id=resolution_id,
        )
        session.add(row)
        await session.flush()
        return row.id  # type: ignore[no-any-return]

    return _run(database, redis_url, world, fn)  # type: ignore[no-any-return]


def test_owner_statement_pdf_positive_path_and_gate(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, open_ = clients
    h = bearer(login(open_, world, "r05admin"))
    mine = _community(open_, h, "971")
    other = _community(open_, h, "972")
    _ledger_with_invoice(open_, h, mine["hoa"], "971", _doc(open_, h, "r.pdf", b"%PDF-1.4 r05a"))
    _ledger_with_invoice(open_, h, other["hoa"], "972", _doc(open_, h, "s.pdf", b"%PDF-1.4 r05b"))
    owner = _portal_user(open_, h, world, "r05own", _contact_of(open_, h, mine["party"]))
    foreign = _portal_user(open_, h, world, "r05frn", _contact_of(open_, h, other["party"]))

    issued = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, mine["hoa"]),
        mine["unit"], "issued", 2025,
    )  # fmt: skip
    draft = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, mine["hoa"]),
        mine["unit"], "calculated", 2024,
    )  # fmt: skip

    listed = _ok(open_.get(f"{P}/owner/statements", headers=owner))["items"]
    assert [(i["statement_id"], i["year"], i["unit_number"]) for i in listed] == [
        (str(issued), 2025, "01")
    ]
    assert _ok(open_.get(f"{P}/owner/statements", headers=foreign))["items"] == []

    url = f"{P}/owner/statements/{issued}/units/{mine['unit']}/pdf"
    pdf = open_.get(url, headers=owner)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert "Hausgeldabrechnung-2025-01.pdf" in pdf.headers["content-disposition"]

    # Not shown: statement before issue, foreign owner, foreign unit; gate G4 closed: 403.
    assert (
        open_.get(
            f"{P}/owner/statements/{draft}/units/{mine['unit']}/pdf", headers=owner
        ).status_code
        == 404
    )
    assert open_.get(url, headers=foreign).status_code == 404
    assert (
        open_.get(
            f"{P}/owner/statements/{issued}/units/{other['unit']}/pdf", headers=owner
        ).status_code
        == 404
    )
    assert closed.get(url, headers=owner).status_code == 403


def test_position_context_with_order_payment_and_key(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    from mhvp.accounting.models import Invoice
    from mhvp.banking.models import OrderStatus as PayStatus
    from mhvp.banking.models import PaymentOrder
    from mhvp.billing.status import StatementStatus
    from mhvp.core import crypto
    from mhvp.hoa.models import HoaCostItem, HoaStatement
    from mhvp.properties.models import AllocationKey
    from mhvp.tickets.models import OrderStatus, WorkOrder

    _, c = clients
    h = bearer(login(c, world, "r05admin"))
    comm = _community(c, h, "973")
    doc = _doc(c, h, "rechnung-r05.pdf", b"%PDF-1.4 r05c")
    invoice_id, _ = _ledger_with_invoice(c, h, comm["hoa"], "973", doc)
    ledger_id = _ledger_of(database, redis_url, world, comm["hoa"])
    accounts = _accounts(c, h, str(ledger_id))
    credit_account = next(i for n, i in accounts.items() if n != "040300")
    booked = _book(
        c,
        h,
        str(ledger_id),
        _entry(
            "custom",
            "2025-06-01",
            [_line(accounts["040300"], debit="120.00"), _line(credit_account, credit="120.00")],
        ),
    )
    entry_id = UUID(str(booked["id"]))
    bank = _ok(
        c.post(
            f"/api/v1/properties/{comm['property']}/bank-accounts",
            json={
                "legal_entity_id": comm["hoa"],
                "kind": "hoa",
                "iban": "DE89370400440532013000",
                "holder": "GdWE R05",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]

    async def seed(session: Any) -> UUID:
        invoice = await session.get(Invoice, UUID(invoice_id))
        invoice.journal_entry_id = entry_id
        key = AllocationKey(
            tenant_id=world.tenant_a,
            property_id=UUID(comm["property"]),
            code="R05",
            name="Miteigentumsanteile R05",
            unit_of_measure="mea",
            kind="static",
        )
        session.add(key)
        statement = HoaStatement(
            tenant_id=world.tenant_a,
            ledger_id=ledger_id,
            year=2025,
            status=StatementStatus.CALCULATED,
            snapshot={"units": []},
            snapshot_hash="b" * 64,
        )
        session.add(statement)
        await session.flush()
        session.add(
            HoaCostItem(
                tenant_id=world.tenant_a,
                statement_id=statement.id,
                label="Gartenpflege R05",
                amount=Decimal("120.00"),
                allocation_key_id=key.id,
                basis="Gemeinschaftsordnung",
                journal_entry_id=entry_id,
            )
        )
        session.add(
            WorkOrder(
                tenant_id=world.tenant_a,
                property_id=UUID(comm["property"]),
                provider_contact_id=invoice.provider_contact_id,
                description="Gartenpflege R05",
                status=OrderStatus.INVOICED,
                invoice_id=invoice.id,
            )
        )
        iban = "DE89370400440532013000"
        session.add(
            PaymentOrder(
                tenant_id=world.tenant_a,
                ledger_id=ledger_id,
                property_bank_account_id=UUID(bank),
                invoice_id=invoice.id,
                amount=Decimal("120.00"),
                counterpart_name="Gärtner R05",
                counterpart_iban=iban,
                counterpart_iban_fingerprint=crypto.fingerprint(iban),
                purpose="BD-973",
                end_to_end_id=uuid.uuid4().hex[:35],
                execution_date=date(2025, 6, 15),
                status=PayStatus.EXECUTED,
                executed_amount=Decimal("120.00"),
            )
        )
        await session.flush()
        return statement.id  # type: ignore[no-any-return]

    statement_id = _run(database, redis_url, world, seed)
    # Statement hash must exist for the engagement; link it by the API.
    engagement = str(
        _ok(
            c.post(
                f"{H}/audits",
                json={
                    "legal_entity_id": comm["hoa"],
                    "period_from": "2025-01-01",
                    "period_to": "2025-12-31",
                    "purpose": "R05 Positivpfad Kontext",
                    "auditor_contact_ids": [comm["board"]["id"]],
                    "statement_id": str(statement_id),
                },
                headers=h,
            ),
            201,
        )["id"]
    )
    item = _ok(
        c.post(
            f"{H}/audits/{engagement}/items",
            json={"journal_entry_id": str(entry_id), "document_id": doc, "amount": "120.00"},
            headers=h,
        ),
        201,
    )
    bh = _board_login(c, h, world, "r05board", engagement, comm["board"]["id"])
    ctx = _ok(c.get(f"{B}/engagements/{engagement}/positions/{item['id']}/context", headers=bh))
    assert ctx["invoice"]["number"] == "BD-973"
    assert Decimal(str(ctx["invoice"]["gross"])) == Decimal("120.00")
    assert ctx["order"]["status"] == "invoiced"
    assert ctx["order"]["description"] == "Gartenpflege R05"
    assert ctx["payment"]["status"] == "executed"
    assert Decimal(str(ctx["payment"]["amount"])) == Decimal("120.00")
    assert Decimal(str(ctx["payment"]["executed_amount"])) == Decimal("120.00")
    assert "iban" not in str(ctx).lower()
    assert ctx["allocation"]["key_code"] == "R05"
    assert ctx["allocation"]["key_name"] == "Miteigentumsanteile R05"
    assert Decimal(str(ctx["allocation"]["amount"])) == Decimal("120.00")
    assert ctx["booking"]["lines"]
    assert ctx["previous_year"] is not None
    assert not any("Zahlungsauftrag" in m or "Rechnung" in m for m in ctx["missing"])
    assert "Kein Beleg" not in " ".join(ctx["missing"])


def _owner_doc(c: TestClient, h: dict[str, str], entity: str, title: str, name: str) -> str:
    import json

    links = json.dumps([{"entity_type": "legal_entity", "entity_id": entity, "role": "attachment"}])
    doc = _ok(
        c.post(
            "/api/v1/documents",
            files={"file": (name, b"%PDF-1.4 " + name.encode(), "application/pdf")},
            data={"links": links, "title": title},
            headers=h,
        ),
        201,
    )
    _ok(c.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": ["owner"]}, headers=h))
    return str(doc["id"])


def test_portal_document_search_in_database(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    _, c = clients
    h = bearer(login(c, world, "r05admin"))
    comm = _community(c, h, "974")
    a = _owner_doc(c, h, comm["hoa"], "Rabatt 100% Gartenbau", "zz-garten.pdf")
    b = _owner_doc(c, h, comm["hoa"], "Rechnung Dach", "aa-dach.pdf")
    owner = _portal_user(c, h, world, "r05own2", _contact_of(c, h, comm["party"]))

    def ids(query: str) -> list[str]:
        return [d["id"] for d in _ok(c.get(f"{P}/documents{query}", headers=owner))]

    assert set(ids("")) >= {a, b}
    assert ids("?q=100%25") == [a]  # literal percent sign, no wildcard
    assert ids("?q=_") == []  # underscore is no wildcard
    assert ids("?q=DACH") == [b]
    assert ids("?q=aa-dach") == [b]
    ordered = ids("?sort=filename_asc")
    assert ordered.index(b) < ordered.index(a)
    ordered = ids("?sort=title_desc")
    assert ordered.index(b) < ordered.index(a)  # "Rechnung" after "Rabatt"
    assert c.get(f"{P}/documents?sort=bogus", headers=owner).status_code == 422


def test_inspection_package_tenant_default_days(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    from tests.integration.test_p08_hoa_audit_inspection import _owner_request

    _, c = clients
    h = bearer(login(c, world, "r05admin"))
    hr = bearer(login(c, world, "r05reader"))
    current = _ok(c.get(TS, headers=h))
    assert current["inspection_package_default_days"] is None

    # Validation and authorization.
    for bad in (0, 366):
        assert (
            c.patch(
                TS,
                json={"inspection_package_default_days": bad},
                headers=h,
            ).status_code
            == 422
        )
    assert c.patch(TS, json={"inspection_package_default_days": 14}, headers=hr).status_code == 403

    def expiry(number: str, **body: Any) -> str | None:
        rid, doc, _ = _owner_request(c, h, number, "2019-06-01")
        _ok(
            c.post(
                f"/api/v1/hoa/inspection-requests/{rid}/package",
                json={"document_ids": [doc], **body},
                headers=h,
            )
        )
        return _ok(c.get(f"/api/v1/hoa/inspection-requests/{rid}", headers=h)).get(
            "package_expires_at"
        )

    assert expiry("975") is None  # empty default: no expiry
    _ok(c.patch(TS, json={"inspection_package_default_days": 14}, headers=h))
    assert _ok(c.get(TS, headers=h))["inspection_package_default_days"] == 14
    assert expiry("976") is not None  # default applies
    assert expiry("977", valid_days=30) is not None
    assert expiry("978", no_expiry=True) is None  # own override
    _ok(
        c.patch(
            TS,
            json={"clear_inspection_package_default_days": True},
            headers=h,
        )
    )
    assert _ok(c.get(TS, headers=h))["inspection_package_default_days"] is None
