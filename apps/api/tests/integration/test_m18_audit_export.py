"""M18, A26, case D55: machine readable audit export per legal entity and period (7.7).

Checks the CSV contents against known postings, the SHA-256 of the ZIP and of every file in
the index, the reversal relation, the packed original receipt with its hash, the reference
only mode above the receipt size limit, the worker path, permissions and tenant separation.
"""

import asyncio
import concurrent.futures
import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas

from mhvp.accounting import audit_export_routers
from mhvp.accounting import tasks as accounting_tasks
from mhvp.accounting.audit_export import BOM
from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings
from tests.integration.test_m18_tax_advisor_scope import assign_ledger_scope

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-audit-export"


def _settings(database: Database, redis_url: str) -> Settings:
    return _base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ax-{RUN}", name=f"Prüfexport {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ay-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("axadmin", a, "tenant_admin"),
            ("axacc", a, "accountant_no_banking"),
            ("axtax", a, "tax_advisor"),
            ("axstandard", a, "standard"),
            ("axcaretaker", a, "caretaker"),
            ("ayadmin", b, "tenant_admin"),
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
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


class Worker:
    """No broker in the test run: the router's ``dispatch_audit_export`` is replaced by
    ``delay``, which only records the call (patching the Celery task's ``.delay`` is not
    deterministic: the ``shared_task`` proxy resolves per thread and current app); ``run``
    executes the task body in a thread with the test settings (own event loop, like a worker
    process)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dispatched: list[tuple[str, str]] = []

    def delay(self, run_id: str, tenant_id: str) -> None:
        self.dispatched.append((run_id, tenant_id))

    def run(self, run_id: str, tenant_id: str) -> str:
        import uuid

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run,
                accounting_tasks.run_audit_export(
                    self.settings, uuid.UUID(run_id), uuid.UUID(tenant_id)
                ),
            ).result()


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch, database: Database, redis_url: str) -> Worker:
    w = Worker(_settings(database, redis_url))
    monkeypatch.setattr(audit_export_routers, "dispatch_audit_export", w.delay)
    return w


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 720, text)
    canvas.save()
    return buffer.getvalue()


def _table(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = zf.read(name).decode("utf-8")
    assert text.startswith(BOM), name
    assert "\r\n" in text
    return list(csv.DictReader(io.StringIO(text.removeprefix(BOM)), delimiter=";"))


def _setup_ledger(
    client: TestClient, h: dict[str, str], acc_user: dict[str, str], number: str = "782"
) -> dict[str, Any]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Prüfhaus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Eva", "last_name": f"Pruef{RUN}"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        client.post(
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
    # One master data change so that the audit log holds field history for the export.
    _ok(
        client.put(
            f"/api/v1/properties/{prop['id']}",
            json={"number": number, "name": f"Prüfhaus {number} Nord", "management_type": "hoa"},
            headers=h,
        )
    )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    debtor = next(a["id"] for a in acc.values() if a["category"] == "debtor")

    def book(body: dict[str, Any]) -> dict[str, Any]:
        draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
        if body["kind"] == "opening_balance":
            _ok(
                client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=acc_user)
            )
        return _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]

    opening = book(
        {
            "kind": "opening_balance",
            "booking_date": "2026-01-01",
            "text": "Anfangsbestand",
            "lines": [
                {"account_id": acc["001200"]["id"], "debit": "5000.00"},
                {"account_id": acc["001201"]["id"], "debit": "20000.00"},
                {"account_id": acc["009000"]["id"], "credit": "25000.00"},
            ],
        }
    )
    receivable = book(
        {
            "kind": "receivable",
            "booking_date": "2026-09-01",
            "due_date": "2026-09-03",
            "text": "Hausgeld",
            "lines": [
                {"account_id": debtor, "debit": "400.00"},
                {"account_id": acc["060100"]["id"], "credit": "400.00"},
            ],
        }
    )
    oi = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-09-30"}, headers=h)
    )[0]["id"]
    payment = book(
        {
            "kind": "debtor_payment",
            "booking_date": "2026-09-05",
            "text": "Zahlung",
            "settlements": [{"open_item_id": oi, "amount": "150.00"}],
            "lines": [
                {"account_id": acc["001200"]["id"], "debit": "150.00"},
                {"account_id": debtor, "credit": "150.00"},
            ],
        }
    )
    pdf = _pdf(f"Beleg {RUN}")
    document = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (f"rechnung-{RUN}.pdf", pdf, "application/pdf")},
            headers=h,
        ),
        201,
    )
    with_receipt = book(
        {
            "kind": "custom",
            "booking_date": "2026-09-10",
            "text": "=Gartenpflege",  # formula prefix must be neutralised in the CSV
            "reference": "RE-2026-0815",
            "document_id": document["id"],
            "lines": [
                {
                    "account_id": acc["040100"]["id"] if "040100" in acc else acc["060100"]["id"],
                    "debit": "119.00",
                },
                {"account_id": acc["001200"]["id"], "credit": "119.00"},
            ],
        }
    )
    reversal = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{with_receipt['id']}/reverse",
            json={"reason": "Falsches Objekt", "booking_date": "2026-09-12"},
            headers=h,
        ),
        201,
    )
    return {
        "property": prop,
        "ledger": ledger,
        "opening": opening,
        "receivable": receivable,
        "payment": payment,
        "with_receipt": with_receipt,
        "reversal": reversal,
        "document": document,
        "pdf": pdf,
        "open_item": oi,
    }


def test_d55_audit_export_zip_contents_hashes_and_reversal(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "axadmin"))
    acc_user = bearer(login(client, world, "axacc"))
    w = _setup_ledger(client, h, acc_user)
    ledger = w["ledger"]

    # A37: the tax advisor only sees assigned legal entities (test_m18_tax_advisor_scope).
    assign_ledger_scope(client, h, world.users["axtax"], ledger)
    tax = bearer(login(client, world, "axtax"))
    run = _ok(
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=tax,
        ),
        201,
    )
    assert run["status"] == "done"
    assert run["format"] == "audit_zip"
    assert run["document_id"]
    assert run["created_by"] == str(world.users["axtax"])
    assert run["params"]["receipts"] == {
        "max_bytes": 100 * 1024 * 1024,
        "total_bytes": len(w["pdf"]),
        "included": 1,
        "listed_only": 0,
    }

    status = _ok(client.get(f"{A}/audit-exports/{run['id']}", headers=tax))
    assert status["sha256"] == run["sha256"]
    listed = _ok(client.get(f"{A}/audit-exports", params={"ledger_id": ledger}, headers=tax))
    assert [r["id"] for r in listed] == [run["id"]]

    download = client.get(f"{A}/audit-exports/{run['id']}/download", headers=tax)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("application/zip")
    data = download.content
    assert hashlib.sha256(data).hexdigest() == run["sha256"]

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        for expected in (
            "konten.csv",
            "buchungen.csv",
            "buchungszeilen.csv",
            "storno_beziehungen.csv",
            "eroeffnungsbestaende.csv",
            "offene_posten.csv",
            "op_ausgleich.csv",
            "freigaben.csv",
            "ereignisse.csv",
            "stammdaten.csv",
            "stammdatenhistorie.csv",
            "verteilungsschluessel.csv",
            "verteilungsschluessel_werte.csv",
            "belege.csv",
            "export.json",
            "index.csv",
            "index.json",
        ):
            assert expected in names, expected

        # Index: every file except index.json is listed with row count, columns and SHA-256.
        index = json.loads(zf.read("index.json"))["files"]
        by_file = {e["file"]: e for e in index}
        assert set(by_file) == set(names) - {"index.json"}
        for name, entry in by_file.items():
            assert hashlib.sha256(zf.read(name)).hexdigest() == entry["sha256"], name
        assert by_file["buchungen.csv"]["columns"][:4] == [
            "Buchung-ID",
            "Jahr",
            "Nummer",
            "Buchungstag",
        ]
        index_csv = _table(zf, "index.csv")
        assert {r["Datei"]: r["SHA-256"] for r in index_csv} == {
            n: by_file[n]["sha256"] for n in by_file if n != "index.csv"
        }

        meta = json.loads(zf.read("export.json"))
        assert meta["export_run_id"] == run["id"]
        assert meta["ledger"]["id"] == ledger
        assert meta["period_from"] == "2026-01-01"
        assert meta["period_to"] == "2026-12-31"
        assert meta["legal_entity"]["kind"] == "hoa"
        assert meta["property"]["number"] == "782"
        assert meta["counts"] == {
            "accounts": len(_table(zf, "konten.csv")),
            "entries": 5,
            "lines": 11,
            "settlements": 1,
        }
        assert "Datenträgerüberlassungsformat" in meta["scope"]

        # Entries: the five posted entries with their known numbers, kinds and relations.
        entries = _table(zf, "buchungen.csv")
        by_id = {r["Buchung-ID"]: r for r in entries}
        assert len(entries) == 5
        assert by_id[w["opening"]["id"]]["Art"] == "opening_balance"
        assert by_id[w["opening"]["id"]]["Freigegeben von"] == str(world.users["axacc"])
        assert by_id[w["with_receipt"]["id"]]["Text"] == "'=Gartenpflege"
        assert by_id[w["with_receipt"]["id"]]["Belegnummer"] == "RE-2026-0815"
        assert by_id[w["with_receipt"]["id"]]["Beleg-Dokument-ID"] == w["document"]["id"]
        assert by_id[w["with_receipt"]["id"]]["Storniert durch"] == w["reversal"]["id"]
        assert by_id[w["reversal"]["id"]]["Storno von"] == w["with_receipt"]["id"]
        assert by_id[w["reversal"]["id"]]["Stornogrund"] == "Falsches Objekt"
        assert [r["Nummer"] for r in entries] == ["1", "2", "3", "4", "5"]

        lines = _table(zf, "buchungszeilen.csv")
        assert len(lines) == 11
        payment_lines = [r for r in lines if r["Buchung-ID"] == w["payment"]["id"]]
        assert [(r["Kontonummer"], r["Soll"], r["Haben"]) for r in payment_lines] == [
            ("001200", "150,00", "0,00"),
            (payment_lines[1]["Kontonummer"], "0,00", "150,00"),
        ]
        reversal_lines = [r for r in lines if r["Buchung-ID"] == w["reversal"]["id"]]
        assert sorted((r["Soll"], r["Haben"]) for r in reversal_lines) == [
            ("0,00", "119,00"),
            ("119,00", "0,00"),
        ]

        storno = _table(zf, "storno_beziehungen.csv")
        assert len(storno) == 1
        assert storno[0]["Original-ID"] == w["with_receipt"]["id"]
        assert storno[0]["Storno-ID"] == w["reversal"]["id"]
        assert storno[0]["Original-Nummer"] == "4"
        assert storno[0]["Storno-Nummer"] == "5"
        assert storno[0]["Stornogrund"] == "Falsches Objekt"

        opening = _table(zf, "eroeffnungsbestaende.csv")
        assert [(r["Kontonummer"], r["Soll"], r["Haben"]) for r in opening] == [
            ("001200", "5000,00", "0,00"),
            ("001201", "20000,00", "0,00"),
            ("009000", "0,00", "25000,00"),
        ]
        assert {r["Freigegeben von"] for r in opening} == {str(world.users["axacc"])}

        settlements = _table(zf, "op_ausgleich.csv")
        settled = [r for r in settlements if r["Ausgleichende Buchung-ID"] == w["payment"]["id"]]
        assert [(r["OP-ID"], r["Betrag"], r["Datum"]) for r in settled] == [
            (w["open_item"], "150,00", "2026-09-05")
        ]
        open_items = _table(zf, "offene_posten.csv")
        assert [
            (r["Buchung-ID"], r["Betrag"], r["Art"])
            for r in open_items
            if r["Buchung-ID"] == w["receivable"]["id"]
        ] == [(w["receivable"]["id"], "400,00", "receivable")]

        approvals = _table(zf, "freigaben.csv")
        assert [(r["Objektart"], r["Objekt-ID"], r["Schritt"], r["Person"]) for r in approvals] == [
            (
                "journal_entry",
                w["opening"]["id"],
                "opening_balance_approval",
                str(world.users["axacc"]),
            )
        ]

        events = _table(zf, "ereignisse.csv")
        assert w["opening"]["id"] in {r["Objekt-ID"] for r in events}
        assert any(r["Typ"].startswith("journal_entry") for r in events)

        master = _table(zf, "stammdaten.csv")
        kinds = {r["Objektart"] for r in master}
        assert kinds >= {"legal_entity", "property", "unit", "contract", "contact"}
        assert any(r["Objektart"] == "property" and r["Nummer"] == "782" for r in master)
        assert any(
            r["Objektart"] == "contact" and f"Pruef{RUN}" in r["Bezeichnung"] for r in master
        )
        history = _table(zf, "stammdatenhistorie.csv")
        changed = [r for r in history if r["Objektart"] == "property"]
        assert changed
        assert changed[0]["Objekt-ID"] == w["property"]["id"]
        assert "Nord" in changed[0]["Änderungen"]

        keys = _table(zf, "verteilungsschluessel.csv")
        assert keys, "the default property templates create allocation keys"

        # Receipts: the PDF is packed and its hash matches the document index.
        receipts = _table(zf, "belege.csv")
        assert len(receipts) == 1
        r = receipts[0]
        assert r["Dokument-ID"] == w["document"]["id"]
        assert r["Im ZIP enthalten"] == "ja"
        assert r["SHA-256"] == hashlib.sha256(w["pdf"]).hexdigest()
        assert set(r["Buchung-IDs"].split(",")) == {w["with_receipt"]["id"]}
        assert zf.read(r["Pfad im ZIP"]) == w["pdf"]
        assert by_file[r["Pfad im ZIP"]]["sha256"] == r["SHA-256"]

    # Above the size limit the receipts are listed with hash only (reference list mode).
    small = _ok(
        client.post(
            f"{A}/audit-exports",
            json={
                "ledger_id": ledger,
                "period_from": "2026-09-01",
                "period_to": "2026-09-30",
                "receipts_max_bytes": 1,
            },
            headers=tax,
        ),
        201,
    )
    assert small["params"]["receipts"]["included"] == 0
    assert small["params"]["receipts"]["listed_only"] == 1
    with zipfile.ZipFile(
        io.BytesIO(client.get(f"{A}/audit-exports/{small['id']}/download", headers=tax).content)
    ) as zf:
        assert not [n for n in zf.namelist() if n.startswith("belege/")]
        receipts = _table(zf, "belege.csv")
        assert receipts[0]["Im ZIP enthalten"] == "nein"
        assert receipts[0]["SHA-256"] == hashlib.sha256(w["pdf"]).hexdigest()
        assert "Grenze" in receipts[0]["Hinweis"]
        entries = _table(zf, "buchungen.csv")
        assert len(entries) == 4  # the opening balance of January is outside September
        assert _table(zf, "eroeffnungsbestaende.csv")  # but opening balances up to the end stay

    # The export itself is a document of the legal entity.
    document = _ok(client.get(f"/api/v1/documents/{run['document_id']}", headers=h))
    assert document["mime_type"] == "application/zip"
    assert document["sha256"] == run["sha256"]

    # Permissions: accounting:read lists and reads status, accounting:export creates and
    # downloads; a role without accounting rights sees nothing.
    standard = bearer(login(client, world, "axstandard"))
    assert client.get(f"{A}/audit-exports", headers=standard).status_code == 200
    assert client.get(f"{A}/audit-exports/{run['id']}", headers=standard).status_code == 200
    assert (
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=standard,
        ).status_code
        == 403
    )
    assert (
        client.get(f"{A}/audit-exports/{run['id']}/download", headers=standard).status_code == 403
    )
    caretaker = bearer(login(client, world, "axcaretaker"))
    assert client.get(f"{A}/audit-exports", headers=caretaker).status_code == 403

    # Tenant separation: the other tenant neither sees the run nor can export the ledger.
    other = bearer(login(client, world, "ayadmin", tenant_id=world.tenant_b))
    assert client.get(f"{A}/audit-exports/{run['id']}", headers=other).status_code == 404
    assert client.get(f"{A}/audit-exports/{run['id']}/download", headers=other).status_code == 404
    assert _ok(client.get(f"{A}/audit-exports", headers=other)) == []
    assert (
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=other,
        ).status_code
        == 404
    )

    # Validation: period order.
    assert (
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger, "period_from": "2026-12-31", "period_to": "2026-01-01"},
            headers=tax,
        ).status_code
        == 422
    )


def test_d55_audit_export_on_worker(client: TestClient, world: World, worker: Worker) -> None:
    h = bearer(login(client, world, "axadmin"))
    acc_user = bearer(login(client, world, "axacc"))
    w = _setup_ledger(client, h, acc_user, number="783")
    ledger = w["ledger"]
    run = _ok(
        client.post(
            f"{A}/audit-exports",
            json={
                "ledger_id": ledger,
                "period_from": "2026-01-01",
                "period_to": "2026-12-31",
                "run_in_background": True,
            },
            headers=h,
        ),
        201,
    )
    assert run["status"] == "queued"
    assert run["sha256"] is None
    assert run["document_id"] is None
    assert worker.dispatched == [(run["id"], str(world.tenant_a))]
    assert client.get(f"{A}/audit-exports/{run['id']}/download", headers=h).status_code == 409
    assert _ok(client.get(f"{A}/audit-exports/{run['id']}", headers=h))["status"] == "queued"

    assert worker.run(run["id"], str(world.tenant_a)) == "done"
    assert worker.run(run["id"], str(world.tenant_a)) == "skipped"  # idempotent re-delivery
    done = _ok(client.get(f"{A}/audit-exports/{run['id']}", headers=h))
    assert done["status"] == "done", done
    assert done["finished_at"]
    assert done["document_id"]
    assert done["params"]["receipts"]["included"] == 1
    download = client.get(f"{A}/audit-exports/{run['id']}/download", headers=h)
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == done["sha256"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        assert json.loads(zf.read("export.json"))["export_run_id"] == run["id"]
        receipts = _table(zf, "belege.csv")
        assert receipts[0]["Im ZIP enthalten"] == "ja"
        assert zf.read(receipts[0]["Pfad im ZIP"]) == w["pdf"]
        assert len(_table(zf, "storno_beziehungen.csv")) == 1
