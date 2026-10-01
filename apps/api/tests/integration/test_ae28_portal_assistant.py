"""AE28 (M7-06, SA-04): portal assistant with permission filter after access_grant, tenant
switches (chat bot, privacy feature), privacy acknowledgement and question log. Fake provider,
no network.

Hand calculated expectations: owner 1 holds the unit grant for unit 1 and the HOA grant, so the
assistant may read exactly D1 (unit 1, released for owners), DH (HOA, released for owners).
D2 belongs to unit 2 (owner 2), DI is linked to unit 1 but not released (internal)."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake
from tests.integration.test_m21_portal import _contact_of, _ok
from tests.integration.test_m21_portal_owner import _ownership, _portal_user, _weg

pytestmark = pytest.mark.integration
__all__ = ["fake"]
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
A = f"{P}/assistant"
AA = f"{PA}/assistant"
NOTICE_CODE = "portal_chat_privacy_notice"
PHONE = "0211 5551234"
IBAN = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae28a-{RUN}", name=f"AE28 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae28b-{RUN}", name=f"AE28 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = (
            ("ae28admin", a, ["tenant_admin"]),
            ("ae28second", a, ["tenant_admin"]),
            ("ae28reader", a, ["read_only"]),
            ("ae28adminb", b, ["tenant_admin"]),
        )
        for name, tenant, roles in specs:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=roles, actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


@dataclass
class W:
    admin: dict[str, str]
    second: dict[str, str]
    reader: dict[str, str]
    admin_b: dict[str, str]
    owner1: dict[str, str]
    owner2: dict[str, str]
    outsider: dict[str, str]
    outsider_contact: str
    unit1: str
    unit2: str
    d1: str
    d2: str
    dh: str
    di: str


def _doc(
    c: TestClient,
    h: dict[str, str],
    title: str,
    content: str,
    entity: str,
    entity_id: str,
    visibility: list[str],
) -> str:
    links = json.dumps([{"entity_type": entity, "entity_id": entity_id}])
    doc = _ok(
        c.post(
            "/api/v1/documents",
            data={"title": title, "links": links},
            files={"file": (f"{title}.txt", content.encode(), "text/plain")},
            headers=h,
        ),
        201,
    )
    if visibility:  # an unreleased document keeps the default (internal)
        _ok(c.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": visibility}, headers=h))
    return str(doc["id"])


@pytest.fixture(scope="module")
def w(client: TestClient, world: World) -> W:
    c = client
    h = bearer(login(c, world, "ae28admin"))
    weg, hoa = _weg(c, h, "928", "AE28 WEG")
    unit1, unit2 = _unit(c, h, weg["id"], "01"), _unit(c, h, weg["id"], "02")
    p1, _ = _party(c, h, "AE28Eig1")
    p2, _ = _party(c, h, "AE28Eig2")
    px, _ = _party(c, h, "AE28Fremd")
    _ownership(c, h, unit1, p1)
    _ownership(c, h, unit2, p2)
    owner1 = _portal_user(c, h, world, "ae28owner1", _contact_of(c, h, p1))
    owner2 = _portal_user(c, h, world, "ae28owner2", _contact_of(c, h, p2))
    outsider_contact = _contact_of(c, h, px)
    outsider = _portal_user(c, h, world, "ae28out", outsider_contact)
    d1 = _doc(
        c,
        h,
        "Wirtschaftsplan Einheit Eins",
        f"Das Hausgeld der Einheit Eins beträgt 250 EUR im Monat. Rückfragen an "
        f"eigentuemer1@example.org oder {IBAN}.",
        "unit",
        unit1,
        ["owner"],
    )
    d2 = _doc(
        c,
        h,
        "Wirtschaftsplan Einheit Zwei",
        "Das Hausgeld der Einheit Zwei beträgt 400 EUR im Monat. Geheimzwei.",
        "unit",
        unit2,
        ["owner"],
    )
    dh = _doc(
        c,
        h,
        "Protokoll Eigentümerversammlung",
        "Beschluss zur Dachsanierung wurde gefasst. Das Hausgeld Rücklage wird erhöht.",
        "legal_entity",
        hoa,
        ["owner"],
    )
    di = _doc(
        c,
        h,
        "Interne Notiz Einheit Eins",
        "Interne Kalkulation Hausgeld Nachzahlung geheiminternx.",
        "unit",
        unit1,
        [],
    )
    return W(
        admin=h,
        second=bearer(login(c, world, "ae28second")),
        reader=bearer(login(c, world, "ae28reader")),
        admin_b=bearer(login(c, world, "ae28adminb")),
        owner1=owner1,
        owner2=owner2,
        outsider=outsider,
        outsider_contact=outsider_contact,
        unit1=unit1,
        unit2=unit2,
        d1=d1,
        d2=d2,
        dh=dh,
        di=di,
    )


def _switch(c: TestClient, w: W, **flags: bool) -> None:
    _ok(c.patch(f"{PA}/features", json=flags, headers=w.admin))


def _ask(
    c: TestClient, h: dict[str, str], question: str, status: int = 201, **extra: Any
) -> dict[str, Any]:
    out = c.post(f"{A}/questions", json={"question": question, **extra}, headers=h)
    assert out.status_code == status, out.text
    return out.json()  # type: ignore[no-any-return]


def _answer(
    text: str, sources: list[dict[str, str]], answerable: bool = True, action: Any = None
) -> dict[str, Any]:
    return {"answer": text, "sources": sources, "answerable": answerable, "action": action}


def _titles(rows: list[dict[str, Any]]) -> set[str]:
    return {r["title"] for r in rows}


def _release_notice(c: TestClient, w: W, body: str = "Testtext, kein geprüfter Rechtstext.") -> int:
    block = _ok(
        c.post(
            "/api/v1/document-text-blocks",
            json={
                "code": NOTICE_CODE,
                "title": "Datenschutzhinweis zur KI-Antwort",
                "body": body,
                "source_note": "Testplatzhalter",
            },
            headers=w.admin,
        ),
        201,
    )
    _ok(c.post(f"/api/v1/document-text-blocks/{block['id']}/submit", headers=w.admin))
    approved = _ok(c.post(f"/api/v1/document-text-blocks/{block['id']}/approve", headers=w.second))
    return int(approved["version"])


def _release_provider(c: TestClient, w: W) -> None:
    dpa = _upload(c, w.admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        c.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=w.admin,
        )
    )
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=w.second))


# Switches and lock ------------------------------------------------------------------------


def test_switches_default_off_and_assistant_is_locked(client: TestClient, w: W) -> None:
    c = client
    features = _ok(c.get(f"{PA}/features", headers=w.admin))
    assert features["chat_bot_enabled"] is False
    assert features["privacy_feature_enabled"] is False
    me = _ok(c.get(f"{P}/me", headers=w.owner1))
    assert me["features"]["chat_bot_enabled"] is False
    assert (
        c.patch(f"{PA}/features", json={"chat_bot_enabled": True}, headers=w.reader).status_code
        == 403
    )
    # Tenant B keeps its own switches.
    assert _ok(c.get(f"{PA}/features", headers=w.admin_b))["chat_bot_enabled"] is False
    for method, path, body in (
        ("get", f"{A}/status", None),
        ("get", f"{A}/scope", None),
        ("get", f"{A}/questions", None),
        ("post", f"{A}/questions", {"question": "Wie hoch ist das Hausgeld?"}),
        ("post", f"{A}/privacy-ack", {"text_version": 1}),
    ):
        res = getattr(c, method)(path, headers=w.owner1, **({"json": body} if body else {}))
        assert res.status_code == 403, (path, res.text)
        assert res.json()["code"] == "MHVP-PORTAL-0001"


# Permission filter after access_grant -----------------------------------------------------


def test_scope_lists_only_documents_of_the_grants(client: TestClient, w: W) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True)
    one = _ok(c.get(f"{A}/scope", headers=w.owner1))
    assert one["total_documents"] == 2
    assert _titles(one["documents"]) == {
        "Wirtschaftsplan Einheit Eins",
        "Protokoll Eigentümerversammlung",
    }
    assert [u["id"] for u in one["units"]] == [w.unit1]
    two = _ok(c.get(f"{A}/scope", headers=w.owner2))
    assert _titles(two["documents"]) == {
        "Wirtschaftsplan Einheit Zwei",
        "Protokoll Eigentümerversammlung",
    }
    # Narrowed to the own unit: the HOA document is no unit document.
    narrowed = _ok(c.get(f"{A}/scope", params={"unit_id": w.unit1}, headers=w.owner1))
    assert _titles(narrowed["documents"]) >= {"Wirtschaftsplan Einheit Eins"}
    assert "Wirtschaftsplan Einheit Zwei" not in _titles(narrowed["documents"])
    assert narrowed["focus_unit_id"] == w.unit1


def test_foreign_unit_and_foreign_document_answer_404(client: TestClient, w: W) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True)
    assert c.get(f"{A}/scope", params={"unit_id": w.unit2}, headers=w.owner1).status_code == 404
    assert c.get(f"{A}/scope", params={"unit_id": w.unit1}, headers=w.owner2).status_code == 404
    assert (
        c.get(f"{A}/scope", params={"unit_id": str(uuid.uuid4())}, headers=w.owner1).status_code
        == 404
    )
    _ask(c, w.owner1, "Wie hoch ist das Hausgeld?", 404, unit_id=w.unit2)
    _ask(c, w.owner1, "Wie hoch ist das Hausgeld?", 404, document_id=w.d2)
    _ask(c, w.owner1, "Wie hoch ist das Hausgeld?", 404, document_id=w.di)  # internal note
    _ask(c, w.owner1, "Wie hoch ist das Hausgeld?", 404, document_id=str(uuid.uuid4()))
    _ask(c, w.outsider, "Wie hoch ist das Hausgeld?", 404, unit_id=w.unit1)


def test_account_without_grant_has_an_empty_scope_and_no_provider_call(
    client: TestClient, w: W, fake: FakeProvider
) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True)
    scope = _ok(c.get(f"{A}/scope", headers=w.outsider))
    assert scope == {"focus_unit_id": None, "units": [], "documents": [], "total_documents": 0}
    before = len(fake.calls)
    out = _ask(c, w.outsider, "Wie hoch ist das Hausgeld der Einheit Eins?")
    assert out["status"] == "no_sources"
    assert out["mode"] == "search"
    assert out["hits"] == []
    assert out["sources"] == []
    assert "keine Unterlagen freigegeben" in out["answer"]
    assert len(fake.calls) == before  # nothing was read, no provider was called


def test_search_hits_stay_inside_the_scope(client: TestClient, w: W, fake: FakeProvider) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=False)
    out = _ask(c, w.owner1, "Hausgeld Einheit Nachzahlung Kalkulation")
    assert out["mode"] == "search"
    assert out["status"] == "search_hits"
    assert out["ai_available"] is False
    assert out["ai_blocked_code"] == "privacy_feature_off"
    assert _titles(out["hits"]) <= {
        "Wirtschaftsplan Einheit Eins",
        "Protokoll Eigentümerversammlung",
    }
    assert "Wirtschaftsplan Einheit Eins" in _titles(out["hits"])
    other = _ask(c, w.owner2, "Hausgeld Einheit Nachzahlung Kalkulation")
    assert "Wirtschaftsplan Einheit Zwei" in _titles(other["hits"])
    assert "Wirtschaftsplan Einheit Eins" not in _titles(other["hits"])
    assert "Interne Notiz Einheit Eins" not in _titles(out["hits"] + other["hits"])
    assert fake.calls == []


# Privacy feature, acknowledgement and gateway gate ----------------------------------------


def test_ai_gate_chain_privacy_notice_ack_and_provider(
    client: TestClient, w: W, fake: FakeProvider
) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=True)
    status = _ok(c.get(f"{A}/status", headers=w.owner1))
    assert status["privacy"]["notice_status"] == "not_released"
    assert status["privacy"]["body"] is None
    assert status["ai"] == {
        "available": False,
        "blocked_code": "privacy_notice_not_released",
        "blocked_message": status["ai"]["blocked_message"],
    }
    # Nothing to acknowledge without a released text.
    refused = c.post(f"{A}/privacy-ack", json={"text_version": 1}, headers=w.owner1)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-PORTAL-0002"
    # Drafts are not shown, only the approved version (four eyes, AE16).
    draft = _ok(
        c.post(
            "/api/v1/document-text-blocks",
            json={"code": NOTICE_CODE, "title": "Entwurf", "body": "Noch nicht freigegeben."},
            headers=w.admin,
        ),
        201,
    )
    assert _ok(c.get(f"{A}/status", headers=w.owner1))["privacy"]["notice_status"] == "not_released"
    _ok(c.post(f"/api/v1/document-text-blocks/{draft['id']}/submit", headers=w.admin))
    _ok(c.post(f"/api/v1/document-text-blocks/{draft['id']}/approve", headers=w.second))
    version = int(draft["version"])
    status = _ok(c.get(f"{A}/status", headers=w.owner1))
    assert status["privacy"]["notice_status"] == "released"
    assert status["privacy"]["version"] == version
    assert status["privacy"]["acknowledged"] is False
    assert status["ai"]["blocked_code"] == "privacy_ack_missing"
    fallback = _ask(c, w.owner1, "Hausgeld Einheit")
    assert fallback["mode"] == "search"
    assert fallback["ai_blocked_code"] == "privacy_ack_missing"
    # The wrong version is refused, the current one is recorded once.
    wrong = c.post(f"{A}/privacy-ack", json={"text_version": version + 1}, headers=w.owner1)
    assert wrong.status_code == 409
    assert c.post(f"{A}/privacy-ack", json={"text_version": 0}, headers=w.owner1).status_code == 422
    first = _ok(c.post(f"{A}/privacy-ack", json={"text_version": version}, headers=w.owner1))
    again = _ok(c.post(f"{A}/privacy-ack", json={"text_version": version}, headers=w.owner1))
    assert first["acknowledged"] is True
    assert again["acknowledged_at"] == first["acknowledged_at"]
    # The acknowledgement belongs to the account: owner 2 still has to acknowledge.
    assert _ok(c.get(f"{A}/status", headers=w.owner2))["privacy"]["acknowledged"] is False
    status = _ok(c.get(f"{A}/status", headers=w.owner1))
    assert status["privacy"]["acknowledged"] is True
    assert status["ai"]["blocked_code"] == "provider_not_released"
    out = _ask(c, w.owner1, "Wie hoch ist das Hausgeld?")
    assert out["mode"] == "search"
    assert out["ai_blocked_code"] == "provider_not_released"
    assert fake.calls == []  # the gateway gate stayed closed, no provider call
    # A new approved version needs a new acknowledgement.
    new_version = _release_notice(c, w, "Neuer Testtext, kein geprüfter Rechtstext.")
    assert new_version == version + 1
    status = _ok(c.get(f"{A}/status", headers=w.owner1))
    assert status["privacy"]["acknowledged"] is False
    assert status["ai"]["blocked_code"] == "privacy_ack_missing"
    _ok(c.post(f"{A}/privacy-ack", json={"text_version": new_version}, headers=w.owner1))
    _ok(c.post(f"{A}/privacy-ack", json={"text_version": new_version}, headers=w.owner2))


def test_ai_answer_checks_sources_masks_and_isolates_accounts(
    client: TestClient, w: W, fake: FakeProvider
) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=True)
    _release_provider(c, w)
    assert _ok(c.get(f"{A}/status", headers=w.owner1))["ai"]["available"] is True
    excerpt = "Das Hausgeld der Einheit Eins beträgt 250 EUR im Monat."
    fake.queue.append(
        _answer(
            "Das Hausgeld beträgt 250 EUR im Monat.",
            [
                {"document_id": w.d1, "excerpt": excerpt},
                {"document_id": w.d2, "excerpt": "Das Hausgeld der Einheit Zwei beträgt 400 EUR"},
                {"document_id": str(uuid.uuid4()), "excerpt": "erfunden"},
                {"document_id": "keine-uuid", "excerpt": "kaputt"},
            ],
            action={"kind": "ticket_create", "refs": [], "title": "Test", "reason": "x"},
        )
    )
    question = f"Wie hoch ist das Hausgeld? Rückruf unter {PHONE}, Konto {IBAN}"
    out = _ask(c, w.owner1, question)
    assert out["mode"] == "ai"
    assert out["status"] == "answered"
    assert out["answer"] == "Das Hausgeld beträgt 250 EUR im Monat."
    # Only the source inside the scope survives; the foreign, invented and malformed ones go.
    assert [s["document_id"] for s in out["sources"]] == [w.d1]
    assert out["sources"][0]["excerpt"] == excerpt
    assert "action" not in out
    sent = str(fake.calls[-1]["messages"])
    assert "250 EUR" in sent  # the own document reached the prompt
    assert "Geheimzwei" not in sent
    assert "400 EUR" not in sent
    assert "geheiminternx" not in sent
    assert "5551234" not in sent.replace(" ", "")
    assert IBAN not in sent
    assert "eigentuemer1@" not in sent
    # The assistant never produces a proposal or a ticket (rule 0.1.6).
    log = _ok(c.get(f"{AA}/log", params={"limit": 1}, headers=w.admin))[0]
    assert log["mode"] == "ai"
    assert log["status"] == "answered"
    run = _ok(c.get(f"/api/v1/ai/runs/{log['run_id']}", headers=w.admin))
    assert run["proposal_id"] is None
    # Owner 2 asks the identical question: no answer is taken over from owner 1 (dedup).
    calls = len(fake.calls)
    fake.queue.append(
        _answer(
            "Das Hausgeld beträgt 400 EUR im Monat.",
            [{"document_id": w.d2, "excerpt": "Das Hausgeld der Einheit Zwei beträgt 400 EUR"}],
        )
    )
    other = _ask(c, w.owner2, question)
    assert len(fake.calls) == calls + 1
    assert other["answer"] == "Das Hausgeld beträgt 400 EUR im Monat."
    sent2 = str(fake.calls[-1]["messages"])
    assert "400 EUR" in sent2
    assert "250 EUR" not in sent2
    assert "geheiminternx" not in sent2
    assert [s["document_id"] for s in other["sources"]] == [w.d2]


def test_ai_without_valid_source_or_answerable_shows_no_answer(
    client: TestClient, w: W, fake: FakeProvider
) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=True)
    fake.queue.append(
        _answer("Eine Antwort ohne Beleg.", [{"document_id": w.d2, "excerpt": "fremd"}])
    )
    no_basis = _ask(c, w.owner1, "Wann ist die Eigentümerversammlung ohne Beleg A?")
    assert no_basis["status"] == "not_answerable"
    assert "keine ausreichende Grundlage" in no_basis["answer"]
    assert no_basis["sources"] == []
    fake.queue.append(_answer("Weiß ich nicht.", [], answerable=False))
    unknown = _ask(c, w.owner1, "Wann ist die Eigentümerversammlung ohne Beleg B?")
    assert unknown["status"] == "not_answerable"
    # Focus on one document: attached, so it is read even without keyword hits.
    fake.queue.append(
        _answer(
            "Beschluss zur Dachsanierung.",
            [{"document_id": w.dh, "excerpt": "Beschluss zur Dachsanierung wurde gefasst."}],
        )
    )
    focused = _ask(c, w.owner1, "Worum geht es hier?", document_id=w.dh)
    assert focused["status"] == "answered"
    assert [s["document_id"] for s in focused["sources"]] == [w.dh]
    assert "Dachsanierung" in str(fake.calls[-1]["messages"])


def test_gateway_rederives_the_scope_even_for_a_forged_caller_scope(
    client: TestClient,
    w: W,
    fake: FakeProvider,
    world: World,
    database: Database,
    redis_url: str,
) -> None:
    """Defence in depth: the gateway takes the readable documents from the account, never from
    the list a caller hands over. An account without grants reads nothing; an attached foreign
    document blocks the run before any provider call."""
    from mhvp.ai import portal_answer
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore
    from mhvp.portal.models import PortalAccount

    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=True)
    accounts = _ok(
        c.get(f"{PA}/accounts", params={"contact_id": w.outsider_contact}, headers=w.admin)
    )
    account_ids = [a["id"] for a in accounts]
    assert len(account_ids) == 1

    async def _run(attach: str | None) -> portal_answer.PortalAnswer:
        settings = _settings(database, redis_url)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                account = await session.get(PortalAccount, uuid.UUID(account_ids[0]))
                assert account is not None
                user_id = account.user_id
            return await portal_answer.answer(
                factory,
                world.tenant_a,
                account_id=uuid.UUID(account_ids[0]),
                user_id=user_id,
                question="Hausgeld Einheit Zwei Betrag",
                scope_ids={uuid.UUID(w.d2), uuid.UUID(w.d1)},  # forged: foreign documents
                focus_ids=None,
                attach_document_id=uuid.UUID(attach) if attach else None,
                blobs=BlobStore(settings),
            )
        finally:
            await engine.dispose()

    fake.queue.append(_answer("Antwort ohne Unterlagen.", [], answerable=False))
    result = asyncio.run(_run(None))
    assert result.status == "not_answerable"
    sent = str(fake.calls[-1]["messages"])
    assert "Geheimzwei" not in sent
    assert "400 EUR" not in sent
    assert "250 EUR" not in sent
    calls = len(fake.calls)
    blocked = asyncio.run(_run(w.d2))
    assert blocked.status == "failed"
    assert "nicht freigegeben" in (blocked.technical_reason or "")
    assert len(fake.calls) == calls
    fake.queue.clear()


def test_provider_error_falls_back_to_hits_and_is_logged(
    client: TestClient, w: W, fake: FakeProvider
) -> None:
    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=True)
    fake.queue.extend([{"unpassend": 1}, {"unpassend": 2}, {"unpassend": 3}, {"unpassend": 4}])
    out = _ask(c, w.owner1, "Hausgeld Einheit Fehlerfall")
    assert out["mode"] == "ai"
    assert out["status"] == "failed"
    assert "derzeit nicht verfügbar" in out["answer"]
    assert out["sources"] == []
    assert "Wirtschaftsplan Einheit Eins" in _titles(out["hits"])
    log = _ok(c.get(f"{AA}/log", params={"status": "failed"}, headers=w.admin))
    assert log
    assert log[0]["reason_code"] == "ai_run_failed"
    fake.queue.clear()


# Log, history, rights, validation, tenants ------------------------------------------------


def test_log_is_masked_filtered_and_tenant_scoped(client: TestClient, w: W) -> None:
    c = client
    rows = _ok(c.get(f"{AA}/log", params={"limit": 200}, headers=w.admin))
    assert rows
    for row in rows:
        assert PHONE.replace(" ", "") not in row["question"].replace(" ", "")
        assert IBAN not in row["question"]
    asked = [r for r in rows if "Rückruf" in r["question"]]
    assert asked
    assert "[TELEFON]" in asked[0]["question"]
    assert "[IBAN]" in asked[0]["question"]
    assert {r["status"] for r in rows} >= {"answered", "no_sources", "search_hits"}
    only = _ok(c.get(f"{AA}/log", params={"status": "no_sources"}, headers=w.admin))
    assert only
    assert all(r["status"] == "no_sources" for r in only)
    # Rights and validation.
    assert c.get(f"{AA}/log", headers=w.reader).status_code == 403
    assert c.get(f"{AA}/log", headers=w.owner1).status_code == 403
    assert c.get(f"{AA}/log", params={"bogus": 1}, headers=w.admin).status_code == 422
    assert c.get(f"{AA}/log", params={"limit": 0}, headers=w.admin).status_code == 422
    assert c.get(f"{AA}/log", params={"status": "x"}, headers=w.admin).status_code == 422
    assert c.get(f"{AA}/log").status_code in (401, 403)
    # Tenant B sees nothing of tenant A.
    assert _ok(c.get(f"{AA}/log", headers=w.admin_b)) == []


def test_history_is_own_only_and_validation(client: TestClient, w: W) -> None:
    c = client
    mine = _ok(c.get(f"{A}/questions", headers=w.owner1))
    theirs = _ok(c.get(f"{A}/questions", headers=w.owner2))
    assert mine
    assert theirs
    assert {r["id"] for r in mine}.isdisjoint({r["id"] for r in theirs})
    for row in mine:
        for source in row["sources"]:
            assert source["document_id"] != w.d2
    nothing = _ok(c.get(f"{A}/questions", headers=w.outsider))
    assert all(r["status"] == "no_sources" for r in nothing)
    assert c.get(f"{A}/questions", params={"limit": 0}, headers=w.owner1).status_code == 422
    assert c.get(f"{A}/questions", params={"sort": "x"}, headers=w.owner1).status_code == 422
    for body in (
        {"question": "ab"},
        {"question": "Wie hoch ist das Hausgeld?", "extra": 1},
        {"question": "Wie hoch ist das Hausgeld?", "unit_id": "keine-uuid"},
        {"question": "x" * 2001},
    ):
        assert c.post(f"{A}/questions", json=body, headers=w.owner1).status_code == 422
    # Staff without a portal account and anonymous callers have no access.
    assert (
        c.post(f"{A}/questions", json={"question": "Hausgeld?"}, headers=w.reader).status_code
        == 403
    )
    assert c.get(f"{A}/status").status_code in (401, 403)


def test_hourly_limit_protects_the_budget(
    client: TestClient, w: W, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.portal import assistant

    c = client
    _switch(c, w, chat_bot_enabled=True, privacy_feature_enabled=False)
    used = len(_ok(c.get(f"{A}/questions", params={"limit": 100}, headers=w.outsider)))
    monkeypatch.setattr(assistant, "HOURLY_LIMIT", used + 2)
    _ask(c, w.outsider, "Hausgeld Frage eins")
    _ask(c, w.outsider, "Hausgeld Frage zwei")
    limited = c.post(f"{A}/questions", json={"question": "Hausgeld Frage drei"}, headers=w.outsider)
    assert limited.status_code == 429
    # The limit is per account.
    assert _ask(c, w.owner2, "Hausgeld Frage vier")["status"] in ("search_hits", "no_sources")
    assert fake.calls == []


def test_switching_off_locks_again_and_keeps_the_log(client: TestClient, w: W) -> None:
    c = client
    before = len(_ok(c.get(f"{AA}/log", params={"limit": 200}, headers=w.admin)))
    _switch(c, w, chat_bot_enabled=False, privacy_feature_enabled=False)
    assert (
        c.post(f"{A}/questions", json={"question": "Hausgeld?"}, headers=w.owner1).status_code
        == 403
    )
    assert len(_ok(c.get(f"{AA}/log", params={"limit": 200}, headers=w.admin))) == before
