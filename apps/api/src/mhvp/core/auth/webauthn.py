"""WebAuthn/passkeys (3.4, M2-03/S16-01): registration and assertion as second factor and,
optionally per credential, as passwordless sign in.

Operator decision 9 a of 30.09.2026: WebAuthn is offered next to TOTP. No WebAuthn specific
library is in ``uv.lock`` (open question P14-02); this module implements only the protocol
checks of WebAuthn Level 2 (7.1 and 7.2) and delegates every signature check to the already
released ``cryptography`` package. It deliberately supports a narrow profile:

* attestation ``none`` only (the attestation statement is not evaluated; the credential is
  bound to the account through the authenticated registration session),
* COSE algorithms ES256 (-7), EdDSA/Ed25519 (-8) and RS256 (-257),
* challenges are random 32 bytes, stored in Redis with a short TTL and consumed exactly once
  (``GETDEL``) before any verification step,
* ``clientDataJSON``: ``type``, ``challenge`` and ``origin`` (allow list) must match;
  ``authenticatorData``: RP ID hash must match, user presence is required, user verification
  is required for passwordless sign in,
* sign counter: strictly increasing; a counter that does not grow (except for the case that
  authenticator and server both stay at 0) is rejected as a possible cloned authenticator.

The whole function is off unless ``Settings.webauthn_enabled`` is set and an RP ID and at
least one origin are configured (release by the operator, P14-02).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from redis.exceptions import RedisError

from mhvp.core.config import Settings
from mhvp.core.problems import ErrorCodes, ProblemError

logger = logging.getLogger(__name__)

UNAVAILABLE_REASON = (
    "Passkeys (WebAuthn) sind nicht freigeschaltet. Bitte TOTP als zweiten Faktor verwenden."
)
CHALLENGE_TTL_SECONDS = 300
TIMEOUT_MS = CHALLENGE_TTL_SECONDS * 1000
ALG_ES256, ALG_EDDSA, ALG_RS256 = -7, -8, -257
SUPPORTED_ALGORITHMS = (ALG_ES256, ALG_EDDSA, ALG_RS256)

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40
FLAG_ED = 0x80


def is_available(settings: Settings) -> bool:
    return bool(settings.webauthn_enabled and settings.webauthn_rp_id and settings.webauthn_origins)


def ensure_available(settings: Settings) -> None:
    if not is_available(settings):
        raise ProblemError(ErrorCodes.WEBAUTHN_UNAVAILABLE, detail=UNAVAILABLE_REASON)


def invalid(reason: str) -> ProblemError:
    """W01 (review 01.10.2026): the precise reason is logged server side only. The response
    carries the generic code text so that a client cannot use the answer as an oracle for
    which check failed (credential known, signature, counter, origin)."""
    logger.info("webauthn check failed: %s", reason)
    return ProblemError(ErrorCodes.WEBAUTHN_INVALID)


# --- encoding helpers ------------------------------------------------------------------------


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


_B64URL = re.compile(r"[A-Za-z0-9_-]*={0,2}")


def b64url_decode(value: str) -> bytes:
    """Strict base64url (RFC 4648 section 5): characters outside the URL safe alphabet are
    refused instead of being silently dropped."""
    if not isinstance(value, str) or not _B64URL.fullmatch(value):
        raise invalid("Invalid base64url value.")
    value = value.rstrip("=")
    if len(value) % 4 == 1:
        raise invalid("Invalid base64url length.")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        raise invalid("Invalid base64url value.") from None


class CborError(ValueError):
    pass


def cbor_decode(data: bytes) -> tuple[Any, int]:
    """Minimal CBOR decoder (RFC 8949) for attestation objects and COSE keys: unsigned and
    negative integers, byte and text strings, arrays, maps, simple values false/true/null.
    Indefinite lengths, tags, floats, non minimal length encodings and duplicate map keys
    are refused. Returns (value, bytes consumed)."""
    return _cbor_item(data, 0, depth=0)


def _cbor_length(data: bytes, pos: int, info: int) -> tuple[int, int]:
    if info < 24:
        return info, pos
    sizes = {24: 1, 25: 2, 26: 4, 27: 8}
    if info not in sizes:
        raise CborError("unsupported length")
    size = sizes[info]
    if pos + size > len(data):
        raise CborError("truncated")
    value = int.from_bytes(data[pos : pos + size], "big")
    if value < (24 if size == 1 else 1 << (4 * size)):
        raise CborError("non minimal length encoding")
    return value, pos + size


def _cbor_item(data: bytes, pos: int, *, depth: int) -> tuple[Any, int]:
    if depth > 8:
        raise CborError("nesting too deep")
    if pos >= len(data):
        raise CborError("truncated")
    head = data[pos]
    major, info = head >> 5, head & 0x1F
    pos += 1
    if major == 7:
        simple = {20: False, 21: True, 22: None}
        if info not in simple:
            raise CborError("unsupported simple value")
        return simple[info], pos
    length, pos = _cbor_length(data, pos, info)
    if major == 0:
        return length, pos
    if major == 1:
        return -1 - length, pos
    if major in (2, 3):
        if pos + length > len(data):
            raise CborError("truncated")
        raw = data[pos : pos + length]
        return (raw if major == 2 else raw.decode("utf-8")), pos + length
    if major == 4:
        items = []
        for _ in range(length):
            item, pos = _cbor_item(data, pos, depth=depth + 1)
            items.append(item)
        return items, pos
    if major == 5:
        result: dict[Any, Any] = {}
        for _ in range(length):
            key, pos = _cbor_item(data, pos, depth=depth + 1)
            if isinstance(key, (list, dict)):
                raise CborError("unsupported map key")
            if key in result:
                raise CborError("duplicate map key")
            value, pos = _cbor_item(data, pos, depth=depth + 1)
            result[key] = value
        return result, pos
    raise CborError("unsupported major type")


# --- authenticator data ----------------------------------------------------------------------


@dataclass(frozen=True)
class AuthenticatorData:
    rp_id_hash: bytes
    flags: int
    sign_count: int
    aaguid: bytes | None = None
    credential_id: bytes | None = None
    cose_key: bytes | None = None

    @property
    def user_present(self) -> bool:
        return bool(self.flags & FLAG_UP)

    @property
    def user_verified(self) -> bool:
        return bool(self.flags & FLAG_UV)


def _check_extensions(data: bytes, pos: int, flags: int) -> None:
    """Without the ED flag no byte may follow; with it exactly one CBOR map must follow."""
    if not flags & FLAG_ED:
        if pos != len(data):
            raise invalid("Trailing bytes in authenticatorData.")
        return
    try:
        ext, used = cbor_decode(data[pos:])
    except (CborError, UnicodeDecodeError):
        raise invalid("Extension data not decodable.") from None
    if not isinstance(ext, dict) or pos + used != len(data):
        raise invalid("Extension data invalid.")


def parse_authenticator_data(
    data: bytes, *, expect_attested: bool | None = None
) -> AuthenticatorData:
    """``expect_attested``: True for registration (AT required), False for assertions (AT
    refused), None leaves it open."""
    if len(data) < 37:
        raise invalid("authenticatorData too short.")
    rp_id_hash, flags = data[:32], data[32]
    (sign_count,) = struct.unpack(">I", data[33:37])
    if expect_attested is not None and bool(flags & FLAG_AT) != expect_attested:
        raise invalid("Attested credential data flag unexpected.")
    if not flags & FLAG_AT:
        _check_extensions(data, 37, flags)
        return AuthenticatorData(rp_id_hash, flags, sign_count)
    if len(data) < 55:
        raise invalid("Attested credential data truncated.")
    aaguid = data[37:53]
    (cred_len,) = struct.unpack(">H", data[53:55])
    cred_end = 55 + cred_len
    if cred_len == 0 or cred_len > 1023 or cred_end > len(data):
        raise invalid("Credential ID length invalid.")
    try:
        _, used = cbor_decode(data[cred_end:])
    except (CborError, UnicodeDecodeError):
        raise invalid("COSE key not decodable.") from None
    cose = data[cred_end : cred_end + used]
    _check_extensions(data, cred_end + used, flags)
    return AuthenticatorData(rp_id_hash, flags, sign_count, aaguid, data[55:cred_end], cose)


# --- COSE keys -------------------------------------------------------------------------------

PublicKey = ec.EllipticCurvePublicKey | ed25519.Ed25519PublicKey | rsa.RSAPublicKey


def cose_algorithm(cose: bytes) -> int:
    key = _cose_map(cose)
    alg = key.get(3)
    if alg not in SUPPORTED_ALGORITHMS:
        raise invalid("Unsupported COSE algorithm.")
    return int(alg)


def _cose_map(cose: bytes) -> dict[Any, Any]:
    try:
        key, _ = cbor_decode(cose)
    except (CborError, UnicodeDecodeError):
        raise invalid("COSE key not decodable.") from None
    if not isinstance(key, dict):
        raise invalid("COSE key is not a map.")
    return key


def cose_public_key(cose: bytes) -> tuple[int, PublicKey]:
    key = _cose_map(cose)
    kty, alg = key.get(1), key.get(3)
    try:
        if alg == ALG_ES256 and kty == 2 and key.get(-1) == 1:
            x, y = key.get(-2), key.get(-3)
            if not (isinstance(x, bytes) and isinstance(y, bytes) and len(x) == len(y) == 32):
                raise invalid("EC2 coordinates invalid.")
            point = b"\x04" + x + y
            return alg, ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
        if alg == ALG_EDDSA and kty == 1 and key.get(-1) == 6:
            x = key.get(-2)
            if not (isinstance(x, bytes) and len(x) == 32):
                raise invalid("OKP key invalid.")
            return alg, ed25519.Ed25519PublicKey.from_public_bytes(x)
        if alg == ALG_RS256 and kty == 3:
            n, e = key.get(-1), key.get(-2)
            if not (isinstance(n, bytes) and isinstance(e, bytes)) or len(n) < 256:
                raise invalid("RSA key invalid or shorter than 2048 bit.")
            numbers = rsa.RSAPublicNumbers(int.from_bytes(e, "big"), int.from_bytes(n, "big"))
            return alg, numbers.public_key()
    except ValueError:
        raise invalid("COSE key not usable.") from None
    raise invalid("Unsupported COSE key type or algorithm.")


def verify_signature(cose: bytes, signature: bytes, signed: bytes) -> None:
    alg, key = cose_public_key(cose)
    try:
        if isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
        elif isinstance(key, ed25519.Ed25519PublicKey):
            key.verify(signature, signed)
        else:
            key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise invalid(f"Signature invalid (alg {alg}).") from None


# --- client data -----------------------------------------------------------------------------


def verify_client_data(
    raw: bytes, *, expected_type: str, challenge: bytes, origins: list[str]
) -> None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise invalid("clientDataJSON not decodable.") from None
    if not isinstance(data, dict) or data.get("type") != expected_type:
        raise invalid("clientDataJSON type mismatch.")
    received = data.get("challenge")
    if not isinstance(received, str) or not secrets.compare_digest(
        b64url_decode(received), challenge
    ):
        raise invalid("Challenge mismatch.")
    if data.get("origin") not in origins:
        raise invalid("Origin not allowed.")
    if data.get("crossOrigin") is True:
        raise invalid("Cross origin ceremony refused.")


def rp_id_hash(settings: Settings) -> bytes:
    return hashlib.sha256((settings.webauthn_rp_id or "").encode("utf-8")).digest()


def check_sign_count(stored: int, received: int) -> None:
    """Strict counter rule: both zero means the authenticator has no counter; otherwise the
    received value must be greater than the stored one (clone detection, WebAuthn 7.2 step 21)."""
    if stored == 0 and received == 0:
        return
    if received <= stored:
        raise invalid("Sign counter did not increase (possible cloned authenticator).")


# --- ceremonies ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredCredential:
    credential_id: str
    public_key: str
    sign_count: int
    aaguid: str | None
    user_verified: bool


def verify_registration(
    settings: Settings,
    *,
    challenge: bytes,
    credential_id: str,
    client_data_json: str,
    attestation_object: str,
    require_user_verification: bool,
) -> RegisteredCredential:
    client_data = b64url_decode(client_data_json)
    verify_client_data(
        client_data,
        expected_type="webauthn.create",
        challenge=challenge,
        origins=list(settings.webauthn_origins),
    )
    raw_attestation = b64url_decode(attestation_object)
    try:
        attestation, used = cbor_decode(raw_attestation)
    except (CborError, UnicodeDecodeError):
        raise invalid("attestationObject not decodable.") from None
    if used != len(raw_attestation):
        raise invalid("Trailing bytes after attestationObject.")
    if not isinstance(attestation, dict) or not isinstance(attestation.get("authData"), bytes):
        raise invalid("attestationObject without authData.")
    if attestation.get("fmt") != "none":
        # Only attestation "none" is requested; other formats are not evaluated (P14-02).
        raise invalid("Only attestation format none is accepted.")
    auth = parse_authenticator_data(attestation["authData"], expect_attested=True)
    if not secrets.compare_digest(auth.rp_id_hash, rp_id_hash(settings)):
        raise invalid("RP ID hash mismatch.")
    if not auth.user_present:
        raise invalid("User presence missing.")
    if require_user_verification and not auth.user_verified:
        raise invalid("User verification missing.")
    if auth.credential_id is None or auth.cose_key is None or auth.aaguid is None:
        raise invalid("Attested credential data missing.")
    if b64url_encode(auth.credential_id) != credential_id.rstrip("="):
        raise invalid("Credential ID mismatch.")
    cose_public_key(auth.cose_key)  # refuses unsupported or malformed keys
    return RegisteredCredential(
        credential_id=b64url_encode(auth.credential_id),
        public_key=b64url_encode(auth.cose_key),
        sign_count=auth.sign_count,
        aaguid=str(uuid.UUID(bytes=auth.aaguid)),
        user_verified=auth.user_verified,
    )


def verify_assertion(
    settings: Settings,
    *,
    challenge: bytes,
    public_key: str,
    stored_sign_count: int,
    client_data_json: str,
    authenticator_data: str,
    signature: str,
    require_user_verification: bool,
) -> int:
    """Returns the new sign counter after a valid assertion."""
    client_data = b64url_decode(client_data_json)
    verify_client_data(
        client_data,
        expected_type="webauthn.get",
        challenge=challenge,
        origins=list(settings.webauthn_origins),
    )
    raw_auth = b64url_decode(authenticator_data)
    auth = parse_authenticator_data(raw_auth, expect_attested=False)
    if not secrets.compare_digest(auth.rp_id_hash, rp_id_hash(settings)):
        raise invalid("RP ID hash mismatch.")
    if not auth.user_present:
        raise invalid("User presence missing.")
    if require_user_verification and not auth.user_verified:
        raise invalid("User verification missing.")
    signed = raw_auth + hashlib.sha256(client_data).digest()
    verify_signature(b64url_decode(public_key), b64url_decode(signature), signed)
    check_sign_count(stored_sign_count, auth.sign_count)
    return auth.sign_count


# --- challenge store (Redis, single use) -----------------------------------------------------


def _challenge_key(challenge_id: str) -> str:
    return f"webauthn:challenge:{challenge_id}"


async def enforce_options_limit(
    redis: Any, settings: Any, *, scope: str, ip: str, user_id: str | None
) -> None:
    """Fixed window counter per client address and per user for the option endpoints (W01-01).

    ``scope`` separates ``login`` from ``register``. Exceeding a limit raises 429
    (``MHVP-CORE-0006``) with ``Retry-After`` in the extensions. Fails open if Redis is
    unavailable, like the global middleware; the challenge store would fail anyway.
    """
    window = int(settings.webauthn_options_window_seconds)
    now = int(time.time())
    start = now - now % window
    reset = start + window - now
    checks = [(f"ip:{ip}", int(settings.webauthn_options_limit_per_ip))]
    if user_id is not None:
        checks.append((f"user:{user_id}", int(settings.webauthn_options_limit_per_user)))
    for subject, limit in checks:
        key = f"webauthn:opts:{scope}:{subject}:{start}"
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, window * 2)
                count = int((await pipe.execute())[0])
        except (RedisError, OSError):
            return
        if count > limit:
            raise ProblemError(
                ErrorCodes.RATE_LIMITED,
                detail=f"Zu viele Anfragen. Bitte in {reset} Sekunden erneut versuchen.",
                extensions={"retry_after": reset},
            )


async def issue_challenge(redis: Any, *, purpose: str, **context: Any) -> tuple[str, bytes]:
    challenge_id = secrets.token_urlsafe(24)
    challenge = secrets.token_bytes(32)
    payload = {"purpose": purpose, "challenge": b64url_encode(challenge), **context}
    await redis.set(_challenge_key(challenge_id), json.dumps(payload), ex=CHALLENGE_TTL_SECONDS)
    return challenge_id, challenge


async def consume_challenge(redis: Any, challenge_id: str, *, purpose: str) -> dict[str, Any]:
    """Atomically reads and deletes the challenge: a second use or an expired one fails."""
    raw = await redis.getdel(_challenge_key(challenge_id))
    if raw is None:
        raise invalid("Challenge unknown, expired or already used.")
    data: dict[str, Any] = json.loads(raw)
    if data.get("purpose") != purpose:
        raise invalid("Challenge purpose mismatch.")
    data["challenge_bytes"] = b64url_decode(str(data["challenge"]))
    return data
