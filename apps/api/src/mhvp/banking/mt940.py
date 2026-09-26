"""MT940 customer statement parser (8.1 FileImportConnector, M11-02).

Only the public SWIFT field structure of MT940 is interpreted: ``:20:`` transaction reference,
``:21:`` related reference, ``:25:`` account, ``:28C:`` statement and sequence number,
``:60F:``/``:60M:`` opening (first or intermediate) balance, ``:61:`` statement line,
``:86:`` information to the account owner, ``:62F:``/``:62M:`` closing (final or intermediate)
balance, ``:64:``/``:65:`` available balances. Several statements in one file (each starting
with ``:20:``, optionally wrapped in SWIFT blocks ``{4:`` ... ``-}``) are all returned.

The content of ``:86:`` is not standardised by SWIFT. It is always kept as raw text
(``raw["info_raw"]``). The subfield layout used by German banks (``GVC?00...?34``: ``?00``
posting text, ``?10`` primanota, ``?20`` to ``?29`` and ``?60`` to ``?63`` purpose, ``?30``
bank code or BIC and ``?31`` account or IBAN of the counterpart, ``?32``/``?33`` name of the
counterpart, ``?34`` text key extension) and the SEPA purpose prefixes (``EREF+``, ``MREF+``,
``CRED+``, ``SVWZ+`` and others) are a known convention, not a SWIFT rule; they are only read
when the text matches that pattern, are marked as ``convention`` in ``raw`` and anything that
does not match stays raw text without guessing. Unsupported structures raise ValueError with a
German message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mhvp.banking.camt import ParsedFile, RawStatement, RawTransaction

VERSION = "mt940"

_TAG = re.compile(r"^:(\d{2}[A-Z]?):", re.MULTILINE)
_BLOCK4 = re.compile(r"\{4:(.*?)-\s*\}", re.DOTALL)
_BALANCE = re.compile(r"^(?P<dc>[DC])(?P<date>\d{6})(?P<ccy>[A-Z]{3})(?P<amount>[\d,]+)$")
_LINE61 = re.compile(
    r"^(?P<value>\d{6})(?P<entry>\d{4})?(?P<dc>R?[DC])(?P<funds>[A-Z])?(?P<amount>\d+,\d*)"
    r"(?P<kind>[NFS][A-Z0-9]{3})(?P<rest>.*)$",
    re.DOTALL,
)
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_BIC = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_SUBFIELD = re.compile(r"\?(\d{2})")
# SEPA purpose prefixes of the German convention; only these are read, everything else is text.
_SEPA_PREFIXES = ("EREF", "KREF", "MREF", "CRED", "DEBT", "COAM", "OAMT", "SVWZ", "ABWA", "ABWE")
_SEPA_SPLIT = re.compile(r"(?=(?:" + "|".join(_SEPA_PREFIXES) + r")\+)")
_PURPOSE_KEYS = tuple(f"{n:02d}" for n in list(range(20, 30)) + list(range(60, 64)))


@dataclass(frozen=True)
class Field:
    tag: str
    value: str


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def looks_like_mt940(data: bytes) -> bool:
    """True when the content starts with ``:20:`` (optionally after SWIFT block headers)."""
    head = _decode(data[:4096]).lstrip("\ufeff \r\n\t")
    if head.startswith(":20:"):
        return True
    return head.startswith("{") and ":20:" in head[:512]


def _amount(text: str, label: str) -> Decimal:
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{label}: Betrag {text!r} nicht lesbar") from None
    if value != value.quantize(Decimal("0.01")):
        raise ValueError(f"{label}: Betrag mit mehr als zwei Nachkommastellen")
    return value.quantize(Decimal("0.01"))


def _yymmdd(text: str, label: str) -> date:
    try:
        return date(2000 + int(text[0:2]), int(text[2:4]), int(text[4:6]))
    except ValueError:
        raise ValueError(f"{label}: Datum {text!r} nicht lesbar") from None


def _entry_date(mmdd: str, value_date: date) -> date:
    """``:61:`` entry date carries no year: take the year of the value date, corrected at the
    turn of the year (entry in December, value in January and vice versa)."""
    month, day = int(mmdd[0:2]), int(mmdd[2:4])
    year = value_date.year
    if month == 12 and value_date.month == 1:
        year -= 1
    elif month == 1 and value_date.month == 12:
        year += 1
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"Buchungstag {mmdd!r} nicht lesbar") from None


def _fields(block: str) -> list[Field]:
    """Split one message into fields; continuation lines belong to the preceding tag."""
    positions = [(m.start(), m.end(), m.group(1)) for m in _TAG.finditer(block)]
    fields = []
    for i, (_start, end, tag) in enumerate(positions):
        stop = positions[i + 1][0] if i + 1 < len(positions) else len(block)
        raw_lines = block[end:stop].replace("\r\n", "\n").strip("\n").split("\n")
        if raw_lines and raw_lines[-1].strip() == "-":  # end of message marker
            raw_lines = raw_lines[:-1]
        fields.append(Field(tag, "\n".join(raw_lines).strip()))
    return fields


def _messages(text: str) -> list[list[Field]]:
    text = text.lstrip("\ufeff")
    blocks = [m.group(1) for m in _BLOCK4.finditer(text)] or [text]
    messages: list[list[Field]] = []
    for block in blocks:
        current: list[Field] = []
        for field in _fields(block):
            if field.tag == "20" and current:
                messages.append(current)
                current = []
            current.append(field)
        if current:
            messages.append(current)
    return messages


def _balance(value: str, label: str) -> tuple[Decimal, date, str]:
    match = _BALANCE.match(value.strip())
    if match is None:
        raise ValueError(f"{label}: Saldo {value!r} nicht lesbar")
    amount = _amount(match["amount"], label)
    return (
        amount if match["dc"] == "C" else -amount,
        _yymmdd(match["date"], label),
        match["ccy"],
    )


def _account(value: str) -> str:
    """``:25:`` is either an IBAN or ``BLZ/Konto``; only an IBAN can be matched to own accounts,
    anything else is returned unchanged and refused later by the account matching."""
    candidate = value.strip().replace(" ", "").upper()
    if "/" in candidate:
        left, right = candidate.split("/", 1)
        if _IBAN.match(right):
            return right
        if _IBAN.match(left):
            return left
    return candidate


def parse_info(text: str) -> dict[str, Any]:
    """Interpret ``:86:`` by the German subfield convention when the text matches it.

    Returns ``{"info_raw": ..., "convention": None}`` for anything else. With a match, the
    result carries ``gvc`` (three digit Geschäftsvorfallcode), ``subfields`` (``?nn`` to text),
    ``purpose`` (``?20`` to ``?29``, ``?60`` to ``?63`` joined), ``counterpart_name``
    (``?32``/``?33``), ``counterpart_account`` (``?31``), ``counterpart_bank`` (``?30``) and
    the SEPA prefixes found in the purpose (``sepa``), all marked ``convention="dk_subfields"``.
    """
    raw = text.replace("\r\n", "\n")
    joined = "".join(line.strip() for line in raw.split("\n"))
    result: dict[str, Any] = {"info_raw": raw, "convention": None}
    if not (len(joined) >= 3 and joined[:3].isdigit() and joined[3:4] == "?"):
        return result
    subfields: dict[str, str] = {}
    parts = _SUBFIELD.split(joined[3:])
    # parts: ["", key, text, key, text, ...]
    for key, value in zip(parts[1::2], parts[2::2], strict=False):
        subfields[key] = subfields.get(key, "") + value
    purpose_parts = [subfields[k] for k in _PURPOSE_KEYS if k in subfields]
    purpose = "".join(purpose_parts)
    sepa: dict[str, str] = {}
    if any(f"{p}+" in purpose for p in _SEPA_PREFIXES):
        for chunk in _SEPA_SPLIT.split(purpose):
            if "+" in chunk and chunk[:4] in _SEPA_PREFIXES:
                sepa[chunk[:4]] = chunk[5:].strip()
    name = "".join(subfields.get(k, "") for k in ("32", "33")).strip() or None
    result.update(
        {
            "convention": "dk_subfields",
            "gvc": joined[:3],
            "subfields": subfields,
            "posting_text": subfields.get("00") or None,
            "purpose": (sepa.get("SVWZ") if sepa.get("SVWZ") else " ".join(purpose_parts).strip())
            or None,
            "counterpart_name": name,
            "counterpart_account": subfields.get("31", "").strip() or None,
            "counterpart_bank": subfields.get("30", "").strip() or None,
            "sepa": sepa,
        }
    )
    return result


def _line(number: int, value: str, info: str | None, statement_ref: str) -> RawTransaction:
    first, _, supplementary = value.partition("\n")
    match = _LINE61.match(first.strip())
    if match is None:
        raise ValueError(f"Umsatz {number}: Zeile :61: {first!r} nicht lesbar")
    value_date = _yymmdd(match["value"], f"Umsatz {number}")
    booking_date = _entry_date(match["entry"], value_date) if match["entry"] else value_date
    amount = _amount(match["amount"], f"Umsatz {number}")
    dc = match["dc"]
    # RC/RD are reversals of a credit/debit: the sign is the opposite of the original entry.
    signed = amount if dc in ("C", "RD") else -amount
    rest = match["rest"].strip()
    customer_ref, _, bank_ref = rest.partition("//")
    customer_ref = customer_ref.strip() or None
    bank_ref = bank_ref.strip().split("\n", 1)[0] or None
    parsed = parse_info(info) if info is not None else {"info_raw": None, "convention": None}
    account = parsed.get("counterpart_account")
    account_clean = account.replace(" ", "").upper() if account else None
    iban = account_clean if account_clean and _IBAN.match(account_clean) else None
    bank = parsed.get("counterpart_bank")
    bic = bank.strip().upper() if bank and _BIC.match(bank.strip().upper()) else None
    sepa = parsed.get("sepa") or {}
    reference = bank_ref or f"{statement_ref}/{number}/{value_date.isoformat()}"
    raw: dict[str, Any] = {
        "format": VERSION,
        "reference_source": "61//bank_reference" if bank_ref else "derived:28C/line/value_date",
        "customer_reference": customer_ref,
        "transaction_type": match["kind"],
        "debit_credit": dc,
        "funds_code": match["funds"],
        "supplementary": supplementary.strip() or None,
        "info": parsed,
    }
    purpose = parsed.get("purpose")
    info_raw = parsed.get("info_raw")
    if purpose is None and isinstance(info_raw, str) and info_raw:
        purpose = " ".join(line.strip() for line in info_raw.split("\n")).strip()
    return RawTransaction(
        bank_reference=reference,
        booking_date=booking_date,
        value_date=value_date,
        amount=signed,
        currency="",  # filled from the balance currency by the statement
        counterpart_name=parsed.get("counterpart_name"),
        counterpart_iban=iban,
        counterpart_bic=bic,
        purpose=purpose or None,
        end_to_end_id=sepa.get("EREF") or None,
        mandate_reference=sepa.get("MREF") or None,
        creditor_id=sepa.get("CRED") or None,
        transaction_code=(parsed.get("gvc") or match["kind"]),
        raw=raw,
    )


def _statement(fields: list[Field]) -> RawStatement:
    by_tag: dict[str, str] = {}
    lines: list[tuple[str, str | None]] = []
    pending: str | None = None
    for field in fields:
        if field.tag == "61":
            if pending is not None:
                lines.append((pending, None))
            pending = field.value
        elif field.tag == "86":
            if pending is not None:
                lines.append((pending, field.value))
                pending = None
            else:
                by_tag["86_statement"] = field.value  # statement level information
        else:
            by_tag[field.tag] = field.value
    if pending is not None:
        lines.append((pending, None))
    if "25" not in by_tag:
        raise ValueError("Kontoauszug ohne Kontoangabe (:25:)")
    opening_tag = "60F" if "60F" in by_tag else "60M" if "60M" in by_tag else None
    closing_tag = "62F" if "62F" in by_tag else "62M" if "62M" in by_tag else None
    if opening_tag is None or closing_tag is None:
        raise ValueError("Kontoauszug ohne Anfangs- oder Schlusssaldo (:60F:/:60M:, :62F:/:62M:)")
    opening, opening_date, currency = _balance(by_tag[opening_tag], "Anfangssaldo")
    closing, closing_date, closing_ccy = _balance(by_tag[closing_tag], "Schlusssaldo")
    if closing_ccy != currency:
        raise ValueError("Anfangs- und Schlusssaldo in verschiedenen Währungen")
    statement_ref = by_tag.get("28C", "").strip() or by_tag.get("20", "").strip()
    transactions = []
    for number, (value, info) in enumerate(lines, start=1):
        tx = _line(number, value, info, statement_ref)
        tx.currency = currency
        transactions.append(tx)
    return RawStatement(
        statement_ref=statement_ref,
        iban=_account(by_tag["25"]),
        currency=currency,
        from_date=opening_date,
        to_date=closing_date,
        opening_balance=opening,
        closing_balance=closing,
        closing_date=closing_date,
        transactions=transactions,
    )


def parse(data: bytes) -> ParsedFile:
    text = _decode(data)
    if not looks_like_mt940(data):
        raise ValueError("Die Datei ist kein MT940-Kontoauszug (kein :20: am Anfang).")
    statements = []
    for number, fields in enumerate(_messages(text), start=1):
        try:
            statements.append(_statement(fields))
        except ValueError as exc:
            raise ValueError(f"Auszug {number}: {exc}") from None
    if not statements:
        raise ValueError("Kein Kontoauszug in der Datei.")
    return ParsedFile(version=VERSION, statements=statements)
