"""GA12-07 (section 16): detail pages below 500 ms (P95). Measures the detail endpoints of
a property, an ownership contract and a ticket with synthetic load data (30 units, 12 tickets).
Marked ``slow`` and skipped unless ``MHVP_PERF=1`` (scheduled run: .github/workflows/perf.yml,
runbook docs/runbooks/leistungsmessung.md). The CI threshold is generous (1 second) because
shared runners are noisy; the 500 ms target of section 16 is checked on the staging server."""

import asyncio
import os
import statistics
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("MHVP_PERF") != "1", reason="set MHVP_PERF=1 to measure"),
]
SAMPLES = 40
TARGET_SECONDS = 0.5  # section 16
CI_LIMIT_SECONDS = float(os.environ.get("MHVP_PERF_DETAIL_LIMIT", "1.0"))


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    settings = _settings(database, redis_url)

    async def build() -> World:
        from mhvp.core import crypto
        from mhvp.core.db.engine import create_app_engine, create_session_factory

        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            tenant, _ = await services.provision_tenant(
                factory, slug=f"ga12perf-{RUN}", name=f"GA12 Perf {RUN}"
            )
            w = World(
                tenant_a=tenant, tenant_b=tenant, app_url=settings.database_url.get_secret_value()
            )
            uid = await services.create_user(
                factory, email=w.email("ga12perf"), display_name="perf", password=PASSWORD
            )
            w.users["ga12perf"] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
            return w
        finally:
            await engine.dispose()

    return asyncio.run(build())


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _p95(client: TestClient, url: str, headers: dict[str, str]) -> tuple[float, float]:
    assert client.get(url, headers=headers).status_code == 200  # warm up and check
    timings: list[float] = []
    for _ in range(SAMPLES):
        started = time.perf_counter()
        response = client.get(url, headers=headers)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    timings.sort()
    return statistics.median(timings), timings[int(len(timings) * 0.95) - 1]


def test_detail_pages_p95(client: TestClient, world: World) -> None:
    from tests.integration.perf_seed import seed_units
    from tests.integration.test_m24_hoa import _owner

    headers = bearer(login(client, world, "ga12perf"))
    property_id = seed_units(client, headers, count=30)
    keys = {
        k["code"]: k["id"]
        for k in client.get(
            f"/api/v1/properties/{property_id}/allocation-keys", headers=headers
        ).json()
    }
    _, contract = _owner(
        client, headers, property_id, "900", "100", keys["MEA"], {"hoa_fee": "300.00"}
    )
    tickets = []
    for n in range(12):
        created = client.post(
            "/api/v1/tickets", json={"title": f"Probe {n}", "category": "Test"}, headers=headers
        )
        assert created.status_code == 201, created.text
        tickets.append(created.json()["id"])
    targets = {
        "property_detail": f"/api/v1/properties/{property_id}",
        "contract_detail": f"/api/v1/contracts/{contract['id']}",
        "ticket_detail": f"/api/v1/tickets/{tickets[0]}",
    }
    for name, url in targets.items():
        median, p95 = _p95(client, url, headers)
        print(  # noqa: T201 - measurement protocol
            f"PERF {name} samples={SAMPLES} median={median * 1000:.0f}ms p95={p95 * 1000:.0f}ms "
            f"target={TARGET_SECONDS * 1000:.0f}ms"
        )
        assert p95 < CI_LIMIT_SECONDS, (name, p95)
