"""M2-02/S16-02 remainder R08-01 (Welle 5, T14): the property assignment of a membership also
limits the portal administration (accounts by the contract property of the contact), the
objektakte routes per property, the migration and history imports (target property), audit
reports of the board by id (through engagement and community), bank rules, sync logs and the
clarification list (through the bank account) and the target of an account assignment. The
account list applies the filter before the limit. Foreign records answer 404, lists are
filtered, read only members get 403 on writes, invalid ids 422, tenant B sees nothing."""

import asyncio
from collections.abc import Iterator
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
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import IBAN_A, IBAN_B
from tests.integration.test_m21_board_portal import _engagement
from tests.integration.test_q13_property_scope_etag import _assign, _estate, _ok
from tests.integration.test_r08_property_scope_domains import _bank

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t14-{RUN}", name=f"T14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t14b-{RUN}", name=f"T14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("t14admin", a, "tenant_admin"),
            ("t14admin_b", b, "tenant_admin"),
            ("t14clerk", a, "standard"),
            ("t14reader", a, "read_only"),
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


def _owner_contact(client: TestClient, h: dict[str, str], prop: str, ref: str) -> str:
    """Contact with an ownership contract on a new unit of ``prop``."""
    party, contact = _party(client, h, f"Portal{ref}")
    unit = _unit(client, h, prop, "02")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2021-01-01",
                "title_transfer_date": "2021-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    return str(contact["id"])


def _rule(client: TestClient, h: dict[str, str], hoa: str, ref: str) -> str:
    return str(
        _ok(
            client.post(
                f"{B}/rules",
                json={"name": f"Regel {ref}", "legal_entity_id": hoa, "name_contains": ref},
                headers=h,
            ),
            201,
        )["id"]
    )


def _report(client: TestClient, h: dict[str, str], hoa: str, ref: str) -> str:
    _, board = _party(client, h, f"Beirat{ref}")
    engagement = _engagement(client, h, hoa, board["id"])
    return str(
        _ok(
            client.post(
                f"{H}/audits/{engagement}/reports", json={"findings": f"Bericht {ref}"}, headers=h
            ),
            201,
        )["id"]
    )


def test_property_assignment_in_remaining_domains(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "t14admin"))
    own = _estate(client, h, "141")
    foreign = _estate(client, h, "142")
    own.update(_bank(client, h, own["property"], IBAN_A, "141"))
    foreign.update(_bank(client, h, foreign["property"], IBAN_B, "142"))
    for estate, ref in ((own, "141"), (foreign, "142")):
        estate["contact"] = _owner_contact(client, h, estate["property"], ref)
        estate["rule"] = _rule(client, h, estate["hoa"], ref)
        estate["report"] = _report(client, h, estate["hoa"], ref)
    foreign_account = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={
                "contact_id": foreign["contact"],
                "email": world.email("t14p142"),
                "display_name": "Portal 142",
            },
            headers=h,
        ),
        201,
    )["id"]
    _assign(client, h, world.users["t14clerk"], [own["property"]])
    _assign(client, h, world.users["t14reader"], [own["property"]])
    c = bearer(login(client, world, "t14clerk"))

    # Bank rules: list filtered, foreign rule by id 404.
    rules = {r["id"] for r in _ok(client.get(f"{B}/rules", headers=c))}
    assert own["rule"] in rules
    assert foreign["rule"] not in rules
    assert client.post(f"{B}/rules/{foreign['rule']}/disable", headers=c).status_code == 404
    assert client.post(f"{B}/rules/{own['rule']}/disable", headers=c).status_code == 200

    # Sync logs: only runs of visible accounts.
    runs = _ok(client.get(f"{B}/runs", headers=c))
    assert {r["property_bank_account_id"] for r in runs} <= {own["account"]}
    admin_runs = _ok(client.get(f"{B}/runs", headers=h))
    assert foreign["account"] in {r["property_bank_account_id"] for r in admin_runs}

    # Clarification list: only rows whose transaction lies on a visible account.
    for row in _ok(client.get(f"{B}/clarifications", params={"open_only": False}, headers=c)):
        assert row.get("bank_transaction_id") != foreign["tx"]

    # Account list: the property filter applies before the limit.
    limited = _ok(client.get(f"{B}/accounts", params={"limit": 1}, headers=c))
    assert [a["id"] for a in limited] == [own["account"]]

    # Account assignment: the target property must be inside the assignment.
    assigned = client.put(
        f"{B}/accounts/{own['account']}/assignments",
        json={"property_id": foreign["property"]},
        headers=c,
    )
    assert assigned.status_code == 404, assigned.text

    # Portal administration: contacts reach properties through their contracts.
    p = "/api/v1/portal-admin/accounts"
    assert _ok(client.get(p, params={"contact_id": foreign["contact"]}, headers=c)) == []
    assert _ok(client.get(p, params={"contact_id": foreign["contact"]}, headers=h))
    refused = client.post(
        p,
        json={
            "contact_id": foreign["contact"],
            "email": world.email("t14p142b"),
            "display_name": "x",
        },
        headers=c,
    )
    assert refused.status_code == 404, refused.text
    own_account = _ok(
        client.post(
            p,
            json={
                "contact_id": own["contact"],
                "email": world.email("t14p141"),
                "display_name": "Portal 141",
            },
            headers=c,
        ),
        201,
    )["id"]
    assert client.post(f"{p}/{foreign_account}/sync-grants", headers=c).status_code == 404
    assert client.post(f"{p}/{own_account}/sync-grants", headers=c).status_code == 200

    # Objektakte per property, migration and history imports: own passes, foreign 404.
    pairs = [
        "/api/v1/objektakte/properties/{property}/completeness",
        "/api/v1/objektakte/properties/{property}/lists/missing-documents",
        "/api/v1/properties/{property}/objektakte-export",
        "/api/v1/imports/migration/properties/{property}/reconciliation",
        "/api/v1/imports/migration/properties/{property}/acceptance",
        "/api/v1/imports/migration/ledgers/{ledger}",
        "/api/v1/imports/immoware24/history/tickets?property_id={property}",
    ]
    for template in pairs:
        mine = client.get(template.format(**own), headers=c)
        assert mine.status_code != 404, (template, mine.text)
        assert client.get(template.format(**foreign), headers=c).status_code == 404, template
    overview = _ok(client.get("/api/v1/objektakte/lists/missing-documents", headers=c))
    listed = {str(i.get("property_id")) for i in overview["items"]}
    assert foreign["property"] not in listed
    status = {
        i["property_id"] for i in _ok(client.get("/api/v1/imports/migration/status", headers=c))
    }
    assert foreign["property"] not in status

    # Audit reports of the board by id: through engagement and community.
    statement = {"statement": "Der Beirat nimmt den Bericht zur Kenntnis."}
    foreign_stmt = f"{H}/audit-reports/{foreign['report']}/board-statement"
    assert client.post(foreign_stmt, json=statement, headers=c).status_code == 404
    own_stmt = f"{H}/audit-reports/{own['report']}/board-statement"
    assert client.post(own_stmt, json=statement, headers=c).status_code == 200
    assert (
        client.post(
            f"{H}/audit-reports/kein-uuid/board-statement", json=statement, headers=c
        ).status_code
        == 422
    )

    # Read only member: 403 on writes inside its own property.
    r = bearer(login(client, world, "t14reader"))
    assert client.post(f"{B}/rules/{own['rule']}/disable", headers=r).status_code == 403

    # Administrator unrestricted; tenant B sees nothing of tenant A.
    assert foreign["rule"] in {x["id"] for x in _ok(client.get(f"{B}/rules", headers=h))}
    hb = bearer(login(client, world, "t14admin_b"))
    assert own["rule"] not in {x["id"] for x in _ok(client.get(f"{B}/rules", headers=hb))}
    assert client.post(f"{p}/{own_account}/sync-grants", headers=hb).status_code == 404
