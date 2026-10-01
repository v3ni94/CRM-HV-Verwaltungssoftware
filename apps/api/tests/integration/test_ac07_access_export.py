"""AC07 (GA08-06, 7.11 S06): the data subject access export is built from an allowlist, holds
no secrets (hashes, fingerprints, tokens, internal notes, AI raw data) and no data of other
persons (only their role), and can be downloaded only after review and release by a second
person; every step is logged."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ac07a-{RUN}", name=f"AC07 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ac07b-{RUN}", name=f"AC07 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ac07prep", a, "tenant_admin"),
            ("ac07rev", a, "tenant_admin"),
            ("ac07view", a, "read_only"),
            ("ac07other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _setup(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    subject = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Clara",
                "last_name": f"Auskunft{RUN}",
                "notes": "Interner Vermerk: schwieriger Kontakt",
                "emails": [{"email": f"clara.{RUN}@example.org"}],
                "bank_accounts": [
                    {
                        "iban": "DE02 1203 0000 0000 2020 51",
                        "valid_from": "2026-01-01",
                        "holder": f"Dora Fremd{RUN}",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    third = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Dora", "last_name": f"Fremd{RUN}"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/parties",
            json={
                "members": [
                    {"contact_id": subject["id"], "role": "primary", "share_percent": "50"},
                    {"contact_id": third["id"], "role": "co_party", "share_percent": "50"},
                ]
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contacts/{subject['id']}/relations",
            json={"related_contact_id": third["id"], "kind": "spouse"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contacts/{subject['id']}/notes",
            json={"body": "Geheimer Rückrufvermerk"},
            headers=h,
        ),
        201,
    )
    return subject["id"], third["id"]


def test_access_export_review_release_download(client: TestClient, world: World) -> None:
    prep = bearer(login(client, world, "ac07prep"))
    rev = bearer(login(client, world, "ac07rev"))
    contact_id, third_id = _setup(client, prep)
    base = f"/api/v1/contacts/{contact_id}/access-exports"

    # The old direct download is closed.
    assert client.get(f"/api/v1/contacts/{contact_id}/export", headers=prep).status_code == 409

    export = _ok(client.post(base, headers=prep), 201)
    assert export["status"] == "prepared"
    url = f"{base}/{export['id']}"

    # Without review and release no download.
    blocked = client.get(f"{url}/download", headers=prep)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MHVP-CONT-0030"
    # The preparer cannot review (second person).
    four_eyes = client.post(f"{url}/review", headers=prep)
    assert four_eyes.status_code == 403
    assert four_eyes.json()["code"] == "MHVP-CONT-0031"
    # Release before review is refused.
    assert client.post(f"{url}/approve", headers=rev).status_code == 409

    preview = _ok(client.get(f"{url}/preview", headers=rev))
    assert preview["for_review_only"] is True

    assert _ok(client.post(f"{url}/review", headers=rev))["status"] == "reviewed"
    assert client.get(f"{url}/download", headers=rev).status_code == 409
    assert client.post(f"{url}/approve", headers=prep).status_code == 403
    released = _ok(client.post(f"{url}/approve", headers=rev))
    assert released["status"] == "released"
    assert released["reviewed_by"] == str(world.users["ac07rev"])

    data = _ok(client.get(f"{url}/download", headers=prep))
    text = str(data)
    # Own data present.
    assert data["contact"]["last_name"] == f"Auskunft{RUN}"
    assert data["bank_accounts"][0]["iban"].replace(" ", "").startswith("DE02")
    # Secrets and internal data absent.
    keys = _keys(data["contact"]) | _keys(data["bank_accounts"])
    assert not {k for k in keys if "hash" in k or "fingerprint" in k or "token" in k}
    assert "iban_fingerprint" not in text
    assert "external_ids" not in keys
    assert "notes" not in keys
    assert "Geheimer Rückrufvermerk" not in text
    assert "schwieriger Kontakt" not in text
    assert data["withheld"]["internal_notes_count"] == 2
    # Other person: neither name nor id, only the role.
    assert f"Fremd{RUN}" not in text
    assert "Dora" not in text
    assert third_id not in text
    assert data["relations"] == [
        {"kind": "spouse", "related_person": "Dritte Person (Angaben zurückgehalten)"}
    ]
    assert data["parties"] == [{"own_role": "primary", "further_members": 1}]
    assert data["bank_accounts"][0]["holder"] == "Dritte Person (Angaben zurückgehalten)"
    # Processing log without payloads.
    assert all(set(e) == {"type", "occurred_at"} for e in data["processing_log"])

    listed = _ok(client.get(base, headers=prep))
    mine = next(x for x in listed if x["id"] == export["id"])
    assert mine["downloads"] == 1
    assert [e["type"] for e in mine["log"]] == [
        "contact.access_export.prepared",
        "contact.access_export.reviewed",
        "contact.access_export.released",
        "contact.access_export.downloaded",
    ]

    # Changing the data after the review invalidates the export.
    second = _ok(client.post(base, headers=prep), 201)
    surl = f"{base}/{second['id']}"
    _ok(client.post(f"{surl}/review", headers=rev))
    current = _ok(client.get(f"/api/v1/contacts/{contact_id}", headers=prep))
    _ok(
        client.patch(
            f"/api/v1/contacts/{contact_id}",
            json={"position": "Beirat"},
            headers={**prep, "If-Match": str(current["version"])},
        )
    )
    changed = client.post(f"{surl}/approve", headers=rev)
    assert changed.status_code == 409
    assert changed.json()["code"] == "MHVP-CONT-0032"
    rejected = _ok(client.post(f"{surl}/reject", json={"reason": "Daten geändert"}, headers=rev))
    assert rejected["status"] == "rejected"
    assert client.post(f"{surl}/reject", json={"reason": "x"}, headers=rev).status_code == 422


def test_access_export_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    prep = bearer(login(client, world, "ac07prep"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Eva", "last_name": f"Rls{RUN}"},
            headers=prep,
        ),
        201,
    )
    base = f"/api/v1/contacts/{contact['id']}/access-exports"
    export = _ok(client.post(base, headers=prep), 201)
    viewer = bearer(login(client, world, "ac07view"))
    assert client.post(base, headers=viewer).status_code == 403
    assert client.post(f"{base}/{export['id']}/review", headers=viewer).status_code == 403
    other = bearer(login(client, world, "ac07other"))
    assert client.post(base, headers=other).status_code == 404
    assert client.get(f"{base}/{export['id']}/download", headers=other).status_code == 404
    assert client.get(base, headers=other).status_code == 404
    unknown = f"/api/v1/contacts/{uuid.uuid4()}/access-exports"
    assert client.post(unknown, headers=prep).status_code == 404
    wrong = f"/api/v1/contacts/{contact['id']}/access-exports/{uuid.uuid4()}/download"
    assert client.get(wrong, headers=prep).status_code == 404
    assert client.get(base, params={"x": "1"}, headers=prep).status_code == 422
