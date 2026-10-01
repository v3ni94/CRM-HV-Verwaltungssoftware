"""S16-01/M2-03: passkey registration and sign in (second factor and passwordless) over the
API with a software authenticator: happy path, single use challenge, origin, sign counter,
user separation, validation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    _settings,
    bearer,
    login_password_only,
)
from tests.webauthn_fake import FakeAuthenticator

pytestmark = pytest.mark.integration
A = "/api/v1/auth"
RP, ORIGIN = "testserver", "http://testserver"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"s16-{RUN}", name=f"S16 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"s16b-{RUN}", name=f"S16 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("s16one", a), ("s16two", a), ("s16pwl", b), ("w01lock", a)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=["standard"], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


def _cfg(database: Database, redis_url: str) -> Any:
    return _settings(
        database, redis_url, webauthn_enabled=True, webauthn_rp_id=RP, webauthn_origins=[ORIGIN]
    )


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_cfg(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_cfg(database, redis_url))) as test_client:
        yield test_client


def _register(
    client: TestClient, h: dict[str, str], fake: FakeAuthenticator, passwordless: bool = False
) -> dict[str, Any]:
    opts = client.post(
        f"{A}/webauthn/register/options", json={"passwordless": passwordless}, headers=h
    )
    assert opts.status_code == 200, opts.text
    pk = opts.json()["public_key"]
    assert pk["rp"]["id"] == RP
    assert pk["attestation"] == "none"
    body = fake.create(pk) | {"challenge_id": opts.json()["challenge_id"], "label": "Laptop"}
    done = client.post(f"{A}/webauthn/register/verify", json=body, headers=h)
    assert done.status_code == 201, done.text
    assert done.json()["passwordless"] is passwordless
    # Single use: the same registration answer cannot be replayed.
    again = client.post(f"{A}/webauthn/register/verify", json=body, headers=h)
    assert again.status_code == 401
    assert again.json()["code"] == "MHVP-AUTH-0013"
    return dict(done.json())


def _mfa_token(client: TestClient, world: World, name: str) -> str:
    step = client.post(f"{A}/login", json={"email": world.email(name), "password": PASSWORD})
    assert step.status_code == 200, step.text
    assert step.json()["status"] == "mfa_required"
    assert step.json()["mfa_methods"] == ["webauthn"]
    return str(step.json()["mfa_token"])


def _options(client: TestClient, mfa_token: str | None) -> dict[str, Any]:
    opts = client.post(f"{A}/login/webauthn/options", json={"mfa_token": mfa_token})
    assert opts.status_code == 200, opts.text
    return dict(opts.json())


def test_passkey_second_factor(client: TestClient, world: World) -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    h = bearer(login_password_only(client, world, "s16one"))
    _register(client, h, fake)
    assert client.get(f"{A}/webauthn/status", headers=h).json()["available"] is True

    token = _mfa_token(client, world, "s16one")
    opts = _options(client, token)
    assert [c["id"] for c in opts["public_key"]["allowCredentials"]] == [fake.id]
    body = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"], "mfa_token": token}
    ok = client.post(f"{A}/login/webauthn/verify", json=body)
    assert ok.status_code == 200, ok.text
    assert client.get(f"{A}/me", headers=bearer(ok.json())).status_code == 200
    # Challenge reuse is refused.
    replay = client.post(f"{A}/login/webauthn/verify", json=body)
    assert replay.status_code == 401
    assert replay.json()["code"] == "MHVP-AUTH-0013"

    # Wrong origin, then a sign counter that does not increase.
    opts = _options(client, token)
    bad = fake.get(opts["public_key"], origin="https://evil.test")
    bad |= {"challenge_id": opts["challenge_id"], "mfa_token": token}
    assert client.post(f"{A}/login/webauthn/verify", json=bad).status_code == 401
    opts = _options(client, token)
    stale = fake.get(opts["public_key"], counter=1)
    stale |= {"challenge_id": opts["challenge_id"], "mfa_token": token}
    assert client.post(f"{A}/login/webauthn/verify", json=stale).status_code == 401

    # A 2FA only credential is not accepted for passwordless sign in.
    opts = _options(client, None)
    pwl = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]}
    assert client.post(f"{A}/login/webauthn/verify", json=pwl).status_code == 401


def test_user_separation_and_validation(client: TestClient, world: World) -> None:
    fake_two = FakeAuthenticator(RP, ORIGIN)
    h_two = bearer(login_password_only(client, world, "s16two"))
    cred_two = _register(client, h_two, fake_two)
    # Another user's mfa_token does not accept s16two's passkey.
    token_one = _mfa_token(client, world, "s16one")
    opts = _options(client, token_one)
    foreign = fake_two.get(opts["public_key"]) | {
        "challenge_id": opts["challenge_id"],
        "mfa_token": token_one,
    }
    assert client.post(f"{A}/login/webauthn/verify", json=foreign).status_code == 401
    # s16one cannot revoke s16two's passkey (404) and does not see it.
    h_one = bearer(login_password_only(client, world, "s16pwl"))
    assert (
        client.delete(f"{A}/webauthn/credentials/{cred_two['id']}", headers=h_one).status_code
        == 404
    )
    assert client.get(f"{A}/webauthn/credentials", headers=h_one).json() == []
    # Unknown challenge id.
    one = client.post(
        f"{A}/login/webauthn/verify",
        json=FakeAuthenticator(RP, ORIGIN).get(_options(client, token_one)["public_key"])
        | {"challenge_id": "x" * 20, "mfa_token": token_one},
    )
    assert one.status_code == 401
    # Validation and authentication.
    assert (
        client.post(f"{A}/login/webauthn/verify", json={"challenge_id": "short"}).status_code == 422
    )
    assert client.post(f"{A}/webauthn/register/options", json={}).status_code == 401
    assert client.delete(f"{A}/webauthn/credentials/{cred_two['id']}").status_code == 401
    assert (
        client.delete(f"{A}/webauthn/credentials/{cred_two['id']}", headers=h_two).status_code
        == 204
    )


def test_passwordless_sign_in(client: TestClient, world: World) -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    h = bearer(login_password_only(client, world, "s16pwl"))
    _register(client, h, fake, passwordless=True)
    opts = _options(client, None)
    assert opts["public_key"]["allowCredentials"] == []
    assert opts["public_key"]["userVerification"] == "required"
    # Without user verification the passwordless sign in is refused.
    no_uv = fake.get(opts["public_key"], uv=False) | {"challenge_id": opts["challenge_id"]}
    assert client.post(f"{A}/login/webauthn/verify", json=no_uv).status_code == 401
    opts = _options(client, None)
    ok = client.post(
        f"{A}/login/webauthn/verify",
        json=fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["tenant_id"] == str(world.tenant_b)


def test_w01_review_negative_paths(client: TestClient, world: World) -> None:
    """W01 (review 01.10.2026): user handle binding, foreign credential id, manipulated
    authenticator data, generic error text and lockout after repeated failed assertions."""
    from mhvp.core.auth import passwords, webauthn

    fake = FakeAuthenticator(RP, ORIGIN)
    h = bearer(login_password_only(client, world, "w01lock"))
    _register(client, h, fake, passwordless=True)

    # A user handle of another account is refused.
    opts = _options(client, None)
    body = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]}
    body["response"]["user_handle"] = webauthn.b64url_encode(world.users["s16one"].bytes)
    bad = client.post(f"{A}/login/webauthn/verify", json=body)
    assert bad.status_code == 401
    # Generic answer: the failed check is not revealed to the client.
    assert "handle" not in bad.text.lower()
    assert bad.json()["code"] == "MHVP-AUTH-0013"

    # A credential id that was never registered.
    opts = _options(client, None)
    unknown = FakeAuthenticator(RP, ORIGIN).get(opts["public_key"])
    unknown |= {"challenge_id": opts["challenge_id"]}
    assert client.post(f"{A}/login/webauthn/verify", json=unknown).status_code == 401

    # The own user handle is accepted.
    opts = _options(client, None)
    body = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]}
    body["response"]["user_handle"] = webauthn.b64url_encode(world.users["w01lock"].bytes)
    assert client.post(f"{A}/login/webauthn/verify", json=body).status_code == 200

    # Repeated manipulated signatures lock the account; afterwards even a valid one fails.
    for _ in range(passwords.MAX_FAILED_LOGINS):
        opts = _options(client, None)
        tampered = fake.get(opts["public_key"], tamper=True)
        tampered |= {"challenge_id": opts["challenge_id"]}
        assert client.post(f"{A}/login/webauthn/verify", json=tampered).status_code == 401
    opts = _options(client, None)
    good = fake.get(opts["public_key"]) | {"challenge_id": opts["challenge_id"]}
    locked = client.post(f"{A}/login/webauthn/verify", json=good)
    assert locked.status_code != 200


def test_webauthn_options_rate_limit(database: Database, redis_url: str, world: World) -> None:
    """W01-01: option endpoints are limited per client address and per user; the window resets."""
    import time

    cfg = _settings(
        database,
        redis_url,
        webauthn_enabled=True,
        webauthn_rp_id=RP,
        webauthn_origins=[ORIGIN],
        webauthn_options_limit_per_ip=1000,
        webauthn_options_limit_per_user=3,
        webauthn_options_window_seconds=2,
    )
    with TestClient(create_app(cfg)) as c:
        h = bearer(login_password_only(c, world, "s16two"))
        time.sleep(2.1 - time.time() % 2)  # start of a fresh window
        codes = [c.post(f"{A}/webauthn/register/options", json={}, headers=h) for _ in range(4)]
        assert [r.status_code for r in codes[:3]] == [200, 200, 200]
        assert codes[3].status_code == 429
        assert codes[3].json()["code"] == "MHVP-CORE-0006"
        assert int(codes[3].headers["Retry-After"]) >= 1
        time.sleep(2.1)
        assert c.post(f"{A}/webauthn/register/options", json={}, headers=h).status_code == 200


def test_webauthn_login_options_ip_limit(database: Database, redis_url: str) -> None:
    import time

    cfg = _settings(
        database,
        redis_url,
        webauthn_enabled=True,
        webauthn_rp_id=RP,
        webauthn_origins=[ORIGIN],
        webauthn_options_limit_per_ip=2,
        webauthn_options_window_seconds=2,
    )
    with TestClient(create_app(cfg)) as c:
        time.sleep(2.1 - time.time() % 2)
        res = [c.post(f"{A}/login/webauthn/options", json={}).status_code for _ in range(3)]
        assert res == [200, 200, 429]
        time.sleep(2.1)
        assert c.post(f"{A}/login/webauthn/options", json={}).status_code == 200
