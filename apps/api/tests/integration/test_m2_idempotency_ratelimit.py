"""A48 idempotency middleware and A49 rate limiting (section 12)."""

import asyncio
import json
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.idempotency import REPLAYED_HEADER, STATE_IN_PROGRESS, fingerprint, redis_key
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, _settings, bearer, login

pytestmark = pytest.mark.integration
RUN = uuid.uuid4().hex[:8]
CONTACTS = "/api/v1/contacts"


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(
        create_app(_settings(database, redis_url, rate_limit_enabled=True))
    ) as test_client:
        yield test_client


def _person(suffix: str) -> dict[str, str]:
    return {"kind": "person", "first_name": "Ida", "last_name": f"Idem{RUN}{suffix}"}


def _count(client: TestClient, headers: dict[str, str], last_name: str) -> int:
    listed = client.get(CONTACTS, params={"q": last_name, "page_size": 200}, headers=headers)
    assert listed.status_code == 200, listed.text
    return sum(1 for item in listed.json()["items"] if last_name in item["display_name"])


def _ident(token: dict[str, object], tenant_id: uuid.UUID) -> str:
    # Scope key of the middleware: tenant hex plus user id from the token subject.
    import jwt

    sub = jwt.decode(str(token["access_token"]), options={"verify_signature": False})["sub"]
    return f"{tenant_id.hex}:user:{uuid.UUID(sub).hex}"


# A48 -------------------------------------------------------------------------------------


def test_idempotent_replay_has_no_second_effect(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    body = _person("a")
    key = f"key-{RUN}-a"
    first = client.post(CONTACTS, json=body, headers={**headers, "Idempotency-Key": key})
    assert first.status_code == 201, first.text
    assert REPLAYED_HEADER not in first.headers

    second = client.post(CONTACTS, json=body, headers={**headers, "Idempotency-Key": key})
    assert second.status_code == 201, second.text
    assert second.headers[REPLAYED_HEADER] == "true"
    assert second.headers["content-type"] == first.headers["content-type"]
    assert second.json() == first.json()
    assert _count(client, headers, body["last_name"]) == 1

    # Without the header the endpoint behaves as before (no idempotency, second contact).
    plain = client.post(CONTACTS, json=body, headers=headers)
    assert plain.status_code == 201, plain.text
    assert _count(client, headers, body["last_name"]) == 2


def test_same_key_with_other_body_is_rejected(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    key = f"key-{RUN}-b"
    first = client.post(CONTACTS, json=_person("b"), headers={**headers, "Idempotency-Key": key})
    assert first.status_code == 201, first.text
    other = client.post(CONTACTS, json=_person("b2"), headers={**headers, "Idempotency-Key": key})
    assert other.status_code == 422, other.text
    assert other.json()["code"] == "MHVP-CORE-0007"
    assert other.headers["content-type"].startswith("application/problem+json")

    invalid = client.post(CONTACTS, json=_person("b3"), headers={**headers, "Idempotency-Key": ""})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "MHVP-CORE-0009"


def test_concurrent_first_call_yields_409(client: TestClient, world: World, redis_url: str) -> None:
    token = login(client, world, "admin")
    headers = bearer(token)
    key = f"key-{RUN}-c"
    body = _person("c")
    raw = json.dumps(body, separators=(",", ":")).encode()
    # Simulate a first call that is still running: the record exists in state in_progress.
    record_key = redis_key(_ident(token, world.tenant_a), key)
    redis = Redis.from_url(redis_url)
    try:
        redis.set(
            record_key,
            json.dumps(
                {"state": STATE_IN_PROGRESS, "fingerprint": fingerprint("POST", CONTACTS, raw)}
            ),
            ex=60,
        )
        blocked = client.post(
            CONTACTS,
            content=raw,
            headers={**headers, "Idempotency-Key": key, "content-type": "application/json"},
        )
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["code"] == "MHVP-CORE-0008"
        assert blocked.headers["Retry-After"] == "1"
        assert _count(client, headers, body["last_name"]) == 0
        redis.delete(record_key)
    finally:
        redis.close()
    # After the lock is released the request executes once and replays afterwards.
    done = client.post(
        CONTACTS,
        content=raw,
        headers={**headers, "Idempotency-Key": key, "content-type": "application/json"},
    )
    assert done.status_code == 201, done.text
    again = client.post(
        CONTACTS,
        content=raw,
        headers={**headers, "Idempotency-Key": key, "content-type": "application/json"},
    )
    assert again.headers[REPLAYED_HEADER] == "true"
    assert _count(client, headers, body["last_name"]) == 1


def test_same_key_in_other_tenant_acts_separately(client: TestClient, world: World) -> None:
    key = f"key-{RUN}-d"
    body = _person("d")
    in_a = bearer(login(client, world, "both", tenant_id=world.tenant_a))
    in_b = bearer(login(client, world, "both", tenant_id=world.tenant_b))
    first = client.post(CONTACTS, json=body, headers={**in_a, "Idempotency-Key": key})
    assert first.status_code == 201, first.text
    second = client.post(CONTACTS, json=body, headers={**in_b, "Idempotency-Key": key})
    assert second.status_code == 201, second.text
    assert REPLAYED_HEADER not in second.headers
    assert second.json()["id"] != first.json()["id"]
    assert _count(client, in_a, body["last_name"]) == 1
    assert _count(client, in_b, body["last_name"]) == 1

    # Another user of the same tenant with the same key: separate as well.
    admin = bearer(login(client, world, "admin"))
    third = client.post(CONTACTS, json=body, headers={**admin, "Idempotency-Key": key})
    assert third.status_code == 201, third.text
    assert REPLAYED_HEADER not in third.headers
    assert _count(client, admin, body["last_name"]) == 2


def test_failed_request_does_not_store_replay(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    key = f"key-{RUN}-e"
    bad = client.post(CONTACTS, json={"kind": "nope"}, headers={**headers, "Idempotency-Key": key})
    assert bad.status_code == 422
    # 4xx answers are stored too (deterministic), a replay returns the same problem.
    again = client.post(
        CONTACTS, json={"kind": "nope"}, headers={**headers, "Idempotency-Key": key}
    )
    assert again.status_code == 422
    assert again.headers[REPLAYED_HEADER] == "true"


# A49 -------------------------------------------------------------------------------------


def test_rate_limit_headers_and_health_exempt(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "admin"))
    listed = client.get(CONTACTS, headers=headers)
    assert listed.status_code == 200
    assert listed.headers["X-RateLimit-Limit"] == "600"
    remaining = int(listed.headers["X-RateLimit-Remaining"])
    assert 0 <= remaining < 600
    assert 1 <= int(listed.headers["X-RateLimit-Reset"]) <= 60
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert "X-RateLimit-Limit" not in live.headers
    # Unauthenticated requests count against the anonymous limit per client address.
    anonymous = client.post("/api/v1/auth/login", json={"email": "x@example.org", "password": "y"})
    assert anonymous.headers["X-RateLimit-Limit"] == "120"


def test_rate_limit_exceeded_returns_429(database: Database, redis_url: str, world: World) -> None:
    settings = _settings(database, redis_url, rate_limit_enabled=True, rate_limit_per_minute_user=3)

    async def fresh_user() -> str:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            email = f"rl-{RUN}@example.org"
            user_id = await services.create_user(
                factory, email=email, display_name="rl", password=PASSWORD
            )
            await services.add_member(
                factory,
                tenant_id=world.tenant_a,
                user_id=user_id,
                role_codes=["standard"],
                actor_user_id=None,
            )
            return email
        finally:
            await engine.dispose()

    email = asyncio.run(fresh_user())
    with TestClient(create_app(settings)) as strict:
        step = strict.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert step.status_code == 200, step.text
        assert step.json()["status"] == "ok", step.json()
        headers = bearer(step.json())
        seen: list[tuple[int, str]] = []
        for _ in range(3):
            ok = strict.get(CONTACTS, headers=headers)
            seen.append((ok.status_code, ok.headers["X-RateLimit-Remaining"]))
        assert seen == [(200, "2"), (200, "1"), (200, "0")]
        blocked = strict.get(CONTACTS, headers=headers)
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["code"] == "MHVP-CORE-0006"
        assert blocked.headers["content-type"].startswith("application/problem+json")
        assert blocked.headers["X-RateLimit-Remaining"] == "0"
        assert blocked.headers["Retry-After"] == blocked.headers["X-RateLimit-Reset"]
        assert 1 <= int(blocked.headers["Retry-After"]) <= 60
        # Health stays reachable while the user is limited.
        assert strict.get("/api/v1/health/live").status_code == 200


def test_forged_api_key_does_not_widen_the_limit(
    database: Database, redis_url: str, world: World
) -> None:
    """Sicherheitsreview 1.22, Befund 1: an API key is only parsed by the middleware, so a
    forged key must not open a fresh counter per prefix. Requests with any key are counted per
    client address; the fourth one is refused although every key differs."""
    settings = _settings(database, redis_url, rate_limit_enabled=True, rate_limit_per_minute_user=3)
    with TestClient(create_app(settings)) as strict:
        seen: list[tuple[int, str]] = []
        for index in range(3):
            key = f"mhvp_{world.tenant_a.hex}_forged{RUN}{index}_not-a-secret"
            answer = strict.get(CONTACTS, headers={"X-API-Key": key})
            seen.append((answer.status_code, answer.headers["X-RateLimit-Remaining"]))
        assert [status for status, _ in seen] == [401, 401, 401], seen
        assert [remaining for _, remaining in seen] == ["2", "1", "0"], seen
        blocked = strict.get(
            CONTACTS, headers={"X-API-Key": f"mhvp_{world.tenant_a.hex}_forged{RUN}x_not-a-secret"}
        )
        assert blocked.status_code == 429, blocked.text
        assert blocked.json()["code"] == "MHVP-CORE-0006"
