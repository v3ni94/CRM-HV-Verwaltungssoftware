"""AO03 (GAK-203): index clause, graduated steps, consumer price index import and the draft
proposals of the daily job. Expected values by hand: rent 600,00, base index 100 (01.2023),
released index 110,5 (08.2026) -> 600,00 * 110,5 / 100 = 663,00; graduated step 650,00 thirty
days ahead -> proposal 600,00 to 650,00, the step 400 days ahead is outside the 60 day horizon.
The index values are test inputs, not published figures."""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.clock import local_today
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_an18_rent_increase_block import _contract
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"
P = "/api/v1/platform/consumer-price-index"
SERIES = f"ao03-{RUN}"[:40]


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ao03a-{RUN}", name=f"AO03 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ao03b-{RUN}", name=f"AO03b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs: list[tuple[str, UUID | None, list[str], bool]] = [
            ("ao03admin", a, ["tenant_admin"], False),
            ("ao03reader", a, ["read_only"], False),
            ("ao03other", b, ["tenant_admin"], False),
            ("ao03padmin", None, [], True),
        ]
        for name, tenant, roles, padmin in specs:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=padmin,
            )
            world.users[name] = uid
            if tenant is not None:
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_cpi_import_release_and_permissions(client: TestClient, world: World) -> None:
    ph = bearer(login(client, world, "ao03padmin"))
    h = bearer(login(client, world, "ao03admin"))
    body = {
        "series": SERIES,
        "source": "Testreihe AO03, keine amtlichen Werte",
        "data_as_of": "2026-09-15",
        "csv": "Monat;Wert\n2023-01;100,0\n08.2026;110,5\n",
    }
    assert client.post(f"{P}/import", json=body, headers=h).status_code == 403
    bad = body | {"csv": "2026-08;abc\n"}
    assert client.post(f"{P}/import", json=bad, headers=ph).status_code == 422
    assert _ok(client.post(f"{P}/import", json=body, headers=ph)) == {
        "created": 2,
        "updated": 0,
        "unchanged": 0,
    }
    assert _ok(client.post(f"{P}/import", json=body, headers=ph))["unchanged"] == 2
    rows = _ok(client.get(f"{L}/consumer-price-index", params={"series": SERIES}, headers=h))
    assert [(r["month"], r["value"], r["released"]) for r in rows] == [
        ("2026-08-01", "110.50000000", False),
        ("2023-01-01", "100.00000000", False),
    ]
    rel = {"series": SERIES, "up_to": "2026-08-31"}
    assert client.post(f"{P}/release", json=rel, headers=h).status_code == 403
    assert _ok(client.post(f"{P}/release", json=rel, headers=ph)) == {"released": 2}


def test_terms_and_proposals(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao03admin"))
    hr = bearer(login(client, world, "ao03reader"))
    ho = bearer(login(client, world, "ao03other"))
    indexed, _, _ = _contract(client, h, "301")
    graduated, _, _ = _contract(client, h, "302")
    # Switch off (default): no run.
    assert client.post(f"{L}/rent-increase-proposals/run", headers=h).status_code == 409
    terms = {
        "index_agreement": {
            "index_name": SERIES,
            "base_index": "100",
            "base_month": "2023-01-01",
            "source": "Paragraph 4 Mietvertrag (Test)",
        }
    }
    url = f"{L}/contracts/{indexed}/index-terms"
    assert client.put(url, json=terms, headers=hr).status_code == 403
    both = terms | {"graduated_steps": [{"valid_from": "2027-01-01", "net": "650.00"}]}
    assert client.put(url, json=both, headers=h).status_code == 422
    mid = {"index_agreement": terms["index_agreement"] | {"base_month": "2023-01-15"}}
    assert client.put(url, json=mid, headers=h).status_code == 422
    out = _ok(client.put(url, json=terms, headers=h))
    assert out["index_agreement"]["base_index"] == "100"
    assert client.get(url, headers=ho).status_code == 404
    today = local_today()
    near, far = today + timedelta(days=30), today + timedelta(days=400)
    steps = {
        "graduated_steps": [
            {"valid_from": near.isoformat(), "net": "650.00"},
            {"valid_from": far.isoformat(), "net": "700.00"},
        ]
    }
    _ok(client.put(f"{L}/contracts/{graduated}/index-terms", json=steps, headers=h))

    _ok(
        client.put(
            f"{L}/rent-increase-settings",
            json={"block_months": {}, "proposals": "draft"},
            headers=h,
        )
    )
    counts = _ok(client.post(f"{L}/rent-increase-proposals/run", headers=h))
    # Index values were imported and released in the first test of this module.
    assert (counts["graduated"], counts["index"]) == (1, 1)
    proposals = _ok(client.get(f"{L}/rent-increase-proposals", headers=h))
    by_contract = {p["contract_id"]: p for p in proposals}
    step = by_contract[graduated]
    assert (step["basis"], step["current_rent"], step["target_rent"]) == (
        "graduated",
        "600.00",
        "650.00",
    )
    assert step["effective_date"] == near.isoformat()
    assert step["status"] == "draft"
    idx = by_contract[indexed]
    assert (idx["current_rent"], idx["target_rent"]) == ("600.00", "663.00")
    assert idx["basis_data"]["index_current"] == "110.50000000"
    again = _ok(client.post(f"{L}/rent-increase-proposals/run", headers=h))
    assert (again["graduated"], again["index"]) == (0, 0)
    # The rent itself is unchanged: no new rent line was created.
    pays = _ok(client.get(f"/api/v1/contracts/{graduated}/payments", headers=h))
    items = pays["items"] if isinstance(pays, dict) else pays
    assert [p["net"] for p in items if p["payment_type_code"] == "rent"] == ["600.00"]
    assert _ok(client.get(f"{L}/rent-increase-proposals", headers=ho)) == []
