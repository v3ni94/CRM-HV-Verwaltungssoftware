"""A36 (M18-01, rule M18-04): CRM account to DATEV Sachkonto mapping per tenant. CRUD, CSV
import with preview, report of unmapped accounts, DATEV batch export refused with the list of
missing accounts and written only with a complete mapping, permissions, tenant separation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m18_tax_advisor_scope import assign_ledger_scope

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
M = f"{A}/datev-mappings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dm-{RUN}", name=f"DATEV {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dn-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("dmadmin", a, "tenant_admin"),
            ("dmacc", a, "accountant_no_banking"),
            ("dmtax", a, "tax_advisor"),
            ("dmstandard", a, "caretaker"),
            ("dnadmin", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ledger_with_postings(client: TestClient, h: dict[str, str], acc_user: dict[str, str]) -> Any:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "836", "name": "Zuordnungshaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}

    def book(body: dict[str, Any]) -> None:
        draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
        if body["kind"] == "opening_balance":
            _ok(
                client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=acc_user)
            )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))

    book(
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
    book(
        {
            "kind": "custom",
            "booking_date": "2026-03-15",
            "text": "Bankgebühr",
            "lines": [
                {"account_id": acc["001200"]["id"], "credit": "12.50"},
                {"account_id": acc["001201"]["id"], "debit": "12.50"},
            ],
        }
    )
    return ledger, acc


def test_datev_mapping_crud_import_report_and_export(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dmadmin"))
    acc_user = bearer(login(client, world, "dmacc"))
    tax = bearer(login(client, world, "dmtax"))
    standard = bearer(login(client, world, "dmstandard"))
    ledger, acc = _ledger_with_postings(client, h, acc_user)
    # A37: the tax advisor only sees assigned legal entities (test_m18_tax_advisor_scope).
    assign_ledger_scope(client, h, world.users["dmtax"], ledger)

    # Nothing preloaded: the report lists every account as unmapped.
    rep = _ok(
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        )
    )
    assert rep["unmapped_count"] == len(acc)
    assert rep["used_unmapped_count"] == 3
    used = {a["account_code"]: a for a in rep["accounts"] if a["lines_in_period"]}
    assert set(used) == {"001200", "001201", "009000"}
    assert used["001200"]["lines_in_period"] == 2
    assert used["001200"]["first_booking_date"] == "2026-01-01"
    assert used["001200"]["last_booking_date"] == "2026-03-15"

    # CRUD ---------------------------------------------------------------------------------
    tenant_wide = _ok(
        client.post(
            M,
            json={"account_code": "001200", "datev_account": "1200", "label": "Bank"},
            headers=h,
        ),
        201,
    )
    assert tenant_wide["ledger_id"] is None
    assert tenant_wide["active"] is True
    assert (
        client.post(
            M, json={"account_code": "001200", "datev_account": "1201"}, headers=h
        ).status_code
        == 409
    )  # duplicate
    assert (
        client.post(
            M, json={"account_code": "001200", "datev_account": "12A0"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            M,
            json={"account_code": "001200", "datev_account": "1", "ledger_id": str(world.tenant_b)},
            headers=h,
        ).status_code
        == 422
    )  # unknown ledger
    ledger_specific = _ok(
        client.post(
            M,
            json={
                "account_code": "001200",
                "datev_account": "1210",
                "ledger_id": ledger,
                "label": "Bank WEG",
            },
            headers=h,
        ),
        201,
    )
    listed = _ok(client.get(M, params={"ledger_id": ledger}, headers=tax))
    assert [m["datev_account"] for m in listed] == ["1200", "1210"]
    patched = _ok(client.patch(f"{M}/{ledger_specific['id']}", json={"active": False}, headers=h))
    assert patched["active"] is False
    assert [m["id"] for m in _ok(client.get(M, headers=h))] == [tenant_wide["id"]]
    assert len(_ok(client.get(M, params={"include_inactive": "true"}, headers=h))) == 2
    assert client.delete(f"{M}/{ledger_specific['id']}", headers=h).status_code == 204
    assert client.patch(f"{M}/{ledger_specific['id']}", json={}, headers=h).status_code == 404

    # A mapping valid only from a later date leaves earlier lines unmapped (report per date).
    later = _ok(
        client.post(
            M,
            json={"account_code": "001201", "datev_account": "1250", "valid_from": "2026-02-01"},
            headers=h,
        ),
        201,
    )
    rep = _ok(
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        )
    )
    line = next(a for a in rep["accounts"] if a["account_code"] == "001201")
    assert line["datev_account"] == "1250"
    assert line["unmapped"] is True
    assert line["unmapped_lines"] == 1
    _ok(client.patch(f"{M}/{later['id']}", json={"clear_valid_from": True}, headers=h))

    # DATEV export: parameters set but mapping incomplete -> 409 with the missing accounts.
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "datev_consultant_number": "12345",
                "datev_client_number": "6789",
                "datev_chart_of_accounts": "skr03",
                "datev_account_length": 4,
            },
            headers=h,
        )
    )
    refused = client.post(
        f"{A}/ledgers/{ledger}/exports/datev",
        params={"start": "2026-01-01", "end": "2026-12-31"},
        headers=h,
    )
    assert refused.status_code == 409, refused.text
    problem = refused.json()
    assert problem["code"] == "MHVP-BILL-0008"
    assert [m["account_code"] for m in problem["missing"]] == ["009000"]
    assert problem["missing"][0]["lines"] == 1
    assert "009000" in problem["detail"]

    # CSV import: preview, then commit; second run reports unchanged; error rows block.
    csv_text = "Konto;DATEV-Konto;Bezeichnung;Gültig ab\r\n009000;9000;Saldenvortrag;\r\n001200;1200;Bank;\r\n"
    preview = _ok(
        client.post(f"{M}/import", json={"content": csv_text, "dry_run": True}, headers=h)
    )
    assert preview["dry_run"] is True
    assert preview["file_errors"] == []
    assert preview["counts"] == {"create": 1, "update": 0, "unchanged": 1, "error": 0}
    assert [m["account_code"] for m in _ok(client.get(M, headers=h))] == ["001200", "001201"]
    done = _ok(client.post(f"{M}/import", json={"content": csv_text, "dry_run": False}, headers=h))
    assert done["counts"]["created"] == 1
    assert done["counts"]["unchanged"] == 1
    again = _ok(client.post(f"{M}/import", json={"content": csv_text, "dry_run": False}, headers=h))
    assert again["counts"]["created"] == 0
    assert again["counts"]["unchanged"] == 2
    bad = client.post(
        f"{M}/import",
        json={"content": "account_code,datev_account\n001202,12x\n", "dry_run": False},
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["rows"][0]["error"] == "DATEV-Konto muss numerisch sein."
    assert (
        client.post(
            f"{M}/import", json={"content": "foo;bar\n1;2\n", "dry_run": True}, headers=h
        ).json()["file_errors"]
        != []
    )
    assert len(_ok(client.get(M, headers=h))) == 3

    # Export now writes the DATEV accounts, never the CRM numbers.
    export = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/exports/datev",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        ),
        201,
    )
    content = export["content"]
    assert content.startswith('"EXTF";"7";"21";"Buchungsstapel"')
    assert export["rows"] == 5
    body = content.split("\r\n", 2)[2]
    assert '"1200"' in body
    assert '"1250"' in body
    assert '"9000"' in body
    for crm_number in ("001200", "001201", "009000"):
        assert crm_number not in body
    rep = _ok(
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        )
    )
    assert rep["used_unmapped_count"] == 0
    assert rep["unmapped_count"] == len(acc) - 3
    assert (
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-12-31", "end": "2026-01-01"},
            headers=h,
        ).status_code
        == 422
    )

    # Permissions: tax advisor reads but does not maintain; a caretaker sees nothing.
    assert (
        client.post(M, json={"account_code": "x", "datev_account": "1"}, headers=tax).status_code
        == 403
    )
    assert client.post(f"{M}/import", json={"content": csv_text}, headers=tax).status_code == 403
    assert (
        client.patch(f"{M}/{tenant_wide['id']}", json={"active": False}, headers=tax).status_code
        == 403
    )
    assert client.delete(f"{M}/{tenant_wide['id']}", headers=tax).status_code == 403
    assert client.get(M, headers=standard).status_code == 403
    assert (
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-01-01", "end": "2026-01-31"},
            headers=standard,
        ).status_code
        == 403
    )

    # Tax advisor scope per legal entity (A37) is not assigned in this world; the tax
    # advisor therefore only exercises the maintenance refusals and the tenant wide list.
    # Tenant separation: the other tenant neither sees nor changes the rows or the ledger.
    other = bearer(login(client, world, "dnadmin", tenant_id=world.tenant_b))
    assert _ok(client.get(M, headers=other)) == []
    assert (
        client.patch(f"{M}/{tenant_wide['id']}", json={"active": False}, headers=other).status_code
        == 404
    )
    assert client.delete(f"{M}/{tenant_wide['id']}", headers=other).status_code == 404
    assert (
        client.get(
            f"{M}/report",
            params={"ledger_id": ledger, "start": "2026-01-01", "end": "2026-01-31"},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.post(
            M,
            json={"account_code": "001200", "datev_account": "1", "ledger_id": ledger},
            headers=other,
        ).status_code
        == 422
    )
    assert len(_ok(client.get(M, headers=h))) == 3
