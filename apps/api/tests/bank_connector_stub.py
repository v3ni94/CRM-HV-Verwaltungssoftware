"""Connector stub (Attrappe) for the bank retrieval measurement (S16-08). Implements the
`BankConnector` protocol of `mhvp.banking.connectors` without any network access and delivers a
fixed number of generated transactions per account. Payment submission is refused like in every
read connector."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from mhvp.banking.camt import RawTransaction
from mhvp.banking.connectors import (
    BalanceInfo,
    BankAccountInfo,
    BankSearchResult,
    ConnectionResult,
    ConnectorNotSupportedError,
    ConsentInfo,
    WebFormHandle,
    refuse_payment_submission,
)


class StubBankConnector:
    def __init__(self, ibans: list[str], transactions_per_account: int = 20) -> None:
        self.ibans = ibans
        self.per_account = transactions_per_account
        self.fetch_calls = 0

    def search_bank(self, query: str) -> list[BankSearchResult]:
        return [BankSearchResult(name="Attrappenbank", external_ref="stub", bic="STUBDEFFXXX")]

    def start_connection(self, bank: BankSearchResult) -> WebFormHandle:
        raise ConnectorNotSupportedError("Attrappe: kein Webformular")

    def complete_connection(self, external_ref: str) -> ConnectionResult:
        return ConnectionResult(status="ok", connection_ref="stub", consent_valid_until=None)

    def list_accounts(self, connection_ref: str | None = None) -> list[BankAccountInfo]:
        return [BankAccountInfo(iban=iban, external_account_id=iban) for iban in self.ibans]

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        self.fetch_calls += 1
        return [
            RawTransaction(
                bank_reference=f"STUB-{account.iban[-6:]}-{n:04d}",
                booking_date=since + timedelta(days=n % 28),
                value_date=None,
                amount=Decimal("100.00") + Decimal(n),
                currency="EUR",
                counterpart_name=f"Zahler {n:03d}",
                counterpart_iban=None,
                counterpart_bic=None,
                purpose=f"Hausgeld Lasttest {n:03d}",
                end_to_end_id=None,
                mandate_reference=None,
                creditor_id=None,
                transaction_code=None,
            )
            for n in range(self.per_account)
        ]

    def refresh_consent(self, connection_ref: str) -> WebFormHandle:
        raise ConnectorNotSupportedError("Attrappe: keine Einwilligung")

    def fetch_balance(self, account: BankAccountInfo) -> BalanceInfo:
        return BalanceInfo(booked="0.00", available="0.00", currency="EUR", as_of=None)

    def consent_status(self, connection_ref: str) -> ConsentInfo:
        return ConsentInfo(status="valid", valid_until=None)

    def submit_payment_batch(self, batch_ref: str) -> str:
        refuse_payment_submission()
        raise AssertionError("unreachable")
