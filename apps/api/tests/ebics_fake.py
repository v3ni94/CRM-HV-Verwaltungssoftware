"""In memory EBICS bank double for tests (AE23, no network).

It implements ``mhvp.banking.ebics_transport.EbicsTransport``. Its "letter hash" is the
internal SHA-256 of the public key with a ``T`` prefix: a test value only, deliberately not
the hash algorithm of the EBICS specification (open question AE23-02).
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date

from mhvp.banking.ebics_keys import generate_key_pair, private_matches_public, public_key_sha256
from mhvp.banking.ebics_transport import (
    EbicsBankKey,
    EbicsClientKeys,
    EbicsDownload,
    EbicsDownloadOrder,
    EbicsOrderResult,
    EbicsSubscriberRef,
    EbicsTransportError,
)


def c53_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@dataclass
class FakeEbicsBank:
    bits: int = 2048
    name: str = "fake"
    zip_content: bytes = b""
    fail_next: EbicsTransportError | None = None
    ini: list[str] = field(default_factory=list)
    hia: list[tuple[str, str]] = field(default_factory=list)
    downloads: list[tuple[str, date | None, date | None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.bank_auth = generate_key_pair(self.bits)
        self.bank_enc = generate_key_pair(self.bits)

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error

    def _check_client(self, keys: EbicsClientKeys) -> None:
        auth_pub, enc_pub = self.hia[-1]
        assert private_matches_public(keys.authentication_private_pem, auth_pub)
        assert private_matches_public(keys.encryption_private_pem, enc_pub)

    def letter_hash(self, public_pem: str, version: str, ebics_version: str) -> str | None:
        return "T" + public_key_sha256(public_pem)[1:]

    def send_ini(
        self, subscriber: EbicsSubscriberRef, signature_public_pem: str
    ) -> EbicsOrderResult:
        self._maybe_fail()
        self.ini.append(signature_public_pem)
        return EbicsOrderResult(transport_ref=f"INI-{len(self.ini)}")

    def send_hia(
        self,
        subscriber: EbicsSubscriberRef,
        authentication_public_pem: str,
        encryption_public_pem: str,
    ) -> EbicsOrderResult:
        self._maybe_fail()
        self.hia.append((authentication_public_pem, encryption_public_pem))
        return EbicsOrderResult(transport_ref=f"HIA-{len(self.hia)}")

    def fetch_bank_keys(
        self, subscriber: EbicsSubscriberRef, keys: EbicsClientKeys
    ) -> list[EbicsBankKey]:
        self._maybe_fail()
        self._check_client(keys)
        return [
            EbicsBankKey(
                "authentication",
                "X002",
                self.bank_auth.public_pem,
                self.letter_hash(self.bank_auth.public_pem, "X002", "3.0"),
            ),
            EbicsBankKey(
                "encryption",
                "E002",
                self.bank_enc.public_pem,
                self.letter_hash(self.bank_enc.public_pem, "E002", "3.0"),
            ),
        ]

    def download(
        self,
        subscriber: EbicsSubscriberRef,
        keys: EbicsClientKeys,
        order: EbicsDownloadOrder,
        since: date | None,
        until: date | None,
    ) -> EbicsDownload:
        self._maybe_fail()
        self._check_client(keys)
        assert keys.bank_authentication_public_pem == self.bank_auth.public_pem
        self.downloads.append((order.btf, since, until))
        return EbicsDownload(content=self.zip_content, transport_ref=f"C53-{len(self.downloads)}")
