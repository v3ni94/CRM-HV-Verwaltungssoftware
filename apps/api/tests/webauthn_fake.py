"""Software authenticator for WebAuthn tests (S16-01): builds attestation objects and
assertions exactly as a browser plus authenticator would, without a browser."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from mhvp.core.auth.webauthn import b64url_decode, b64url_encode


def cbor(value: Any) -> bytes:
    def head(major: int, n: int) -> bytes:
        if n < 24:
            return bytes([major << 5 | n])
        for info, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * size):
                return bytes([major << 5 | info]) + n.to_bytes(size, "big")
        raise ValueError(n)

    if isinstance(value, bool):
        return bytes([0xF5 if value else 0xF4])
    if isinstance(value, int):
        return head(0, value) if value >= 0 else head(1, -1 - value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode()
        return head(3, len(raw)) + raw
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(cbor(v) for v in value)
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(cbor(k) + cbor(v) for k, v in value.items())
    raise TypeError(type(value))


class FakeAuthenticator:
    def __init__(self, rp_id: str, origin: str, *, alg: int = -7, counter: int = 0) -> None:
        self.rp_id, self.origin, self.alg = rp_id, origin, alg
        self.counter = counter
        self.credential_id = os.urandom(32)
        self.key: Any = (
            ec.generate_private_key(ec.SECP256R1())
            if alg == -7
            else ed25519.Ed25519PrivateKey.generate()
        )

    @property
    def id(self) -> str:
        return b64url_encode(self.credential_id)

    def cose(self) -> bytes:
        if self.alg == -7:
            nums = self.key.public_key().public_numbers()
            return cbor(
                {1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}
            )
        raw = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return cbor({1: 1, 3: -8, -1: 6, -2: raw})

    def _client_data(self, type_: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {"type": type_, "challenge": challenge, "origin": origin or self.origin}
        ).encode()

    def _rp_hash(self, rp_id: str | None) -> bytes:
        return hashlib.sha256((rp_id or self.rp_id).encode()).digest()

    def create(
        self,
        options: dict[str, Any],
        *,
        uv: bool = True,
        origin: str | None = None,
        fmt: str = "none",
    ) -> dict[str, Any]:
        flags = 0x01 | 0x40 | (0x04 if uv else 0)
        auth = (
            self._rp_hash(None)
            + bytes([flags])
            + struct.pack(">I", self.counter)
            + b"\0" * 16
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self.cose()
        )
        att = cbor({"fmt": fmt, "attStmt": {}, "authData": auth})
        return {
            "credential_id": self.id,
            "response": {
                "client_data_json": b64url_encode(
                    self._client_data("webauthn.create", options["challenge"], origin)
                ),
                "attestation_object": b64url_encode(att),
                "transports": ["internal"],
            },
        }

    def get(
        self,
        options: dict[str, Any],
        *,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
        counter: int | None = None,
        tamper: bool = False,
    ) -> dict[str, Any]:
        self.counter = self.counter + 1 if counter is None else counter
        auth = (
            self._rp_hash(rp_id)
            + bytes([0x01 | (0x04 if uv else 0)])
            + struct.pack(">I", self.counter)
        )
        client = self._client_data("webauthn.get", options["challenge"], origin)
        signed = auth + hashlib.sha256(client).digest()
        sig = (
            self.key.sign(signed, ec.ECDSA(hashes.SHA256()))
            if self.alg == -7
            else self.key.sign(signed)
        )
        if tamper:
            sig = b64url_decode(b64url_encode(sig))[:-1] + bytes([sig[-1] ^ 1])
        return {
            "credential_id": self.id,
            "response": {
                "client_data_json": b64url_encode(client),
                "authenticator_data": b64url_encode(auth),
                "signature": b64url_encode(sig),
            },
        }
