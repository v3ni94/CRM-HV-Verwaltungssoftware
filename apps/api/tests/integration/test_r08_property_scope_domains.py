"""M2-02/S16-02 remainder (Q13-01): the property assignment of a membership also limits
banking (accounts, transactions), WEG lists and records, ledger reports, the property sub
routers (tax profile, consumption info, takeover, creditors, notices), service contracts and
the global search. Foreign records answer 404, lists are filtered, read only members get 403
on writes, invalid ids 422, and tenant B sees nothing of tenant A."""

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
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import IBAN_A, IBAN_B, PAYER, _camt, _ntry, _upload
from tests.integration.test_q13_property_scope_etag import _assign, _estate, _ok

pytestmark = pytest.mark.integration
B = "/api/v1/banking"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r08-{RUN}", name=f"R08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r08b-{RUN}", name=f"R08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("r08admin", a, "tenant_admin"),
            ("r08admin_b", b, "tenant_admin"),
            ("r08clerk", a, "standard"),
            ("r08reader", a, "read_only"),
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


def _bank(client: TestClient, h: dict[str, str], prop: str, iban: str, ref: str) -> dict[str, str]:
    detail = _ok(client.get(f"/api/v1/properties/{prop}", headers=h))
    hoa = next(e["id"] for e in detail["legal_entities"] if e["kind"] == "hoa")
    account = _ok(
        client.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": iban,
                "holder": f"GdWE {ref}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    data = _camt(
        f"S-{ref}",
        iban,
        "1000.00",
        "1400.00",
        [_ntry(f"R-{ref}", "400.00", "CRDT", "2026-01-05", PAYER, f"Hausgeld {ref}")],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, f"{ref}.xml", data)}, headers=h
        ),
        201,
    )
    tx = _ok(client.get(f"{B}/transactions", params={"bank_account_id": account}, headers=h))
    ledgers = _ok(client.get("/api/v1/accounting/ledgers", headers=h))
    ledger = next(x["id"] for x in ledgers if x["legal_entity_id"] == hoa)
    return {"account": account, "tx": tx[0]["id"], "hoa": hoa, "ledger": ledger}


def _ids(payload: Any) -> set[str]:
    rows = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
    return {str(r["id"]) for r in rows}


def test_property_assignment_in_further_domains(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r08admin"))
    own = _estate(client, h, "801")
    foreign = _estate(client, h, "802")
    own.update(_bank(client, h, own["property"], IBAN_A, "801"))
    foreign.update(_bank(client, h, foreign["property"], IBAN_B, "802"))
    _, provider = _party(client, h, "Hausmeister801", kind="company")
    contracts = {}
    for key, estate in (("own", own), ("foreign", foreign)):
        contracts[key] = _ok(
            client.post(
                "/api/v1/service-contracts",
                json={
                    "provider_contact_id": provider["id"],
                    "property_id": estate["property"],
                    "title": f"Hausmeister {key}",
                    "starts_at": "2026-01-01",
                    "notice_period_days": 3,
                },
                headers=h,
            ),
            201,
        )["id"]
    _assign(client, h, world.users["r08clerk"], [own["property"]])
    _assign(client, h, world.users["r08reader"], [own["property"]])
    c = bearer(login(client, world, "r08clerk"))

    # Banking lists: accounts and transactions of the foreign property are not listed.
    accounts = {a["id"] for a in _ok(client.get(f"{B}/accounts", headers=c))}
    assert own["account"] in accounts
    assert foreign["account"] not in accounts
    txs = {t["id"] for t in _ok(client.get(f"{B}/transactions", headers=c))}
    assert own["tx"] in txs
    assert foreign["tx"] not in txs

    # Service contracts list.
    listed = _ids(_ok(client.get("/api/v1/service-contracts", headers=c)))
    assert contracts["own"] in listed
    assert contracts["foreign"] not in listed

    # Detail and sub router paths: own 200, foreign 404.
    pairs = [
        (f"{B}/transactions/{{tx}}/candidates", "tx"),
        (f"{B}/accounts/{{account}}/reconciliation", "account"),
        ("/api/v1/accounting/tax/properties/{property}/profile", "property"),
        ("/api/v1/properties/{property}/takeover-checklist", "property"),
        ("/api/v1/properties/{property}/creditors", "property"),
        ("/api/v1/properties/{property}/notices", "property"),
        ("/api/v1/properties/{property}/consumption-info", "property"),
        ("/api/v1/accounting/ledgers/{ledger}/reports/trial-balance", "ledger"),
        ("/api/v1/hoa/meetings?legal_entity_id={hoa}", "hoa"),
        ("/api/v1/hoa/resolutions?legal_entity_id={hoa}", "hoa"),
        ("/api/v1/hoa/plans?ledger_id={ledger}", "ledger"),
    ]
    for template, key in pairs:
        own_path = template.format(**{key: own[key]})
        foreign_path = template.format(**{key: foreign[key]})
        mine = client.get(own_path, headers=c)
        assert mine.status_code != 404, (own_path, mine.text)
        assert client.get(foreign_path, headers=c).status_code == 404, foreign_path
    assert (
        client.get(f"/api/v1/service-contracts/{contracts['foreign']}", headers=c).status_code
        == 404
    )

    # Global search: only the assigned property is found.
    hits = _ok(client.get("/api/v1/workspace/search", params={"q": "80"}, headers=c))
    found = {x["id"] for x in hits if x["entity_type"] == "property"}
    assert own["property"] in found
    assert foreign["property"] not in found

    # Writes: a service contract on a foreign property is refused like an unknown property.
    refused = client.post(
        "/api/v1/service-contracts",
        json={
            "provider_contact_id": provider["id"],
            "property_id": foreign["property"],
            "title": "Fremd",
            "starts_at": "2026-01-01",
            "notice_period_days": 3,
        },
        headers=c,
    )
    assert refused.status_code == 422, refused.text

    # Read only member: 403 on write, the guard does not hide its own property.
    r = bearer(login(client, world, "r08reader"))
    denied = client.post(
        f"/api/v1/properties/{own['property']}/notices",
        json={"title": "Aushang", "body": "Text"},
        headers=r,
    )
    assert denied.status_code == 403, denied.text
    # Validation: an unparsable id still answers 422.
    assert client.get(f"{B}/transactions/kein-uuid/candidates", headers=c).status_code == 422

    # Administrator unrestricted; tenant B sees nothing of tenant A.
    admin_accounts = {a["id"] for a in _ok(client.get(f"{B}/accounts", headers=h))}
    assert {own["account"], foreign["account"]} <= admin_accounts
    hb = bearer(login(client, world, "r08admin_b"))
    assert own["account"] not in {a["id"] for a in _ok(client.get(f"{B}/accounts", headers=hb))}
    assert client.get(f"{B}/transactions/{own['tx']}/candidates", headers=hb).status_code == 404
