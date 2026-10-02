"""Fake python-fints client for unit and integration tests of `mhvp.banking.fints`. It mimics
the parts of `fints.client.FinTS3PinTanClient` the workflow uses (TAN mechanisms, dialog
context, `init_tan_response`, `pause_dialog`/`resume_dialog`, `send_tan`, accounts, balances,
transactions, `deconstruct`) and never opens a network connection. Exception class names
match python-fints so `fints.problem_for_exception` maps them the same way."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, ClassVar

GOOD_PIN = "geheim-pin-7"
GOOD_TAN = "123456"
IBAN_1 = "DE02120300000000202051"
IBAN_2 = "DE02500105170137075030"


class FinTSClientPINError(Exception):
    pass


class FinTSClientTemporaryAuthError(Exception):
    pass


class FinTSDialogError(Exception):
    pass


class FinTSClientError(Exception):
    pass


class FakeTan:
    """Stands in for `fints.client.NeedTANResponse` (duck typed by `fints.is_tan_request`)."""

    def __init__(self, kind: str, decoupled: bool, matrix: bool = False) -> None:
        self.kind = kind
        self.decoupled = decoupled
        self.challenge = "Bitte in der App freigeben" if decoupled else f"TAN für {kind} eingeben"
        self.challenge_hhduc = None if decoupled else "0248A0123456789"
        self.challenge_matrix = ("image/png", b"\x89PNG-fake") if matrix else None

    def get_data(self) -> bytes:
        return json.dumps({"kind": self.kind, "decoupled": self.decoupled}).encode()

    @classmethod
    def from_data(cls, blob: bytes) -> FakeTan:
        data = json.loads(blob)
        return cls(data["kind"], data["decoupled"])


class Scenario:
    """Class level switches a test sets before the workflow runs."""

    init_tan: ClassVar[bool] = True
    decoupled: ClassVar[bool] = False
    decoupled_polls_until_confirmed: ClassVar[int] = 1
    tan_for_transactions: ClassVar[bool] = False
    reject_pin: ClassVar[bool] = False
    lock_account: ClassVar[bool] = False
    unreachable: ClassVar[bool] = False
    matrix: ClassVar[bool] = False
    transactions: ClassVar[list[dict[str, Any]]] = []
    accounts: ClassVar[list[str]] = [IBAN_1, IBAN_2]
    balances: ClassVar[dict[str, str]] = {IBAN_1: "1234.56", IBAN_2: "-10.00"}
    constructed: ClassVar[list[dict[str, Any]]] = []
    polls: ClassVar[int] = 0
    transactions_tan_done: ClassVar[bool] = False
    mt940_unsupported: ClassVar[bool] = False
    balance_unsupported: ClassVar[bool] = False
    sepa_unsupported: ClassVar[bool] = False
    mt940_empty: ClassVar[bool] = False
    camt_with_balance: ClassVar[bool] = False
    # 9010 at dialog initialisation: "stored" rejects only a client built from stored state,
    # "always" rejects every dialog and the fake records the bank's return message.
    init_rejected: ClassVar[str | None] = None

    @classmethod
    def reset(cls) -> None:
        cls.init_tan, cls.decoupled, cls.decoupled_polls_until_confirmed = True, False, 1
        cls.tan_for_transactions = cls.reject_pin = cls.lock_account = cls.matrix = False
        cls.unreachable = cls.mt940_unsupported = False
        cls.balance_unsupported = cls.sepa_unsupported = False
        cls.mt940_empty = cls.camt_with_balance = False
        cls.init_rejected = None
        cls.transactions = [
            mt940_tx("2026-09-20", "700.00", "C", "GdWE Testweg Hausgeld 09/2026", "REF-1"),
            mt940_tx("2026-09-20", "700.00", "C", "GdWE Testweg Hausgeld 09/2026", "REF-2"),
        ]
        cls.accounts = [IBAN_1, IBAN_2]
        cls.balances = {IBAN_1: "1234.56", IBAN_2: "-10.00"}
        cls.constructed = []
        cls.polls = 0
        cls.transactions_tan_done = False


def mt940_tx(day: str, amount: str, status: str, purpose: str, bank_ref: str | None) -> Any:
    """A `mt940.models.Transaction` look-alike (only `.data` is used)."""
    return SimpleNamespace(
        data={
            "date": date.fromisoformat(day),
            "entry_date": date.fromisoformat(day),
            "amount": SimpleNamespace(amount=Decimal(amount), currency="EUR"),
            "status": status,
            "id": "NMSC",
            "customer_reference": "NONREF",
            "bank_reference": bank_ref,
            "transaction_details": (
                "166?00SEPA-GUTSCHRIFT?20EREF+E2E-1?21SVWZ+" + purpose + "?30COBADEFFXXX?31"
                "DE89370400440532013000?32Max Mustermann"
            ),
            "extra_details": "",
        }
    )


class FakeClient:
    def __init__(
        self,
        blz: str,
        login: str,
        pin: str,
        url: str,
        *,
        product_id: str,
        product_version: str = "1.0",
        from_data: bytes | None = None,
    ) -> None:
        if not product_id:
            raise TypeError("product_id mandatory")
        self.blz, self.login, self.pin, self.url = blz, login, pin, url
        Scenario.constructed.append(
            {"blz": blz, "login": login, "from_data": from_data, "url": url}
        )
        self.selected_tan_medium: str | None = None
        self._mechanism: str | None = None
        self.init_tan_response: Any = None
        self._in_dialog = False
        self._from_stored_state = bool(from_data)
        self.mhvp_responses: list[tuple[str, str]] = []
        if from_data:
            state = json.loads(from_data)
            self._mechanism = state.get("mechanism")
            self.selected_tan_medium = state.get("medium")

    # --- TAN mechanisms ---
    def fetch_tan_mechanisms(self) -> str | None:
        if self._mechanism is None:
            self._mechanism = "922" if Scenario.decoupled else "912"
        return self._mechanism

    def get_tan_mechanisms(self) -> dict[str, Any]:
        return {
            "912": SimpleNamespace(name="chipTAN optisch", decoupled=False),
            "922": SimpleNamespace(name="pushTAN 2.0", decoupled=True),
        }

    def set_tan_mechanism(self, code: str) -> None:
        self._mechanism = code

    def get_current_tan_mechanism(self) -> str | None:
        return self._mechanism

    def is_tan_media_required(self) -> bool:
        return True

    def get_tan_media(self) -> tuple[Any, list[Any]]:
        return "ALL", [SimpleNamespace(tan_medium_name="Handy 1")]

    def set_tan_medium(self, medium: Any) -> None:
        self.selected_tan_medium = medium.tan_medium_name

    # --- dialog ---
    def _auth(self) -> None:
        if Scenario.unreachable:
            import requests

            raise requests.exceptions.ConnectionError(
                f"HTTPSConnectionPool(host={self.url!r}): Max retries exceeded"
            )
        if Scenario.lock_account:
            raise FinTSClientTemporaryAuthError("Account is temporarily locked.")
        if Scenario.reject_pin or self.pin != GOOD_PIN:
            raise FinTSClientPINError("Error during dialog initialization, PIN wrong?")
        if Scenario.init_rejected == "always" or (
            Scenario.init_rejected == "stored" and self._from_stored_state
        ):
            self.mhvp_responses.append(("9010", "Verarbeitung zur Zeit nicht möglich"))
            raise FinTSClientError(
                "Error during dialog initialization, could not fetch BPD. Please check that "
                "you passed the correct bank identifier to the HBCI URL of the correct bank."
            )

    def __enter__(self) -> FakeClient:
        self._auth()
        self._in_dialog = True
        if Scenario.init_tan:
            self.init_tan_response = FakeTan(
                "init", self._mechanism == "922", matrix=Scenario.matrix
            )
        return self

    def __exit__(self, *exc: object) -> None:
        self._in_dialog = False

    def pause_dialog(self) -> bytes:
        return b"dialog-paused"

    @contextmanager
    def resume_dialog(self, dialog_data: bytes) -> Any:
        assert dialog_data == b"dialog-paused"
        self._in_dialog = True
        try:
            yield self
        finally:
            self._in_dialog = False

    def send_tan(self, challenge: FakeTan, tan: str) -> Any:
        if challenge.decoupled:
            Scenario.polls += 1
            if Scenario.polls < Scenario.decoupled_polls_until_confirmed:
                return FakeTan(challenge.kind, True)
        elif tan != GOOD_TAN:
            raise FinTSDialogError("Dialog response: 9941 - TAN ungültig")
        if challenge.kind == "transactions":
            Scenario.transactions_tan_done = True
            return list(Scenario.transactions)
        return SimpleNamespace(kind="init-response")

    def deconstruct(self, including_private: bool = False) -> bytes:
        assert including_private
        return json.dumps(
            {"mechanism": self._mechanism, "medium": self.selected_tan_medium}
        ).encode()

    # --- data ---
    def get_sepa_accounts(self) -> list[Any]:
        assert self._in_dialog
        if Scenario.sepa_unsupported:
            raise FinTSUnsupportedOperation("No supported HISPAS version found.")
        return [
            SimpleNamespace(
                iban=iban,
                bic="COBADEFFXXX",
                accountnumber=iban[-10:],
                subaccount=None,
                blz=self.blz,
            )
            for iban in Scenario.accounts
        ]

    def get_information(self) -> dict[str, Any]:
        assert self._in_dialog
        return {
            "bank": {},
            "accounts": [
                {
                    "iban": iban,
                    "account_number": iban[-10:],
                    "subaccount_number": None,
                    "bank_identifier": SimpleNamespace(bank_code=self.blz),
                }
                for iban in Scenario.accounts
            ]
            + [{"iban": None, "account_number": "999"}],
        }

    def get_balance(self, account: Any) -> Any:
        assert self._in_dialog
        if Scenario.balance_unsupported:
            raise FinTSUnsupportedOperation("No supported HISALS version found.")
        value = Scenario.balances.get(account.iban)
        if value is None:
            return None
        return SimpleNamespace(
            amount=SimpleNamespace(amount=Decimal(value), currency="EUR"), date=date(2026, 9, 27)
        )

    def get_transactions(self, account: Any, start: date | None, end: date | None) -> Any:
        assert self._in_dialog
        if Scenario.mt940_unsupported:
            raise FinTSUnsupportedOperation(
                "No supported HIKAZS version found. I support (5, 6, 7), bank supports ()."
            )
        if Scenario.tan_for_transactions and not Scenario.transactions_tan_done:
            return FakeTan("transactions", False)
        if account.iban != IBAN_1 or Scenario.mt940_empty:
            return []
        return list(Scenario.transactions)

    def get_transactions_xml(self, account: Any, start: date | None, end: date | None) -> Any:
        assert self._in_dialog
        if account.iban != IBAN_1:
            return ([], [])
        if Scenario.camt_with_balance:
            return ([CAMT052_DOC_WITH_BALANCE], [b""])
        return ([CAMT052_DOC], [b""])


class FinTSUnsupportedOperation(Exception):  # noqa: N818  (name mirrors python-fints)
    """Same class name as python-fints; the production code matches on the name."""


CAMT052_DOC = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.02">
  <BkToCstmrAcctRpt>
    <Rpt>
      <Id>RPT-1</Id>
      <Acct><Id><IBAN>DE02120300000000202051</IBAN></Id><Ccy>EUR</Ccy></Acct>
      <Ntry>
        <Amt Ccy="EUR">700.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
        <BookgDt><Dt>2026-09-02</Dt></BookgDt>
        <ValDt><Dt>2026-09-02</Dt></ValDt>
        <AcctSvcrRef>CAMT-REF-1</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>E2E-C1</EndToEndId></Refs>
          <RltdPties><Dbtr><Nm>Max Mieter</Nm></Dbtr>
            <DbtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></DbtrAcct></RltdPties>
          <RmtInf><Ustrd>Miete September</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">10.00</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <Sts>PDNG</Sts>
        <BookgDt><Dt>2026-09-03</Dt></BookgDt>
        <AcctSvcrRef>CAMT-REF-PENDING</AcctSvcrRef>
      </Ntry>
    </Rpt>
  </BkToCstmrAcctRpt>
</Document>
"""

CAMT052_DOC_WITH_BALANCE = CAMT052_DOC.replace(
    b"      <Ntry>",
    b"""      <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">100.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-01</Dt></Dt></Bal>
      <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">800.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-30</Dt></Dt></Bal>
      <Ntry>""",
    1,
)


def install(monkeypatch: Any) -> None:
    from mhvp.banking import fints as fints_mod

    Scenario.reset()
    monkeypatch.setattr(fints_mod, "CLIENT_FACTORY", lambda: FakeClient)
    monkeypatch.setattr(fints_mod, "RESTORE_RETRY", FakeTan.from_data)
