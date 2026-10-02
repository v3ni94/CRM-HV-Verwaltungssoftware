"""AG05 / GAE-24: local state handling of EBICS key change (rotation) and lock (SPR) with an in
memory bank double (no network): rotation resets initialisation and blocks retrieval until the
new initialisation is verified again, state per subscriber is independent, a local lock blocks
every order and the scheduled fetch, tenant separation (404), read right (403), validation
(422). Acceptance on the bank test system stays an operator task. Own world with prefix 0ag05."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking import ebics_keys, ebics_transport, tasks
from mhvp.banking.ebics_connector import EbicsClientKeys
from mhvp.banking.ebics_keys import private_matches_public
from mhvp.main import create_app
from mhvp.platform import services
from tests.ebics_fake import FakeEbicsBank, c53_zip
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
E = "/api/v1/banking/ebics"
STATE = "MHVP-BANK-0052"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag05a-{RUN}", name=f"AG05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag05b-{RUN}", name=f"AG05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ag05admin", a, "tenant_admin"),
            ("ag05second", a, "tenant_admin"),
            ("ag05reader", a, "read_only"),
            ("ag05other", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


class _MultiSubscriberBank(FakeEbicsBank):
    """The shared double checks the client keys against the last HIA only; this test runs two
    subscribers, so any registered HIA pair of the keys counts."""

    def _check_client(self, keys: EbicsClientKeys) -> None:
        assert any(
            private_matches_public(keys.authentication_private_pem, auth)
            and private_matches_public(keys.encryption_private_pem, enc)
            for auth, enc in self.hia
        )


@pytest.fixture
def bank(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEbicsBank]:
    monkeypatch.setattr(ebics_keys, "STRICT_FROM", date(2099, 1, 1))
    fake = _MultiSubscriberBank()
    ebics_transport.set_transport_factory(lambda: fake)
    try:
        yield fake
    finally:
        ebics_transport.set_transport_factory(None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _state(response: Any) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == STATE


def _new_subscriber(client: TestClient, h: dict[str, str], user: str) -> str:
    body = {
        "label": "Hausbank",
        "host_id": "HOSTAG05",
        "partner_id": f"P{RUN}"[:30],
        "ebics_user_id": user,
        "url": "https://ebics.bank.example/ebicsweb",
        "ebics_version": "3.0",
        "signature_version": "A006",
        "key_bits": 2048,
    }
    return str(_ok(client.post(f"{E}/subscribers", json=body, headers=h), 201)["id"])


def _initialise(
    client: TestClient, h: dict[str, str], h2: dict[str, str], sid: str, *, first: bool = True
) -> None:
    """Initialisation (signature key external) up to verified bank keys, status ready. After a
    key change the uploaded signature key stays valid, so it is uploaded only the first time."""
    base = f"{E}/subscribers/{sid}"
    if first:
        signer = ebics_keys.generate_key_pair(2048)
        body = {"public_key_pem": signer.public_pem}
        _ok(client.post(f"{base}/signature-key", json=body, headers=h))
    _ok(client.post(f"{base}/ini", headers=h))
    _ok(client.post(f"{base}/hia", headers=h))
    _ok(
        client.post(
            f"{base}/activation",
            json={"activated_on": "2026-09-30", "note": "Bankbrief"},
            headers=h,
        )
    )
    sub = _ok(client.post(f"{base}/hpb", headers=h))
    bank_keys = {k["usage"]: k for k in sub["keys"] if k["owner"] == "bank"}
    hashes = {
        "authentication_hash": bank_keys["authentication"]["letter_hash"],
        "encryption_hash": bank_keys["encryption"]["letter_hash"],
    }
    assert _ok(client.post(f"{base}/bank-keys/verify", json=hashes, headers=h2))["status"] == (
        "ready"
    )


def _ready(client: TestClient, h: dict[str, str], h2: dict[str, str], user: str) -> str:
    sid = _new_subscriber(client, h, user)
    _ok(client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h))
    _initialise(client, h, h2, sid)
    return sid


def _statuses(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    return {s["ebics_user_id"]: s["status"] for s in _ok(client.get(f"{E}/subscribers", headers=h))}


def test_key_change_and_lock_state_handling(
    client: TestClient, world: World, bank: FakeEbicsBank, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ag05admin"))
    h2 = bearer(login(client, world, "ag05second"))
    r = bearer(login(client, world, "ag05reader"))
    o = bearer(login(client, world, "ag05other"))
    _ok(
        client.put(
            f"{E}/settings", json={"enabled": True, "signature_key_mode": "external"}, headers=h
        )
    )
    keep = _ready(client, h, h2, "UKEEP")
    chg = _ready(client, h, h2, "UCHG")
    assert _statuses(client, h) == {"UKEEP": "ready", "UCHG": "ready"}
    bank.zip_content = c53_zip({"info.txt": b"x"})
    base = f"{E}/subscribers/{chg}"

    # key change: reason mandatory, read right and other tenant refused
    assert client.post(f"{base}/keys", json={}, headers=h).status_code == 422
    assert (
        client.post(f"{base}/keys", json={"reason": "Jahreswechsel"}, headers=r).status_code == 403
    )
    assert client.post(f"{base}/keys", json={"reason": "Jahreswechsel"}, headers=o).status_code in (
        404,
        409,
    )
    assert _statuses(client, h)["UCHG"] == "ready"
    old_ids = {
        k["id"]
        for k in _ok(client.get(base, headers=h))["keys"]
        if k["owner"] == "subscriber" and k["usage"] != "signature"
    }
    sub = _ok(client.post(f"{base}/keys", json={"reason": "Jahreswechsel"}, headers=h))
    assert sub["status"] == "keys_ready"
    assert sub["next_step"] != "download_statements"
    assert sub["ini_sent_at"] is None
    assert sub["hia_sent_at"] is None
    assert sub["activated_on"] is None
    assert sub["bank_keys_verified_at"] is None
    new_ids = {k["id"] for k in sub["keys"] if k["owner"] == "subscriber"}
    assert len(old_ids) == 2
    assert old_ids.isdisjoint(new_ids)

    # state is per subscriber: the other subscriber stays ready and downloads
    assert _statuses(client, h) == {"UKEEP": "ready", "UCHG": "keys_ready"}
    calls = len(bank.downloads)
    _ok(client.post(f"{E}/subscribers/{keep}/statements", json={}, headers=h))
    assert len(bank.downloads) == calls + 1

    # until verified again: retrieval, HPB, activation and verification are refused, no transport call
    calls = len(bank.downloads)
    _state(client.post(f"{base}/statements", json={}, headers=h))
    _state(client.post(f"{base}/hpb", headers=h))
    _state(
        client.post(
            f"{base}/activation", json={"activated_on": "2026-10-01", "note": "n"}, headers=h
        )
    )
    _state(
        client.post(
            f"{base}/bank-keys/verify",
            json={"authentication_hash": "0" * 64, "encryption_hash": "0" * 64},
            headers=h2,
        )
    )
    assert len(bank.downloads) == calls
    settings = _settings(database, redis_url)
    blocked = asyncio.run(tasks._ebics_fetch_once(settings, world.tenant_a, uuid.UUID(chg)))
    assert blocked["error"] == STATE
    assert len(bank.downloads) == calls

    # new initialisation completes the change
    _initialise(client, h, h2, chg, first=False)
    _ok(client.post(f"{base}/statements", json={}, headers=h))
    assert _statuses(client, h) == {"UKEEP": "ready", "UCHG": "ready"}

    # lock (SPR local): reason validated, read right and other tenant refused
    assert client.post(f"{base}/suspend", json={}, headers=h).status_code == 422
    reason = {"reason": "Verdacht auf Missbrauch"}
    assert client.post(f"{base}/suspend", json=reason, headers=r).status_code == 403
    assert client.post(f"{base}/suspend", json=reason, headers=o).status_code == 404
    sub = _ok(client.post(f"{base}/suspend", json=reason, headers=h))
    assert sub["status"] == "suspended"
    assert sub["suspend_reason"] == reason["reason"]
    assert not any(k["has_private_key"] for k in sub["keys"])
    assert _statuses(client, h) == {"UKEEP": "ready", "UCHG": "suspended"}

    # a lock blocks every order and the scheduled fetch, and it is final
    calls = len(bank.downloads)
    _state(client.post(f"{base}/suspend", json=reason, headers=h))
    _state(client.post(f"{base}/keys", json={"reason": "Neuer Schluessel"}, headers=h))
    _state(client.post(f"{base}/statements", json={}, headers=h))
    _state(client.post(f"{base}/hpb", headers=h))
    _state(client.post(f"{base}/ini", headers=h))
    _state(client.post(f"{base}/hia", headers=h))
    _state(
        client.post(
            f"{base}/activation", json={"activated_on": "2026-10-01", "note": "n"}, headers=h
        )
    )
    assert len(bank.downloads) == calls
    locked = asyncio.run(tasks._ebics_fetch_once(settings, world.tenant_a, uuid.UUID(chg)))
    assert locked["error"] == STATE
    assert len(bank.downloads) == calls
    _ok(client.post(f"{E}/subscribers/{keep}/statements", json={}, headers=h))
