"""Bank specific CSV import (8, M11-02): format detection, encoding/delimiter/date/amount
normalisation and mapping into `RawTransaction`/`RawStatement` (same shape as CAMT/MT940, so
`services.import_file` and its hash based duplicate protection, D05, apply unchanged).

Formats are recognised only from an actually matching header row (rule 0.1.3: no invented
column names as certain). A bank's export can change without notice; every recognised format
below is therefore additionally flagged with a `confidence`:

- "erkannt": the header matches a signature this module was built and tested against.
- "zu_pruefen": the header is a plausible variant of a known export but was not verified
  against a real sample file; the operator should check the preview carefully
  (see `docs/OPEN_QUESTIONS.md`, M11-02-csv-header-verification).

Anything that does not match a known signature falls back to `GENERIC`, which requires an
explicit user column mapping (stored per account, see `BankCsvMapping` in `models.py`); no
column name is ever guessed there.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from mhvp.banking.camt import ParsedFile, RawStatement, RawTransaction

GENERIC = "generic"

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")

_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")

_DELIMITERS = (";", ",", "\t")


class CsvImportError(ValueError):
    """A CSV file could not be read at all (encoding/delimiter/header unreadable)."""


@dataclass(frozen=True)
class ColumnMapping:
    """Maps normalised header names (lower cased, stripped) to `RawTransaction` fields. A
    generic/user mapping is expressed the same way. `amount` XOR (`amount_debit`,
    `amount_credit`) is used, never both."""

    booking_date: str
    amount: str | None = None
    amount_debit: str | None = None
    amount_credit: str | None = None
    value_date: str | None = None
    counterpart_name: str | None = None
    counterpart_iban: str | None = None
    counterpart_bic: str | None = None
    purpose: str | None = None
    purpose_extra: tuple[str, ...] = ()
    end_to_end_id: str | None = None
    mandate_reference: str | None = None
    creditor_id: str | None = None
    own_iban: str | None = None
    bank_reference: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class BankCsvFormat:
    format_id: str
    label: str
    """Header names (normalised) that must all be present for a match."""
    signature: tuple[str, ...]
    mapping: ColumnMapping
    confidence: str  # "erkannt" | "zu_pruefen"
    delimiter: str = ";"


def _norm(name: str) -> str:
    return name.strip().strip('"').lower()


# Reference: the widely used Sparkassen "CAMT-CSV" export column set (also produced,
# unchanged in header, by many Sparkassen online banking front ends). Verified against a
# sample export (M11-02).
_SPARKASSE_CAMT = BankCsvFormat(
    format_id="sparkasse_camt_csv",
    label="Sparkasse (CSV-CAMT-Export)",
    signature=(
        "auftragskonto",
        "buchungstag",
        "valutadatum",
        "buchungstext",
        "verwendungszweck",
        "beguenstigter/zahlungspflichtiger",
        "kontonummer/iban",
        "betrag",
        "waehrung",
    ),
    mapping=ColumnMapping(
        booking_date="buchungstag",
        value_date="valutadatum",
        amount="betrag",
        currency="waehrung",
        counterpart_name="beguenstigter/zahlungspflichtiger",
        counterpart_iban="kontonummer/iban",
        counterpart_bic="bic (swift-code)",
        purpose="verwendungszweck",
        end_to_end_id="kundenreferenz (end-to-end)",
        mandate_reference="mandatsreferenz",
        creditor_id="glaeubiger id",
        own_iban="auftragskonto",
    ),
    confidence="erkannt",
)

# Sparkasse's separate "MT940-CSV" export uses the same column set with a "Sammlerreferenz"
# and "Lastschrift Ursprungsbetrag" column and no explicit currency column; treated as a
# variant of the above, not verified against a live sample -> zu_pruefen.
_SPARKASSE_MT940_CSV = BankCsvFormat(
    format_id="sparkasse_mt940_csv",
    label="Sparkasse (CSV-MT940-Export)",
    signature=(
        "auftragskonto",
        "buchungstag",
        "valutadatum",
        "buchungstext",
        "verwendungszweck",
        "sammlerreferenz",
        "kontonummer/iban",
        "betrag",
    ),
    mapping=ColumnMapping(
        booking_date="buchungstag",
        value_date="valutadatum",
        amount="betrag",
        currency="waehrung",
        counterpart_name="beguenstigter/zahlungspflichtiger",
        counterpart_iban="kontonummer/iban",
        counterpart_bic="bic (swift-code)",
        purpose="verwendungszweck",
        end_to_end_id="kundenreferenz (end-to-end)",
        mandate_reference="mandatsreferenz",
        creditor_id="glaeubiger id",
        own_iban="auftragskonto",
    ),
    confidence="zu_pruefen",
)

# Atruvia (Volksbank/Raiffeisen core banking provider) "Umsatzexport CSV" header, not
# verified against a live sample -> zu_pruefen.
_VOLKSBANK_ATRUVIA = BankCsvFormat(
    format_id="volksbank_atruvia_csv",
    label="Volksbank/Raiffeisen (Atruvia Umsatzexport)",
    signature=(
        "bezeichnung auftragskonto",
        "iban auftragskonto",
        "buchungstag",
        "valutadatum",
        "name zahlungsbeteiligter",
        "iban zahlungsbeteiligter",
        "bic (swift-code) zahlungsbeteiligter",
        "buchungstext",
        "verwendungszweck",
        "betrag",
        "waehrung",
    ),
    mapping=ColumnMapping(
        booking_date="buchungstag",
        value_date="valutadatum",
        amount="betrag",
        currency="waehrung",
        counterpart_name="name zahlungsbeteiligter",
        counterpart_iban="iban zahlungsbeteiligter",
        counterpart_bic="bic (swift-code) zahlungsbeteiligter",
        purpose="verwendungszweck",
        own_iban="iban auftragskonto",
    ),
    confidence="zu_pruefen",
)

# DKB "Kontoumsätze" CSV export (two-line preamble above the header is stripped separately).
_DKB = BankCsvFormat(
    format_id="dkb_csv",
    label="DKB",
    signature=(
        "buchungsdatum",
        "wertstellung",
        "status",
        "zahlungspflichtige*r",
        "zahlungsempfänger*in",
        "verwendungszweck",
        "betrag (€)",
    ),
    mapping=ColumnMapping(
        booking_date="buchungsdatum",
        value_date="wertstellung",
        amount="betrag (€)",
        counterpart_name="zahlungsempfänger*in",
        purpose="verwendungszweck",
    ),
    confidence="zu_pruefen",
)

# ING "Umsatzanzeige" CSV export, header appears after a preamble block (Kontostand, IBAN...).
_ING = BankCsvFormat(
    format_id="ing_csv",
    label="ING",
    signature=(
        "buchung",
        "valuta",
        "auftraggeber/empfänger",
        "buchungstext",
        "verwendungszweck",
        "saldo",
        "betrag",
        "währung",
    ),
    mapping=ColumnMapping(
        booking_date="buchung",
        value_date="valuta",
        amount="betrag",
        currency="währung",
        counterpart_name="auftraggeber/empfänger",
        purpose="verwendungszweck",
    ),
    confidence="zu_pruefen",
)

# N26 CSV export header (English column names, as delivered by the N26 web app).
_N26 = BankCsvFormat(
    format_id="n26_csv",
    label="N26",
    signature=(
        "date",
        "payee",
        "account number",
        "transaction type",
        "payment reference",
        "amount (eur)",
    ),
    delimiter=",",
    mapping=ColumnMapping(
        booking_date="date",
        amount="amount (eur)",
        counterpart_name="payee",
        counterpart_iban="account number",
        purpose="payment reference",
        currency=None,
    ),
    confidence="zu_pruefen",
)

# comdirect "Umsätze" CSV export, header after a preamble ("Umsätze Girokonto...").
_COMDIRECT = BankCsvFormat(
    format_id="comdirect_csv",
    label="comdirect",
    signature=("buchungstag", "wertstellung (valuta)", "vorgang", "buchungstext", "umsatz in eur"),
    mapping=ColumnMapping(
        booking_date="buchungstag",
        value_date="wertstellung (valuta)",
        amount="umsatz in eur",
        purpose="buchungstext",
    ),
    confidence="zu_pruefen",
)

# Deutsche Bank, Commerzbank, Postbank and Hypovereinsbank: these institutes' online banking
# CSV exports are configurable/branch-dependent and no header of theirs has been verified
# against a real sample yet. Rather than guess column names, no signature is registered for
# them (rule 0.1.3); they are picked up by the generic mapping instead, and this gap is
# tracked in `docs/OPEN_QUESTIONS.md` (M11-02-csv-header-verification) so a real export can
# be added once available.

KNOWN_FORMATS: tuple[BankCsvFormat, ...] = (
    _SPARKASSE_CAMT,
    _SPARKASSE_MT940_CSV,
    _VOLKSBANK_ATRUVIA,
    _DKB,
    _ING,
    _N26,
    _COMDIRECT,
)


@dataclass
class RowError:
    line: int
    message: str


@dataclass
class CsvPreview:
    format_id: str
    label: str
    confidence: str
    encoding: str
    delimiter: str
    headers: list[str]
    row_count: int
    sample_rows: list[dict[str, str]]
    errors: list[RowError] = field(default_factory=list)
    parsed: ParsedFile | None = None


def decode(data: bytes) -> tuple[str, str]:
    """Try UTF-8 (with/without BOM) then Windows-1252; raise on genuine garbage."""
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise CsvImportError("Zeichensatz nicht erkannt (weder UTF-8 noch Windows-1252).")


def sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in _DELIMITERS}
        best = max(counts, key=lambda d: counts[d])
        if counts[best] == 0:
            raise CsvImportError("Trennzeichen nicht erkannt.") from None
        return best


def _find_header_row(lines: list[str], delimiter_hint: str | None) -> tuple[int, str]:
    """Some exports (DKB, ING, comdirect) place a preamble of key/value lines before the
    actual header row; the header row is the first line whose normalised cells match a
    registered signature, else the first non-empty line."""
    known_signatures = {frozenset(f.signature) for f in KNOWN_FORMATS}
    first_nonempty = None
    for idx, line in enumerate(lines[:40]):
        if not line.strip():
            continue
        if first_nonempty is None:
            first_nonempty = idx
        delim = delimiter_hint or sniff_delimiter(line)
        cells = {_norm(c) for c in next(csv.reader([line], delimiter=delim))}
        if any(sig <= cells for sig in known_signatures):
            return idx, delim
    if first_nonempty is None:
        raise CsvImportError("Datei enthält keine lesbaren Zeilen.")
    delim = delimiter_hint or sniff_delimiter(lines[first_nonempty])
    return first_nonempty, delim


def parse_amount(raw: str) -> Decimal:
    text = raw.strip().replace(" ", "").replace(" ", "")  # noqa: RUF001
    if not text:
        raise ValueError("Betrag fehlt")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace("EUR", "").replace("€", "")
    if "," in text and "." in text:
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Betrag {raw!r} nicht lesbar") from None
    return -value if negative else value


def parse_date(raw: str) -> date:
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007 (date only, no time)
        except ValueError:
            continue
    raise ValueError(f"Datum {raw!r} nicht lesbar")


def detect_format(data: bytes) -> tuple[BankCsvFormat | None, str, str, list[str], int, str]:
    """Returns (format or None for generic, encoding, delimiter, headers, header_line_index,
    decoded text)."""
    text, encoding = decode(data)
    lines = text.splitlines()
    header_idx, delimiter = _find_header_row(lines, None)
    headers = next(csv.reader([lines[header_idx]], delimiter=delimiter))
    normalised = {_norm(h) for h in headers}
    for fmt in KNOWN_FORMATS:
        if set(fmt.signature) <= normalised:
            return fmt, encoding, delimiter, headers, header_idx, text
    return None, encoding, delimiter, headers, header_idx, text


def _get(row: dict[str, str], mapping_field: str | None) -> str | None:
    if mapping_field is None:
        return None
    value = row.get(mapping_field)
    return value.strip() if value else None


def build_transactions(
    text: str,
    delimiter: str,
    header_idx: int,
    mapping: ColumnMapping,
) -> tuple[list[RawTransaction], list[RowError], str | None]:
    lines = text.splitlines()
    body = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(body), delimiter=delimiter)
    reader.fieldnames = (
        [_norm(h) for h in reader.fieldnames] if reader.fieldnames else reader.fieldnames
    )
    transactions: list[RawTransaction] = []
    errors: list[RowError] = []
    own_iban: str | None = None
    for line_no, row in enumerate(reader, start=header_idx + 2):
        row = {_norm(k): v for k, v in row.items() if k}
        if not any(v and v.strip() for v in row.values()):
            continue
        try:
            booking = parse_date(_get(row, mapping.booking_date) or "")
            value_raw = _get(row, mapping.value_date)
            value_date = parse_date(value_raw) if value_raw else None
            if mapping.amount:
                amount = parse_amount(_get(row, mapping.amount) or "")
            else:
                debit = _get(row, mapping.amount_debit)
                credit = _get(row, mapping.amount_credit)
                amount = parse_amount(credit or "0") - parse_amount(debit or "0")
            purpose_parts = [_get(row, mapping.purpose) or ""]
            purpose_parts += [_get(row, f) or "" for f in mapping.purpose_extra]
            purpose = " ".join(p for p in purpose_parts if p).strip() or None
            currency = (_get(row, mapping.currency) or "EUR").upper()
            iban = _get(row, mapping.own_iban)
            if iban and own_iban is None:
                own_iban = iban.replace(" ", "")
            transactions.append(
                RawTransaction(
                    bank_reference=_get(row, mapping.bank_reference)
                    or _get(row, mapping.end_to_end_id),
                    booking_date=booking,
                    value_date=value_date,
                    amount=amount,
                    currency=currency,
                    counterpart_name=_get(row, mapping.counterpart_name),
                    counterpart_iban=(_get(row, mapping.counterpart_iban) or "").replace(" ", "")
                    or None,
                    counterpart_bic=_get(row, mapping.counterpart_bic),
                    purpose=purpose,
                    end_to_end_id=_get(row, mapping.end_to_end_id),
                    mandate_reference=_get(row, mapping.mandate_reference),
                    creditor_id=_get(row, mapping.creditor_id),
                    transaction_code=None,
                    raw=dict(row),
                )
            )
        except ValueError as exc:
            errors.append(RowError(line=line_no, message=str(exc)))
    return transactions, errors, own_iban


def preview(
    data: bytes,
    *,
    mapping_override: ColumnMapping | None = None,
    own_iban_override: str | None = None,
) -> CsvPreview:
    """Detects the format (or falls back to a supplied `mapping_override` for the generic
    path) and builds a preview, without touching the database. Raises `CsvImportError` when
    the file cannot be read at all, and no known format matched, and no override was given."""
    fmt, encoding, delimiter, headers, header_idx, text = detect_format(data)
    if fmt is None and mapping_override is None:
        return CsvPreview(
            format_id=GENERIC,
            label="Unbekanntes Format (Spaltenzuordnung erforderlich)",
            confidence="zu_pruefen",
            encoding=encoding,
            delimiter=delimiter,
            headers=headers,
            row_count=0,
            sample_rows=[],
        )
    mapping = mapping_override or fmt.mapping  # type: ignore[union-attr]
    format_id = GENERIC if mapping_override else fmt.format_id  # type: ignore[union-attr]
    label = "Generisches Mapping" if mapping_override else fmt.label  # type: ignore[union-attr]
    confidence = "zu_pruefen" if mapping_override else fmt.confidence  # type: ignore[union-attr]
    transactions, errors, own_iban = build_transactions(text, delimiter, header_idx, mapping)
    iban = own_iban_override or own_iban
    statement = RawStatement(
        statement_ref="",
        iban=iban or "",
        currency=transactions[0].currency if transactions else None,
        from_date=min((t.booking_date for t in transactions), default=None),
        to_date=max((t.booking_date for t in transactions), default=None),
        opening_balance=None,
        closing_balance=None,
        closing_date=None,
        transactions=transactions,
    )
    parsed = ParsedFile(version=f"csv:{format_id}", statements=[statement]) if iban else None
    reader_rows = list(
        csv.DictReader(io.StringIO("\n".join(text.splitlines()[header_idx:])), delimiter=delimiter)
    )
    return CsvPreview(
        format_id=format_id,
        label=label,
        confidence=confidence,
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        row_count=len(transactions),
        sample_rows=reader_rows[:5],
        errors=errors,
        parsed=parsed,
    )
