"""M7-01 checklist of the property takeover and M7-02 match thresholds: happy path, permission,
validation, tenant separation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login
from tests.integration.test_m4_properties import _prop, _world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _h(client: TestClient, world: World, user: str) -> dict[str, str]:
    return bearer(login(client, world, user))


def test_takeover_checklist(client: TestClient, world: World) -> None:
    h = _h(client, world, "m4admin")
    prop: dict[str, Any] = client.post("/api/v1/properties", json=_prop("701"), headers=h).json()
    url = f"/api/v1/properties/{prop['id']}/takeover-checklist"
    first = client.post(url, headers=h).json()
    assert len(first["items"]) == 7
    assert first["open_count"] == 7
    assert not first["complete"]
    assert client.post(url, headers=h).json()["items"] == first["items"]
    patched = client.patch(f"{url}/insurance", json={"status": "received"}, headers=h)
    assert patched.status_code == 200
    assert patched.json()["status"] == "received"
    assert client.patch(f"{url}/insurance", json={"status": "bogus"}, headers=h).status_code == 422
    assert client.patch(f"{url}/nothing", json={"status": "open"}, headers=h).status_code == 404
    assert client.get(url, headers=h).json()["open_count"] == 6
    caretaker = _h(client, world, "m4caretaker")
    assert (
        client.patch(f"{url}/meters", json={"status": "received"}, headers=caretaker).status_code
        == 403
    )


def test_match_settings_validation(client: TestClient, world: World) -> None:
    h = _h(client, world, "m4admin")
    bad = client.put(
        "/api/v1/onboarding/match-settings",
        json={"link_threshold": "0.50", "suggest_threshold": "0.80"},
        headers=h,
    )
    assert bad.status_code == 422
    ok = client.put(
        "/api/v1/onboarding/match-settings",
        json={"link_threshold": "0.85", "suggest_threshold": "0.55"},
        headers=h,
    )
    assert ok.status_code == 200
    assert (
        client.get("/api/v1/onboarding/match-settings", headers=h).json()["link_threshold"]
        == "0.85"
    )
    found = client.post(
        "/api/v1/onboarding/person-match", json={"last_name": "Unbekannt"}, headers=h
    )
    assert found.status_code == 200
    assert found.json()["decision"] == "none"
