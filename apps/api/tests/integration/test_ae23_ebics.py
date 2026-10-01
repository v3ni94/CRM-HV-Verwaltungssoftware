"""AE23 / M11-01: EBICS connector scaffold through the API with an in memory bank double (no
network): tenant switch, subscriber, keys stored encrypted, INI/HIA, activation, HPB, bank key
verification by a second person, C53 download imported idempotently, rotation, suspension,
transport unavailable, tenant separation (404), read right (403), validation (422). Own world
with prefix ae23."""

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.banking import ebics_keys, ebics_transport
from mhvp.banking.ebics_transport import EbicsTransportError
from mhvp.main import create_app
from mhvp.platform import services
from tests.ebics_fake import FakeEbicsBank, c53_zip
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.unit.test_ae23_ebics import camt

pytestmark = pytest.mark.integration
E = "/api/v1/banking/ebics"
IBAN_KNOWN = "DE02120300000000202051"
IBAN_UNKNOWN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae23a-{RUN}", name=f"AE23 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae23b-{RUN}", name=f"AE23 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae23admin", a, "tenant_admin"),
            ("ae23second", a, "tenant_admin"),
            ("ae23reader", a, "read_only"),
            ("ae23other", b, "tenant_admin"),
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


@pytest.fixture
def bank(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEbicsBank]:
    # 2048 bit test keys stay valid after 11/2027 in this test (generation speed only)
    monkeypatch.setattr(ebics_keys, "STRICT_FROM", date(2099, 1, 1))
    fake = FakeEbicsBank()
    ebics_transport.set_transport_factory(lambda: fake)
    try:
        yield fake
    finally:
        ebics_transport.set_transport_factory(None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _code(response: Any, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def _enable(client: TestClient, h: dict[str, str], **extra: Any) -> dict[str, Any]:
    return dict(_ok(client.put(f"{E}/settings", json={"enabled": True, **extra}, headers=h)))


def _subscriber(client: TestClient, h: dict[str, str], user: str, **extra: Any) -> dict[str, Any]:
    body = {
        "label": "Hausbank",
        "host_id": "HOSTAE23",
        "partner_id": f"P{RUN}"[:30],
        "ebics_user_id": user,
        "url": "https://ebics.bank.example/ebicsweb",
        "ebics_version": "3.0",
        "signature_version": "A006",
        "key_bits": 2048,
    }
    return dict(_ok(client.post(f"{E}/subscribers", json=body | extra, headers=h), 201))


def _property_account(client: TestClient, h: dict[str, str], number: str, iban: str) -> str:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Objekt {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    return str(
        _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": hoa,
                    "kind": "hoa",
                    "iban": iban,
                    "holder": f"GdWE {number}",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_status_switch_and_validation(client: TestClient, world: World) -> None:
    ebics_transport.set_transport_factory(None)
    h = bearer(login(client, world, "ae23admin"))
    r = bearer(login(client, world, "ae23reader"))
    status = _ok(client.get(f"{E}/status", headers=r))
    assert status["transport_available"] is False
    assert status["transport"] == "unavailable"
    assert status["c53_btf"] == "EOP/DE//camt.053/ZIP"
    assert status["default_key_bits"] == 4096
    assert status["payment_submission"] == "locked_g2"
    assert "AE23-01" in status["open_questions"]
    if not status["enabled"]:
        body = {
            "label": "x",
            "host_id": "H",
            "partner_id": "P",
            "ebics_user_id": "U0",
            "url": "https://x.example",
            "ebics_version": "3.0",
            "signature_version": "A006",
        }
        _code(client.post(f"{E}/subscribers", json=body, headers=h), 409, "MHVP-BANK-0051")
    assert client.put(f"{E}/settings", json={"enabled": True}, headers=r).status_code == 403
    assert client.put(f"{E}/settings", json={"x": 1}, headers=h).status_code == 422
    assert (
        client.put(f"{E}/settings", json={"signature_key_mode": "usb"}, headers=h).status_code
        == 422
    )
    state = _enable(client, h, signature_key_mode="external")
    assert state["enabled"] is True
    assert state["signature_key_mode"] == "external"
    assert client.get(f"{E}/subscribers?x=1", headers=h).status_code == 422
    base = {
        "label": "x",
        "host_id": "H",
        "partner_id": "P",
        "ebics_user_id": "U1",
        "ebics_version": "3.0",
        "signature_version": "A006",
    }
    plain = base | {"url": "http://unverschluesselt.example"}
    assert client.post(f"{E}/subscribers", json=plain, headers=h).status_code == 422
    weak = base | {"url": "https://x.example", "key_bits": 1024}
    assert client.post(f"{E}/subscribers", json=weak, headers=h).status_code == 422
    old = base | {"url": "https://x.example", "ebics_version": "2.4"}
    assert client.post(f"{E}/subscribers", json=old, headers=h).status_code == 422
    assert (
        client.post(f"{E}/subscribers", json=base | {"url": "https://x"}, headers=r).status_code
        == 403
    )


def test_full_flow_with_fake_bank(
    client: TestClient, world: World, database: Database, bank: FakeEbicsBank
) -> None:
    h = bearer(login(client, world, "ae23admin"))
    h2 = bearer(login(client, world, "ae23second"))
    r = bearer(login(client, world, "ae23reader"))
    o = bearer(login(client, world, "ae23other"))
    _enable(client, h, signature_key_mode="external")
    sub = _subscriber(client, h, "UFLOW")
    sid = sub["id"]
    assert sub["status"] == "created"
    assert sub["signature_key_mode"] == "external"
    assert sub["next_step"] == "generate_keys"
    duplicate = client.post(
        f"{E}/subscribers",
        json={
            "label": "x",
            "host_id": "HOSTAE23",
            "partner_id": sub["partner_id"],
            "ebics_user_id": "UFLOW",
            "url": "https://x.example",
            "ebics_version": "3.0",
            "signature_version": "A006",
        },
        headers=h,
    )
    assert duplicate.status_code == 409

    # keys: authentication and encryption only (signature key stays external)
    sub = _ok(client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h))
    assert sub["status"] == "keys_ready"
    assert {(k["usage"], k["version"], k["has_private_key"]) for k in sub["keys"]} == {
        ("authentication", "X002", True),
        ("encryption", "E002", True),
    }
    assert sub["next_step"] == "upload_signature_key_or_confirm_ini"
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        blobs = conn.execute(
            text("SELECT private_key FROM ebics_key WHERE subscriber_id = :s"), {"s": sid}
        ).scalars()
        for blob in blobs:
            assert bytes(blob).startswith(b"v1")
            assert b"PRIVATE KEY" not in bytes(blob)
    engine.dispose()
    letters = _ok(client.get(f"{E}/subscribers/{sid}/letters", headers=r))
    assert [(x["order_type"], x["usage"]) for x in letters["letters"]] == [
        ("HIA", "authentication"),
        ("HIA", "encryption"),
    ]
    assert all(x["letter_hash_status"] == "transport" for x in letters["letters"])
    assert letters["letters"][0]["exponent_hex"] == "10001"

    # INI needs the signature key; upload only the public key
    _code(client.post(f"{E}/subscribers/{sid}/ini", headers=h), 409, "MHVP-BANK-0052")
    bad = {
        "public_key_pem": "-----BEGIN PUBLIC KEY-----\n" + "A" * 120 + "\n-----END PUBLIC KEY-----"
    }
    assert (
        client.post(f"{E}/subscribers/{sid}/signature-key", json=bad, headers=h).status_code == 422
    )
    signer = ebics_keys.generate_key_pair(2048)
    sub = _ok(
        client.post(
            f"{E}/subscribers/{sid}/signature-key",
            json={"public_key_pem": signer.public_pem},
            headers=h,
        )
    )
    sig = next(k for k in sub["keys"] if k["usage"] == "signature")
    assert sig["source"] == "uploaded"
    assert sig["has_private_key"] is False
    sub = _ok(client.post(f"{E}/subscribers/{sid}/ini", headers=h))
    assert sub["ini_sent_at"] is not None
    assert bank.ini == [signer.public_pem]
    _code(client.post(f"{E}/subscribers/{sid}/ini", headers=h), 409, "MHVP-BANK-0052")
    sub = _ok(client.post(f"{E}/subscribers/{sid}/hia", headers=h))
    assert sub["status"] == "initialised"

    # activation by the bank, confirmed with date; not in the future
    future = {"activated_on": "2999-01-01"}
    assert (
        client.post(f"{E}/subscribers/{sid}/activation", json=future, headers=h).status_code == 422
    )
    sub = _ok(
        client.post(
            f"{E}/subscribers/{sid}/activation",
            json={"activated_on": "2026-09-30", "note": "Bankbrief vom 30.09.2026"},
            headers=h,
        )
    )
    assert sub["status"] == "activated"

    # HPB, then verification by a second person against the bank letter
    sub = _ok(client.post(f"{E}/subscribers/{sid}/hpb", headers=h))
    assert sub["status"] == "bank_keys_received"
    bank_keys = {k["usage"]: k for k in sub["keys"] if k["owner"] == "bank"}
    assert set(bank_keys) == {"authentication", "encryption"}
    right = {
        "authentication_hash": bank_keys["authentication"]["letter_hash"].lower(),
        "encryption_hash": " ".join(bank_keys["encryption"]["letter_hash"]),
    }
    verify = f"{E}/subscribers/{sid}/bank-keys/verify"
    _code(client.post(verify, json=right, headers=h), 409, "MHVP-BANK-0054")
    wrong = right | {"encryption_hash": "0" * 64}
    _code(client.post(verify, json=wrong, headers=h2), 409, "MHVP-BANK-0053")
    assert _ok(client.get(f"{E}/subscribers/{sid}", headers=h))["status"] == "bank_keys_received"
    _code(
        client.post(f"{E}/subscribers/{sid}/statements", json={}, headers=h), 409, "MHVP-BANK-0052"
    )
    sub = _ok(client.post(verify, json=right, headers=h2))
    assert sub["status"] == "ready"
    assert sub["bank_keys_verified_by"] == str(world.users["ae23second"])

    # C53: known account imported, unknown account and non XML member skipped, re-import idle
    _property_account(client, h, "923", IBAN_KNOWN)
    bank.zip_content = c53_zip(
        {
            f"2026-02-01_C53_{IBAN_KNOWN}_EUR_000001.xml": camt(
                f"S{RUN}",
                IBAN_KNOWN,
                [(f"R1{RUN}", "100.00", "2026-01-15"), (f"R2{RUN}", "5.50", "2026-01-20")],
            ),
            f"2026-02-01_C53_{IBAN_UNKNOWN}_EUR_000002.xml": camt(
                f"U{RUN}", IBAN_UNKNOWN, [(f"R3{RUN}", "1.00", "2026-01-15")]
            ),
            "info.txt": b"x",
        }
    )
    statements = f"{E}/subscribers/{sid}/statements"
    span = {"date_from": "2026-01-01", "date_to": "2026-01-31"}
    order = _ok(client.post(statements, json=span, headers=h))
    assert order["status"] == "done"
    assert order["btf"] == "EOP/DE//camt.053/ZIP"
    assert order["result"]["new"] == 2
    assert order["result"]["skipped_members"] == ["info.txt"]
    assert order["result"]["skipped_accounts"][0]["iban_suffix"] == IBAN_UNKNOWN[-4:]
    assert len(order["result"]["runs"]) == 1
    assert bank.downloads[-1] == ("EOP/DE//camt.053/ZIP", date(2026, 1, 1), date(2026, 1, 31))
    again = _ok(client.post(statements, json={}, headers=h))
    assert again["result"]["new"] == 0
    assert again["result"]["duplicates"] == 2
    bad_span = {"date_from": "2026-02-01", "date_to": "2026-01-01"}
    assert client.post(statements, json=bad_span, headers=h).status_code == 422
    assert client.post(statements, json={"x": 1}, headers=h).status_code == 422

    # bank error and unreadable download: failed order logged, nothing imported
    bank.fail_next = EbicsTransportError("Teilnehmer gesperrt", code="091002")
    failed = client.post(statements, json={}, headers=h)
    _code(failed, 502, "MHVP-BANK-0056")
    assert "091002" in failed.json()["detail"]
    bank.zip_content = b"kein zip"
    _code(client.post(statements, json={}, headers=h), 422, "MHVP-CORE-0004")
    detail = _ok(client.get(f"{E}/subscribers/{sid}", headers=r))
    orders = [(x["order_type"], x["status"], x["error_code"]) for x in detail["orders"]]
    assert orders[0] == ("C53", "failed", "MHVP-CORE-0004")
    assert orders[1] == ("C53", "failed", "MHVP-BANK-0056")
    assert ("HPB", "done", None) in orders

    # tenant separation and read right
    assert client.get(f"{E}/subscribers/{sid}", headers=o).status_code == 404
    assert client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=o).status_code in (404, 409)
    assert client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=r).status_code == 403
    assert all(s["id"] != sid for s in _ok(client.get(f"{E}/subscribers", headers=o)))

    # rotation: reason required, old rows retired with private key wiped, initialisation again
    assert client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h).status_code == 422
    sub = _ok(
        client.post(f"{E}/subscribers/{sid}/keys", json={"reason": "Jahreswechsel"}, headers=h)
    )
    assert sub["status"] == "keys_ready"
    assert sub["ini_sent_at"] is None
    retired = [k for k in sub["retired_keys"] if k["owner"] == "subscriber"]
    assert {k["usage"] for k in retired} == {"authentication", "encryption"}
    assert all(k["has_private_key"] is False for k in retired)
    assert all(k["retire_reason"] == "Jahreswechsel" for k in retired)

    # suspension is final and wipes the remaining private keys
    reason = {"reason": "Verdacht auf Missbrauch"}
    sub = _ok(client.post(f"{E}/subscribers/{sid}/suspend", json=reason, headers=h))
    assert sub["status"] == "suspended"
    assert not any(k["has_private_key"] for k in sub["keys"])
    _code(
        client.post(f"{E}/subscribers/{sid}/keys", json={"reason": "neu"}, headers=h),
        409,
        "MHVP-BANK-0052",
    )


def test_server_variant_and_unavailable_transport(
    client: TestClient, world: World, bank: FakeEbicsBank
) -> None:
    h = bearer(login(client, world, "ae23admin"))
    _enable(client, h, signature_key_mode="server")
    try:
        sub = _subscriber(client, h, "USERVER")
        sid = sub["id"]
        assert sub["signature_key_mode"] == "server"
        sub = _ok(client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h))
        sig = next(k for k in sub["keys"] if k["usage"] == "signature")
        assert sig["version"] == "A006"
        assert sig["has_private_key"] is True
        assert sub["next_step"] == "send_ini"
        _code(
            client.post(
                f"{E}/subscribers/{sid}/ini/external", json={"note": "Bankportal"}, headers=h
            ),
            409,
            "MHVP-BANK-0052",
        )
        signer = ebics_keys.generate_key_pair(2048)
        _code(
            client.post(
                f"{E}/subscribers/{sid}/signature-key",
                json={"public_key_pem": signer.public_pem},
                headers=h,
            ),
            409,
            "MHVP-BANK-0052",
        )
        # without a transport implementation: 503 and a failed order, state unchanged
        ebics_transport.set_transport_factory(None)
        _code(client.post(f"{E}/subscribers/{sid}/ini", headers=h), 503, "MHVP-BANK-0050")
        detail = _ok(client.get(f"{E}/subscribers/{sid}", headers=h))
        assert detail["status"] == "keys_ready"
        assert detail["ini_sent_at"] is None
        assert detail["orders"][0]["error_code"] == "MHVP-BANK-0050"
        assert _ok(client.get(f"{E}/status", headers=h))["transport_available"] is False
    finally:
        _enable(client, h, signature_key_mode="external")


def test_external_ini_confirmation_and_switch_off(
    client: TestClient, world: World, bank: FakeEbicsBank
) -> None:
    h = bearer(login(client, world, "ae23admin"))
    _enable(client, h, signature_key_mode="external")
    sub = _subscriber(client, h, "UEXTERN")
    sid = sub["id"]
    _ok(client.post(f"{E}/subscribers/{sid}/keys", json={}, headers=h))
    assert (
        client.post(f"{E}/subscribers/{sid}/ini/external", json={"note": ""}, headers=h).status_code
        == 422
    )
    sub = _ok(
        client.post(
            f"{E}/subscribers/{sid}/ini/external",
            json={"note": "INI über Chipkarte im Bankportal am 30.09.2026"},
            headers=h,
        )
    )
    assert sub["ini_external"] is True
    assert sub["next_step"] == "send_hia"
    sub = _ok(client.post(f"{E}/subscribers/{sid}/hia", headers=h))
    assert sub["status"] == "initialised"
    assert bank.ini == []
    # switch off: every EBICS action stops, reading and the local lock stay possible
    _ok(client.put(f"{E}/settings", json={"enabled": False}, headers=h))
    try:
        act = {"activated_on": "2026-09-30"}
        _code(
            client.post(f"{E}/subscribers/{sid}/activation", json=act, headers=h),
            409,
            "MHVP-BANK-0051",
        )
        assert _ok(client.get(f"{E}/subscribers/{sid}", headers=h))["status"] == "initialised"
        reason = {"reason": "Teilnehmer nicht mehr benötigt"}
        assert (
            _ok(client.post(f"{E}/subscribers/{sid}/suspend", json=reason, headers=h))["status"]
            == "suspended"
        )
    finally:
        _enable(client, h)
