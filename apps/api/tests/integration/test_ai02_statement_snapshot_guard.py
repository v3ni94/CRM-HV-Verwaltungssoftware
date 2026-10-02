"""AI02: the database refuses UPDATE and DELETE on statement_snapshot (GAH-103, 6.9.3, B03)
and the liquidity preview carries the common report header and an Excel variant (GAH-104)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_a61_inspection import _world
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "ai02", "ai02admin", "ai02reader"))


@pytest.fixture(scope="module")
def other_world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "ai02b", "ai02other"))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


LEDGERS: dict[str, str] = {}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _run(database: Database, redis_url: str, world: World, fn: Any) -> Any:
    async def go() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_statement_snapshot_is_insert_only(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.accounting.models import Ledger
    from mhvp.billing.models import Statement, StatementKind, StatementSnapshot
    from mhvp.billing.status import StatementStatus

    h = bearer(login(client, world, "ai02admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "902", "name": "Miete AI02", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(client, h, "EigAI02", "company")
    entity = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]

    async def seed(session: Any) -> UUID:
        ledger = Ledger(
            tenant_id=world.tenant_a,
            legal_entity_id=UUID(entity),
            property_id=UUID(prop["id"]),
            name="AI02 Ledger",
        )
        session.add(ledger)
        await session.flush()
        st = Statement(
            tenant_id=world.tenant_a,
            kind=StatementKind.OPERATING_COSTS,
            ledger_id=ledger.id,
            property_id=UUID(prop["id"]),
            period_from=date(2025, 1, 1),
            period_to=date(2025, 12, 31),
            status=StatementStatus.CALCULATED,
        )
        session.add(st)
        await session.flush()
        snap = StatementSnapshot(
            tenant_id=world.tenant_a,
            statement_id=st.id,
            rule_version="ai02",
            hash="a" * 64,
            inputs={"positions": []},
            results={"results": [{"balance": "50.00"}]},
        )
        session.add(snap)
        await session.flush()
        st.snapshot_id = snap.id
        await session.flush()
        return snap.id, ledger.id

    snap_id, ledger_id = _run(database, redis_url, world, seed)
    LEDGERS["ai02"] = str(ledger_id)

    for statement in (
        "UPDATE statement_snapshot SET hash = :h WHERE id = :id",
        "UPDATE statement_snapshot SET results = '{}'::jsonb WHERE id = :id",
        "DELETE FROM statement_snapshot WHERE id = :id",
    ):

        async def attempt(session: Any, sql: str = statement) -> None:
            await session.execute(text(sql), {"id": snap_id, "h": "0" * 64})

        with pytest.raises(DBAPIError, match="statement_snapshot is insert only"):
            _run(database, redis_url, world, attempt)

    async def read(session: Any) -> tuple[str, Any]:
        row = (
            await session.execute(
                text("SELECT hash, results FROM statement_snapshot WHERE id = :id"),
                {"id": snap_id},
            )
        ).one()
        return row[0], row[1]

    assert _run(database, redis_url, world, read) == (
        "a" * 64,
        {"results": [{"balance": "50.00"}]},
    )


def test_liquidity_report_header_and_xlsx(
    client: TestClient, world: World, other_world: World
) -> None:
    ledger = LEDGERS["ai02"]
    base = f"/api/v1/accounting/ledgers/{ledger}/reports"
    h = bearer(login(client, world, "ai02admin"))
    body = _ok(client.get(f"{base}/liquidity", params={"as_of": "2026-03-31"}, headers=h))
    header = body["header"]
    assert header["report"] == "liquidity"
    assert header["legal_entity_name"]
    assert header["as_of"] == "2026-03-31"
    assert header["status"] == "draft"
    assert header["filters"] == {"horizon": "2026-06-29"}
    assert body["horizon"] == "2026-06-29"
    assert body["free_funds"] == "0.00"
    assert body["accounts"] == []

    xlsx = client.get(
        f"{base}/xlsx", params={"report": "liquidity", "as_of": "2026-03-31"}, headers=h
    )
    assert xlsx.status_code == 200, xlsx.text
    assert xlsx.content[:2] == b"PK"
    assert "liquidity-" in xlsx.headers["content-disposition"]

    # validation, read permission for the export, tenant separation
    bad = client.get(f"{base}/liquidity", params={"as_of": "kein-datum"}, headers=h)
    assert bad.status_code == 422
    reader = bearer(login(client, world, "ai02reader"))
    assert client.get(f"{base}/liquidity", headers=reader).status_code == 200
    denied = client.get(f"{base}/xlsx", params={"report": "liquidity"}, headers=reader)
    assert denied.status_code == 403
    other = bearer(login(client, other_world, "ai02other"))
    assert client.get(f"{base}/liquidity", headers=other).status_code == 404
