"""AO07: direct debit creator switch (GAK-106) and unvalidated CHECK constraints (AN14-07).

Own world with prefix ``ao07-<run>``; the scratch table for the constraint test carries no
tenant data and is dropped again.
"""

import asyncio
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from mhvp.core.problems import ProblemError
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration

RUN = f"ao07-{uuid.uuid4().hex[:8]}"
SW = "/api/v1/accounting/direct-debit-settings"
CC = "/api/v1/platform/constraint-checks"


def _email(name: str) -> str:
    return f"{name}-{RUN}@example.org"


async def _build(cfg: Any) -> dict[str, uuid.UUID]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(cfg)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        tenant, _ = await services.provision_tenant(factory, slug=f"{RUN}-a", name=f"AO07 {RUN}")
        ids["tenant"] = tenant
        for name, role in (("adm", "tenant_admin"), ("rd", "read_only")):
            uid = await services.create_user(
                factory, email=_email(name), display_name=name, password=PASSWORD
            )
            ids[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def ids(database: Database, redis_url: str) -> dict[str, uuid.UUID]:
    return asyncio.run(_build(base_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(
        create_app(
            base_settings(
                database, redis_url, migration_database_url=SecretStr(database.migrator_url)
            )
        )
    ) as c:
        yield c


def _h(client: TestClient, name: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": _email(name), "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_creator_switch_api(client: TestClient, ids: dict[str, uuid.UUID]) -> None:
    adm, rd = _h(client, "adm"), _h(client, "rd")
    assert client.get(SW, headers=adm).json()["direct_debit_creator_may_not_approve"] is False
    assert client.get(SW, headers=rd).status_code == 200
    body = {"direct_debit_creator_may_not_approve": True}
    assert client.put(SW, json=body, headers=rd).status_code == 403
    assert client.put(SW, json={"x": 1}, headers=adm).status_code == 422
    assert client.put(SW, json=body, headers=adm).json() == body
    assert client.get(SW, headers=adm).json() == body
    assert client.get(SW + "?foo=1", headers=adm).status_code == 422


def test_creator_may_not_approve_when_switch_on(
    client: TestClient, ids: dict[str, uuid.UUID], database: Database, redis_url: str
) -> None:
    from mhvp.accounting.direct_debit import _ensure_creator_may_approve
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    adm = _h(client, "adm")
    creator, other = ids["adm"], uuid.uuid4()
    run: Any = SimpleNamespace(tenant_id=ids["tenant"], created_by=creator)

    async def check(user: uuid.UUID, created_by: uuid.UUID | None) -> str | None:
        run.created_by = created_by
        engine = create_app_engine(base_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, ids["tenant"]) as session:
                try:
                    await _ensure_creator_may_approve(session, run, user)
                except ProblemError as exc:
                    return exc.error.code
                return None
        finally:
            await engine.dispose()

    on = {"direct_debit_creator_may_not_approve": True}
    off = {"direct_debit_creator_may_not_approve": False}
    client.put(SW, json=off, headers=adm)
    assert asyncio.run(check(creator, creator)) is None  # default off: unchanged
    client.put(SW, json=on, headers=adm)
    assert asyncio.run(check(creator, creator)) == "MHVP-GATE-0002"
    assert asyncio.run(check(other, creator)) is None
    assert asyncio.run(check(creator, None)) is None
    client.put(SW, json=off, headers=adm)


def test_unvalidated_constraint_report_and_validate(
    client: TestClient, ids: dict[str, uuid.UUID], database: Database
) -> None:
    adm, rd = _h(client, "adm"), _h(client, "rd")
    eng = create_engine(database.migrator_url)
    table = f"ao07_scratch_{uuid.uuid4().hex[:6]}"
    with eng.begin() as conn:
        conn.execute(text(f"CREATE TABLE {table} (v int)"))
        conn.execute(text(f"GRANT SELECT ON {table} TO {database.app_role}"))
        conn.execute(text(f"INSERT INTO {table} VALUES (-1), (5)"))
        conn.execute(
            text(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table} CHECK (v >= 0) NOT VALID")
        )
    try:
        assert client.get(CC, headers=rd).status_code == 200
        assert client.post(f"{CC}/validate", headers=rd).status_code == 403
        found = [
            c for c in client.get(CC, headers=adm).json()["constraints"] if c["table"] == table
        ]
        assert found == [{"constraint": f"ck_{table}", "table": table, "violations": 1}]
        assert client.get(CC, headers=adm).json()["ok"] is False
        bad = client.post(f"{CC}/validate", headers=adm)
        assert bad.status_code == 409, bad.text
        assert bad.json()["code"] == "MHVP-ACC-0041"
        assert any(c["table"] == table for c in bad.json()["constraints"])
        with eng.begin() as conn:
            conn.execute(text(f"DELETE FROM {table} WHERE v < 0"))
        good = client.post(f"{CC}/validate", headers=adm)
        assert good.status_code == 200, good.text
        assert all(c["table"] != table for c in good.json()["constraints"])
    finally:
        with eng.begin() as conn:
            conn.execute(text(f"DROP TABLE {table}"))
        eng.dispose()
