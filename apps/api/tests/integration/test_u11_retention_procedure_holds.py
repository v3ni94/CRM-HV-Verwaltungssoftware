"""S711-06 rest (U11): automatic hold from an open procedure (litigation or insolvency block
of accounting on an open item of a linked contract), four eyes when a hold is lifted, the
retention status endpoint; tenant separation (404), read only role (403), validation (422)."""

import asyncio
import json
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
from tests.integration.test_m16_dunning_default_and_account import _hoa_property_without_account
from tests.integration.test_m16_dunning_letters import (
    BUCKET,
    OpenG1,
    _debtor_contract,
    _ok,
    _settings,
)

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u11-{RUN}", name=f"U11 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u11b-{RUN}", name=f"U11b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("u11admin", a, "tenant_admin"),
            ("u11second", a, "tenant_admin"),
            ("u11read", a, "read_only"),
            ("u11other", b, "tenant_admin"),
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
def gated(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(
            create_app(_settings(database, redis_url), release_gate_resolver=OpenG1())
        ) as client:
            yield client


def _doc(c: TestClient, h: dict[str, str], title: str, links: list[dict[str, str]]) -> Any:
    return _ok(
        c.post(
            "/api/v1/documents",
            files={"file": (f"{title}.txt", f"{title} {RUN}".encode(), "text/plain")},
            data={"title": title, "links": json.dumps(links)},
            headers=h,
        ),
        201,
    )


def test_procedure_block_holds_linked_documents(gated: TestClient, world: World) -> None:
    h = bearer(login(gated, world, "u11admin"))
    reader = bearer(login(gated, world, "u11read"))
    other = bearer(login(gated, world, "u11other"))
    prop, ledger, _hoa = _hoa_property_without_account(gated, h, "811", "Sperrhaus")
    contract = _debtor_contract(gated, h, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(gated.get(f"{A}/ledgers/{ledger}/open-items?as_of=2026-12-31", headers=h))
    item = next(i for i in items if i["contract_id"] == contract["id"])

    doc = _doc(gated, h, "Klageschrift", [{"entity_type": "contract", "entity_id": contract["id"]}])
    status_url = f"/api/v1/documents/{doc['id']}/retention-status"
    before = _ok(gated.get(status_url, headers=h))
    assert before["procedure_hold"] is None
    assert gated.get(status_url, headers=other).status_code == 404

    # A dispute alone is no procedure; litigation is.
    disputed = _ok(
        gated.post(
            f"{A}/open-items/{item['id']}/dunning-blocks",
            json={"reason_code": "disputed"},
            headers=h,
        ),
        201,
    )
    assert _ok(gated.get(status_url, headers=h))["procedure_hold"] is None
    _ok(gated.post(f"{A}/dunning-blocks/{disputed['id']}/release", headers=h))
    block = _ok(
        gated.post(
            f"{A}/open-items/{item['id']}/dunning-blocks",
            json={"reason_code": "litigation", "note": "Klage eingereicht"},
            headers=h,
        ),
        201,
    )
    held = _ok(gated.get(status_url, headers=reader))  # read access is enough
    assert held["procedure_hold"] == "Rechtsstreit (Prozess)"
    assert "offenes Verfahren" in held["deletion_blocker"]
    refused = gated.delete(f"/api/v1/documents/{doc['id']}", headers=h)
    assert refused.status_code == 409
    assert "offenes Verfahren" in refused.json()["detail"]

    # Lifting the block in accounting lifts the automatic hold.
    _ok(gated.post(f"{A}/dunning-blocks/{block['id']}/release", headers=h))
    after = _ok(gated.get(status_url, headers=h))
    assert after["procedure_hold"] is None
    assert "offenes Verfahren" not in (after["deletion_blocker"] or "")


def test_hold_is_lifted_only_by_a_second_person(gated: TestClient, world: World) -> None:
    h = bearer(login(gated, world, "u11admin"))
    second = bearer(login(gated, world, "u11second"))
    reader = bearer(login(gated, world, "u11read"))
    other = bearer(login(gated, world, "u11other"))
    doc = _doc(gated, h, "Beweisfoto", [])
    url = f"/api/v1/documents/{doc['id']}/hold"
    assert gated.post(url, json={"reason": ""}, headers=h).status_code == 422
    assert gated.post(url, json={"reason": "Beweis"}, headers=reader).status_code == 403
    assert gated.post(url, json={"reason": "Beweis"}, headers=other).status_code == 404
    _ok(gated.post(url, json={"reason": "Beweissicherung", "kind": "evidence"}, headers=h))
    # V11-07: an active hold is not overwritten, neither by the setter nor by another user.
    for who in (h, second):
        again = gated.post(url, json={"reason": "andere Sperrart", "kind": "other"}, headers=who)
        assert again.status_code == 409
    kept = _ok(gated.get(f"/api/v1/documents/{doc['id']}", headers=h))
    assert kept["retention_hold_reason"] == "Beweissicherung"
    assert kept["retention_hold_kind"] == "evidence"
    own = gated.request("DELETE", url, json={"reason": "erledigt"}, headers=h)
    assert own.status_code == 403
    assert "zweite Person" in own.json()["detail"]
    assert (
        _ok(gated.get(f"/api/v1/documents/{doc['id']}", headers=h))["retention_hold_reason"]
        == "Beweissicherung"
    )
    cleared = _ok(gated.request("DELETE", url, json={"reason": "erledigt"}, headers=second))
    assert cleared["retention_hold_reason"] is None

    # Same rule for the hold on a ticket (Vorgang).
    ticket = _ok(gated.post("/api/v1/tickets", json={"title": f"Streit {RUN}"}, headers=h), 201)
    turl = f"/api/v1/tickets/{ticket['id']}/retention-hold"
    _ok(gated.post(turl, json={"reason": "Rechtsstreit"}, headers=h))
    assert gated.request("DELETE", turl, json={"reason": "beendet"}, headers=h).status_code == 403
    _ok(gated.request("DELETE", turl, json={"reason": "beendet"}, headers=second))


def test_resolution_start_rule_takes_the_decision_date(gated: TestClient, world: World) -> None:
    """U11-01: start rule ``resolution``: the period starts with the year end of the decision
    date of the referenced resolution; without it the document stays locked."""
    h = bearer(login(gated, world, "u11admin"))
    second = bearer(login(gated, world, "u11second"))
    reader = bearer(login(gated, world, "u11read"))
    other = bearer(login(gated, world, "u11other"))
    _prop, _ledger, hoa = _hoa_property_without_account(gated, h, "813", "Beschlusshaus")
    resolution = _ok(
        gated.post(
            "/api/v1/hoa/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2024-05-17",
                "subject": "Dachsanierung",
                "wording": "Die Dachsanierung wird beschlossen.",
                "status": "positive",
            },
            headers=h,
        ),
        201,
    )
    profile = _ok(
        gated.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"u11_beschluss_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 3,
                "start_rule": "resolution",
            },
            headers=h,
        ),
        201,
    )
    _ok(gated.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second), 200)
    doc = _doc(gated, h, "Beschlussanlage", [])
    url = f"/api/v1/documents/{doc['id']}"
    # Profile without a resolution reference: period open, locked with the missing start.
    _ok(gated.patch(url, json={"retention_profile_id": profile["id"]}, headers=h), 200)
    status = _ok(gated.get(f"{url}/retention-status", headers=h))
    assert status["retention_until"] is None
    assert "Fristbeginn fehlt" in status["deletion_blocker"]
    # Validation, permission, tenant separation.
    bad = gated.patch(url, json={"retention_resolution_id": "not-a-uuid"}, headers=h)
    assert bad.status_code == 422
    unknown = gated.patch(
        url, json={"retention_resolution_id": "01920000-0000-7000-8000-0000000000aa"}, headers=h
    )
    assert unknown.status_code == 404
    body = {"retention_resolution_id": resolution["id"]}
    # Review W79: a resolution of a community the document is not linked to is refused.
    unlinked = gated.patch(url, json=body, headers=h)
    assert unlinked.status_code == 422, unlinked.text
    _other_prop, _other_ledger, other_hoa = _hoa_property_without_account(
        gated, h, "814", "Nachbarhaus"
    )
    foreign_link = {"entity_type": "legal_entity", "entity_id": other_hoa}
    _ok(gated.post(f"{url}/links", json=foreign_link, headers=h), 201)
    assert gated.patch(url, json=body, headers=h).status_code == 422
    _ok(
        gated.post(
            f"{url}/links", json={"entity_type": "legal_entity", "entity_id": hoa}, headers=h
        ),
        201,
    )
    assert gated.patch(url, json=body, headers=reader).status_code == 403
    assert gated.patch(url, json=body, headers=other).status_code == 404
    patched = _ok(gated.patch(url, json=body, headers=h), 200)
    assert patched["retention_resolution_id"] == resolution["id"]
    assert patched["retention_base_on"] == "2024-05-17"
    assert patched["retention_until"] == "2027-12-31"  # 31.12.2024 plus 3 years
    status = _ok(gated.get(f"{url}/retention-status", headers=reader))
    assert status["retention_resolution_id"] == resolution["id"]
    assert "Aufbewahrungsfrist ist nicht abgelaufen" in status["deletion_blocker"]
    # A hold shows the four eyes requirement.
    _ok(gated.post(f"{url}/hold", json={"reason": "Anfechtung", "kind": "litigation"}, headers=h))
    held = _ok(gated.get(f"{url}/retention-status", headers=h))
    assert held["hold_set_by_four_eyes_required"] is True
