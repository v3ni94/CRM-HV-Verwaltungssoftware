"""AL05 (GAI-110): filters ``as_of`` and ``trigger`` of GET /accounting/payment-runs/previews."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.aj06_authz_world import AuthzWorld, build_world, headers, settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

URL = "/api/v1/accounting/payment-runs/previews"


async def _seed(cfg: Any, tenant: uuid.UUID) -> None:
    from mhvp.accounting.direct_debit_models import PaymentRunPreview
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant) as session:
            for as_of, trigger in (
                (date(2026, 9, 7), "manual"),
                (date(2026, 9, 7), "schedule"),
                (date(2026, 9, 14), "schedule"),
            ):
                session.add(
                    PaymentRunPreview(
                        tenant_id=tenant, as_of=as_of, trigger=trigger, summary={"invoice_count": 1}
                    )
                )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> AuthzWorld:
    w = build_world(database, redis_url)
    asyncio.run(_seed(settings(database, redis_url), w.tenant_a))
    return w


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings(database, redis_url))) as test_client:
        yield test_client


def test_filters_narrow_the_list(client: TestClient, world: AuthzWorld) -> None:
    h = headers(client, world, "aj06adm")
    assert len(client.get(URL, headers=h).json()) == 3
    by_date = client.get(URL, params={"as_of": "2026-09-07"}, headers=h).json()
    assert len(by_date) == 2
    by_trigger = client.get(URL, params={"trigger": "schedule"}, headers=h).json()
    assert {r["trigger"] for r in by_trigger} == {"schedule"}
    both = client.get(URL, params={"as_of": "2026-09-14", "trigger": "schedule"}, headers=h).json()
    assert len(both) == 1


def test_invalid_values_and_unknown_parameters(client: TestClient, world: AuthzWorld) -> None:
    h = headers(client, world, "aj06adm")
    assert client.get(URL, params={"trigger": "x"}, headers=h).status_code == 422
    assert client.get(URL, params={"as_of": "kaputt"}, headers=h).status_code == 422
    assert client.get(URL, params={"foo": "1"}, headers=h).status_code == 422


def test_other_tenant_sees_nothing(client: TestClient, world: AuthzWorld) -> None:
    h = headers(client, world, "aj06oth")
    assert client.get(URL, params={"as_of": "2026-09-07"}, headers=h).json() == []
