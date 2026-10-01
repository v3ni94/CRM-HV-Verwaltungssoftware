"""S16-01: WebAuthn protocol checks with a software authenticator (no browser, no network)."""

import asyncio
from typing import Any

import pytest

from mhvp.core.auth import webauthn
from mhvp.core.problems import ProblemError
from tests.conftest import make_settings
from tests.webauthn_fake import FakeAuthenticator

RP, ORIGIN = "crm.example.test", "https://crm.example.test"


def _settings() -> Any:
    return make_settings(webauthn_enabled=True, webauthn_rp_id=RP, webauthn_origins=[ORIGIN])


def _register(
    fake: FakeAuthenticator, challenge: bytes, **kw: Any
) -> webauthn.RegisteredCredential:
    created = fake.create({"challenge": webauthn.b64url_encode(challenge)}, **kw)
    return webauthn.verify_registration(
        _settings(),
        challenge=challenge,
        credential_id=created["credential_id"],
        client_data_json=created["response"]["client_data_json"],
        attestation_object=created["response"]["attestation_object"],
        require_user_verification=True,
    )


def _assert(
    fake: FakeAuthenticator, cred: webauthn.RegisteredCredential, stored: int, **kw: Any
) -> int:
    challenge = b"c" * 32
    got = fake.get({"challenge": webauthn.b64url_encode(challenge)}, **kw)
    return webauthn.verify_assertion(
        _settings(),
        challenge=challenge,
        public_key=cred.public_key,
        stored_sign_count=stored,
        client_data_json=got["response"]["client_data_json"],
        authenticator_data=got["response"]["authenticator_data"],
        signature=got["response"]["signature"],
        require_user_verification=True,
    )


@pytest.mark.parametrize("alg", [-7, -8])
def test_register_and_assert(alg: int) -> None:
    fake = FakeAuthenticator(RP, ORIGIN, alg=alg)
    cred = _register(fake, b"r" * 32)
    assert cred.credential_id == fake.id
    assert cred.sign_count == 0
    assert _assert(fake, cred, 0) == 1
    assert _assert(fake, cred, 1) == 2


def test_rejects_wrong_origin_rp_type_and_signature() -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    cred = _register(fake, b"r" * 32)
    for kw in (
        {"origin": "https://evil.test"},
        {"rp_id": "evil.test"},
        {"tamper": True},
        {"uv": False},
    ):
        with pytest.raises(ProblemError) as exc:
            _assert(fake, cred, 0, **kw)
        assert exc.value.error.code == "MHVP-AUTH-0013"
    with pytest.raises(ProblemError):
        _register(FakeAuthenticator(RP, ORIGIN), b"r" * 32, origin="https://evil.test")
    with pytest.raises(ProblemError):
        _register(FakeAuthenticator(RP, ORIGIN), b"r" * 32, fmt="packed")
    # Challenge mismatch: registration answered for another challenge.
    other = FakeAuthenticator(RP, ORIGIN).create({"challenge": webauthn.b64url_encode(b"x" * 32)})
    with pytest.raises(ProblemError):
        webauthn.verify_registration(
            _settings(),
            challenge=b"y" * 32,
            credential_id=other["credential_id"],
            client_data_json=other["response"]["client_data_json"],
            attestation_object=other["response"]["attestation_object"],
            require_user_verification=False,
        )


def test_sign_count_strict() -> None:
    webauthn.check_sign_count(0, 0)
    webauthn.check_sign_count(4, 5)
    for stored, received in ((5, 5), (5, 4), (1, 0)):
        with pytest.raises(ProblemError):
            webauthn.check_sign_count(stored, received)
    fake = FakeAuthenticator(RP, ORIGIN, counter=10)
    cred = _register(fake, b"r" * 32)
    with pytest.raises(ProblemError):
        _assert(fake, cred, 10, counter=10)  # replayed or cloned counter


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int) -> None:
        self.data[key], self.ttl[key] = value, ex

    async def getdel(self, key: str) -> str | None:
        return self.data.pop(key, None)


def test_challenge_single_use_with_ttl() -> None:
    redis = _FakeRedis()

    async def run() -> None:
        cid, challenge = await webauthn.issue_challenge(redis, purpose="login", user_id=None)
        assert redis.ttl[f"webauthn:challenge:{cid}"] == webauthn.CHALLENGE_TTL_SECONDS
        data = await webauthn.consume_challenge(redis, cid, purpose="login")
        assert data["challenge_bytes"] == challenge
        with pytest.raises(ProblemError):
            await webauthn.consume_challenge(redis, cid, purpose="login")
        cid2, _ = await webauthn.issue_challenge(redis, purpose="register")
        with pytest.raises(ProblemError):
            await webauthn.consume_challenge(redis, cid2, purpose="login")

    asyncio.run(run())


def test_cbor_refuses_garbage() -> None:
    for raw in (b"", b"\x5f", b"\xa1", b"\xc0\x00", b"\x9b" + b"\xff" * 8):
        with pytest.raises(webauthn.CborError):
            webauthn.cbor_decode(raw)


def test_unavailable_without_configuration() -> None:
    assert not webauthn.is_available(make_settings())
    assert not webauthn.is_available(make_settings(webauthn_enabled=True))
    assert webauthn.is_available(_settings())


# --- W01 review 01.10.2026: negative tests for the hardened parser --------------------------


def _raw_assert(auth: bytes, fake: FakeAuthenticator, cred: webauthn.RegisteredCredential) -> int:
    import hashlib
    import json

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    challenge = b"c" * 32
    client = json.dumps(
        {"type": "webauthn.get", "challenge": webauthn.b64url_encode(challenge), "origin": ORIGIN}
    ).encode()
    sig = fake.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
    return webauthn.verify_assertion(
        _settings(),
        challenge=challenge,
        public_key=cred.public_key,
        stored_sign_count=0,
        client_data_json=webauthn.b64url_encode(client),
        authenticator_data=webauthn.b64url_encode(auth),
        signature=webauthn.b64url_encode(sig),
        require_user_verification=False,
    )


def _auth(flags: int, tail: bytes = b"") -> bytes:
    import hashlib
    import struct

    return hashlib.sha256(RP.encode()).digest() + bytes([flags]) + struct.pack(">I", 5) + tail


def test_assertion_authenticator_data_is_strict() -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    cred = _register(fake, b"r" * 32)
    assert _raw_assert(_auth(0x01), fake, cred) == 5
    assert _raw_assert(_auth(0x81, b"\xa0"), fake, cred) == 5  # ED with an empty map
    for auth in (
        _auth(0x01, b"\x00"),  # trailing byte without ED
        _auth(0x81),  # ED without extension map
        _auth(0x81, b"\xa0\x00"),  # trailing byte after extensions
        _auth(0x81, b"\x01"),  # extensions not a map
        _auth(0x41),  # AT flag in an assertion
        _auth(0x00),  # no user presence
    ):
        with pytest.raises(ProblemError):
            _raw_assert(auth, fake, cred)


def test_foreign_credential_key_refused() -> None:
    fake, other = FakeAuthenticator(RP, ORIGIN), FakeAuthenticator(RP, ORIGIN)
    cred_other = _register(other, b"r" * 32)
    with pytest.raises(ProblemError):
        _assert(fake, cred_other, 0)


def test_cbor_strictness() -> None:
    for raw in (
        b"\xa2\x01\x01\x01\x02",  # duplicate map key
        b"\x18\x05",  # 5 encoded in one extra byte
        b"\x19\x00\x10",  # 16 encoded in two bytes
        b"\x58\x01\x00",  # byte string length 1 in one extra byte
    ):
        with pytest.raises(webauthn.CborError):
            webauthn.cbor_decode(raw)
    assert webauthn.cbor_decode(b"\x18\x18") == (24, 2)
    assert webauthn.cbor_decode(b"\x19\x01\x00") == (256, 3)


def test_attestation_object_trailing_bytes_refused() -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    created = fake.create({"challenge": webauthn.b64url_encode(b"r" * 32)})
    raw = webauthn.b64url_decode(created["response"]["attestation_object"]) + b"\x00"
    with pytest.raises(ProblemError):
        webauthn.verify_registration(
            _settings(),
            challenge=b"r" * 32,
            credential_id=created["credential_id"],
            client_data_json=created["response"]["client_data_json"],
            attestation_object=webauthn.b64url_encode(raw),
            require_user_verification=False,
        )


def test_base64url_strict() -> None:
    assert webauthn.b64url_decode("AAEC") == b"\x00\x01\x02"
    assert webauthn.b64url_decode("-_8") == b"\xfb\xff"
    for bad in ("AA EC", "AA+C", "AA/C", "A", "AA$C", "AAEC==="):
        with pytest.raises(ProblemError):
            webauthn.b64url_decode(bad)


def test_client_data_negative_paths() -> None:
    import json

    ch = b"c" * 32
    good = {"type": "webauthn.get", "challenge": webauthn.b64url_encode(ch), "origin": ORIGIN}
    webauthn.verify_client_data(
        json.dumps(good).encode(), expected_type="webauthn.get", challenge=ch, origins=[ORIGIN]
    )
    for patch in (
        {"type": "webauthn.create"},
        {"challenge": webauthn.b64url_encode(b"d" * 32)},
        {"origin": "https://crm.example.test.evil.test"},
        {"origin": "http://crm.example.test"},
        {"crossOrigin": True},
    ):
        with pytest.raises(ProblemError):
            webauthn.verify_client_data(
                json.dumps(good | patch).encode(),
                expected_type="webauthn.get",
                challenge=ch,
                origins=[ORIGIN],
            )


def test_error_detail_is_generic() -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    cred = _register(fake, b"r" * 32)
    with pytest.raises(ProblemError) as exc:
        _assert(fake, cred, 0, tamper=True)
    assert "Signature" not in str(exc.value.developer_message)
    assert exc.value.developer_message == exc.value.error.developer_message


def test_registration_requires_attested_data() -> None:
    fake = FakeAuthenticator(RP, ORIGIN)
    auth = _auth(0x05)
    att = __import__("tests.webauthn_fake", fromlist=["cbor"]).cbor(
        {"fmt": "none", "attStmt": {}, "authData": auth}
    )
    created = fake.create({"challenge": webauthn.b64url_encode(b"r" * 32)})
    with pytest.raises(ProblemError):
        webauthn.verify_registration(
            _settings(),
            challenge=b"r" * 32,
            credential_id=created["credential_id"],
            client_data_json=created["response"]["client_data_json"],
            attestation_object=webauthn.b64url_encode(att),
            require_user_verification=False,
        )
