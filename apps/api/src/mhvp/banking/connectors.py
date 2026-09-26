"""Bank connector interface (8.1, M11-finapi Stage 1).

Two connector families exist today:

- `FileConnector`: CSV/CAMT file upload, parsed by `mhvp.banking.camt`. Unlimited banks,
  no consent, no online fetch; the operator uploads a statement file.
- `FinApiConnector`: PSD2/XS2A open banking via the finAPI aggregator (`mhvp.banking.finapi`),
  read only, WebForm based. Primary path for unlimited banks going forward (operator
  decision 25.09.2026).

HBCI/FinTS is intentionally **not** implemented; this module only keeps the seam (the
`BankConnector` protocol) so a `FinTsConnector` can be added later without changing callers.
`UnconfiguredConnector` still stands in for that and for any connector without a signed
contract or credentials (EBICS, GoCardless).

Credentials for online banking never touch this codebase: WebForm based connectors return a
provider hosted URL (`WebFormHandle.url`) that the browser is redirected to; bank login and
account authorization happen there (see `docs/rules/M11-04-no-credentials-in-crm.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from mhvp.banking import camt, mt940
from mhvp.banking.camt import ParsedFile, RawTransaction

MT940_SUFFIXES = (".sta", ".mt940", ".940", ".swi")


@dataclass(frozen=True)
class BankAccountInfo:
    iban: str
    currency: str = "EUR"
    external_account_id: str | None = None
    account_holder_name: str | None = None
    account_type: str | None = None
    account_name: str | None = None
    balance_booked: str | None = None
    balance_available: str | None = None
    balance_currency: str | None = None
    balance_as_of: str | None = None


@dataclass(frozen=True)
class BankSearchResult:
    """One bank a connector's search returned. `external_ref` is opaque and connector
    specific (e.g. a finAPI bank id); callers pass it back into `start_connection` unchanged."""

    name: str
    external_ref: str
    bic: str | None = None
    iban_prefix: str | None = None


@dataclass(frozen=True)
class WebFormHandle:
    """A provider hosted authorization page the browser is redirected to. `external_ref`
    identifies the connector's own pending connection/session (e.g. finAPI WebForm id) and is
    opaque outside the connector; callers pass it back into `complete_connection` unchanged."""

    external_ref: str
    url: str
    status: str


@dataclass(frozen=True)
class ConnectionResult:
    """Outcome of `complete_connection`: still pending, or the connector's own reference to
    the now (partially) authorized bank connection, used by `list_accounts`/`refresh_consent`."""

    status: str
    connection_ref: str | None
    consent_valid_until: date | None
    error_message: str | None = None


class ConnectorNotConfiguredError(Exception):
    """The connector has no contract, credentials or provider decision yet."""


class ConnectorNotSupportedError(Exception):
    """The connector exists but this operation is not part of its scope (e.g. `FileConnector`
    has no online bank search or consent to refresh)."""


@runtime_checkable
class BankConnector(Protocol):
    """Common seam for every way MHVP can learn about a bank account. A concrete connector
    may raise `ConnectorNotSupportedError` for a method outside its nature (a file upload has
    no bank search) and `ConnectorNotConfiguredError` when it exists but has no credentials or
    contract yet; callers must handle both, never assume every method is reachable."""

    def search_bank(self, query: str) -> list[BankSearchResult]: ...

    def start_connection(self, bank: BankSearchResult) -> WebFormHandle: ...

    def complete_connection(self, external_ref: str) -> ConnectionResult: ...

    def list_accounts(self, connection_ref: str | None = None) -> list[BankAccountInfo]: ...

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]: ...

    def refresh_consent(self, connection_ref: str) -> WebFormHandle: ...


class UnconfiguredConnector:
    """Placeholder for a connector family without a signed contract or credentials yet
    (EBICS, GoCardless) and for the not-yet-built FinTS/HBCI adapter. Every call reports
    exactly that instead of guessing at behaviour."""

    def __init__(self, name: str) -> None:
        self.name = name

    def _refuse(self) -> None:
        raise ConnectorNotConfiguredError(self.name)

    def search_bank(self, query: str) -> list[BankSearchResult]:
        self._refuse()
        return []

    def start_connection(self, bank: BankSearchResult) -> WebFormHandle:
        self._refuse()
        raise AssertionError  # pragma: no cover - _refuse always raises

    def complete_connection(self, external_ref: str) -> ConnectionResult:
        self._refuse()
        raise AssertionError  # pragma: no cover

    def list_accounts(self, connection_ref: str | None = None) -> list[BankAccountInfo]:
        self._refuse()
        return []

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        self._refuse()
        return []

    def refresh_consent(self, connection_ref: str) -> WebFormHandle:
        self._refuse()
        raise AssertionError  # pragma: no cover


class FileConnector:
    """CAMT.053/MT940 file upload (`mhvp.banking.camt.parse`, `mhvp.banking.mt940.parse`,
    `mhvp.banking.services.import_file`). Parsing and import still happen where they always
    have (the upload endpoint and `services.import_file`); `parse` only chooses the parser by
    file name suffix or content, both parsers yield the same `ParsedFile` and the import
    normalises both the same way (bank reference primary, content hash secondary, D05). This
    class gives the file path a place on the common `BankConnector` seam so callers can treat
    every connector uniformly where that makes sense. It has no bank search, no WebForm and
    no consent to refresh: those calls raise `ConnectorNotSupportedError` rather than
    pretending to support them. Bank specific CSV remains open (M11-02)."""

    @staticmethod
    def detect_format(data: bytes, filename: str | None = None) -> str:
        """``"mt940"`` for an MT940 suffix or content starting with ``:20:``, else ``"camt"``."""
        name = (filename or "").lower()
        if name.endswith(MT940_SUFFIXES) or mt940.looks_like_mt940(data):
            return "mt940"
        return "camt"

    @classmethod
    def parse(cls, data: bytes, filename: str | None = None) -> ParsedFile:
        """Parse an uploaded statement file; raises ValueError with a German message."""
        if cls.detect_format(data, filename) == "mt940":
            return mt940.parse(data)
        return camt.parse(data)

    def _unsupported(self, what: str) -> None:
        raise ConnectorNotSupportedError(
            f"{what} ist beim Datei-Upload nicht vorgesehen (keine Online-Anbindung)."
        )

    def search_bank(self, query: str) -> list[BankSearchResult]:
        self._unsupported("Banksuche")
        return []

    def start_connection(self, bank: BankSearchResult) -> WebFormHandle:
        self._unsupported("Freigabe-WebForm")
        raise AssertionError  # pragma: no cover

    def complete_connection(self, external_ref: str) -> ConnectionResult:
        self._unsupported("Freigabe-Abschluss")
        raise AssertionError  # pragma: no cover

    def list_accounts(self, connection_ref: str | None = None) -> list[BankAccountInfo]:
        self._unsupported("Kontenabruf")
        return []

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        self._unsupported("Online-Umsatzabruf")
        return []

    def refresh_consent(self, connection_ref: str) -> WebFormHandle:
        self._unsupported("Zustimmungserneuerung")
        raise AssertionError  # pragma: no cover
