"""M18, A37 (M18-02, docs/rules/M18-05-steuerberaterzugang.md): legal entity scope per
membership for the tax advisor role.

A tax advisor with an assigned legal entity sees only that ledger in the ledger list, the
journal, the trial balance, the open items, the journal and DATEV exports and the audit export
(list, create, download); foreign ledgers answer 404. A tax advisor without an assignment sees
nothing (empty list means no access for scoped roles). Administrators and other unscoped
roles are never limited by the list. Maintenance needs ``tenant_settings:update``; tenant
separation holds for the membership and for the legal entity ids.
"""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
T = "/api/v1/tenant"
BUCKET = "mhvp-tax-scope"


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
        a, _ = await services.provision_tenant(factory, slug=f"ts-{RUN}", name=f"Scope {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tt-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, roles in [
            ("tsadmin", a, ["tenant_admin"]),
            ("tstax", a, ["tax_advisor"]),
            ("tstaxnone", a, ["tax_advisor"]),
            ("tsacc", a, ["accountant_no_banking"]),
            ("tsmixed", a, ["tax_advisor", "standard"]),
            ("ttadmin", b, ["tenant_admin"]),
        ]:
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


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if status != 204 else None


def _membership_id(client: TestClient, h: dict[str, str], user_id: uuid.UUID) -> str:
    members = _ok(client.get(f"{T}/members", headers=h))
    return str(next(m["membership_id"] for m in members if m["user_id"] == str(user_id)))


def assign_ledger_scope(
    client: TestClient, admin: dict[str, str], user_id: uuid.UUID, ledger_id: str
) -> None:
    """Shared test helper (A37): adds the legal entity of ``ledger_id`` to the scope of the
    user's membership. Existing tests with a tax advisor call this before the advisor reads or
    exports, because an unassigned tax advisor sees nothing."""
    ledger = _ok(client.get(f"{A}/ledgers/{ledger_id}", headers=admin))
    members = _ok(client.get(f"{T}/members", headers=admin))
    member = next(m for m in members if m["user_id"] == str(user_id))
    ids = sorted({*member.get("legal_entity_ids", []), ledger["legal_entity_id"]})
    _ok(
        client.put(
            f"{T}/members/{member['membership_id']}/legal-entities",
            json={"legal_entity_ids": ids},
            headers=admin,
        ),
        204,
    )


def _hoa_with_ledger(client: TestClient, h: dict[str, str], number: str) -> tuple[str, str]:
    """Creates a HOA property and its ledger; returns (legal_entity_id, ledger_id)."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Haus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    templates = _ok(client.get(f"{A}/templates", headers=h))
    template_id = templates[0]["id"] if templates else None
    if template_id is None:
        template_id = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template_id}, headers=h
        ),
        201,
    )["id"]
    return str(hoa), str(ledger)


def _grant_documents_read_to_tax_advisor(world: World) -> None:
    """Test helper: the tax advisor role has no documents right by default; the document scope
    is checked with the right granted directly in the tenant's role table (RLS bound)."""
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        role_id = conn.execute(
            text("SELECT id FROM role WHERE tenant_id = :t AND code = 'tax_advisor'"),
            {"t": str(world.tenant_a)},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO role_permission (id, tenant_id, role_id, resource, action) "
                "VALUES (:id, :t, :r, 'documents', 'read') ON CONFLICT DO NOTHING"
            ),
            {"id": str(uuid.uuid4()), "t": str(world.tenant_a), "r": role_id},
        )
    engine.dispose()


def test_tax_advisor_scope_limits_ledgers_reports_and_exports(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "tsadmin"))
    hoa1, ledger1 = _hoa_with_ledger(client, h, "901")
    hoa2, ledger2 = _hoa_with_ledger(client, h, "902")
    tax_member = _membership_id(client, h, world.users["tstax"])

    # Legal entity options for the CRM selection list both communities.
    options = _ok(client.get(f"{T}/legal-entities", headers=h))
    assert {hoa1, hoa2} <= {o["id"] for o in options}

    _ok(
        client.put(
            f"{T}/members/{tax_member}/legal-entities",
            json={"legal_entity_ids": [hoa1]},
            headers=h,
        ),
        204,
    )
    members = _ok(client.get(f"{T}/members", headers=h))
    assert next(m for m in members if m["membership_id"] == tax_member)["legal_entity_ids"] == [
        hoa1
    ]

    # Admin creates an audit export for the foreign ledger (the advisor must not see it).
    foreign_run = _ok(
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger2, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=h,
        ),
        201,
    )["id"]

    tax = bearer(login(client, world, "tstax"))
    ledgers = _ok(client.get(f"{A}/ledgers", headers=tax))
    assert [x["id"] for x in ledgers] == [ledger1]
    _ok(client.get(f"{A}/ledgers/{ledger1}", headers=tax))
    assert client.get(f"{A}/ledgers/{ledger2}", headers=tax).status_code == 404

    # Reports: journal, balances, open items.
    _ok(client.get(f"{A}/ledgers/{ledger1}/entries", headers=tax))
    assert client.get(f"{A}/ledgers/{ledger2}/entries", headers=tax).status_code == 404
    _ok(client.get(f"{A}/ledgers/{ledger1}/trial-balance?as_of=2026-12-31", headers=tax))
    assert (
        client.get(f"{A}/ledgers/{ledger2}/trial-balance?as_of=2026-12-31", headers=tax).status_code
        == 404
    )
    _ok(client.get(f"{A}/ledgers/{ledger1}/open-items?as_of=2026-12-31", headers=tax))
    assert (
        client.get(f"{A}/ledgers/{ledger2}/open-items?as_of=2026-12-31", headers=tax).status_code
        == 404
    )

    # Exports: journal CSV, DATEV (404 before the configuration check), audit export.
    period = {"start": "2026-01-01", "end": "2026-12-31"}
    _ok(client.post(f"{A}/ledgers/{ledger1}/exports/journal", params=period, headers=tax), 201)
    assert (
        client.post(
            f"{A}/ledgers/{ledger2}/exports/journal", params=period, headers=tax
        ).status_code
        == 404
    )
    assert (
        client.post(f"{A}/ledgers/{ledger2}/exports/datev", params=period, headers=tax).status_code
        == 404
    )
    own_run = _ok(
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger1, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=tax,
        ),
        201,
    )["id"]
    assert (
        client.post(
            f"{A}/audit-exports",
            json={"ledger_id": ledger2, "period_from": "2026-01-01", "period_to": "2026-12-31"},
            headers=tax,
        ).status_code
        == 404
    )
    listed = {r["id"] for r in _ok(client.get(f"{A}/audit-exports", headers=tax))}
    assert own_run in listed
    assert foreign_run not in listed
    assert client.get(f"{A}/audit-exports/{foreign_run}", headers=tax).status_code == 404
    assert client.get(f"{A}/audit-exports/{foreign_run}/download", headers=tax).status_code == 404
    assert client.get(f"{A}/audit-exports/{own_run}/download", headers=tax).status_code == 200
    # The administrator still sees both runs.
    assert {foreign_run, own_run} <= {
        r["id"] for r in _ok(client.get(f"{A}/audit-exports", headers=h))
    }


def test_documents_are_filtered_by_legal_entity_link(client: TestClient, world: World) -> None:
    _grant_documents_read_to_tax_advisor(world)
    h = bearer(login(client, world, "tsadmin"))
    hoa1, _ = _hoa_with_ledger(client, h, "903")
    hoa2, _ = _hoa_with_ledger(client, h, "904")
    tax_member = _membership_id(client, h, world.users["tstax"])
    _ok(
        client.put(
            f"{T}/members/{tax_member}/legal-entities",
            json={"legal_entity_ids": [hoa1]},
            headers=h,
        ),
        204,
    )

    def upload(title: str, legal_entity_id: str) -> str:
        doc = _ok(
            client.post(
                "/api/v1/documents",
                files={"file": (f"{title}.txt", b"Inhalt", "text/plain")},
                data={
                    "title": title,
                    "links": f'[{{"entity_type": "legal_entity", "entity_id": "{legal_entity_id}"}}]',
                },
                headers=h,
            ),
            201,
        )
        return str(doc["id"])

    own = upload(f"Eigen {RUN}", hoa1)
    foreign = upload(f"Fremd {RUN}", hoa2)

    tax = bearer(login(client, world, "tstax"))
    ids = {d["id"] for d in _ok(client.get("/api/v1/documents", headers=tax))["items"]}
    assert own in ids
    assert foreign not in ids
    _ok(client.get(f"/api/v1/documents/{own}", headers=tax))
    assert client.get(f"/api/v1/documents/{foreign}", headers=tax).status_code == 404
    assert client.get(f"/api/v1/documents/{foreign}/content", headers=tax).status_code == 404


def test_tax_advisor_without_assignment_sees_nothing(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "tsadmin"))
    _, ledger = _hoa_with_ledger(client, h, "905")
    none = bearer(login(client, world, "tstaxnone"))
    assert _ok(client.get(f"{A}/ledgers", headers=none)) == []
    assert client.get(f"{A}/ledgers/{ledger}", headers=none).status_code == 404
    assert _ok(client.get(f"{A}/audit-exports", headers=none)) == []


def test_unscoped_roles_ignore_the_list(client: TestClient, world: World) -> None:
    """The list only limits memberships whose roles are all scoped roles (tax_advisor). An
    administrator, an accountant or a mixed membership (tax_advisor plus standard) keeps the
    full tenant view even with an assignment."""
    h = bearer(login(client, world, "tsadmin"))
    hoa1, ledger1 = _hoa_with_ledger(client, h, "906")
    _, ledger2 = _hoa_with_ledger(client, h, "907")
    for name in ("tsadmin", "tsacc", "tsmixed"):
        member = _membership_id(client, h, world.users[name])
        _ok(
            client.put(
                f"{T}/members/{member}/legal-entities",
                json={"legal_entity_ids": [hoa1]},
                headers=h,
            ),
            204,
        )
    for name in ("tsadmin", "tsacc", "tsmixed"):
        headers = bearer(login(client, world, name))
        ids = {x["id"] for x in _ok(client.get(f"{A}/ledgers", headers=headers))}
        assert {ledger1, ledger2} <= ids
        _ok(client.get(f"{A}/ledgers/{ledger2}", headers=headers))


def test_scope_maintenance_rights_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "tsadmin"))
    hoa1, _ = _hoa_with_ledger(client, h, "908")
    tax_member = _membership_id(client, h, world.users["tstax"])

    # The tax advisor cannot change scopes (needs tenant_settings:update), the accountant neither.
    for name in ("tstax", "tsacc"):
        assert (
            client.put(
                f"{T}/members/{tax_member}/legal-entities",
                json={"legal_entity_ids": [hoa1]},
                headers=bearer(login(client, world, name)),
            ).status_code
            == 403
        )

    # Tenant separation: the other tenant's administrator neither reaches the membership nor
    # can its legal entity be assigned in tenant A.
    other = bearer(login(client, world, "ttadmin"))
    assert (
        client.put(
            f"{T}/members/{tax_member}/legal-entities",
            json={"legal_entity_ids": [hoa1]},
            headers=other,
        ).status_code
        == 404
    )
    foreign_hoa, _ = _hoa_with_ledger(client, other, "909")
    assert (
        client.put(
            f"{T}/members/{tax_member}/legal-entities",
            json={"legal_entity_ids": [foreign_hoa]},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{T}/members/{uuid.uuid4()}/legal-entities",
            json={"legal_entity_ids": []},
            headers=h,
        ).status_code
        == 404
    )
    # The change is recorded in the event log.
    _ok(
        client.put(
            f"{T}/members/{tax_member}/legal-entities",
            json={"legal_entity_ids": [hoa1]},
            headers=h,
        ),
        204,
    )
    events = _ok(client.get(f"{T}/events", params={"limit": 50}, headers=h))
    rows = events if isinstance(events, list) else events.get("items", [])
    assert any(e["type"] == "membership.legal_entities_changed" for e in rows)
