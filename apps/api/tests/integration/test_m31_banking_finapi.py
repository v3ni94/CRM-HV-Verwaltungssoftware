"""M31 acceptance against a fake finAPI (no real bank, no demo data): connect via web form,
server-side verification, controlled account mapping, explicit fetch runs (never scheduled),
idempotent import of booked transactions only, partial results, re-connect via IBAN mapping,
tenant isolation and a callback that is only a hint."""

import asyncio
import itertools
import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from mhvp.banking import finapi
from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    bearer,
    login,
)
from tests.integration.test_m2_platform import (
    _settings as base_settings,
)

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
IBAN_1 = "DE02120300000000202051"
IBAN_2 = "DE89370400440532013000"


def _settings(database: Database, redis_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "banking_finapi_base_url": "https://finapi.test",
        "banking_finapi_client_id": SecretStr("client"),
        "banking_finapi_client_secret": SecretStr("secret"),
        "banking_finapi_callback_base_url": "http://testserver",
        "banking_inline": True,
    }
    values.update(overrides)
    return base_settings(database, redis_url, **values)


class FakeFinApi:
    """Stateful fake of the documented finAPI endpoints used by the adapter."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.webforms: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.accounts: dict[str, list[dict[str, Any]]] = {}
        self.transactions: dict[str, list[dict[str, Any]]] = {}
        self.fail_account_ids: set[str] = set()
        self.next_task_status = "COMPLETED"
        self.deleted_connections: list[str] = []
        self.calls: list[str] = []
        self._seq = 0

    def seq(self) -> int:
        self._seq += 1
        return self._seq

    @property
    def last_webform_id(self) -> str:
        return f"wf{self._seq}"

    def complete_webform(self, webform_id: str, bank_connection_id: str | None = None) -> None:
        form = self.webforms[webform_id]
        form["status"] = "COMPLETED"
        if bank_connection_id is not None:
            form["payload"] = {"bankConnectionId": int(bank_connection_id)}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if path == "/oauth/token":
            return httpx.Response(200, json={"access_token": f"tok{self.seq()}"})
        if path == "/api/v1/users":
            body = json.loads(request.content)
            self.users[str(body["id"])] = body
            return httpx.Response(201, json={"id": body["id"]})
        if path in ("/api/webForms/bankConnectionImport", "/api/webForms/bankConnectionUpdate"):
            wid = f"wf{self.seq()}"
            self.webforms[wid] = {
                "id": wid,
                "url": f"https://webform.test/{wid}",
                "status": "NOT_YET_OPENED",
                "payload": {},
            }
            return httpx.Response(201, json=self.webforms[wid])
        if path.startswith("/api/webForms/"):
            form = self.webforms.get(path.rsplit("/", 1)[-1])
            if form is None:
                return httpx.Response(404, json={"errors": [{"code": "NOT_FOUND"}]})
            return httpx.Response(200, json=form)
        if path == "/api/tasks/backgroundUpdate":
            tid = f"task{self.seq()}"
            self.tasks[tid] = {"id": tid, "status": self.next_task_status, "errors": []}
            return httpx.Response(200, json=self.tasks[tid])
        if path.startswith("/api/tasks/"):
            return httpx.Response(200, json=self.tasks[path.rsplit("/", 1)[-1]])
        if path == "/api/v1/accounts":
            key = str(request.url.params.get("bankConnectionIds"))
            return httpx.Response(200, json={"accounts": self.accounts.get(key, [])})
        if path == "/api/v1/transactions":
            account_id = str(request.url.params.get("accountIds"))
            if account_id in self.fail_account_ids:
                return httpx.Response(500, json={"errors": [{"code": "BANK_UNAVAILABLE"}]})
            rows = self.transactions.get(account_id, [])
            min_date = request.url.params.get("minBankBookingDate")
            if min_date:
                rows = [r for r in rows if str(r["bankBookingDate"]) >= str(min_date)]
            return httpx.Response(200, json={"transactions": rows, "paging": {"pageCount": 1}})
        if request.method == "DELETE" and path.startswith("/api/v1/bankConnections/"):
            self.deleted_connections.append(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"errors": [{"code": "UNKNOWN_PATH"}]})


def _account(account_id: str, iban: str, balance: str = "1000.00") -> dict[str, Any]:
    return {
        "id": account_id,
        "iban": iban,
        "accountHolderName": "Hausverwaltung Testkunde",
        "accountName": f"Konto {account_id}",
        "accountType": "CHECKING",
        "currency": "EUR",
        "balance": balance,
        "availableFunds": balance,
        "lastSuccessfulUpdate": "2026-09-25T08:00:00Z",
    }


def _tx(tx_id: str, amount: str, day: str = "2026-09-20", booked: bool = True) -> dict[str, Any]:
    return {
        "id": tx_id,
        "bankBookingDate": day,
        "valueDate": day,
        "amount": amount,
        "currency": "EUR",
        "counterpart": {"name": "Mieter Muster", "iban": "DE75512108001245126199"},
        "purpose": f"Miete {tx_id}",
        "isBooked": booked,
    }


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"fa-{RUN}", name=f"FinA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"fb-{RUN}", name=f"FinB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        members = [
            ("m31admin", a, "tenant_admin"),
            ("m31reader", a, "read_only"),
            ("m31other", b, "tenant_admin"),
        ]
        for name, tenant_id, role in members:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake() -> FakeFinApi:
    return FakeFinApi()


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakeFinApi, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    real = finapi.FinApiClient

    def patched(
        settings: Settings,
        credentials: dict[str, str] | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> finapi.FinApiClient:
        return real(settings, credentials, transport=fake.transport())

    monkeypatch.setattr(finapi, "FinApiClient", patched)
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


_NUMBERS = itertools.count(101)


def _property_accounts(client: TestClient, h: dict[str, str]) -> tuple[str, str, str]:
    number = f"{next(_NUMBERS):03d}"  # Objektnummer NNN, je Mandant eindeutig
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Objekt {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    internal = []
    for iban, kind in [(IBAN_1, "hoa"), (IBAN_2, "reserve")]:
        internal.append(
            _ok(
                client.post(
                    f"/api/v1/properties/{prop['id']}/bank-accounts",
                    json={
                        "legal_entity_id": entity,
                        "kind": kind,
                        "iban": iban,
                        "holder": "GdWE Testobjekt",
                        "valid_from": "2020-01-01",
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
    return str(prop["id"]), str(internal[0]), str(internal[1])


def _connect(client: TestClient, h: dict[str, str], fake: FakeFinApi) -> tuple[str, str]:
    """Connect + web form + server-side confirm; returns (connection_id, bank_connection_id)."""
    created = _ok(
        client.post(
            f"{B}/finapi/connections",
            json={
                "bank_name": "Testbank",
                "authorization_context": "Kontovollmacht des Verwalters laut Vertrag vom "
                "01.02.2026",
            },
            headers=h,
        ),
        201,
    )
    assert created["webform_url"].startswith("https://webform.test/")
    pending = _ok(
        client.post(f"{B}/finapi/connections/{created['connection_id']}/confirm", headers=h)
    )
    assert pending["status"] == "pending"  # Redirect allein ist kein Nachweis
    bank_connection_id = str(700 + fake.seq())
    fake.accounts[bank_connection_id] = [
        _account("acc-1", IBAN_1),
        _account("acc-2", IBAN_2),
    ]
    fake.complete_webform(created["webform_url"].rsplit("/", 1)[-1], bank_connection_id)
    done = _ok(client.post(f"{B}/finapi/connections/{created['connection_id']}/confirm", headers=h))
    assert done == {"status": "succeeded", "accounts": 2}
    return str(created["connection_id"]), bank_connection_id


def _assign(
    client: TestClient,
    h: dict[str, str],
    connection_id: str,
    mapping: dict[str, str | None],
) -> list[dict[str, Any]]:
    links = _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=h))
    by_provider = {link["provider_account_id"]: link for link in links}
    body = {
        "accounts": [
            {
                "link_id": by_provider[provider_id]["id"],
                "selected": True,
                "property_bank_account_id": internal_id,
            }
            for provider_id, internal_id in mapping.items()
        ]
    }
    return list(
        _ok(client.put(f"{B}/finapi/connections/{connection_id}/accounts", json=body, headers=h))
    )


def test_unconfigured_shows_409_and_no_demo_data(
    database: Database, redis_url: str, world: World
) -> None:
    settings = _settings(database, redis_url, banking_finapi_base_url=None)
    with TestClient(create_app(settings)) as client:
        h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
        assert _ok(client.get(f"{B}/finapi/status", headers=h)) == {"configured": False}
        refused = client.post(
            f"{B}/finapi/connections",
            json={"bank_name": "Bank", "authorization_context": "Vollmacht liegt vor."},
            headers=h,
        )
        assert refused.status_code == 409
        assert "nicht eingerichtet" in refused.text
        assert _ok(client.get(f"{B}/finapi/runs", headers=h)) == []


def test_connect_confirm_assign_and_persistence(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, internal_2 = _property_accounts(client, h)
    connection_id, _ = _connect(client, h, fake)
    # Identität wurde ohne automatische Abrufe angelegt.
    assert all(u["isAutoUpdateEnabled"] is False for u in fake.users.values())
    links = _assign(client, h, connection_id, {"acc-1": internal_1, "acc-2": internal_2})
    assert {link["property_bank_account_id"] for link in links} == {internal_1, internal_2}
    # Persistenz: neue Abfrage liefert Zuordnung, Salden-Schnappschuss und IBAN nur als Suffix.
    stored = _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=h))
    assert all(link["is_selected"] for link in stored)
    assert {link["iban_suffix"] for link in stored} == {IBAN_1[-4:], IBAN_2[-4:]}
    assert all(link["balance"] == "1000.00" for link in stored)
    assert all(link["balance_bank_reference_at"] is not None for link in stored)


def test_reader_may_look_but_not_connect(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m31reader", tenant_id=world.tenant_a))
    assert _ok(client.get(f"{B}/finapi/status", headers=h)) == {"configured": True}
    refused = client.post(
        f"{B}/finapi/connections",
        json={"bank_name": "Bank", "authorization_context": "Vollmacht liegt vor."},
        headers=h,
    )
    assert refused.status_code == 403


def test_fetch_imports_booked_only_and_stays_idempotent(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, _ = _property_accounts(client, h)
    connection_id, _ = _connect(client, h, fake)
    # acc-2 ist ausgewaehlt, aber ohne internes Konto: wird protokolliert und uebersprungen.
    _assign(client, h, connection_id, {"acc-1": internal_1, "acc-2": None})
    fake.transactions["acc-1"] = [
        _tx("t-1", "700.00"),
        _tx("t-2", "700.00"),  # zwei echte Zahlungen über 700,00: bleiben zwei
        _tx("t-3", "-120.50"),
        _tx("t-4", "80.00", booked=False),  # Vormerkung: wird nie endgültig übernommen
    ]
    run = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert run["fetch_status"] == "succeeded"
    assert run["counts"]["new"] == 3
    assert run["counts"]["pending_skipped"] == 1
    assert "POST /api/tasks/backgroundUpdate" in fake.calls  # echter Update-Aufruf je Klick
    # Der nicht zugeordnete Kontoverweis wird protokolliert und gelangt nicht in die Buchhaltung.
    skipped = [r for r in run["account_results"].values() if r["status"] == "skipped"]
    assert len(skipped) == 1
    assert "kein internes Konto" in skipped[0]["reason"]
    # Wiederholtes Einlesen erzeugt keine Duplikate.
    again = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert again["id"] != run["id"]
    assert again["counts"]["new"] == 0
    assert again["counts"]["duplicates"] == 3
    txs = _ok(client.get(f"{B}/transactions", params={"bank_account_id": internal_1}, headers=h))
    assert len(txs) == 3
    assert sorted(t["amount"] for t in txs) == ["-120.50", "700.00", "700.00"]
    # Kein Buchungssatz entsteht: alle Umsätze bleiben im Status "new".
    assert all(t["status"] == "new" for t in txs)
    # Zeitstempel getrennt gepflegt.
    link = _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=h))[0]
    assert link["last_attempt_at"] is not None
    assert link["last_bank_success_at"] is not None
    assert link["last_imported_at"] is not None


def test_webform_required_parks_run_and_resume_continues_same_run(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, _ = _property_accounts(client, h)
    connection_id, _ = _connect(client, h, fake)
    _assign(client, h, connection_id, {"acc-1": internal_1})
    fake.transactions["acc-1"] = [_tx("t-10", "10.00")]
    fake.next_task_status = "WEB_FORM_REQUIRED"
    run = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert run["fetch_status"] == "awaiting_authorization"
    assert run["webform_url"] is not None
    # Doppelklick oder zweiter Tab: derselbe aktive Lauf, kein zweiter Provider-Vorgang.
    same = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert same["id"] == run["id"]
    # Vor der Freigabe passiert nichts.
    parked = _ok(client.post(f"{B}/finapi/runs/{run['id']}/resume", headers=h))
    assert parked["fetch_status"] == "awaiting_authorization"
    fake.complete_webform(run["webform_url"].rsplit("/", 1)[-1])
    resumed = _ok(client.post(f"{B}/finapi/runs/{run['id']}/resume", headers=h))
    assert resumed["id"] == run["id"]  # derselbe Lauf wird fortgesetzt
    assert resumed["fetch_status"] == "succeeded"
    assert resumed["counts"]["new"] == 1


def test_aborted_or_expired_webform_never_destroys_links(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, _ = _property_accounts(client, h)
    connection_id, _ = _connect(client, h, fake)
    _assign(client, h, connection_id, {"acc-1": internal_1})
    fake.next_task_status = "WEB_FORM_REQUIRED"
    run = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    fake.webforms[run["webform_url"].rsplit("/", 1)[-1]]["status"] = "ABORTED"
    canceled = _ok(client.post(f"{B}/finapi/runs/{run['id']}/resume", headers=h))
    assert canceled["fetch_status"] == "canceled"
    links = _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=h))
    assert links[0]["property_bank_account_id"] == internal_1  # Verknüpfung bleibt bestehen


def test_partial_when_one_account_fails(client: TestClient, world: World, fake: FakeFinApi) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, internal_2 = _property_accounts(client, h)
    connection_id, _ = _connect(client, h, fake)
    _assign(client, h, connection_id, {"acc-1": internal_1, "acc-2": internal_2})
    fake.transactions["acc-1"] = [_tx("t-20", "55.00")]
    fake.fail_account_ids.add("acc-2")
    run = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert run["fetch_status"] == "partial"  # READY allein ist kein Erfolg
    statuses = sorted(r["status"] for r in run["account_results"].values())
    assert statuses == ["failed", "ok"]
    assert run["counts"]["new"] == 1  # das fehlerhafte Konto blockiert das andere nicht


def test_reconnect_with_new_provider_ids_keeps_assignment_via_iban(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, _ = _property_accounts(client, h)
    connection_id, bank_connection_id = _connect(client, h, fake)
    before = _assign(client, h, connection_id, {"acc-1": internal_1})
    link_id = next(x["id"] for x in before if x["provider_account_id"] == "acc-1")
    # Bank liefert nach Wiederanbindung neue externe Konto-IDs für dieselben IBANs.
    fake.accounts[bank_connection_id] = [
        _account("neu-1", IBAN_1),
        _account("neu-2", IBAN_2),
    ]
    fake.transactions["neu-1"] = [_tx("t-30", "42.00")]
    run = _ok(
        client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    )[0]
    assert run["counts"]["new"] == 1
    links = _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=h))
    moved = next(x for x in links if x["id"] == link_id)
    # Kontrollierte Wiederanbindung: gleicher Datensatz, gleiche Zuordnung, neue Provider-ID.
    assert moved["provider_account_id"] == "neu-1"
    assert moved["property_bank_account_id"] == internal_1
    assert len(links) == 2  # keine neuen internen Konten, keine verdoppelten Verweise


def test_foreign_tenant_sees_nothing_and_callback_needs_valid_token(
    client: TestClient, world: World, fake: FakeFinApi, migrator_engine: Engine
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    connection_id, _ = _connect(client, h, fake)
    runs = _ok(client.get(f"{B}/finapi/runs", headers=h))
    run_id = runs[0]["id"]
    other = bearer(login(client, world, "m31other", tenant_id=world.tenant_b))
    assert (
        client.post(f"{B}/finapi/connections/{connection_id}/confirm", headers=other).status_code
        == 404
    )
    assert client.post(f"{B}/finapi/runs/{run_id}/resume", headers=other).status_code == 404
    assert _ok(client.get(f"{B}/finapi/connections/{connection_id}/accounts", headers=other)) == []
    # Manipulierter Callback-Token wird ignoriert und ändert nichts.
    bad = _ok(
        client.post(
            f"{B}/finapi/callback/{world.tenant_a}/{run_id}",
            params={"token": "x" * 32},
        )
    )
    assert bad == {"status": "ignored"}
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_a)},
        )
        token = conn.execute(
            text("SELECT provider_refs->>'callback_token' FROM bank_connection WHERE id = :id"),
            {"id": connection_id},
        ).scalar_one()
    good = _ok(
        client.post(f"{B}/finapi/callback/{world.tenant_a}/{run_id}", params={"token": token})
    )
    assert good == {"status": "ok"}


def test_disconnect_blocks_fetches_and_keeps_history(
    client: TestClient, world: World, fake: FakeFinApi
) -> None:
    h = bearer(login(client, world, "m31admin", tenant_id=world.tenant_a))
    _, internal_1, _ = _property_accounts(client, h)
    connection_id, bank_connection_id = _connect(client, h, fake)
    _assign(client, h, connection_id, {"acc-1": internal_1})
    fake.transactions["acc-1"] = [_tx("t-40", "99.99")]
    _ok(client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h))
    result = _ok(client.delete(f"{B}/finapi/connections/{connection_id}", headers=h))
    assert result["status"] == "disabled"
    assert result["external_error"] is None
    assert fake.deleted_connections == [bank_connection_id]
    refused = client.post(f"{B}/finapi/fetch", json={"connection_ids": [connection_id]}, headers=h)
    assert refused.status_code == 409  # Trennen stoppt weitere Abrufe
    # Historie bleibt: Umsätze und Abrufprotokolle sind weiterhin lesbar.
    txs = _ok(client.get(f"{B}/transactions", params={"bank_account_id": internal_1}, headers=h))
    assert [t["amount"] for t in txs] == ["99.99"]
    runs = _ok(client.get(f"{B}/finapi/runs", params={"connection_id": connection_id}, headers=h))
    assert runs
