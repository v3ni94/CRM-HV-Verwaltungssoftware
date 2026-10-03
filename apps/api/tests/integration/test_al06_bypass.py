"""AL06 (review wave 22): bypass attempts against the wave 22 protections.

* four eyes on the deposit settlement release (AK14, GAI-410): the creator cannot release,
  neither directly nor by repeating the call with an idempotency key; a second person can;
* payout orders without invoice stay behind G2 (AK14, GAI-402) on every route, including
  the replay with an idempotency key;
* body limit (AK17, GAI-315) inside the full application: chunked transfer and a declared
  Content-Length that understates the real body;
* X-Forwarded-For without trusted networks (GAI-311) never changes the counted address.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.core.request_identity import client_ip
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_deposit_settlement import _deposit_with_movements, _settings

pytestmark = pytest.mark.integration


class OpenG3:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"6-al-{RUN}", name=f"AL06 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"6-am-{RUN}", name=f"AL06b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name in ("al06maker", "al06checker"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
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
def open_g3(database: Database, redis_url: str) -> Iterator[TestClient]:
    app = create_app(_settings(database, redis_url), release_gate_resolver=OpenG3())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def closed(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_deposit_release_four_eyes_bypass(open_g3: TestClient, world: World) -> None:
    maker = bearer(login(open_g3, world, "al06maker"))
    checker = bearer(login(open_g3, world, "al06checker"))
    deposit, _ = _deposit_with_movements(open_g3, maker)
    draft = open_g3.post(
        f"/api/v1/deposits/{deposit}/settlements",
        json={"settlement_date": "2026-06-30", "interest_mode": "none"},
        headers=maker,
    )
    assert draft.status_code == 201, draft.text
    release = f"/api/v1/deposit-settlements/{draft.json()['id']}/release"
    # Direct attempt and replays with idempotency keys by the creator: always refused.
    for extra in ({}, {"Idempotency-Key": f"al06-{RUN}-1"}, {"Idempotency-Key": f"al06-{RUN}-1"}):
        refused = open_g3.post(release, headers={**maker, **extra})
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "MHVP-CONTR-0002"
    listed = open_g3.get(f"/api/v1/deposits/{deposit}/settlements", headers=maker).json()
    assert listed[0]["status"] == "draft"
    # The second person releases; a later creator call stays a conflict (already released).
    ok = open_g3.post(release, headers=checker)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "released"
    again = open_g3.post(release, headers=maker)
    assert again.status_code == 409


def test_payout_without_invoice_stays_behind_g2(closed: TestClient, world: World) -> None:
    h = bearer(login(closed, world, "al06maker"))
    body = {
        "open_item_id": str(uuid.uuid4()),
        "contact_bank_account_id": str(uuid.uuid4()),
        "property_bank_account_id": str(uuid.uuid4()),
        "execution_date": "2026-10-05",
        "reason": "deposit_refund",
    }
    path = "/api/v1/accounting/payment-runs/payout-orders"
    for extra in ({}, {"Idempotency-Key": f"al06-{RUN}-p"}, {"Idempotency-Key": f"al06-{RUN}-p"}):
        refused = closed.post(path, json=body, headers={**h, **extra})
        assert refused.status_code == 403, refused.text
        assert refused.json()["gate"] == "G2"
    # The payable route checks the row first (no existence leak beyond the tenant), then gates.
    other = closed.post(
        f"/api/v1/accounting/credit-payables/{uuid.uuid4()}/payment-order",
        json={k: v for k, v in body.items() if k not in ("open_item_id", "reason")},
        headers=h,
    )
    assert other.status_code in (403, 404), other.text
    orders = closed.get("/api/v1/accounting/payment-orders", headers=h)
    if orders.status_code == 200:
        items = orders.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        assert all(o.get("kind") != "payout" for o in items)


@pytest.fixture
def small_limit(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url).model_copy(
        update={"body_limit_default_bytes": 2048, "body_limit_upload_bytes": 4096}
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _chunks(total: int) -> Iterator[bytes]:
    while total > 0:
        yield b"x" * min(512, total)
        total -= 512


def test_body_limit_chunked_and_understated_length(small_limit: TestClient) -> None:
    path = "/api/v1/auth/login"
    chunked = small_limit.post(
        path, content=_chunks(10_000), headers={"Content-Type": "application/json"}
    )
    assert chunked.status_code == 413, chunked.text
    assert chunked.json()["code"] == "MHVP-DOC-0010"
    lying = small_limit.post(
        path,
        content=b"x" * 10_000,
        headers={"Content-Type": "application/json", "Content-Length": "10"},
    )
    assert lying.status_code in (400, 413), lying.text
    overstated = small_limit.post(
        path,
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "999999"},
    )
    assert overstated.status_code == 413
    # Multipart on a JSON route uses the upload group (finding AL06-03): still bounded.
    multipart = small_limit.post(
        path,
        content=_chunks(10_000),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert multipart.status_code == 413


@pytest.mark.parametrize("chunked", [False, True])
def test_multipart_on_json_route_gets_default_limit(small_limit: TestClient, chunked: bool) -> None:
    """AM15 (AL06-01): the Content-Type no longer selects the larger upload limit."""
    headers = {"Content-Type": "multipart/form-data; boundary=x"}
    body = _chunks(3000) if chunked else b"x" * 3000  # above default 2048, below upload 4096
    r = small_limit.post("/api/v1/auth/login", content=body, headers=headers)
    assert r.status_code == 413, r.text
    assert r.json()["code"] == "MHVP-DOC-0010"
    # A registered upload route keeps the upload limit: not 413 (401 without login).
    body = _chunks(3000) if chunked else b"x" * 3000
    upload = small_limit.post("/api/v1/documents", content=body, headers=headers)
    assert upload.status_code != 413, upload.text
    # Upload route with JSON Content-Type: still the upload group, bounded by its limit.
    over = small_limit.post(
        "/api/v1/documents", content=b"x" * 5000, headers={"Content-Type": "application/json"}
    )
    assert over.status_code == 413


def test_forwarded_for_without_trusted_networks() -> None:
    scope = {
        "type": "http",
        "client": ("10.9.8.7", 5000),
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
    }
    assert client_ip(scope, trust_forwarded_for=False, trusted_proxies=[]) == "10.9.8.7"
    # Invalid CIDR entries do not turn trust on.
    assert client_ip(scope, trust_forwarded_for=False, trusted_proxies=["nonsense"]) == "10.9.8.7"
    # Peer not in the trusted net: header ignored.
    assert client_ip(scope, trust_forwarded_for=False, trusted_proxies=["172.16.0.0/12"]) == (
        "10.9.8.7"
    )
    # Trusted peer: the rightmost untrusted hop counts, a prepended value does not.
    assert client_ip(scope, trust_forwarded_for=False, trusted_proxies=["10.0.0.0/8"]) == (
        "5.6.7.8"
    )


def test_forwarded_for_does_not_open_new_rate_counters(database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url).model_copy(
        update={"rate_limit_enabled": True, "rate_limit_per_minute_anonymous": 3}
    )
    with TestClient(create_app(settings)) as c:
        codes = [
            c.get(
                "/api/v1/al06-missing",
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            ).status_code
            for i in range(6)
        ]
    assert 429 in codes, codes
