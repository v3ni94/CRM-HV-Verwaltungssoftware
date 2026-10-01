"""AE16 / AA11-01, AA11-02: text blocks with release workflow.

Expected (hand derived): a new text starts as draft version 1; only an approved text is
shown in the code list (released, version 1) and printed. Author and submitter cannot approve
(four eyes, 403/409 problem); a second approved version retires version 1; a reader may not
write (403); another tenant sees 404; unknown code and empty body give 422.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
B = "/api/v1/document-text-blocks"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae16a-{RUN}", name=f"AE16 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae16b-{RUN}", name=f"AE16 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae16first", a, "tenant_admin"),
            ("ae16second", a, "tenant_admin"),
            ("ae16reader", a, "read_only"),
            ("ae16other", b, "tenant_admin"),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def test_text_block_lifecycle(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "ae16first"))
    h2 = bearer(login(client, world, "ae16second"))
    hr = bearer(login(client, world, "ae16reader"))
    ho = bearer(login(client, world, "ae16other"))
    code = "info_sheet_inspection"

    codes = client.get(f"{B}/codes", headers=h1).json()["items"]
    row = next(i for i in codes if i["code"] == code)
    assert row["released"] is False
    assert row["display"] == "Text nicht freigegeben"

    # validation and permission
    assert (
        client.post(B, json={"code": "x", "title": "t", "body": "b"}, headers=h1).status_code == 422
    )
    assert (
        client.post(B, json={"code": code, "title": "t", "body": ""}, headers=h1).status_code == 422
    )
    assert (
        client.post(B, json={"code": code, "title": "t", "body": "b"}, headers=hr).status_code
        == 403
    )
    assert client.get(f"{B}?unknown=1", headers=h1).status_code == 422

    v1 = client.post(B, json={"code": code, "title": "Belegeinsicht", "body": "Text 1"}, headers=h1)
    assert v1.status_code == 201, v1.text
    bid = v1.json()["id"]
    assert v1.json()["version"] == 1
    assert v1.json()["status"] == "draft"
    assert client.get(f"{B}/{bid}", headers=ho).status_code == 404

    # not submitted yet: cannot approve
    assert client.post(f"{B}/{bid}/approve", headers=h2).status_code == 409
    assert (
        client.patch(f"{B}/{bid}", json={"body": "Text 1b"}, headers=h1).json()["body"] == "Text 1b"
    )
    assert client.post(f"{B}/{bid}/submit", headers=h1).json()["status"] == "submitted"
    assert client.patch(f"{B}/{bid}", json={"body": "x"}, headers=h1).status_code == 409
    # draft/submitted is never released
    assert not next(
        i for i in client.get(f"{B}/codes", headers=h1).json()["items"] if i["code"] == code
    )["released"]
    # four eyes
    assert client.post(f"{B}/{bid}/approve", headers=h1).status_code in (403, 409)
    done = client.post(f"{B}/{bid}/approve", headers=h2)
    assert done.status_code == 200
    assert done.json()["status"] == "approved"
    assert (
        next(i for i in client.get(f"{B}/codes", headers=h1).json()["items"] if i["code"] == code)[
            "approved_version"
        ]
        == 1
    )

    # second version retires the first one
    v2 = client.post(
        B, json={"code": code, "title": "Belegeinsicht", "body": "Text 2"}, headers=h2
    ).json()
    assert v2["version"] == 2
    client.post(f"{B}/{v2['id']}/submit", headers=h2)
    assert client.post(f"{B}/{v2['id']}/approve", headers=h2).status_code in (403, 409)
    assert client.post(f"{B}/{v2['id']}/approve", headers=h1).status_code == 200
    assert client.get(f"{B}/{bid}", headers=h1).json()["status"] == "retired"

    # reject returns to draft with reason
    v3 = client.post(B, json={"code": code, "title": "t", "body": "Text 3"}, headers=h1).json()
    client.post(f"{B}/{v3['id']}/submit", headers=h1)
    rej = client.post(f"{B}/{v3['id']}/reject", json={"reason": "unklar"}, headers=h2).json()
    assert rej["status"] == "draft"
    assert rej["reject_reason"] == "unklar"


def test_texts_are_printed_only_when_approved() -> None:
    from datetime import date

    from mhvp.billing import info_sheet

    kw: dict[str, Any] = {
        "period_from": date(2025, 1, 1),
        "period_to": date(2025, 12, 31),
        "object_line": "Objekt 1",
        "snapshot_inputs": {"positions": []},
        "snapshot_hash": "a" * 64,
        "version": 1,
        "letter_date": date(2026, 10, 1),
    }
    pending = info_sheet.build(**kw)
    assert "Text nicht freigegeben" in pending.body
    released = info_sheet.build(
        **kw, texts={"inspection": "Freigegebener Text A", "objection": "Freigegebener Text B"}
    )
    assert "Freigegebener Text A" in released.body
    assert "Text nicht freigegeben" not in released.body
