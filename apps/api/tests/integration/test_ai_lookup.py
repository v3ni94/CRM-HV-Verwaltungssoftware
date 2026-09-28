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


def _ask(c: TestClient, h: dict[str, str], question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    conversation = _ok(c.post("/api/v1/ai/conversations", json={}, headers=h))
    run = _ok(
        c.post(
            f"/api/v1/ai/conversations/{conversation['id']}/messages",
            json={"content": question, "task": "answer_question", "document_ids": []},
            headers=h,
        ),
        202,
    )
    detail = _ok(c.get(f"/api/v1/ai/conversations/{conversation['id']}", headers=h), 200)
    answer = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    return run, answer


def _hrefs(links: list[dict[str, Any]]) -> set[str]:
    return {link["href"] for link in links}


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
    assert fake.calls[-1]["system"].startswith("Du beantwortest Fragen")
    assert run["prompt_version"] == "v2"
