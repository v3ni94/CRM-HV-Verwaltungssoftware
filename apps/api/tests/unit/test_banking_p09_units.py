"""P09 (Lückenliste 30.09.2026): connector protocol extension (M11-03), retry policy of the
per account sync (M11-04), B09 helper of the weekly digest (M12-02). Fixed expected values."""

from datetime import date
from typing import Any

import pytest

from mhvp.banking import digest, tasks
from mhvp.banking.connectors import (
    BankAccountInfo,
    BankConnector,
    ConnectorNotConfiguredError,
    ConnectorNotSupportedError,
    FileConnector,
    UnconfiguredConnector,
)
from mhvp.banking.finapi import FinApiConnector
from mhvp.core.problems import ErrorCodes, ProblemError


def test_protocol_has_balance_consent_and_payment_methods() -> None:
    for name in ("fetch_balance", "consent_status", "submit_payment_batch"):
        assert hasattr(BankConnector, name)
    assert isinstance(FileConnector(), BankConnector)
    assert isinstance(UnconfiguredConnector("ebics"), BankConnector)


def test_file_and_unconfigured_connectors_refuse_online_balance_and_payments() -> None:
    account = BankAccountInfo(iban="DE02120300000000202051")
    with pytest.raises(ConnectorNotSupportedError):
        FileConnector().fetch_balance(account)
    with pytest.raises(ConnectorNotSupportedError):
        FileConnector().submit_payment_batch("batch-1")
    assert FileConnector().consent_status("x").status == "not_required"
    with pytest.raises(ConnectorNotConfiguredError):
        UnconfiguredConnector("ebics").consent_status("x")


class _Client:
    def list_accounts(self, **_: Any) -> list[Any]:
        class A:
            account_id = "1001"
            balance_booked = "1234.56"
            balance_available = None
            balance_currency = "EUR"
            balance_as_of = "2026-09-30"

        return [A()]

    def get_bank_connection(self, _id: str) -> dict[str, Any]:
        return {"status": "COMPLETED", "errorMessage": None}


def test_finapi_connector_balance_consent_and_no_payment() -> None:
    connector: Any = FinApiConnector(_Client())  # type: ignore[arg-type]
    assert isinstance(connector, BankConnector)
    balance = connector.fetch_balance(BankAccountInfo(iban="", external_account_id="1001"))
    assert balance.booked == "1234.56"
    assert balance.currency == "EUR"
    consent = connector.consent_status("c1")
    assert consent.status == "COMPLETED"
    assert consent.valid_until is None  # expiry field not verified (M11-41)
    with pytest.raises(ConnectorNotSupportedError):
        connector.submit_payment_batch("b1")


def test_retry_policy() -> None:
    assert [tasks.retry_countdown(n) for n in range(3)] == [60, 120, 240]
    assert tasks.SYNC_MAX_RETRIES == 3
    assert tasks.is_transient_sync_error(ProblemError(ErrorCodes.FINAPI_UNAVAILABLE))
    assert tasks.is_transient_sync_error(ProblemError(ErrorCodes.FINAPI_RATE_LIMITED))
    assert not tasks.is_transient_sync_error(ProblemError(ErrorCodes.FINAPI_AUTH))
    assert tasks.should_retry({"transient": 1}, called_directly=False, retries=0) is True
    assert tasks.should_retry({"transient": 1}, called_directly=False, retries=3) is False
    assert tasks.should_retry({"transient": 1}, called_directly=True, retries=0) is False
    assert tasks.should_retry({"new": 0}, called_directly=False, retries=0) is False


def test_digest_helpers() -> None:
    assert digest.week_start_of(date(2026, 9, 30)) == date(2026, 9, 28)
    assert digest.previous_month(date(2026, 9, 28)) == (date(2026, 8, 1), date(2026, 8, 31))
    assert digest.previous_month(date(2026, 1, 5)) == (date(2025, 12, 1), date(2025, 12, 31))
    ok = [{"statements": [{"statement_difference": "0.00", "ledger_difference": None}]}]
    assert digest.reconciliation_ok(ok) is True
    assert digest.reconciliation_ok([{"statements": []}]) is False
    diff = [{"statements": [{"statement_difference": "0.01", "ledger_difference": "0"}]}]
    assert digest.reconciliation_ok(diff) is False
    ledger = [{"statements": [{"statement_difference": "0", "ledger_difference": "-5.00"}]}]
    assert digest.reconciliation_ok(ledger) is False
    assert digest.reconciliation_ok([]) is True


def test_local_hour_default_sync_hour() -> None:
    assert tasks.DEFAULT_SYNC_HOUR == 6
