"""Q06 (30.09.2026): chat actions property, document filing, portal invitation and letter
(M7-03) with follow up steps (M7-04), cascade small to large with cost per stage (M7-08),
budget stop notification (M7-09), rent increase AI check (M26-01). Fake provider, no network.

Expected cascade cost by hand (PROVIDER prices, 1.000 tokens in and 500 out per fake call):
small tier two calls (schema error, one retry) = (2.000 x 1 + 1.000 x 5) / 1.000.000 = 0,007;
large tier one call = (1.000 x 5 + 500 x 25) / 1.000.000 = 0,0175; total 0,0245 EUR.
Budget stop: one small answer = (1.000 x 1 + 500 x 5) / 1.000.000 = 0,0035 EUR; at the latest
the fourth run after three answers (0,0105 EUR) is blocked by the budget of 0,01 EUR."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake

pytestmark = pytest.mark.integration
__all__ = ["fake"]
L = "/api/v1/letting"
SURNAME = f"Test{RUN}"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q6a-{RUN}", name=f"Q06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q6b-{RUN}", name=f"Q06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("q6admin", a, "tenant_admin"),
            ("q6second", a, "tenant_admin"),
            ("q6reader", a, "read_only"),
            ("q6other", b, "tenant_admin"),
        ):
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


def _release(c: TestClient, world: World, **overrides: Any) -> dict[str, str]:
    admin = bearer(login(c, world, "q6admin"))
    second = bearer(login(c, world, "q6second"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa, **overrides},
            headers=admin,
        )
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second))
    return admin


def _answer(text: str, action: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"answer": text, "sources": [], "answerable": True, "action": action}


def _ask(
    c: TestClient, h: dict[str, str], question: str, **extra: Any
) -> tuple[dict[str, Any], dict[str, Any], str]:
    conversation = _ok(c.post("/api/v1/ai/conversations", json={}, headers=h), 201)["id"]
    body = {"content": question, "task": "answer_question", "document_ids": [], **extra}
    run = _ok(
        c.post(f"/api/v1/ai/conversations/{conversation}/messages", json=body, headers=h), 202
    )
    detail = _ok(c.get(f"/api/v1/ai/conversations/{conversation}", headers=h))
    answer = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    return run, answer, conversation


def _messages(c: TestClient, h: dict[str, str], conversation: str) -> list[str]:
    detail = _ok(c.get(f"/api/v1/ai/conversations/{conversation}", headers=h))
    return [m["content"] for m in detail["messages"] if m["role"] == "assistant"]


def _rent_case(c: TestClient, h: dict[str, str]) -> str:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "961", "name": f"Mieterhöhung {RUN}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "60",
            },
            headers=h,
        ),
        201,
    )["id"]
    owner, _ = _party(c, h, "VermieterQ06", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(c, h, "MieterQ06")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        c.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "gross": "600.00",
                "valid_from": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )
    case = _ok(
        c.post(
            f"{L}/rent-increases",
            json={
                "contract_id": contract,
                "basis": "index",
                "effective_date": "2026-12-01",
                "target_rent": "630.00",
                "source_note": "Testwerte, keine Rechtsquelle",
                "basis_data": {"index_base": "100", "index_current": "105"},
            },
            headers=h,
        ),
        201,
    )
    return str(case["id"])


def test_rent_increase_ai_check_is_a_hint_linked_to_the_case(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "q6admin"))
    reader = bearer(login(client, world, "q6reader"))
    other = bearer(login(client, world, "q6other"))
    case_id = _rent_case(client, admin)
    before = _ok(client.get(f"{L}/rent-increases/{case_id}", headers=admin))
    # Not released yet: the run is blocked, no proposal, the case stays as it is.
    blocked = _ok(client.post(f"{L}/rent-increases/{case_id}/ai-check", headers=admin), 202)
    assert blocked["latest_run"]["status"] == "blocked"
    assert blocked["ai_check_id"] is None
    _release(client, world)
    fake.queue.append(
        {
            "findings": [
                {
                    "field": "source_missing",
                    "description": "Quelldokument fehlt.",
                    "severity": "medium",
                },
                {
                    "field": "source_missing",
                    "description": "Quelldokument fehlt.",
                    "severity": "medium",
                },
            ],
            "overall": "unauffaellig",
            "summary": "Eine fehlende Quelle.",
        }
    )
    state = _ok(client.post(f"{L}/rent-increases/{case_id}/ai-check", headers=admin), 202)
    assert state["latest_run"]["status"] == "succeeded"
    latest = state["latest"]
    assert latest["entity_type"] == "rent_increase_check"
    assert state["ai_check_id"] == latest["id"]
    assert len(latest["proposed"]["findings"]) == 1  # deduplicated
    assert latest["proposed"]["overall"] == "pruefen"  # derived, not the model's word
    sent = fake.calls[-1]["messages"][-1]["content"]
    assert "MieterQ06" not in sent  # no names; the case id is the gateway context only
    after = _ok(client.get(f"{L}/rent-increases/{case_id}", headers=admin))
    assert after["check"] == before["check"]
    assert after["status"] == before["status"]
    assert after["ai_check_id"] == latest["id"]
    refused = client.post(f"/api/v1/ai/proposals/{latest['id']}/apply", json={}, headers=admin)
    assert refused.status_code == 409  # hints are never applied
    assert client.post(f"{L}/rent-increases/{case_id}/ai-check", headers=reader).status_code == 403
    assert client.get(f"{L}/rent-increases/{case_id}/ai-check", headers=other).status_code == 404
    assert client.post(f"{L}/rent-increases/{case_id}/ai-check", headers=other).status_code == 404


def test_chat_property_proposal_written_after_confirmation_with_next_steps(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "q6admin"))
    reader = bearer(login(client, world, "q6reader"))
    number = "962"
    name = f"Lindenhof {RUN}"
    action = {
        "kind": "property_create",
        "refs": [],
        "property": {
            "number": number,
            "name": name,
            "management_type": "hoa",
            "street": "Lindenweg",
            "house_number": "4",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        },
        "reason": "Nutzer möchte das Objekt anlegen",
    }
    # A value the user did not state is refused (never a value of the model).
    fake.queue.append(
        _answer("Vorschlag.", {**action, "property": {**action["property"], "city": "Berlin"}})
    )
    _, answer, _ = _ask(
        client, admin, f"Lege das Objekt {number} {name}, Lindenweg 4, 40789 Monheim am Rhein an"
    )
    assert answer["proposal_id"] is None
    assert "den Ort wörtlich" in answer["content"]
    fake.queue.append(_answer("Vorschlag zur Bestätigung bereit.", action))
    _, answer, conversation = _ask(
        client,
        admin,
        f"Lege das Objekt {number} {name} als WEG, Lindenweg 4, 40789 Monheim am Rhein an",
    )
    proposal_id = answer["proposal_id"]
    assert proposal_id is not None
    listed = _ok(client.get("/api/v1/properties", params={"q": name}, headers=admin))
    items = listed["items"] if isinstance(listed, dict) else listed
    assert all(p["number"] != number for p in items)  # nothing written before confirmation
    denied = client.post(
        f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=reader
    )
    assert denied.status_code == 403
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        ),
        201,
    )
    summary = applied["summary"]
    assert summary["kind"] == "property_create"
    assert summary["status"] == "onboarding"
    assert [s["code"] for s in summary["next_steps"]] == ["units", "documents", "contracts"]
    prop = _ok(client.get(f"/api/v1/properties/{summary['property_id']}", headers=admin))
    assert prop["number"] == number
    assert prop["name"] == name
    assert "Mögliche nächste Schritte" in _messages(client, admin, conversation)[-1]


def test_chat_letter_portal_invite_and_document_filing(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _release(client, world)
    created = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Hanna",
                "last_name": SURNAME,
                "emails": [{"email": f"hanna.q6.{RUN}@example.org"}],
                "addresses": [
                    {
                        "street": "Rheinpromenade",
                        "house_number": "13",
                        "postal_code": "40789",
                        "city": "Monheim am Rhein",
                    }
                ],
            },
            headers=admin,
        ),
        201,
    )
    contact_id = created["id"]
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=admin))
    _ok(
        client.post(
            "/api/v1/document-templates",
            json={
                "code": f"q6brief{RUN}".lower()[:60],
                "name": f"Begrüßung {RUN}",
                "subject": "Willkommen",
                "body": "Sehr geehrte Damen und Herren, willkommen.",
            },
            headers=admin,
        ),
        201,
    )
    # Letter from a template: draft filed, never sent.
    fake.queue.append(
        _answer(
            "Briefentwurf vorbereitet.",
            {"kind": "letter_create", "refs": [contact_id], "template": f"Begrüßung {RUN}"},
        )
    )
    _, answer, _ = _ask(
        client, admin, f"Erstelle einen Brief aus der Vorlage Begrüßung {RUN} für Hanna {SURNAME}"
    )
    proposal_id = answer["proposal_id"]
    assert proposal_id is not None, answer["content"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin))
    assert proposal["proposed"]["template_label"] == f"Begrüßung {RUN}"
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        ),
        201,
    )
    document_id = applied["summary"]["document_id"]
    assert _ok(client.get(f"/api/v1/documents/{document_id}", headers=admin))["id"] == document_id
    # Portal invitation prepared: account created from the contact file, nothing sent.
    fake.queue.append(
        _answer("Einladung vorbereitet.", {"kind": "portal_invite_prepare", "refs": [contact_id]})
    )
    _, answer, _ = _ask(client, admin, f"Bereite eine Portaleinladung für Hanna {SURNAME} vor")
    proposal_id = answer["proposal_id"]
    assert proposal_id is not None, answer["content"]
    proposed = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin))["proposed"]
    assert proposed["email_masked"].startswith("h***@")
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        ),
        201,
    )
    assert applied["summary"]["portal_account_id"]
    assert "invitation_token" not in str(applied["summary"])
    fake.queue.append(
        _answer("Einladung vorbereitet.", {"kind": "portal_invite_prepare", "refs": [contact_id]})
    )
    _, answer, _ = _ask(
        client, admin, f"Bereite nochmal eine Portaleinladung für Hanna {SURNAME} vor"
    )
    assert answer["proposal_id"] is None
    assert "bereits ein Portalzugang" in answer["content"]
    # Document filing: the attached document is linked to the contact hit.
    doc = _upload(client, admin, "vollmacht.txt", b"Vollmacht Muster", "text/plain")
    fake.queue.append(
        _answer("Ablage vorbereitet.", {"kind": "document_file", "refs": [contact_id]})
    )
    _, answer, _ = _ask(
        client,
        admin,
        f"Lege das angehängte Dokument bei Hanna {SURNAME} ab",
        document_ids=[doc],
    )
    proposal_id = answer["proposal_id"]
    assert proposal_id is not None, answer["content"]
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        ),
        201,
    )
    assert applied["summary"]["linked"] == [doc]
    links = _ok(client.get(f"/api/v1/documents/{doc}", headers=admin))["links"]
    assert any(x["entity_id"] == contact_id for x in links)


def test_cascade_small_to_large_on_schema_error_with_cost_per_stage(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _release(client, world)
    bad = {"answer": 1}
    fake.queue.extend([bad, bad, _answer("Antwort des großen Modells.")])
    run, answer, _ = _ask(client, admin, f"Wie funktioniert die Kaskade {RUN}?")
    detail = _ok(client.get(f"/api/v1/ai/runs/{run['id']}", headers=admin))
    assert detail["status"] == "succeeded", detail
    assert detail["model"] == "claude-opus-5"
    stages = detail["cascade"]
    assert [s["tier"] for s in stages] == ["small", "large"]
    assert Decimal(stages[0]["cost_eur"]) == Decimal("0.007")
    assert Decimal(stages[1]["cost_eur"]) == Decimal("0.0175")
    assert Decimal(detail["cost_eur"]) == Decimal("0.0245")
    assert stages[1]["reason"] == "Schemafehler im kleinen Modell"
    assert "großen Modells" in answer["content"]


def test_budget_stop_notifies_the_settings_admins(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = _release(client, world, monthly_budget_eur="0.01")
    status = None
    for n in range(5):  # earlier runs of this tenant may already have used the budget
        fake.queue.append(_answer(f"Antwort {n}."))
        run, _, _ = _ask(client, admin, f"Frage {n} zum Budget {RUN}")
        status = run["status"]
        if status == "blocked":
            break
    fake.queue.clear()
    assert status == "blocked"
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    assert any(n["kind"] == "ai.budget_blocked" for n in notes)
    _ask(client, admin, f"Dritte Frage zum Budget {RUN}")
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=admin))
    assert sum(1 for n in notes if n["kind"] == "ai.budget_blocked") == 1  # one unread per user
    _release(client, world)  # restore the budget for later tests


def test_portal_prequalification_runs_masked_through_the_gateway(
    client: TestClient, world: World, fake: FakeProvider, database: Database, redis_url: str
) -> None:
    import uuid

    from mhvp.ai import portal_prequalify
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.documents.blobs import BlobStore

    _release(client, world)
    fake.queue.append(
        {
            "category": "Reparaturanfrage",
            "urgency": "high",
            "summary": "Heizung ausgefallen.",
            "property_number": None,
            "contact_name": None,
            "reply_draft": None,
        }
    )

    async def _run() -> dict[str, Any]:
        settings = _settings(database, redis_url)
        engine = create_app_engine(settings)
        try:
            return await portal_prequalify.prequalify(
                create_session_factory(engine),
                world.tenant_a,
                uuid.uuid4(),
                f"Heizung aus {RUN}, bitte Rückruf unter 0211 5551234",
                BlobStore(settings),
            )
        finally:
            await engine.dispose()

    out = asyncio.run(_run())
    sent = str(fake.calls[-1]["messages"])
    assert "5551234" not in sent.replace(" ", "")  # masked before the provider (0.1.13)
    assert out["status"] == "succeeded", out
    assert out["urgency"] == "high"
    assert out["summary"] == "Heizung ausgefallen."
