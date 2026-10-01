"""Assistant platform lookup (rule AI-LOOKUP-01): the chat answers from the platform's own data
with links. Tools run in the caller's session under RLS with the permission of their regular
endpoint; without a released provider the hit list is still answered; links come from the
platform only; nothing found is said plainly. No live model calls.

Fixed expected values: tenant A holds contact "Jan Kowalski<RUN>" (phone +49 221 555123), rental
property 893 "Lindenhof<RUN>" with unit 07, a tenancy of Kowalski on unit 07 and ticket
"Heizung<RUN> defekt"; tenant B holds a contact with the same surname that must never appear.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.ai import lookup
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _property, _unit
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake

pytestmark = pytest.mark.integration
__all__ = ["fake"]  # fixture re-used from test_m7_ai

SURNAME = f"Kowalski{RUN}"
HOUSE = f"Lindenhof{RUN}"
HEATING = f"Heizung{RUN}"
# Digits only: a hex RUN such as "ab12cd34" after a space reads as an IBAN to the bank guard.
TICKET_NO = str(int(RUN, 16))


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lka-{RUN}", name=f"Lookup {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lkb-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("lkadmin", a, "tenant_admin"),
            ("lksecond", a, "tenant_admin"),
            ("lkcaretaker", a, "caretaker"),
            ("lkclerk", a, "clerk_no_delete"),  # ai:create, communication:read, no admin
            ("lkother", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _contact(c: TestClient, h: dict[str, str], first: str) -> str:
    body = {
        "kind": "person",
        "first_name": first,
        "last_name": SURNAME,
        "phones": [{"number": "+49 221 555123", "is_primary": True}],
        "emails": [{"email": f"jan.{RUN}@example.org", "is_primary": True}],
    }
    return str(_ok(c.post("/api/v1/contacts", json=body, headers=h))["id"])


@pytest.fixture(scope="module")
def records(database: Database, redis_url: str, world: World) -> dict[str, str]:
    with (
        mock_aws(),
        TestClient(create_app(_settings(database, redis_url))) as c,
    ):
        h = bearer(login(c, world, "lkadmin"))
        contact = _contact(c, h, "Jan")
        prop = _property(c, h, "893", "rental")
        _ok(c.patch(f"/api/v1/properties/{prop['id']}", json={"name": HOUSE}, headers=h), 200)
        unit = _unit(c, h, prop["id"], "07")
        owner = _ok(
            c.post(
                "/api/v1/contacts",
                json={"kind": "company", "company_name": f"V{RUN} GmbH"},
                headers=h,
            )
        )
        owner_party = _ok(
            c.post("/api/v1/parties", json={"members": [{"contact_id": owner["id"]}]}, headers=h)
        )
        _ok(
            c.post(
                f"/api/v1/properties/{prop['id']}/owners",
                json={"party_id": owner_party["id"], "valid_from": "2020-01-01"},
                headers=h,
            )
        )
        party = _ok(
            c.post("/api/v1/parties", json={"members": [{"contact_id": contact}]}, headers=h)
        )
        contract = _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": unit,
                    "party_id": party["id"],
                    "start_date": "2026-01-01",
                },
                headers=h,
            )
        )
        ticket = _ok(c.post("/api/v1/tickets", json={"title": f"{HEATING} defekt"}, headers=h))
        foreign = _contact(c, bearer(login(c, world, "lkother")), "Fremd")
        return {
            "contact": contact,
            "property": str(prop["id"]),
            "unit": unit,
            "contract": str(contract["id"]),
            "ticket": str(ticket["id"]),
            "ticket_number": str(ticket["number"]),
            "foreign": foreign,
        }


def _ask(
    c: TestClient,
    h: dict[str, str],
    question: str,
    conversation_id: str | None = None,
    **extra: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if conversation_id is None:
        conversation_id = _ok(c.post("/api/v1/ai/conversations", json={}, headers=h))["id"]
    body = {"content": question, "task": "answer_question", "document_ids": [], **extra}
    run = _ok(
        c.post(f"/api/v1/ai/conversations/{conversation_id}/messages", json=body, headers=h),
        202,
    )
    detail = _ok(c.get(f"/api/v1/ai/conversations/{conversation_id}", headers=h), 200)
    answer = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    return run, answer


def _hrefs(links: list[dict[str, Any]]) -> set[str]:
    return {link["href"] for link in links}


def _sent(fake: FakeProvider) -> str:
    return str(fake.calls[-1]["messages"][-1]["content"])


def _message(database: Database, redis_url: str, tenant_id: uuid.UUID, **fields: Any) -> uuid.UUID:
    """Stores a mail of the tenant directly (the IMAP or Gmail sync is not part of this test)."""
    from datetime import UTC, datetime

    from mhvp.communication.models import Message
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _store() -> uuid.UUID:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                row = Message(
                    tenant_id=tenant_id,
                    direction="in",
                    from_address=f"absender-{RUN}@example.org",
                    received_at=datetime.now(UTC),
                    **fields,
                )
                session.add(row)
                await session.flush()
                return row.id
        finally:
            await engine.dispose()

    return asyncio.run(_store())


# Order matters: the fallback tests run before the provider is released in this tenant.


def test_fallback_without_provider_answers_contact_with_link(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lkadmin"))
    run, answer = _ask(client, h, f"Wie ist die Telefonnummer von Herrn {SURNAME}?")
    assert run["status"] == "blocked"
    assert fake.calls == []  # nothing left the platform
    assert _hrefs(run["links"]) == {f"/kontakte/{records['contact']}"}
    contact_link = run["links"][0]
    assert contact_link["type"] == "contact"
    assert contact_link["label"] == f"Jan {SURNAME}" or SURNAME in contact_link["label"]
    assert "555123" in contact_link["detail"].replace(" ", "")
    assert "Plattformsuche" in answer["content"]
    assert "Gefunden (1)" in answer["content"]
    assert answer["links"] == run["links"]  # stored with the message (audit)
    assert run["lookup_answer"].startswith("Gefunden (1)")


def test_fallback_links_for_property_unit_contract_and_ticket(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lkadmin"))
    run, _ = _ask(client, h, f"Objekt {HOUSE}")
    assert f"/objekte/{records['property']}" in _hrefs(run["links"])
    run, _ = _ask(client, h, f"Einheit 07 im {HOUSE}")
    assert f"/vermietung/einheit/{records['unit']}" in _hrefs(run["links"])
    run, _ = _ask(client, h, f"Mietvertrag von {SURNAME}")
    assert f"/vertraege/{records['contract']}" in _hrefs(run["links"])
    contract = next(x for x in run["links"] if x["type"] == "contract")
    assert "Objekt 893 Einheit 07" in contract["detail"]
    run, _ = _ask(client, h, f"Status vom Ticket {HEATING}")
    ticket = next(x for x in run["links"] if x["type"] == "ticket")
    assert ticket["href"] == f"/tickets/{records['ticket']}"
    assert ticket["label"].startswith(f"#{records['ticket_number']} ")
    assert "neu" in ticket["detail"]
    run, _ = _ask(client, h, f"Ticket #{records['ticket_number']}")
    assert f"/tickets/{records['ticket']}" in _hrefs(run["links"])


def test_not_found_is_said_plainly(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lkadmin"))
    run, answer = _ask(client, h, f"Wer ist Nichtvorhanden{RUN}?")
    assert run["links"] == []
    assert (
        f"Keine passenden Datensätze gefunden zu: nichtvorhanden{RUN.lower()}."
        in (answer["content"])
    )


def test_where_do_i_find_links_the_settings_page(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lkadmin"))
    run, _ = _ask(client, h, "Wo finde ich die Markenfarben?")
    page = next(x for x in run["links"] if x["type"] == "page")
    assert page["href"] == "/einstellungen/mandant#company-branding-title"


def test_tenant_separation(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    other = bearer(login(client, world, "lkother"))
    run, _ = _ask(client, other, f"Telefonnummer {SURNAME}")
    ids = {x["id"] for x in run["links"]}
    assert ids == {records["foreign"]}
    admin = bearer(login(client, world, "lkadmin"))
    run, _ = _ask(client, admin, f"Telefonnummer {SURNAME}")
    assert records["foreign"] not in {x["id"] for x in run["links"]}


def test_chat_needs_ai_permission(client: TestClient, world: World) -> None:
    caretaker = bearer(login(client, world, "lkcaretaker"))
    response = client.post("/api/v1/ai/conversations", json={}, headers=caretaker)
    assert response.status_code == 403


def test_tool_without_permission_returns_nothing_and_says_so(
    database: Database, redis_url: str, world: World, records: dict[str, str]
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _run(permissions: frozenset[str]) -> dict[str, Any]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(
                create_session_factory(engine), world.tenant_a
            ) as session:
                return await lookup.run(session, permissions, f"Mietvertrag {SURNAME}")
        finally:
            await engine.dispose()

    only_properties = asyncio.run(_run(frozenset({"properties:read"})))
    assert only_properties["links"] == []
    denied = {t["tool"] for t in only_properties["tools"] if not t["permitted"]}
    assert {"contacts", "contracts"} <= denied
    assert "Ohne Berechtigung nicht durchsucht: Kontakte" in lookup.answer_text(only_properties)
    full = asyncio.run(_run(frozenset({"contacts:read", "contracts:read", "properties:read"})))
    assert uuid.UUID(records["contract"]) in {
        uuid.UUID(x["id"]) for x in full["links"] if x["type"] == "contract"
    }


def test_with_provider_model_answers_from_masked_hits(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "lkadmin"))
    second = bearer(login(client, world, "lksecond"))
    dpa = _upload(client, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    _ok(
        client.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": dpa},
            headers=admin,
        ),
        200,
    )
    _ok(client.post("/api/v1/ai/providers/anthropic/release", headers=second), 200)
    fake.queue.append(
        {
            "answer": f"Jan {SURNAME} ist als Kontakt erfasst.",
            "sources": [{"document_id": "contact", "excerpt": SURNAME}],
            "answerable": True,
        }
    )
    run, answer = _ask(client, admin, f"Telefonnummer von {SURNAME}")
    assert run["status"] == "succeeded", run
    sent = fake.calls[-1]["messages"][-1]["content"]
    assert "Treffer der Plattformsuche" in sent
    assert SURNAME in sent
    assert "555123" not in sent.replace(" ", "")  # masked before it leaves (9.1)
    assert "[TELEFON]" in sent
    assert answer["content"].startswith(f"Jan {SURNAME} ist als Kontakt erfasst.")
    assert "Gefunden (1)" in answer["content"]
    assert _hrefs(answer["links"]) == {f"/kontakte/{records['contact']}"}
    assert fake.calls[-1]["system"].startswith("Du bist der Assistent im CRM")
    assert run["prompt_version"] == "v4"


def _answer(text: str, action: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"answer": text, "sources": [], "answerable": True, "action": action}


def test_foreign_phone_and_any_iban_spelling_never_reach_the_provider(
    client: TestClient,
    world: World,
    records: dict[str, str],
    fake: FakeProvider,
    database: Database,
    redis_url: str,
) -> None:
    """Contacts store E.164 numbers (a Swiss owner: +41...), mails spell IBANs in any case with
    any separator; neither leaves the platform (0.1.13). Provider released by the previous
    test."""
    admin = bearer(login(client, world, "lkadmin"))
    surname = f"Zimmerli{RUN}"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Ruedi",
                "last_name": surname,
                "phones": [{"number": "+41 79 123 45 67", "is_primary": True}],
                "emails": [{"email": f"ruedi.{RUN}@example.ch", "is_primary": True}],
            },
            headers=admin,
        )
    )
    _message(
        database,
        redis_url,
        world.tenant_a,
        contact_id=uuid.UUID(contact["id"]),
        subject=f"Neue Bankverbindung {RUN}",
        body="Bitte künftig auf de44-5001-0517-5407-3249-31 überweisen.\nDanke, Ruedi",
    )
    fake.queue.append(_answer("Die Bankverbindung ändere ich nicht."))
    run, _ = _ask(
        client,
        admin,
        f"Was schreibt {surname}?",
        context_entity_type="contact",
        context_entity_id=contact["id"],
        page="Kontakte",
    )
    assert run["status"] == "succeeded", run
    sent = _sent(fake)
    assert surname in sent
    assert "Ruedi" in sent
    assert "Neue Bankverbindung" in sent  # the mail is a fact of the open record
    assert "41791234567" not in sent.replace(" ", "")
    assert "791234567" not in sent.replace(" ", "")
    assert f"ruedi.{RUN}@example.ch" not in sent
    assert "5001" not in sent
    assert "3249" not in sent
    assert "[IBAN]" in sent
    assert "[TELEFON]" in sent
    assert "[E-MAIL]" in sent
    # The chat itself (employee with contacts:read) still shows the number in the hit list.
    hit = next(x for x in run["links"] if x["type"] == "contact")
    assert "+41791234567" in hit["detail"]
    assert "model_detail" not in hit


def test_mail_facts_follow_the_mailbox_rule_of_the_mail_endpoints(
    client: TestClient,
    world: World,
    records: dict[str, str],
    fake: FakeProvider,
    database: Database,
    redis_url: str,
) -> None:
    """A member without a grant on a colleague's personal mailbox never gets its mails as
    facts (same rule as GET /mail/messages); an administrator reads every mailbox."""
    admin = bearer(login(client, world, "lkadmin"))
    clerk = bearer(login(client, world, "lkclerk"))
    box = _ok(
        client.post(
            "/api/v1/mail/mailboxes",
            json={"address": f"privat-{RUN}@example.com", "kind": "gmail", "secret": "x"},
            headers=admin,
        )
    )
    assert box["is_default"] is False
    contact_id = uuid.UUID(records["contact"])
    _message(
        database,
        redis_url,
        world.tenant_a,
        contact_id=contact_id,
        mailbox_id=uuid.UUID(box["id"]),
        subject=f"Persönlich {RUN}",
        body=f"Vertraulich{RUN} nur für das persönliche Postfach.",
    )
    _message(
        database,
        redis_url,
        world.tenant_a,
        contact_id=contact_id,
        subject=f"Allgemein {RUN}",
        body=f"Allgemein{RUN} ohne Postfach.",
    )
    focus = {
        "context_entity_type": "contact",
        "context_entity_id": records["contact"],
        "page": "Kontakte",
    }
    fake.queue.append(_answer("Es gibt eine Mail."))
    run, _ = _ask(client, clerk, "Was ist offen bei diesem Kontakt?", **focus)
    assert run["status"] == "succeeded", run
    sent = _sent(fake)
    assert f"Allgemein{RUN}" in sent
    assert f"Vertraulich{RUN}" not in sent
    assert f"Persönlich {RUN}" not in sent
    # The regular endpoint answers the same way for this member (no inference from 404).
    listed = _ok(client.get("/api/v1/mail/messages", headers=clerk), 200)
    subjects = {m["subject"] for m in (listed["data"] if isinstance(listed, dict) else listed)}
    assert f"Persönlich {RUN}" not in subjects
    fake.queue.append(_answer("Es gibt zwei Mails."))
    run, _ = _ask(client, admin, "Was ist offen bei diesem Kontakt?", **focus)
    assert run["status"] == "succeeded", run
    sent = _sent(fake)
    assert f"Allgemein{RUN}" in sent
    assert f"Vertraulich{RUN}" in sent


def test_answer_question_outside_the_chat_keeps_v1_and_never_proposes(
    client: TestClient,
    world: World,
    records: dict[str, str],
    fake: FakeProvider,
    database: Database,
    redis_url: str,
) -> None:
    """The automation action ``ai_task`` starts ``answer_question`` through
    ``create_extraction_run`` (no chat user, no platform lookup): prompt v1, and an action in
    the model output never becomes a chat action proposal."""
    from mhvp.ai import jobs
    from mhvp.ai.models import AiProposal, AiTask, AiTaskRun
    from mhvp.ai.routers import create_extraction_run
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore

    settings = _settings(database, redis_url)
    fake.queue.append(
        _answer(
            "Ticket vorbereitet.",
            {"kind": "ticket_create", "refs": [], "title": f"Aus der Regel {RUN}"},
        )
    )

    async def _run() -> tuple[str, str, int, dict[str, Any] | None]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                run_id = await create_extraction_run(
                    session,
                    world.tenant_a,
                    None,
                    AiTask.ANSWER_QUESTION,
                    [],
                    f"Lege ein Ticket an: Aus der Regel {RUN}",
                    "automation",
                    None,
                    trigger="automation:test",
                )
            with mock_aws():
                boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
                await jobs.run_and_propose(
                    factory, world.tenant_a, run_id, BlobStore(settings), None
                )
            async with tenant_transaction(factory, world.tenant_a) as session:
                run = await session.get(AiTaskRun, run_id)
                assert run is not None
                proposals = (
                    await session.scalars(
                        select(AiProposal).where(AiProposal.task_run_id == run_id)
                    )
                ).all()
                return run.status.value, run.prompt_version, len(proposals), run.output
        finally:
            await engine.dispose()

    status, version, proposals, output = asyncio.run(_run())
    assert status == "succeeded", output
    assert version == "v1"
    assert proposals == 0
    assert fake.calls[-1]["system"].startswith("Du beantwortest Fragen von Mitarbeitenden")
    assert "<frage>" in _sent(fake)  # the instruction stays outside the data block


def test_page_context_focus_and_multi_turn_history(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    """Provider released by the previous test. The record open on the page is looked up
    without a search term; the second turn carries the first one as history."""
    admin = bearer(login(client, world, "lkadmin"))
    conversation = _ok(client.post("/api/v1/ai/conversations", json={}, headers=admin))["id"]
    fake.queue += [_answer("Beim Kontakt ist ein Vertrag hinterlegt."), _answer("Ja, seit 2026.")]
    context = {
        "context_entity_type": "contact",
        "context_entity_id": records["contact"],
        "page": "Kontakte",
    }
    run, answer = _ask(client, admin, "Was ist offen bei diesem Kontakt?", conversation, **context)
    assert run["status"] == "succeeded", run
    hrefs = _hrefs(answer["links"])
    assert f"/kontakte/{records['contact']}" in hrefs
    assert f"/vertraege/{records['contract']}" in hrefs  # contracts of the focused contact
    first = fake.calls[-1]["messages"][-1]["content"]
    assert "Geöffneter Datensatz auf der Seite: contact" in first
    assert '"page": "Kontakte"' in first
    run, _ = _ask(client, admin, "Und seit wann?", conversation, **context)
    assert run["status"] == "succeeded", run
    second = fake.calls[-1]["messages"][-1]["content"]
    assert "Bisheriger Gesprächsverlauf" in second
    assert "Nutzer: Was ist offen bei diesem Kontakt?" in second
    assert "Assistent: Beim Kontakt ist ein Vertrag hinterlegt." in second


def test_phone_change_is_a_proposal_until_confirmed(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "lkadmin"))
    fake.queue.append(
        _answer(
            "Ich habe die Änderung vorbereitet.",
            {
                "kind": "contact_change",
                "refs": [records["contact"]],
                "changes": [{"field": "phone", "new": "[TELEFON]"}],
                "reason": "Nutzer nennt neue Nummer",
            },
        )
    )
    run, answer = _ask(client, admin, f"Neue Telefonnummer von {SURNAME}: 0211 7654321")
    assert run["status"] == "succeeded", run
    assert "7654321" not in fake.calls[-1]["messages"][-1]["content"].replace(" ", "")
    assert "Vorschlag erstellt" in answer["content"]
    proposal_id = answer["proposal_id"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["entity_type"] == "chat_action"
    assert proposal["proposed"]["changes"] == [
        {"field": "phone", "old": None, "new": "0211 7654321"}
    ]
    before = _ok(client.get(f"/api/v1/contacts/{records['contact']}", headers=admin), 200)
    assert all("7654321" not in p["number"] for p in before["phones"])  # nothing written yet
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        )
    )
    assert applied["summary"]["kind"] == "contact_change"
    after = _ok(client.get(f"/api/v1/contacts/{records['contact']}", headers=admin), 200)
    assert any("7654321" in p["number"] for p in after["phones"])
    again = client.post(
        f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
    )
    assert again.status_code == 409
    # The import run of a chat action has no items: the import undo refuses it instead of
    # logging a rollback that reverts nothing (0.1.7).
    assert applied["source"] == "ai:answer_question:contact_change"
    undo = client.post(f"/api/v1/imports/{applied['id']}/undo", headers=admin)
    assert undo.status_code == 409, undo.text
    assert "Chat-Aktionen" in undo.json()["detail"]
    kept = _ok(client.get(f"/api/v1/imports/{applied['id']}", headers=admin), 200)
    assert kept["status"] == "applied"
    assert kept["undone_at"] is None
    still = _ok(client.get(f"/api/v1/contacts/{records['contact']}", headers=admin), 200)
    assert any("7654321" in p["number"] for p in still["phones"])


def test_rejected_chat_action_is_learned_masked(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    """A rejected proposal with a reason becomes a learning example; the raw phone number of
    the chat action never reaches the provider through the examples (0.1.13)."""
    admin = bearer(login(client, world, "lkadmin"))
    _ok(
        client.patch(
            "/api/v1/tenant/settings", json={"ai_learning_examples_enabled": True}, headers=admin
        ),
        200,
    )
    try:
        fake.queue.append(
            _answer(
                "Vorbereitet.",
                {
                    "kind": "contact_change",
                    "refs": [records["contact"]],
                    "changes": [{"field": "phone", "new": "[TELEFON]"}],
                },
            )
        )
        _, answer = _ask(client, admin, f"Neue Telefonnummer von {SURNAME}: 0221 9998877")
        proposal_id = answer["proposal_id"]
        assert proposal_id
        rejected = _ok(
            client.post(
                f"/api/v1/ai/proposals/{proposal_id}/reject",
                json={"reason": "falsche Nummer"},
                headers=admin,
            ),
            200,
        )
        assert rejected["decision"] == "rejected"
        fake.queue.append(_answer(f"{SURNAME} ist erfasst."))
        run, _ = _ask(client, admin, f"Wer ist {SURNAME}?")
        assert run["status"] == "succeeded", run
        sent = _sent(fake)
        assert "Bestätigte Beispiele" in sent
        assert "falsche Nummer" in sent
        assert "9998877" not in sent.replace(" ", "")
        assert '"new": "[TELEFON]"' in sent
    finally:
        _ok(
            client.patch(
                "/api/v1/tenant/settings",
                json={"ai_learning_examples_enabled": False},
                headers=admin,
            ),
            200,
        )


def test_bank_details_are_never_a_chat_proposal(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "lkadmin"))
    fake.queue.append(
        _answer(
            "Erledige ich.",
            {
                "kind": "contact_change",
                "refs": [records["contact"]],
                "changes": [{"field": "iban", "new": "[IBAN]"}],
            },
        )
    )
    _, answer = _ask(client, admin, f"Neue IBAN von {SURNAME}: DE02120300000000202051")
    assert answer["proposal_id"] is None
    assert "Vier-Augen-Freigabe" in answer["content"]


def test_ticket_create_proposal_needs_confirmation(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "lkadmin"))
    fake.queue.append(
        _answer(
            "Ticket vorbereitet.",
            {
                "kind": "ticket_create",
                "refs": [records["contact"], str(uuid.uuid4())],  # unknown id is ignored
                "title": f"Rückruf {TICKET_NO}",
                "description": "Bitte zurückrufen.",
            },
        )
    )
    _, answer = _ask(client, admin, f"Lege ein Ticket für {SURNAME} an: Rückruf")
    proposal_id = answer["proposal_id"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["proposed"]["contact_id"] == records["contact"]
    listed = _ok(
        client.get("/api/v1/tickets", params={"q": f"Rückruf {TICKET_NO}"}, headers=admin), 200
    )
    assert listed == []  # nothing before the confirmation
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        )
    )
    ticket_id = applied["summary"]["ticket_id"]
    ticket = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=admin), 200)
    assert ticket["title"] == f"Rückruf {TICKET_NO}"
    assert ticket["contact_id"] == records["contact"]


def test_ticket_create_apply_is_one_transaction_with_the_decision(
    client: TestClient,
    world: World,
    records: dict[str, str],
    fake: FakeProvider,
    database: Database,
    redis_url: str,
) -> None:
    """When the ticket cannot be created, nothing else is written either: the proposal stays
    pending, no import run exists, no ticket (AI-LOOKUP-Q3)."""
    from sqlalchemy import create_engine, text

    admin = bearer(login(client, world, "lkadmin"))
    unit = _unit(client, admin, records["property"], "08")
    fake.queue.append(
        _answer(
            "Ticket vorbereitet.",
            {
                "kind": "ticket_create",
                "refs": [unit],
                "title": f"Dachfenster {RUN}",
                "description": "Undicht.",
            },
        )
    )
    _, answer = _ask(client, admin, f"Lege ein Ticket für Einheit 08 im {HOUSE} an: Dachfenster")
    proposal_id = answer["proposal_id"]
    assert proposal_id, answer
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["proposed"]["unit_id"] == unit

    def _applied_ticket_events() -> int:
        rows = _ok(
            client.get(
                "/api/v1/tenant/events", params={"type": "import_run.applied"}, headers=admin
            ),
            200,
        )
        return sum(
            1 for e in rows if e["payload"].get("source") == "ai:answer_question:ticket_create"
        )

    imports_before = len(_ok(client.get("/api/v1/imports", headers=admin), 200))
    events_before = _applied_ticket_events()
    # The unit disappears between proposal and confirmation (owner connection, outside RLS).
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_a)},
        )
        deleted = conn.execute(text("DELETE FROM unit WHERE id = :id"), {"id": unit}).rowcount
    engine.dispose()
    assert deleted == 1
    failed = client.post(
        f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
    )
    assert failed.status_code == 404, failed.text
    assert "Einheit nicht gefunden" in failed.json()["detail"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["decision"] == "pending"
    assert proposal["import_run_id"] is None
    assert len(_ok(client.get("/api/v1/imports", headers=admin), 200)) == imports_before
    assert _applied_ticket_events() == events_before
    listed = _ok(
        client.get("/api/v1/tickets", params={"q": f"Dachfenster {RUN}"}, headers=admin), 200
    )
    assert listed == []
    # A second confirmation is still possible once the cause is fixed: nothing is stuck.
    assert (
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/reject",
            json={"reason": "Einheit weg"},
            headers=admin,
        ).status_code
        == 200
    )
