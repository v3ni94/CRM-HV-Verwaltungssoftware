"""EBICS transport seam (M11-01, AE23, rule M11-11).

The EBICS protocol itself (XML schema H004/H005, authentication signature, hybrid
encryption, compression, segmentation, receipts, the hash value of the INI and HIA letters
and of the bank keys) is defined by the official EBICS specification. That specification is
downloadable from ebics.de only after accepting its terms of use, which has not been done for
this repository, and the client library ``fintech`` (joonis) is licensed and not installed
(operator decision V2). Therefore no protocol message is built here (open questions AE23-01
and AE23-02): the platform talks to a bank only through an implementation of
:class:`EbicsTransport`. In production :class:`UnavailableEbicsTransport` answers every call
with ``MHVP-BANK-0050``; tests register an in memory double (no network) through
:func:`set_transport_factory`.

Order types and BTF parameters used by the platform:

* ``INI``, ``HIA``, ``HPB``: initialisation and bank key download as named in the bank
  contracts and in docs/runbooks/ebics-setup.md (wire details: AE23-02).
* ``C53``: download of all camt.053 statements of the customer as ZIP container, BTF
  ``EOP/DE//camt.053/ZIP`` (DFÜ-Abkommen Anlage 3 V26.11, chapter 9.2.1, page 808).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from mhvp.core.problems import ErrorCodes, ProblemError


@dataclass(frozen=True)
class EbicsDownloadOrder:
    """A download order with its EBICS 2.5 order type and its EBICS 3.0 BTF parameters."""

    order_type: str
    service: str
    scope: str
    option: str | None
    message: str
    container: str

    @property
    def btf(self) -> str:
        return f"{self.service}/{self.scope}/{self.option or ''}/{self.message}/{self.container}"


# DFÜ-Abkommen Anlage 3 V26.11, chapter 9.2.1: EOP/DE//camt.053/ZIP (C53).
C53 = EbicsDownloadOrder(
    order_type="C53",
    service="EOP",
    scope="DE",
    option=None,
    message="camt.053",
    container="ZIP",
)


@dataclass(frozen=True)
class EbicsSubscriberRef:
    host_id: str
    partner_id: str
    user_id: str
    url: str
    ebics_version: str
    signature_version: str


@dataclass(frozen=True)
class EbicsClientKeys:
    """Key material a transport needs for authenticated orders. Private keys are PEM strings
    decrypted from ``ebics_key.private_key`` for the duration of one call; a transport must not
    keep or log them."""

    authentication_private_pem: str
    encryption_private_pem: str
    bank_authentication_public_pem: str | None = None
    bank_encryption_public_pem: str | None = None


@dataclass(frozen=True)
class EbicsBankKey:
    usage: str  # "authentication" or "encryption"
    version: str
    public_pem: str
    letter_hash: str | None


@dataclass(frozen=True)
class EbicsOrderResult:
    transport_ref: str | None = None


@dataclass(frozen=True)
class EbicsDownload:
    content: bytes
    transport_ref: str | None = None


class EbicsTransportError(Exception):
    """The bank or the connection rejected an order; ``code`` is the return code the
    transport reported (kept unchanged, never interpreted by the platform)."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@runtime_checkable
class EbicsTransport(Protocol):
    name: str

    def letter_hash(self, public_pem: str, version: str, ebics_version: str) -> str | None: ...

    def send_ini(
        self, subscriber: EbicsSubscriberRef, signature_public_pem: str
    ) -> EbicsOrderResult: ...

    def send_hia(
        self,
        subscriber: EbicsSubscriberRef,
        authentication_public_pem: str,
        encryption_public_pem: str,
    ) -> EbicsOrderResult: ...

    def fetch_bank_keys(
        self, subscriber: EbicsSubscriberRef, keys: EbicsClientKeys
    ) -> list[EbicsBankKey]: ...

    def download(
        self,
        subscriber: EbicsSubscriberRef,
        keys: EbicsClientKeys,
        order: EbicsDownloadOrder,
        since: date | None,
        until: date | None,
    ) -> EbicsDownload: ...


class UnavailableEbicsTransport:
    """Production default: no specification conform implementation is installed."""

    name = "unavailable"

    def _refuse(self) -> None:
        raise ProblemError(ErrorCodes.EBICS_TRANSPORT_UNAVAILABLE)

    def letter_hash(self, public_pem: str, version: str, ebics_version: str) -> str | None:
        return None

    def send_ini(
        self, subscriber: EbicsSubscriberRef, signature_public_pem: str
    ) -> EbicsOrderResult:
        self._refuse()
        raise AssertionError  # pragma: no cover

    def send_hia(
        self,
        subscriber: EbicsSubscriberRef,
        authentication_public_pem: str,
        encryption_public_pem: str,
    ) -> EbicsOrderResult:
        self._refuse()
        raise AssertionError  # pragma: no cover

    def fetch_bank_keys(
        self, subscriber: EbicsSubscriberRef, keys: EbicsClientKeys
    ) -> list[EbicsBankKey]:
        self._refuse()
        raise AssertionError  # pragma: no cover

    def download(
        self,
        subscriber: EbicsSubscriberRef,
        keys: EbicsClientKeys,
        order: EbicsDownloadOrder,
        since: date | None,
        until: date | None,
    ) -> EbicsDownload:
        self._refuse()
        raise AssertionError  # pragma: no cover


_factory: Callable[[], EbicsTransport] | None = None


def set_transport_factory(factory: Callable[[], EbicsTransport] | None) -> None:
    """Registers the transport used by the API (tests: an in memory double). ``None`` resets
    to :class:`UnavailableEbicsTransport`; callers must reset after use."""
    global _factory
    _factory = factory


def get_transport() -> EbicsTransport:
    return _factory() if _factory is not None else UnavailableEbicsTransport()


def is_available() -> bool:
    return _factory is not None
