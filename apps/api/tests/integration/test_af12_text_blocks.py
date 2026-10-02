"""AF12 (GAE-16, GAE-17, GAE-18): tenant switch require_second_person for text blocks,
text block letter_notice in the tenant letter and filing of the info sheet with approved text.

Expected (hand derived):
* Default: switch on, the author cannot approve (403/409), a second person can.
* Switching off needs a reason (422 without), a reader may not write (403), another tenant is
  unaffected (own default on); with the switch off the author may approve and an audit event
  ``text_block.approved_without_second_person`` is written.
* Info sheet filed behind G3: the PDF of the filed document contains the approved paragraph
  and no "Text nicht freigegeben" for the two info sheet codes.
* Tenant letter: placeholder "Text nicht freigegeben" until letter_notice is approved, then the
  approved text appears and the placeholder is gone.
"""

import asyncio
import io
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m17_operating_costs import _rental_world, _tenant_contract
from tests.integration.test_m21_portal_owner import _ok

pytestmark = pytest.mark.integration
B = "/api/v1/document-text-blocks"
S = "/api/v1/statements"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af12a-{RUN}", name=f"AF12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af12b-{RUN}", name=f"AF12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af12first", a, "tenant_admin"),
            ("af12second", a, "tenant_admin"),
            ("af12reader", a, "read_only"),
            ("af12other", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
        ):
            yield closed, open_


def _text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def _approve(
    c: TestClient, author: dict[str, str], approver: dict[str, str], code: str, body: str
) -> None:
    block = _ok(c.post(B, json={"code": code, "title": code, "body": body}, headers=author), 201)
    _ok(c.post(f"{B}/{block['id']}/submit", headers=author))
    _ok(c.post(f"{B}/{block['id']}/approve", headers=approver))


def test_second_person_switch(clients: tuple[TestClient, TestClient], world: World) -> None:
    c, _ = clients
    h1 = bearer(login(c, world, "af12first"))
    hr = bearer(login(c, world, "af12reader"))
    ho = bearer(login(c, world, "af12other"))
    pol = f"{B}/policy"
    assert _ok(c.get(pol, headers=h1))["require_second_person"] is True
    assert c.get(f"{pol}?x=1", headers=h1).status_code == 422
    assert _ok(c.get(pol, headers=hr))["require_second_person"] is True
    assert (
        c.put(
            pol, json={"require_second_person": False, "reason": "x" * 20}, headers=hr
        ).status_code
        == 403
    )
    assert c.put(pol, json={"require_second_person": False}, headers=h1).status_code == 422
    assert (
        c.put(pol, json={"require_second_person": False, "reason": "kurz"}, headers=h1).status_code
        == 422
    )

    code = "owner_s35a_note"
    block = _ok(c.post(B, json={"code": code, "title": "t", "body": "Text eins"}, headers=h1), 201)
    _ok(c.post(f"{B}/{block['id']}/submit", headers=h1))
    assert c.post(f"{B}/{block['id']}/approve", headers=h1).status_code in (403, 409)

    off = _ok(
        c.put(
            pol,
            json={"require_second_person": False, "reason": "Kleiner Betrieb, ein Bearbeiter"},
            headers=h1,
        )
    )
    assert off["require_second_person"] is False
    assert _ok(c.get(pol, headers=ho))["require_second_person"] is True  # other tenant unaffected
    assert _ok(c.post(f"{B}/{block['id']}/approve", headers=h1))["status"] == "approved"
    _ok(c.put(pol, json={"require_second_person": True}, headers=h1))
    again = _ok(c.post(B, json={"code": code, "title": "t", "body": "Text zwei"}, headers=h1), 201)
    _ok(c.post(f"{B}/{again['id']}/submit", headers=h1))
    assert c.post(f"{B}/{again['id']}/approve", headers=h1).status_code in (403, 409)


def test_letter_notice_and_filed_info_sheet(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, gated = clients
    h1 = bearer(login(closed, world, "af12first"))
    h2 = bearer(login(closed, world, "af12second"))
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h1))
    _ok(
        closed.put(
            "/api/v1/billing/allocation-basis-setting", json={"block_output": False}, headers=h1
        )
    )
    w = _rental_world(closed, h1, "912")
    unit = _ok(closed.get(f"/api/v1/units/{w['unit']}", headers=h1))
    unit2 = _ok(
        closed.post(
            f"/api/v1/properties/{w['property']}/units",
            json={"building_id": unit["building_id"], "number": "02", "unit_type": "apartment"},
            headers=h1,
        ),
        201,
    )["id"]
    _ok(
        closed.post(
            f"/api/v1/units/{unit2}/allocation-values",
            json={"allocation_key_id": w["keys"]["WFL"], "value": "40", "valid_from": "2020-01-01"},
            headers=h1,
        ),
        201,
    )
    contract = _tenant_contract(closed, h1, unit2, f"Brief{RUN}", "2024-01-01")
    assert contract["id"]
    sid = _ok(
        closed.post(
            S,
            json={"ledger_id": w["ledger"], "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h1,
        ),
        201,
    )["id"]
    item = {
        "label": "Gartenpflege",
        "amount": "120.00",
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "Mietvertrag",
    }
    _ok(closed.post(f"{S}/{sid}/cost-items", json=item, headers=h1), 201)
    _ok(closed.post(f"{S}/{sid}/calculate", headers=h1))
    assert unit["id"] == w["unit"]

    # letter_notice: placeholder until approved
    body = {"contract_id": contract["id"]}
    before = closed.post(f"{S}/{sid}/letters/preview", json=body, headers=h1)
    assert before.status_code == 200, before.text
    assert "Text nicht freigegeben" in _text(before.content)
    _approve(closed, h1, h2, "letter_notice", "Freigegebener Hinweis AF12 zur Abrechnung")
    after = closed.post(f"{S}/{sid}/letters/preview", json=body, headers=h1)
    assert after.status_code == 200, after.text
    assert "Freigegebener Hinweis AF12 zur Abrechnung" in _text(after.content)
    assert "Text nicht freigegeben" not in _text(after.content)

    # GAE-18: filed info sheet (G3 open) carries the approved text
    _approve(closed, h1, h2, "info_sheet_inspection", "Freigegebener Absatz Belegeinsicht AF12")
    _approve(closed, h1, h2, "info_sheet_objection", "Freigegebener Absatz Einwendungen AF12")
    filed = _ok(gated.post(f"{S}/{sid}/info-sheet", headers=h1), 201)
    assert filed["text_status"] == "freigegeben"
    pdf = gated.get(f"/api/v1/documents/{filed['document_id']}/content", headers=h1)
    assert pdf.status_code == 200
    text = _text(pdf.content)
    assert "Freigegebener Absatz Belegeinsicht AF12" in text
    assert "Freigegebener Absatz Einwendungen AF12" in text
    assert "Text nicht freigegeben" not in text
