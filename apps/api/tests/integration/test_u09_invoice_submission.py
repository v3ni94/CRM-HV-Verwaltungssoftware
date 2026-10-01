"""U09 (M22-02 remainder): net, VAT rate and IBAN of a portal invoice submission reach the receipt
draft, the IBAN is compared with the creditor master data and the Rechnungsbuch is checked for
duplicates. Findings only mark, nothing is blocked or posted."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.problems import ProblemError
from mhvp.main import create_app
from mhvp.portal.routers import PortalInvoiceSubmitIn, _invoice_breakdown
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_q11_workspace_w3 import _contact, _ok, _with_session

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u09a-{RUN}", name=f"U09 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u09b-{RUN}", name=f"U09 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("u09admin"), display_name="u09admin", password=PASSWORD
        )
        world.users["u09admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


GOOD_IBAN = "DE89370400440532013000"
OTHER_IBAN = "DE02120300000000202051"


def _body(**kw: Any) -> PortalInvoiceSubmitIn:
    base: dict[str, Any] = {
        "number": "R-1",
        "invoice_date": date(2026, 9, 29),
        "gross": Decimal("119.00"),
        "document_id": uuid.uuid4(),
    }
    return PortalInvoiceSubmitIn(**{**base, **kw})


def test_breakdown_derives_and_validates() -> None:
    assert _invoice_breakdown(_body()) == {}
    out = _invoice_breakdown(_body(net=Decimal("100.00"), vat_rate=Decimal("19")))
    assert (out["net"], out["vat"], out["vat_rate"]) == ("100.00", "19.00", "19")
    # Rate alone: net derived from gross, VAT is the difference.
    out = _invoice_breakdown(_body(vat_rate=Decimal("19")))
    assert (out["net"], out["vat"]) == ("100.00", "19.00")
    out = _invoice_breakdown(_body(iban="de89 3704 0044 0532 0130 00"))
    assert out["iban"] == GOOD_IBAN


@pytest.mark.parametrize(
    "kw",
    [
        {"net": Decimal("100.00"), "vat_rate": Decimal("7")},  # does not add up
        {"net": Decimal("120.00")},  # net above gross
        {"iban": "DE00 1234"},  # invalid IBAN
    ],
)
def test_breakdown_rejects_inconsistent_values(kw: dict[str, Any]) -> None:
    with pytest.raises(ProblemError) as exc:
        _invoice_breakdown(_body(**kw))
    assert exc.value.status == 422


def test_receipt_draft_carries_breakdown_and_findings(
    client: TestClient,
    world: Any,
    database: Any,
    redis_url: str,
) -> None:
    from mhvp.accounting.models import Invoice, InvoiceKind
    from mhvp.contacts.models import ContactBankAccount
    from mhvp.core import crypto
    from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
    from mhvp.portal.models import ChangeRequest
    from mhvp.portal.routers import _apply_invoice_submission
    from mhvp.receipts.models import ReceiptDraft
    from mhvp.tickets.models import OrderStatus, WorkOrder

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "u09admin"))
    acc = "/api/v1/accounting"
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "965", "name": f"U09 Haus {RUN}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{acc}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{acc}/ledgers",
            json={"legal_entity_id": hoa["id"], "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    provider = _contact(client, h, "Elektriker")
    no_master = _contact(client, h, "Maler")

    class _Principal:
        user_id = world.users["u09admin"]
        tenant_id = world.tenant_a

        def has(self, permission: str) -> bool:
            return True

    async def run(session: Any) -> dict[str, Any]:
        def doc(tag: str) -> Document:
            return Document(
                tenant_id=world.tenant_a,
                title="Rechnung",
                filename="r.pdf",
                mime_type="application/pdf",
                size=1,
                sha256="e" * 64,
                storage=StorageKind.MINIO,
                storage_ref=f"u09-{tag}-{RUN}",
                text_status=TextStatus.NONE,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )

        session.add(
            ContactBankAccount(
                tenant_id=world.tenant_a,
                contact_id=uuid.UUID(provider["id"]),
                iban=GOOD_IBAN,
                iban_suffix=GOOD_IBAN[-4:],
                iban_fingerprint=crypto.fingerprint(GOOD_IBAN),
                valid_from=date(2026, 1, 1),
            )
        )
        session.add(
            Invoice(
                tenant_id=world.tenant_a,
                ledger_id=uuid.UUID(ledger),
                provider_contact_id=uuid.UUID(provider["id"]),
                kind=InvoiceKind.INVOICE,
                number="E-100",
                invoice_date=date(2026, 8, 1),
                net=Decimal("200.00"),
                vat=Decimal("38.00"),
                gross=Decimal("238.00"),
            )
        )

        async def apply(contact: dict[str, Any], tag: str, **extra: Any) -> ReceiptDraft:
            d = doc(tag)
            order = WorkOrder(
                tenant_id=world.tenant_a,
                property_id=uuid.UUID(prop["id"]),
                provider_contact_id=uuid.UUID(contact["id"]),
                description="Arbeit",
                status=OrderStatus.DONE,
            )
            session.add_all([d, order])
            await session.flush()
            payload = {
                "number": "E-100",
                "invoice_date": "2026-09-29",
                "gross": "238.00",
                "document_id": str(d.id),
                "work_order_id": str(order.id),
                **extra,
            }
            row = ChangeRequest(
                tenant_id=world.tenant_a,
                account_id=uuid.uuid4(),
                kind="invoice_submission",
                payload=json.dumps(payload),
            )
            draft_id = await _apply_invoice_submission(session, _Principal(), row, payload)  # type: ignore[arg-type]
            return await session.get(ReceiptDraft, draft_id)

        breakdown = {"net": "200.00", "vat": "38.00", "vat_rate": "19"}
        same = await apply(provider, "a", iban=GOOD_IBAN, **breakdown)
        differs = await apply(provider, "b", iban=OTHER_IBAN, number="E-200", **breakdown)
        nomaster = await apply(no_master, "c", iban=GOOD_IBAN, number="E-300")
        plain = await apply(no_master, "d", number="E-400")
        return {
            "fields": {k: v["value"] for k, v in same.fields.items()},
            "vat_note": same.fields["vat"]["note"],
            "same": same.findings,
            "same_iban": json.loads(same.iban_candidates),
            "differs": differs.findings,
            "nomaster": nomaster.findings,
            "plain": (plain.findings, plain.iban_candidates, "net" in plain.fields),
        }

    out = asyncio.run(_with_session(settings, world.tenant_a, run))
    assert (out["fields"]["net"], out["fields"]["vat"]) == ("200.00", "38.00")
    assert "19" in out["vat_note"]
    assert out["same_iban"] == [GOOD_IBAN]
    assert any("stimmt mit dem Kreditorenstamm überein" in f for f in out["same"])
    # Same issuer, same number: possible duplicate (marks only, draft exists).
    assert any("Mögliches Duplikat" in f and "E-100" in f for f in out["same"])
    assert any("IBAN-Abweichung" in f for f in out["differs"])
    # E-200 with the same date as E-100? No (01.08. vs 29.09.), so no duplicate finding here.
    assert not any("Duplikat" in f for f in out["differs"])
    assert any("keine gültige Bankverbindung" in f for f in out["nomaster"])
    # Other issuer: no duplicate although number and amount match.
    assert not any("Duplikat" in f for f in out["nomaster"])
    assert out["plain"] == ([], None, False)
