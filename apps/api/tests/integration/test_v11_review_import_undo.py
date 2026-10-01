"""V11 review (01.10.2026) of the U13 import undo: a SEPA overview row never creates a payment
schedule after the end of the contract, and the undo of a schedule reopens the previous one
only up to the contract end (never an open schedule on an ended contract)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_q08_import_history import _ok, _setup
from tests.integration.test_u13_import_history import SEPA_COLS, SEPA_HEAD, SEPA_MAPS, _apply

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"v11-{RUN}", name=f"V11 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"v11b-{RUN}", name=f"V11b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("v11admin"), display_name="v11admin", password=PASSWORD
        )
        world.users["v11admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _end_contract(database: Database, tenant_id: Any, contract_id: str, end: str) -> None:
    """Ownership ends only by a transfer; the test sets the end directly like a finished
    transfer would (end date and closed schedules)."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            conn.execute(
                text("UPDATE contract SET end_date = :e WHERE id = :id"),
                {"e": end, "id": contract_id},
            )
            conn.execute(
                text(
                    "UPDATE payment_schedule SET valid_to = :e "
                    "WHERE contract_id = :id AND valid_to IS NULL"
                ),
                {"e": end, "id": contract_id},
            )
    finally:
        engine.dispose()


def _row(due_day: str, valid_from: str) -> list[Any]:
    return ["881", "01", "K881", "E", "quartalsweise", due_day, valid_from] + [None] * 5


def test_schedule_import_and_undo_respect_contract_end(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "v11admin"))
    contract_id = _setup(client, h)["contract"]["id"]
    _, report1 = _apply(
        client,
        h,
        "sepa_overview",
        [SEPA_HEAD, _row("5", "01.01.2026")],
        SEPA_COLS,
        "a.xlsx",
        **SEPA_MAPS,
    )
    assert report1["counts"] == {"created": 1}
    run2, report2 = _apply(
        client,
        h,
        "sepa_overview",
        [SEPA_HEAD, _row("3", "01.04.2026")],
        SEPA_COLS,
        "b.xlsx",
        **SEPA_MAPS,
    )
    assert report2["counts"] == {"created": 1}
    # Contract ends on 30.06.2026: schedule of run 2 is closed on that day.
    _end_contract(database, world.tenant_a, contract_id, "2026-06-30")
    # A row starting after the end finds no contract (no schedule after the end).
    _, report3 = _apply(
        client,
        h,
        "sepa_overview",
        [SEPA_HEAD, _row("7", "01.10.2026")],
        SEPA_COLS,
        "c.xlsx",
        **SEPA_MAPS,
    )
    assert report3["counts"] == {"invalid": 1}
    # Undo of run 2: the schedule of run 1 is reopened up to 30.06.2026, not open ended.
    _ok(client.post(f"/api/v1/imports/{run2}/undo", headers=h))
    schedules = _ok(client.get(f"/api/v1/contracts/{contract_id}", headers=h))["schedules"]
    assert [(s["due_day"], s["valid_to"]) for s in schedules] == [(5, "2026-06-30")]
