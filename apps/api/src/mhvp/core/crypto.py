"""Field encryption (section 3.5, ADR 0006).

AES-256-GCM with one key per scope, derived by HKDF-SHA256 from ``MHVP_MASTER_KEY``. The scope is
the tenant id (tenant data) or ``platform`` (user level secrets such as TOTP seeds). The scope is
stored in the ciphertext header, bound as associated data and must match the scope of the caller,
so ciphertext copied into another tenant cannot be decrypted there.

Format: ``b"v1" | len(scope) (1 byte) | scope | nonce (12) | ciphertext+tag``.
"""

import base64
import os
from contextvars import ContextVar
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import LargeBinary
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

PLATFORM_SCOPE = "platform"
_VERSION = b"v1"
_NONCE_BYTES = 12

# Process wide (set once at startup); the scope is per request/task.
_master_key: bytes | None = None
_scope: ContextVar[str] = ContextVar("mhvp_crypto_scope", default=PLATFORM_SCOPE)


class CryptoError(Exception):
    pass


def decode_master_key(value: str) -> bytes:
    key = base64.b64decode(value, validate=True)
    if len(key) != 32:
        raise CryptoError("MHVP_MASTER_KEY must decode to 32 bytes")
    return key


def set_master_key(key: bytes) -> None:
    global _master_key
    if len(key) != 32:
        raise CryptoError("master key must be 32 bytes")
    _master_key = key
    _derive.cache_clear()


def is_configured() -> bool:
    return _master_key is not None


def set_scope(scope: str) -> object:
    return _scope.set(scope)


def reset_scope(token: object) -> None:
    _scope.reset(token)  # type: ignore[arg-type]


def current_scope() -> str:
    return _scope.get()


@lru_cache(maxsize=256)
def _derive(master: bytes, scope: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"mhvp-field-encryption", info=scope.encode()
    ).derive(master)


def _key(scope: str) -> bytes:
    master = _master_key
    if master is None:
        raise CryptoError("field encryption is not configured (MHVP_MASTER_KEY)")
    return _derive(master, scope)


def encrypt(plaintext: str, scope: str | None = None) -> bytes:
    scope = scope or current_scope()
    scope_bytes = scope.encode()
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(_key(scope)).encrypt(nonce, plaintext.encode(), scope_bytes)
    return _VERSION + bytes([len(scope_bytes)]) + scope_bytes + nonce + sealed


def decrypt(blob: bytes, scope: str | None = None) -> str:
    expected = scope or current_scope()
    if blob[:2] != _VERSION:
        raise CryptoError("unknown ciphertext version")
    length = blob[2]
    stored_scope = blob[3 : 3 + length].decode()
    if stored_scope != expected:
        raise CryptoError("ciphertext belongs to another scope")
    nonce = blob[3 + length : 3 + length + _NONCE_BYTES]
    sealed = blob[3 + length + _NONCE_BYTES :]
    try:
        return AESGCM(_key(expected)).decrypt(nonce, sealed, stored_scope.encode()).decode()
    except Exception as exc:  # InvalidTag and friends
        raise CryptoError("ciphertext cannot be decrypted") from exc


class EncryptedText(TypeDecorator[str]):
    """Column type storing text encrypted for the current scope (tenant or platform)."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> bytes | None:
        return None if value is None else encrypt(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        return None if value is None else decrypt(bytes(value))
