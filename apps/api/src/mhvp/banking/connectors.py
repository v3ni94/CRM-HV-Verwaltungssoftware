"""Bank connector interface (8.1). Only the file import is implemented; EBICS, aggregator and
FinTS need bank contracts and a provider decision (V2, V3) and report "not configured"."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from mhvp.banking.camt import RawTransaction


@dataclass(frozen=True)
class BankAccountInfo:
    iban: str
    currency: str = "EUR"


class ConnectorNotConfiguredError(Exception):
    """The connector has no contract, credentials or provider decision yet."""


class BankConnector(Protocol):
    def list_accounts(self) -> list[BankAccountInfo]: ...
    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]: ...


class UnconfiguredConnector:
    def __init__(self, name: str) -> None:
        self.name = name

    def list_accounts(self) -> list[BankAccountInfo]:
        raise ConnectorNotConfiguredError(self.name)

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        raise ConnectorNotConfiguredError(self.name)
