"""EBICS statement download (order type C53) on the common connector seam (M11-01, AE23).

Source: DFÜ-Abkommen Anlage 3 "Spezifikation der Datenformate", Version 26.11 vom 09.04.2026
(Die Deutsche Kreditwirtschaft):

* chapter 9.2.1 (page 808): C53 (BTF ``EOP/DE//camt.053/ZIP``) delivers a ZIP file with all
  camt.053 messages of the customer that are ready for download;
* chapter 9.2.2 (pages 808 to 810): the bank uses Zip32 and Zip64, the compression algorithm
  is not fixed; the XML files inside are named ``JJJJ-MM-TT_C53_<Konto>_<WWW>_<ID>.xml``
  (account as IBAN, or BIC or bank code plus "." plus account number; optional extension of
  up to 12 characters by bilateral agreement);
* page 698: one camt message carries the information of exactly one account; page 697: size
  related splits keep statement id and electronic sequence number and raise the page number.

The file name is informational only: the account is always taken from the XML (IBAN), the
name check is reported, never used to reject a file. Limits on member count and size are
product protection against oversized archives, not a rule of the source.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date

from mhvp.banking import camt
from mhvp.banking.camt import ParsedFile, RawTransaction
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
from mhvp.banking.ebics_transport import (
    C53,
    EbicsClientKeys,
    EbicsSubscriberRef,
    EbicsTransport,
)

MAX_MEMBERS = 2000
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 200 * 1024 * 1024
# JJJJ-MM-TT_C53_<account>_<currency>_<id>[<extension>].xml (Anlage 3, 9.2.2.1)
C53_NAME = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})_C53_(?P<account>[A-Za-z0-9.]+)_(?P<currency>[A-Z]{3})_"
    r"(?P<id>[A-Za-z0-9]+)\.xml$"
)


@dataclass(frozen=True)
class C53Member:
    name: str
    data: bytes
    sha256: str
    name_conforms: bool
    created_on: date | None
    account_hint: str | None


def _member_info(name: str) -> tuple[bool, date | None, str | None]:
    base = name.rsplit("/", 1)[-1]
    match = C53_NAME.fullmatch(base)
    if match is None:
        return False, None, None
    try:
        day = date.fromisoformat(match["day"])
    except ValueError:
        return False, None, match["account"]
    return True, day, match["account"]


def unpack_c53(content: bytes) -> tuple[list[C53Member], list[str]]:
    """XML members of a C53 ZIP and the names of skipped members (directories excluded).
    Raises ``ValueError`` with a German message for an unreadable or oversized archive."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ValueError("Der EBICS-Abruf ist keine lesbare ZIP-Datei.") from None
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_MEMBERS:
        raise ValueError("Der EBICS-Abruf enthält zu viele Dateien.")
    members: list[C53Member] = []
    skipped: list[str] = []
    total = 0
    for info in infos:
        if not info.filename.lower().endswith(".xml"):
            skipped.append(info.filename)
            continue
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"Datei {info.filename} im EBICS-Abruf ist zu groß.")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Der EBICS-Abruf ist entpackt zu groß.")
        try:
            with archive.open(info) as handle:
                data = handle.read(MAX_MEMBER_BYTES + 1)  # declared size may be wrong
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
            raise ValueError(f"Datei {info.filename} im EBICS-Abruf ist nicht lesbar.") from None
        if len(data) > MAX_MEMBER_BYTES:
            raise ValueError(f"Datei {info.filename} im EBICS-Abruf ist zu groß.")
        conforms, created_on, account = _member_info(info.filename)
        members.append(
            C53Member(
                name=info.filename,
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                name_conforms=conforms,
                created_on=created_on,
                account_hint=account,
            )
        )
    return members, skipped


def parse_c53(content: bytes) -> tuple[list[tuple[C53Member, ParsedFile]], list[str]]:
    """Every XML member parsed as camt.053 (``mhvp.banking.camt``); a member that is not a
    camt.053 statement raises ``ValueError`` naming the member."""
    members, skipped = unpack_c53(content)
    parsed: list[tuple[C53Member, ParsedFile]] = []
    for member in members:
        try:
            parsed.append((member, camt.parse(member.data)))
        except ValueError as exc:
            raise ValueError(f"{member.name}: {exc}") from None
    return parsed, skipped


class EbicsConnector:
    """`BankConnector` view of one ready EBICS subscriber: only ``fetch_transactions`` (C53)
    reaches the bank. There is no bank search, no web form and no consent to renew (EBICS
    works with the bank contract and the initialised keys), and payments are never submitted
    here (G2, ``mhvp.banking.ebics.EbicsSubmitter``)."""

    def __init__(
        self, subscriber: EbicsSubscriberRef, keys: EbicsClientKeys, transport: EbicsTransport
    ) -> None:
        self.subscriber = subscriber
        self.keys = keys
        self.transport = transport

    def _unsupported(self, what: str) -> None:
        raise ConnectorNotSupportedError(f"{what} ist bei EBICS nicht vorgesehen.")

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

    def download_statements(
        self, since: date | None, until: date | None
    ) -> tuple[bytes, str | None]:
        result = self.transport.download(self.subscriber, self.keys, C53, since, until)
        return result.content, result.transport_ref

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        """Booked transactions of ``account`` (by IBAN) from one C53 download."""
        content, _ = self.download_statements(since, until)
        parsed, _ = parse_c53(content)
        iban = account.iban.replace(" ", "").upper()
        return [
            tx
            for _, file in parsed
            for stmt in file.statements
            if stmt.iban == iban
            for tx in stmt.transactions
            if since <= tx.booking_date <= until
        ]

    def refresh_consent(self, connection_ref: str) -> WebFormHandle:
        self._unsupported("Zustimmungserneuerung")
        raise AssertionError  # pragma: no cover

    def fetch_balance(self, account: BankAccountInfo) -> BalanceInfo:
        """Balances come from the downloaded statement (opening and closing balance, B09)."""
        self._unsupported("Online-Saldenabruf")
        raise AssertionError  # pragma: no cover

    def consent_status(self, connection_ref: str) -> ConsentInfo:
        return ConsentInfo(status="not_required", valid_until=None)

    def submit_payment_batch(self, batch_ref: str) -> str:
        refuse_payment_submission()
        raise AssertionError  # pragma: no cover
