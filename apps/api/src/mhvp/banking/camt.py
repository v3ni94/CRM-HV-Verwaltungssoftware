"""CAMT.053 bank-to-customer statement parser (8.1 FileImportConnector).

Namespace agnostic (element local names), parsed with defusedxml against XML attacks. Only the
fields named in 6.4/6.9.7 are read; the version in use is recorded (6.9.14, P05). Unsupported
structures raise ValueError with a German message; nothing is guessed.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml import ElementTree  # type: ignore[import-untyped]


@dataclass
class RawTransaction:
    bank_reference: str | None
    booking_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    counterpart_name: str | None
    counterpart_iban: str | None
    counterpart_bic: str | None
    purpose: str | None
    end_to_end_id: str | None
    mandate_reference: str | None
    creditor_id: str | None
    transaction_code: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawStatement:
    statement_ref: str
    iban: str
    currency: str | None
    from_date: date | None
    to_date: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    closing_date: date | None
    transactions: list[RawTransaction]


@dataclass
class ParsedFile:
    version: str
    statements: list[RawStatement]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: Element | None, *path: str) -> Element | None:
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == name), None)
    return el


def _children(el: Element | None, name: str) -> list[Element]:
    return [c for c in el if _local(c.tag) == name] if el is not None else []


def _text(el: Element | None, *path: str) -> str | None:
    node = _child(el, *path)
    value = node.text.strip() if node is not None and node.text else None
    return value or None


def _date(el: Element | None) -> date | None:
    if el is None:
        return None
    own = el.text.strip() if el.text and el.text.strip() else ""
    value = _text(el, "Dt") or (_text(el, "DtTm") or own)[:10]
    return date.fromisoformat(value) if value else None


def _amount(el: Element | None) -> tuple[Decimal, str]:
    node = _child(el, "Amt")
    if node is None or not node.text:
        raise ValueError("Betrag fehlt")
    try:
        value = Decimal(node.text.strip())
    except InvalidOperation:
        raise ValueError(f"Betrag {node.text!r} nicht lesbar") from None
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("Betrag mit mehr als zwei Nachkommastellen")
    return value, node.get("Ccy", "EUR")


def _signed(el: Element, value: Decimal) -> Decimal:
    indicator = _text(el, "CdtDbtInd")
    if indicator not in {"CRDT", "DBIT"}:
        raise ValueError("Soll/Haben-Kennzeichen fehlt")
    return value if indicator == "CRDT" else -value


def _balance(stmt: Element, code: str) -> tuple[Decimal | None, date | None]:
    for bal in _children(stmt, "Bal"):
        if _text(bal, "Tp", "CdOrPrtry", "Cd") == code:
            value, _ = _amount(bal)
            return _signed(bal, value), _date(_child(bal, "Dt"))
    return None, None


def _entry(ntry: Element) -> RawTransaction:
    value, currency = _amount(ntry)
    amount = _signed(ntry, value)
    tx = _child(ntry, "NtryDtls", "TxDtls")
    credit = amount > 0
    party = "Dbtr" if credit else "Cdtr"
    agent = "DbtrAgt" if credit else "CdtrAgt"
    name = _text(tx, "RltdPties", party, "Nm") or _text(tx, "RltdPties", party, "Pty", "Nm")
    iban = _text(tx, "RltdPties", f"{party}Acct", "Id", "IBAN")
    ustrd = [c.text.strip() for c in _children(_child(tx, "RmtInf"), "Ustrd") if c.text]
    reference = (
        _text(ntry, "AcctSvcrRef")
        or _text(tx, "Refs", "AcctSvcrRef")
        or _text(ntry, "NtryRef")
        or _text(tx, "Refs", "TxId")
    )
    return RawTransaction(
        bank_reference=reference,
        booking_date=_date(_child(ntry, "BookgDt")) or _required_date(),
        value_date=_date(_child(ntry, "ValDt")),
        amount=amount,
        currency=currency,
        counterpart_name=name,
        counterpart_iban=iban.replace(" ", "").upper() if iban else None,
        counterpart_bic=_text(tx, "RltdAgts", agent, "FinInstnId", "BICFI")
        or _text(tx, "RltdAgts", agent, "FinInstnId", "BIC"),
        purpose=" ".join(ustrd) or None,
        end_to_end_id=_text(tx, "Refs", "EndToEndId"),
        mandate_reference=_text(tx, "Refs", "MndtId"),
        creditor_id=_text(tx, "RltdPties", "Cdtr", "Id", "PrvtId", "Othr", "Id"),
        transaction_code=_text(ntry, "BkTxCd", "Domn", "Cd")
        or _text(ntry, "BkTxCd", "Prtry", "Cd"),
        raw={"reference_source": "AcctSvcrRef/NtryRef/TxId"},
    )


def _required_date() -> date:
    raise ValueError("Buchungstag fehlt")


def parse(data: bytes) -> ParsedFile:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        raise ValueError("Die Datei ist kein lesbares XML.") from None
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if "camt.053" not in namespace:
        raise ValueError("Nur CAMT.053 Kontoauszüge werden unterstützt.")
    body = _child(root, "BkToCstmrStmt")
    statements = []
    for stmt in _children(body, "Stmt"):
        iban = _text(stmt, "Acct", "Id", "IBAN")
        if not iban:
            raise ValueError("Kontoauszug ohne IBAN")
        opening, _ = _balance(stmt, "OPBD")
        if opening is None:
            opening, _ = _balance(stmt, "PRCD")
        closing, closing_date = _balance(stmt, "CLBD")
        period = _child(stmt, "FrToDt")
        entries = []
        for number, ntry in enumerate(_children(stmt, "Ntry"), start=1):
            if _text(ntry, "Sts") not in (None, "BOOK") and _text(ntry, "Sts", "Cd") not in (
                None,
                "BOOK",
            ):
                continue  # pending entries are not booked transactions
            try:
                entries.append(_entry(ntry))
            except ValueError as exc:
                raise ValueError(f"Umsatz {number}: {exc}") from None
        statements.append(
            RawStatement(
                statement_ref=_text(stmt, "Id") or _text(stmt, "ElctrncSeqNb") or "",
                iban=iban.replace(" ", "").upper(),
                currency=_text(stmt, "Acct", "Ccy"),
                from_date=_date(_child(period, "FrDtTm")) if period is not None else None,
                to_date=_date(_child(period, "ToDtTm")) if period is not None else None,
                opening_balance=opening,
                closing_balance=closing,
                closing_date=closing_date,
                transactions=entries,
            )
        )
    if not statements:
        raise ValueError("Kein Kontoauszug in der Datei.")
    return ParsedFile(version=namespace.rsplit(":", 1)[-1], statements=statements)
