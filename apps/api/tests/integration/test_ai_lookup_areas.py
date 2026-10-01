"""Area tools of the assistant lookup (rule AI-LOOKUP-01, operator request 29.09.2026): the
chat relates to the page that is open. Calendar, deadlines, documents, WEG (resolutions,
meetings, reserve), rent increases, work orders, bank transactions and open items answer the
page's standard questions without a search term, under the caller's permissions, tenant RLS
and the legal entity scope; calendar and deadline entries become proposals that are written
only after the confirmation and only once. No live model calls (fake provider).

Fixed expected values: tenant A holds a community 921 "Rosenhof<RUN>" with owner "Eig<RUN>",
one open receivable of 250,00 EUR, one unmatched credit of 400,00 EUR, a meeting, a
resolution "Dachsanierung<RUN>", a document "Protokoll-<RUN>.txt", a handover appointment in
three days, a site visit in four days, an overdue deadline and one due in five days, a work
order "Dachrinne<RUN>" and a rent increase case; tenant B sees none of it.
"""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import lookup
from mhvp.core.auth.principal import Principal
from mhvp.core.auth.scope import SESSION_PRINCIPAL_KEY
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit
from tests.integration.test_m7_ai import BUCKET, PROVIDER, FakeProvider, _settings, _upload, fake
from tests.integration.test_m11_banking import _camt, _ntry

pytestmark = pytest.mark.integration
__all__ = ["fake"]  # fixture re-used from test_m7_ai

A = "/api/v1/accounting"
B = "/api/v1/banking"
H = "/api/v1/hoa"
L = "/api/v1/letting"
W = "/api/v1/workspace"
IBAN = "DE02120300000000202051"
PAYER = "DE89370400440532013000"
HOUSE = f"Rosenhof{RUN}"
OWNER = f"Eig{RUN}"
TODAY = local_today()


def _iso(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def _de(days: int) -> str:
    return (TODAY + timedelta(days=days)).strftime("%d.%m.%Y")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lxa-{RUN}", name=f"Areas {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lxb-{RUN}", name=f"FremdA {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("lxadmin", a, "tenant_admin"),
            ("lxsecond", a, "tenant_admin"),
            ("lxother", b, "tenant_admin"),
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


def _store(database: Database, redis_url: str, tenant_id: uuid.UUID, rows: list[Any]) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _run() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                for row in rows:
                    session.add(row)
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.fixture(scope="module")
def records(database: Database, redis_url: str, world: World) -> dict[str, str]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            return _records(c, database, redis_url, world)


def _records(c: TestClient, database: Database, redis_url: str, world: World) -> dict[str, str]:
    from mhvp.workspace.models import ComplianceDeadline

    if True:
        h = bearer(login(c, world, "lxadmin"))
        # Community with one owner, its bank account, ledger and an open receivable.
        prop = _ok(
            c.post(
                "/api/v1/properties",
                json={"number": "921", "name": HOUSE, "management_type": "hoa"},
                headers=h,
            )
        )
        hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        owner_party, owner_contact = _party(c, h, OWNER)
        unit = _unit(c, h, prop["id"], "01")
        ownership = _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": unit,
                    "party_id": owner_party,
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                },
                headers=h,
            )
        )
        bank_account = _ok(
            c.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": "hoa",
                    "iban": IBAN,
                    "holder": f"GdWE {HOUSE}",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            )
        )["id"]
        template = _ok(c.post(f"{A}/templates/default", headers=h))
        ledger = _ok(
            c.post(
                f"{A}/ledgers",
                json={"legal_entity_id": hoa, "template_id": template["id"]},
                headers=h,
            )
        )["id"]
        accounts = {
            a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h), 200)
        }
        _ok(
            c.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={
                    "number": "001211",
                    "name": "Hausgeldkonto",
                    "category": "bank",
                    "type": "asset",
                    "property_bank_account_id": bank_account,
                },
                headers=h,
            )
        )
        debtor = next(
            a["id"] for a in accounts.values() if a["category"] == "debtor" and a["unit_id"] == unit
        )
        draft = _ok(
            c.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": "2026-01-01",
                    "text": "Hausgeld Januar",
                    "contract_id": ownership["id"],
                    "lines": [
                        {"account_id": debtor, "debit": "250.00"},
                        {"account_id": accounts["060100"]["id"], "credit": "250.00"},
                    ],
                },
                headers=h,
            )
        )
        _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h), 200)
        # One unmatched credit of 400,00 EUR from the bank statement.
        statement = _camt(
            f"LX-{RUN}",
            IBAN,
            "1000.00",
            "1400.00",
            [_ntry(f"LX-{RUN}-1", "400.00", "CRDT", "2026-02-05", PAYER, f"Hausgeld {RUN}")],
        )
        doc = _ok(
            c.post(
                "/api/v1/documents",
                files={"file": ("lx.xml", statement, "application/xml")},
                headers=h,
            )
        )["id"]
        _ok(c.post(f"{B}/imports", json={"document_id": doc}, headers=h))
        # Meeting and resolution.
        meeting = _ok(
            c.post(
                f"{H}/meetings",
                json={
                    "legal_entity_id": hoa,
                    "scheduled_at": f"{_iso(20)}T10:00:00+02:00",
                    "location": "Gemeinschaftsraum",
                    "voting_principle": "head",
                },
                headers=h,
            )
        )
        resolution = _ok(
            c.post(
                f"{H}/resolutions",
                json={
                    "legal_entity_id": hoa,
                    "decided_on": "2026-06-20",
                    "subject": f"Dachsanierung{RUN}",
                    "wording": "Die Dachsanierung wird beauftragt.",
                    "status": "positive",
                    "kind": "meeting",
                },
                headers=h,
            )
        )
        # Document, calendar entries, work order.
        document = _upload(c, h, f"Protokoll-{RUN}.txt", b"Protokoll der Begehung", "text/plain")
        handover = _ok(
            c.post(
                f"{W}/calendar",
                json={
                    "title": f"Übergabe Rosenweg {RUN}",
                    "starts_on": _iso(3),
                    "reminders": ["1d"],
                },
                headers=h,
            )
        )
        visit = _ok(
            c.post(
                f"{W}/calendar",
                json={"title": f"Begehung Dach {RUN}", "starts_on": _iso(4)},
                headers=h,
            )
        )
        provider_party, provider = _party(c, h, f"Dachdecker{RUN}", "company")
        order = _ok(
            c.post(
                "/api/v1/work-orders",
                json={
                    "property_id": prop["id"],
                    "provider_contact_id": provider["id"],
                    "description": f"Dachrinne{RUN} reinigen",
                },
                headers=h,
            )
        )
        # Rent increase on a rental property.
        rental = _property(c, h, "922", "rental")
        landlord, _ = _party(c, h, f"Verm{RUN}", "company")
        _ok(
            c.post(
                f"/api/v1/properties/{rental['id']}/owners",
                json={"party_id": landlord, "valid_from": "2020-01-01"},
                headers=h,
            )
        )
        rental_unit = _unit(c, h, rental["id"], "01")
        tenant_party, tenant_contact = _party(c, h, f"Mieter{RUN}")
        tenancy = _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": rental_unit,
                    "party_id": tenant_party,
                    "start_date": "2023-01-01",
                },
                headers=h,
            )
        )["id"]
        _ok(
            c.post(
                f"/api/v1/contracts/{tenancy}/payments",
                json={
                    "payment_type_code": "rent",
                    "net": "600.00",
                    "gross": "600.00",
                    "valid_from": "2023-01-01",
                },
                headers=h,
            )
        )
        case = _ok(
            c.post(
                f"{L}/rent-increases",
                json={
                    "contract_id": tenancy,
                    "basis": "mietspiegel",
                    "effective_date": "2026-12-01",
                    "reference_rent": "600.00",
                    "cap_limit_percent": "15",
                    "comparison_rent_per_sqm": "11.50",
                    "source_note": "Testwerte, keine Rechtsquelle",
                    "target_rent": "660.00",
                },
                headers=h,
            )
        )
        foreign = _ok(
            c.post(
                f"{W}/calendar",
                json={"title": f"Fremdtermin {RUN}", "starts_on": _iso(3)},
                headers=bearer(login(c, world, "lxother")),
            )
        )
    _store(
        database,
        redis_url,
        world.tenant_a,
        [
            ComplianceDeadline(
                tenant_id=world.tenant_a,
                kind="contract_end",
                source_type="contract",
                source_id=uuid.UUID(tenancy),
                reference=f"Vertragsende alt {RUN}",
                due_on=TODAY - timedelta(days=3),
                lead_days=30,
                status="open",
            ),
            ComplianceDeadline(
                tenant_id=world.tenant_a,
                kind="meter_calibration",
                source_type="meter",
                source_id=uuid.uuid4(),
                reference=f"Eichfrist Zähler {RUN}",
                due_on=TODAY + timedelta(days=5),
                lead_days=30,
                status="open",
                property_id=uuid.UUID(prop["id"]),
            ),
        ],
    )
    return {
        "property": str(prop["id"]),
        "hoa": hoa,
        "ledger": ledger,
        "owner_contact": str(owner_contact["id"]),
        "ownership": str(ownership["id"]),
        "meeting": str(meeting["id"]),
        "resolution": str(resolution["id"]),
        "document": document,
        "handover": str(handover["calendar_entry_id"]),
        "visit": str(visit["calendar_entry_id"]),
        "order": str(order["id"]),
        "case": str(case["id"]),
        "tenant_contact": str(tenant_contact["id"]),
        "provider_party": provider_party,
        "foreign_entry": str(foreign["calendar_entry_id"]),
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
        c.post(f"/api/v1/ai/conversations/{conversation_id}/messages", json=body, headers=h), 202
    )
    detail = _ok(c.get(f"/api/v1/ai/conversations/{conversation_id}", headers=h), 200)
    answer = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    return run, answer


def _of(run: dict[str, Any], type_: str) -> list[dict[str, Any]]:
    return [x for x in run["links"] if x["type"] == type_]


# Order matters: the fallback tests run before the provider is released in this tenant.


def test_calendar_page_answers_todays_and_handover_appointments_and_free_day(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lxadmin"))
    run, answer = _ask(
        client, h, "Welche Termine habe ich in den nächsten 7 Tagen?", area="calendar"
    )
    assert run["status"] == "blocked"  # no provider released: deterministic answer
    assert fake.calls == []
    entries = _of(run, "calendar_entry")
    assert {x["label"] for x in entries} == {f"Übergabe Rosenweg {RUN}", f"Begehung Dach {RUN}"}
    handover = next(x for x in entries if x["label"].startswith("Übergabe"))
    assert handover["href"] == f"/kalender?termin={records['handover']}&datum={_iso(3)}"
    assert handover["detail"].startswith(_de(3))
    assert "Gefunden (2)" in answer["content"]
    run, _ = _ask(client, h, "Übergabetermine in den nächsten 7 Tagen", area="calendar")
    assert [x["label"] for x in _of(run, "calendar_entry")] == [f"Übergabe Rosenweg {RUN}"]
    run, answer = _ask(client, h, "Welche Termine habe ich heute?", area="calendar")
    assert _of(run, "calendar_entry") == []
    assert f"Keine Termine im CRM-Kalender vom {_de(0)} bis {_de(0)}" in answer["content"]
    run, answer = _ask(client, h, "Freien Termin nächste Woche finden", area="calendar")
    assert "Nächster Werktag ohne Termin im CRM-Kalender:" in answer["content"]
    assert "Google-Kalender nicht geprüft" in answer["content"]


def test_calendar_entries_of_another_user_and_tenant_stay_hidden(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    other = bearer(login(client, world, "lxother"))
    run, _ = _ask(
        client, other, "Welche Termine habe ich in den nächsten 7 Tagen?", area="calendar"
    )
    assert [x["label"] for x in _of(run, "calendar_entry")] == [f"Fremdtermin {RUN}"]
    second = bearer(login(client, world, "lxsecond"))  # same tenant, not owner, not shared
    run, _ = _ask(
        client, second, "Welche Termine habe ich in den nächsten 7 Tagen?", area="calendar"
    )
    assert _of(run, "calendar_entry") == []


def test_deadlines_page_answers_overdue_and_next_days(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lxadmin"))
    run, _ = _ask(client, h, "Welche Fristen sind überfällig?", area="deadlines")
    overdue = _of(run, "deadline")
    assert [x["label"] for x in overdue] == [f"Vertragsende: Vertragsende alt {RUN}"]
    assert "überfällig seit 3 Tagen, zu prüfen" in overdue[0]["detail"]
    assert _of(run, "calendar_entry") == []
    run, _ = _ask(client, h, "Fristen in den nächsten 7 Tagen", area="deadlines")
    labels = {x["label"] for x in run["links"]}
    assert f"Eichfrist: Eichfrist Zähler {RUN}" in labels
    assert f"Übergabe Rosenweg {RUN}" in labels  # own appointment with a reminder
    assert f"Begehung Dach {RUN}" not in labels  # no reminder: an appointment, not a deadline
    meter = next(x for x in run["links"] if x["label"].startswith("Eichfrist"))
    assert "fällig in 5 Tagen" in meter["detail"]
    assert meter["href"] == f"/objekte/{records['property']}#zaehler"


def test_documents_page_finds_by_title_under_tenant_separation(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lxadmin"))
    run, _ = _ask(client, h, f"Dokument Protokoll-{RUN} suchen", area="documents")
    docs = _of(run, "document")
    assert [x["href"] for x in docs] == [f"/dokumente/{records['document']}"]
    assert docs[0]["label"] == f"Protokoll-{RUN}.txt"
    other = bearer(login(client, world, "lxother"))
    run, _ = _ask(client, other, f"Dokument Protokoll-{RUN} suchen", area="documents")
    assert _of(run, "document") == []


def test_hoa_page_answers_resolutions_meetings_and_reserve_state(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lxadmin"))
    focus = {"context_entity_type": "hoa", "context_entity_id": records["property"], "area": "hoa"}
    run, _ = _ask(client, h, "Beschlüsse dieser WEG", **focus)
    res = _of(run, "resolution")
    assert [x["label"] for x in res] == [f"Beschluss 1: Dachsanierung{RUN}"]
    assert res[0]["detail"] == "20.06.2026, angenommen"
    assert res[0]["href"] == f"/weg/{records['property']}"
    run, _ = _ask(client, h, "Eigentümerversammlungen dieser WEG", **focus)
    meetings = _of(run, "meeting")
    assert [x["href"] for x in meetings] == [
        f"/weg/{records['property']}/versammlung/{records['meeting']}"
    ]
    assert meetings[0]["label"] == f"Eigentümerversammlung {_de(20)}"
    run, answer = _ask(client, h, "Stand der Erhaltungsrücklage", **focus)
    assert (
        f"Rücklage 921 {HOUSE}: keine berechnete Jahresabrechnung vorhanden." in answer["content"]
    )
    # The meeting page: its agenda and record links come from the focus.
    run, _ = _ask(
        client,
        h,
        "Tagesordnung dieser Versammlung",
        context_entity_type="meeting",
        context_entity_id=records["meeting"],
        area="hoa",
        sub_area="meeting",
    )
    assert [x["id"] for x in _of(run, "meeting")] == [records["meeting"]]


def test_reserve_is_withheld_outside_the_legal_entity_scope(
    database: Database, redis_url: str, world: World, records: dict[str, str]
) -> None:
    """A scoped membership (tax advisor) without this community: the tool says so instead of
    reading the reserve; the resolutions and meetings of the community are not listed."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _run(scope: tuple[uuid.UUID, ...]) -> dict[str, Any]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(
                create_session_factory(engine), world.tenant_a
            ) as session:
                session.info[SESSION_PRINCIPAL_KEY] = Principal(
                    user_id=world.users["lxadmin"],
                    tenant_id=world.tenant_a,
                    permissions=frozenset({"accounting:read", "properties:read"}),
                    roles=("tax_advisor",),
                    legal_entity_ids=scope,
                )
                return await lookup.run(
                    session,
                    frozenset({"accounting:read", "properties:read"}),
                    "Rücklage und Beschlüsse",
                    ("hoa", uuid.UUID(records["property"])),
                    area="hoa",
                )
        finally:
            await engine.dispose()

    outside = asyncio.run(_run((uuid.uuid4(),)))
    assert any("Rechtsträger nicht im Zugriff" in f for f in outside["facts"]), outside["facts"]
    assert [x for x in outside["links"] if x["type"] in ("resolution", "meeting")] == []
    inside = asyncio.run(_run((uuid.UUID(records["hoa"]),)))
    assert any("keine berechnete Jahresabrechnung" in f for f in inside["facts"])
    assert [x["id"] for x in inside["links"] if x["type"] == "resolution"] == [
        records["resolution"]
    ]


def test_letting_orders_bank_and_open_items_pages(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "lxadmin"))
    run, _ = _ask(client, h, "Offene Mieterhöhungen", area="letting")
    cases = _of(run, "rent_increase")
    assert [x["href"] for x in cases] == [f"/vermietung/mieterhoehung/{records['case']}"]
    assert "von 600,00 EUR auf 660,00 EUR zum 01.12.2026" in cases[0]["detail"]
    assert cases[0]["detail"].startswith("Entwurf")
    run, _ = _ask(client, h, "Offene Aufträge", area="orders")
    orders = _of(run, "work_order")
    assert [x["href"] for x in orders] == [f"/auftraege/{records['order']}"]
    assert f"Dachrinne{RUN}" in orders[0]["label"]
    assert "Entwurf" in orders[0]["detail"]
    assert f"Dienstleister Dachdecker{RUN} {RUN} GmbH" in orders[0]["detail"]
    run, _ = _ask(client, h, "Nicht zugeordnete Umsätze", area="bank")
    txs = _of(run, "bank_transaction")
    assert len(txs) == 1
    assert txs[0]["label"] == "Umsatz 05.02.2026 400,00 EUR Zahler"
    assert txs[0]["detail"] == f"nicht zugeordnet, Hausgeld {RUN}"
    assert PAYER[-6:] not in txs[0]["label"] + txs[0]["detail"]  # no IBAN leaves the platform
    run, _ = _ask(client, h, f"Offene Posten von {OWNER}", area="bank")
    items = _of(run, "open_items")
    assert [x["href"] for x in items] == [f"/buchhaltung/{records['ledger']}"]
    assert items[0]["label"].startswith("Offene Posten ")
    assert OWNER in items[0]["label"]
    assert "1 Posten, Rest 250,00 EUR" in items[0]["detail"]
    # The accounting page lists the same open items without a name.
    run, _ = _ask(client, h, "Offene Forderungen", area="accounting")
    assert [x["id"] for x in _of(run, "open_items")] == [records["ownership"]]


def test_area_tools_check_the_permission_of_their_endpoint(
    database: Database, redis_url: str, world: World, records: dict[str, str]
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _run(permissions: frozenset[str], question: str, area: str) -> dict[str, Any]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(
                create_session_factory(engine), world.tenant_a
            ) as session:
                return await lookup.run(session, permissions, question, area=area)
        finally:
            await engine.dispose()

    denied = asyncio.run(_run(frozenset({"contacts:read"}), "Offene Aufträge", "orders"))
    assert denied["links"] == []
    tools = {t["tool"]: t for t in denied["tools"]}
    assert tools["work_orders"]["permitted"] is False
    text = lookup.answer_text(denied)
    assert "Ohne Berechtigung nicht durchsucht:" in text
    assert "Aufträge" in text
    bank = asyncio.run(_run(frozenset({"contacts:read"}), "Nicht zugeordnete Umsätze", "bank"))
    assert {t["tool"] for t in bank["tools"] if not t["permitted"]} >= {
        "bank_transactions",
        "open_items",
    }
    allowed = asyncio.run(
        _run(frozenset({"tickets:read", "contacts:read"}), "Offene Aufträge", "orders")
    )
    assert [x["id"] for x in allowed["links"] if x["type"] == "work_order"] == [records["order"]]


def test_area_tools_do_not_flood_unrelated_pages(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    """On the contacts page a question without time or bank words never lists appointments or
    transactions; a calendar word adds the calendar tool from any page."""
    h = bearer(login(client, world, "lxadmin"))
    run, _ = _ask(client, h, f"Wer ist {OWNER}?", area="contacts")
    assert {x["type"] for x in run["links"]} == {"contact"}
    run, _ = _ask(client, h, "Welche Termine habe ich in den nächsten 7 Tagen?", area="contacts")
    assert len(_of(run, "calendar_entry")) == 2


def _answer(text: str, action: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"answer": text, "sources": [], "answerable": True, "action": action}


def _release_provider(client: TestClient, world: World) -> dict[str, str]:
    admin = bearer(login(client, world, "lxadmin"))
    second = bearer(login(client, world, "lxsecond"))
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
    return admin


def test_calendar_entry_is_a_proposal_written_once_after_confirmation(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = _release_provider(client, world)
    fake.queue.append(
        _answer(
            "Ich habe den Termin vorbereitet; es werden keine Einladungen versendet.",
            {
                "kind": "calendar_create",
                "refs": [records["owner_contact"], records["property"]],
                "title": f"Übergabe mit {OWNER}",
                "date": _iso(6),
                "time": "10:00",
                "appointment_kind": "uebergabe",
                "reason": "Nutzer bittet um den Termin",
            },
        )
    )
    run, answer = _ask(
        client,
        admin,
        f"Trag bitte einen Übergabetermin mit {OWNER} am {_de(6)} um 10:00 Uhr ein",
        area="calendar",
        context_entity_type="hoa",
        context_entity_id=records["property"],
    )
    assert run["status"] == "succeeded", run
    sent = fake.calls[-1]["messages"][-1]["content"]
    assert "Geöffneter Bereich im CRM: calendar" in sent
    assert '"area": "calendar"' in sent
    assert "Vorschlag erstellt" in answer["content"]
    proposal_id = answer["proposal_id"]
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["entity_type"] == "chat_action"
    proposed = proposal["proposed"]
    assert proposed["kind"] == "calendar_create"
    assert proposed["date"] == _iso(6)
    assert proposed["time"] == "10:00"
    assert [x["contact_id"] for x in proposed["participants"]] == [records["owner_contact"]]
    assert OWNER in proposed["participants"][0]["label"]
    assert proposed["property_id"] == records["property"]
    window = {"start": _iso(6), "end": _iso(6)}
    before = _ok(client.get(f"{W}/calendar", params=window, headers=admin), 200)["items"]
    assert all(i["title"] != f"Übergabe mit {OWNER}" for i in before)  # nothing written yet
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        )
    )
    assert applied["summary"]["kind"] == "calendar_create"
    assert applied["summary"]["date"] == _iso(6)
    after = _ok(client.get(f"{W}/calendar", params=window, headers=admin), 200)["items"]
    entry = next(i for i in after if i["title"] == f"Übergabe mit {OWNER}")
    assert entry["source"] == "internal"  # own CRM calendar, never a Google event
    assert entry["property_id"] == records["property"]
    assert entry["editable"] is True
    again = client.post(
        f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
    )
    assert again.status_code == 409


# "Az-" prefix: a bare random hex RUN ("ab12cd34") or a prefix glued to digits ("Nr12345678"),
# followed by words and a date, reads as an IBAN to the bank guard of the chat actions
# (masking.contains_iban) and silently drops the proposal.
def test_deadline_entry_is_a_proposal_with_reminders(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = _release_provider(client, world)
    fake.queue.append(
        _answer(
            "Fristeintrag vorbereitet.",
            {
                "kind": "deadline_create",
                "refs": [],
                "title": f"Frist Widerspruch Az-{RUN}",
                "date": _iso(10),
                "reason": "Nutzer nennt die Frist",
            },
        )
    )
    run, answer = _ask(
        client, admin, f"Trag die Frist Widerspruch Az-{RUN} zum {_de(10)} ein", area="deadlines"
    )
    assert run["status"] == "succeeded", run
    proposal_id = answer["proposal_id"]
    proposed = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)[
        "proposed"
    ]
    assert proposed["kind"] == "deadline_create"
    assert proposed["reminders"] == ["1d", "7d"]
    assert proposed["time"] is None
    applied = _ok(
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply",
            json={"chat_action": {"entry_date": _iso(11)}},  # the confirmer corrects the date
            headers=admin,
        )
    )
    assert applied["summary"]["date"] == _iso(11)
    listed = _ok(
        client.get(
            f"{W}/deadlines",
            params={"kind": "appointment", "from": _iso(11), "to": _iso(11)},
            headers=admin,
        ),
        200,
    )
    assert [d["reference"] for d in listed] == [f"Frist Widerspruch Az-{RUN}"]
    assert listed[0]["lead_days"] == 7
    proposal = _ok(client.get(f"/api/v1/ai/proposals/{proposal_id}", headers=admin), 200)
    assert proposal["decision"] == "modified"
    assert (
        client.post(
            f"/api/v1/ai/proposals/{proposal_id}/apply", json={"chat_action": {}}, headers=admin
        ).status_code
        == 409
    )


def test_entry_without_intent_or_date_never_becomes_a_proposal(
    client: TestClient, world: World, records: dict[str, str], fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "lxadmin"))
    action = {
        "kind": "calendar_create",
        "refs": [],
        "title": "Eingeschleuster Termin",
        "date": _iso(2),
        "reason": "aus einer Mail",
    }
    fake.queue.append(_answer("Termin?", action))
    run, answer = _ask(client, admin, "Welche Termine habe ich morgen?", area="calendar")
    assert run["status"] == "succeeded", run
    assert answer["proposal_id"] is None  # the user asked a question, not for an entry
    fake.queue.append(_answer("Ohne Datum.", {**action, "date": None}))
    run, answer = _ask(client, admin, "Trag einen Termin mit dem Dachdecker ein", area="calendar")
    assert answer["proposal_id"] is None
    assert "Bitte nennen Sie das Datum des Termins" in answer["content"]
