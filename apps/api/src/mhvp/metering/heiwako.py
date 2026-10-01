"""Parser for the bved / ARGE HeiWaKo file based "Standard-Datenaustausch" version 3.10
(fixed width records, ISO 8859-15, CR LF).

Source (Q14, downloaded and evaluated 27.09.2026): bved, "Standard-Datenaustausch zwischen
Software der Wohnungswirtschaft und Abrechnungsunternehmen für Heiz-, Warm- und
Kaltwasserkosten", Version 3.10 dritte Erweiterung (September 2025),
``2025-09-10_bved_datenaustausch_310_dritte-Erweiterung.pdf`` on https://bved.info/
datenaustauschneu/spezifikationen/. Field positions below are the "von - bis" columns of that
document (1 based, inclusive); nothing here is taken from a provider's own material.

Implemented record types (pages 6, 7, 14 to 19, 24, 25 and 27 of the PDF):

* ``A`` (128 bytes, file ``DTA310_*.DAT``): exchange of order references.
* ``L`` and ``M`` (2048 bytes, file ``DTM310_*.DAT``): property and user (Nutzer) data.
* ``D`` (1024 bytes, file ``DTD310_*.DAT``): billing results, several lines per user (one per
  cost type, table K).
* ``E898`` (120 bytes, file ``DTE898_*.DAT``): index to the image (PDF) of a user's billing.

``B``/``K`` (fuels and costs), ``E835`` (tax relevant service shares) and ``P`` (price brake) are
not parsed: they are not needed for the import of billing results and user data (M40-02).

Rules of the standard applied here: empty fields are blank regardless of their type and are
returned as ``None`` (never zero); numeric fields are right aligned with leading zeros and a
minus sign in the first position; amounts "8,2 Stellen" carry two implied decimals, shares
"6,3 Stellen" three, the area "5,2" two, the percentage "1,2" two; dates are ``TTMMJJ``. The
two digit year has no pivot in the standard; this module reads ``00`` to ``69`` as 2000 to 2069
and ``70`` to ``99`` as 1970 to 1999 (documented assumption, docs/ASSUMPTIONS.md M40-02).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.metering.adapters import BillingResultRecord

__all__ = [
    "ARecord",
    "DRecord",
    "E898Record",
    "HeiwakoFile",
    "HeiwakoParseError",
    "LRecord",
    "MRecord",
    "ParsedLine",
    "billing_results_from_d",
    "detect_file_kind",
    "parse_file",
    "write_a_records",
    "write_l_records",
    "write_m_records",
]

ENCODING = "iso-8859-15"
VERSION_RANGE = ("03.00", "99.99")

# Record lengths without CR LF (PDF page 6, "Satzlänge").
RECORD_LENGTHS: dict[str, int] = {"A": 128, "L": 2048, "M": 2048, "D": 1024, "E898": 120}

# File name prefixes (PDF page 6, "Standard-Dateiname") to the record types they carry.
FILE_KINDS: dict[str, tuple[str, ...]] = {
    "DTA310": ("A",),
    "DTM310": ("L", "M"),
    "DTD310": ("D",),
    "DTE898": ("E898",),
}

MAX_LINES = 200_000


class HeiwakoParseError(ValueError):
    """A line that does not follow the standard; carries the 1 based line number."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"Zeile {line}: {message}")
        self.line = line
        self.detail = message


# Field access ----------------------------------------------------------------------------


def _slice(line: str, start: int, end: int) -> str:
    """Characters ``start`` to ``end`` of the record (1 based, inclusive, as in the PDF)."""
    return line[start - 1 : end]


def _text(line: str, start: int, end: int) -> str | None:
    value = _slice(line, start, end).strip()
    return value or None


def _number(line: str, start: int, end: int, *, decimals: int = 0) -> Decimal | None:
    raw = _slice(line, start, end)
    if not raw.strip():
        return None  # not filled: blank, never zero (PDF page 7)
    text = raw.strip()
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    if not digits.isdigit():
        raise ValueError(f"numerisches Feld {start}-{end} enthält '{raw}'")
    value = Decimal(digits).scaleb(-decimals) if decimals else Decimal(digits)
    return -value if negative else value


def _int(line: str, start: int, end: int) -> int | None:
    value = _number(line, start, end)
    return int(value) if value is not None else None


def _date6(line: str, start: int) -> date | None:
    raw = _slice(line, start, start + 5)
    if not raw.strip():
        return None
    if not raw.isdigit():
        raise ValueError(f"Datum {start}-{start + 5} enthält '{raw}'")
    day, month, year2 = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    year = 2000 + year2 if year2 <= 69 else 1900 + year2
    return date(year, month, day)


def _split_ref(value: str | None) -> tuple[str | None, str | None]:
    """Ordnungsbegriff des Abrechnungsunternehmens: 9 digits property, 4 digits unit."""
    if value is None or len(value) < 13:
        return value, None
    unit = value[9:13]
    return value[0:9], (None if unit in {"0000", "    "} else unit)


# Records ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Header:
    record_type: str
    version: str
    customer_number: str | None
    provider_key: str | None
    provider_ref: str | None
    provider_property_number: str | None
    provider_unit_number: str | None


def _header(line: str, record_type: str) -> _Header:
    version = _slice(line, 2, 6)
    if not (VERSION_RANGE[0] <= version <= VERSION_RANGE[1]):
        raise ValueError(f"Version '{version}' außerhalb 03.00 bis 99.99")
    ref = _text(line, 19, 31)
    prop, unit = _split_ref(ref)
    return _Header(
        record_type=record_type,
        version=version,
        customer_number=_text(line, 7, 16),
        provider_key=_text(line, 17, 18),
        provider_ref=ref,
        provider_property_number=prop,
        provider_unit_number=unit,
    )


@dataclass(frozen=True)
class ARecord:
    """Satzart A (PDF page 14)."""

    header: _Header
    client_ref: str | None  # field 6, Ordnungsbegriff des Auftraggebers


@dataclass(frozen=True)
class LRecord:
    """Satzart L (PDF pages 15 and 16), fields 1 to 18; the CO2 flags 19 to 23 stay in
    ``extra`` as text."""

    header: _Header
    vat_flag: int | None  # field 6: 3 gross only, 4 net only, 5 per M record field 25
    street: str | None
    country: str | None
    postal_code: str | None
    city: str | None
    period_from: date | None  # field 11, Abrechnungszeitraum
    period_to: date | None
    object_number: str | None  # field 12, Ordnungsbegriff des Kunden
    risk_allocation_flag: int | None  # field 13, Umlageausfallwagnis
    risk_allocation_percent: Decimal | None  # field 14, 1,2
    wage_share_flag: int | None  # field 15
    currency: str | None  # field 16
    weg_flag: int | None  # field 17
    total_area: Decimal | None  # field 18, 5,2
    extra: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class MRecord:
    """Satzart M (PDF pages 17 to 19): user, owner, occupancy period, budget payments,
    shares. Service provider / recipient blocks (fields 42 to 66) are kept as text in
    ``extra`` and never used for postings (they carry account data of the provider)."""

    header: _Header
    client_ref: str | None  # field 6
    address_flag: int | None  # field 7
    user_names: tuple[str | None, str | None, str | None, str | None]  # fields 8 to 11
    user_street: str | None
    user_country: str | None
    user_postal_code: str | None
    user_city: str | None
    owner_names: tuple[str | None, str | None, str | None, str | None]  # fields 16 to 19
    owner_street: str | None
    owner_country: str | None
    owner_postal_code: str | None
    owner_city: str | None
    occupancy_from: date | None  # field 24
    occupancy_to: date | None
    vat_flag: int | None  # field 25
    risk_allocation_flag: int | None  # field 26
    heating_shares: Decimal | None  # field 27, 8,2 (key in field 69)
    heating_prepayment_gross: Decimal | None  # field 28
    heating_prepayment_net: Decimal | None  # field 29
    hot_water_shares: Decimal | None  # field 30 (key in field 70)
    hot_water_prepayment_gross: Decimal | None  # field 31
    hot_water_prepayment_net: Decimal | None  # field 32
    cold_water_shares: Decimal | None  # field 33
    cold_water_prepayment_gross: Decimal | None  # field 34
    cold_water_prepayment_net: Decimal | None  # field 35
    allocations: tuple[tuple[int | None, Decimal | None], ...]  # fields 36 to 41 (key, share)
    vacancy_flag: int | None  # field 67
    change_fee_flag: int | None  # field 68
    heating_shares_key: int | None  # field 69, table E
    hot_water_shares_key: int | None  # field 70, table E
    extra: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class DRecord:
    """Satzart D (PDF pages 24 and 25): one line per user and cost type (field 17, table K).
    Balance positive = Nachzahlung des Nutzers, negative = Guthaben (field 15)."""

    header: _Header
    client_ref: str | None  # field 6
    usage_period_end: date | None  # field 7, letzter Tag des Nutzungszeitraumes
    total_gross: Decimal | None  # field 8
    total_net: Decimal | None  # field 9
    prepayment_gross: Decimal | None  # field 10
    prepayment_net: Decimal | None  # field 11
    new_monthly_prepayment_gross: Decimal | None  # field 12
    new_monthly_prepayment_net: Decimal | None  # field 13
    risk_allocation_gross: Decimal | None  # field 14 (contained in total gross)
    balance_gross: Decimal | None  # field 15
    balance_net: Decimal | None  # field 16
    cost_type_key: str | None  # field 17, table K (3 digits, kept as text)
    consumption_shares: Decimal | None  # field 18, 6,3
    consumption_unit_key: str | None  # field 19, table E
    reading_flag: str | None  # field 20, table S
    name: str | None  # field 21, information only
    currency: str | None  # field 22
    co2_allocated_gross: Decimal | None  # field 23
    co2_allocated_net: Decimal | None  # field 24
    co2_not_allocated_gross: Decimal | None  # field 25
    co2_not_allocated_net: Decimal | None  # field 26
    co2_tenant_share_gross: Decimal | None  # field 27
    co2_tenant_share_net: Decimal | None  # field 28


@dataclass(frozen=True)
class E898Record:
    """Satzart E898 (PDF page 27): index of a billing image file per user."""

    sequence: int | None  # field 2
    provider_key: str | None  # field 3
    provider_ref: str | None  # field 4 (18 characters: property, user group, user, sequence)
    client_ref: str | None  # field 5
    billing_sequence: str | None  # field 6
    image_path: str | None  # field 7
    page: int | None  # field 8
    usage_period_end: date | None  # field 9
    document_kind: str | None  # field 10: HKA, BKA, VDA


Record = ARecord | LRecord | MRecord | DRecord | E898Record


@dataclass(frozen=True)
class ParsedLine:
    line: int
    record_type: str
    record: Record


@dataclass
class HeiwakoFile:
    kind: str | None  # file name prefix (DTA310, DTM310, DTD310, DTE898) or None
    records: list[ParsedLine] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def of_type(self, record_type: str) -> list[Any]:
        return [p.record for p in self.records if p.record_type == record_type]


# Line parsers ----------------------------------------------------------------------------


def _parse_a(line: str) -> ARecord:
    return ARecord(header=_header(line, "A"), client_ref=_text(line, 32, 51))


def _parse_l(line: str) -> LRecord:
    return LRecord(
        header=_header(line, "L"),
        vat_flag=_int(line, 32, 32),
        street=_text(line, 33, 67),
        country=_text(line, 68, 70),
        postal_code=_text(line, 71, 80),
        city=_text(line, 81, 115),
        period_from=_date6(line, 116),
        period_to=_date6(line, 122),
        object_number=_text(line, 128, 142),
        risk_allocation_flag=_int(line, 143, 143),
        risk_allocation_percent=_number(line, 144, 146, decimals=2),
        wage_share_flag=_int(line, 147, 147),
        currency=_text(line, 148, 150),
        weg_flag=_int(line, 151, 151),
        total_area=_number(line, 152, 158, decimals=2),
        extra={
            "non_residential_flag": _text(line, 159, 159),
            "section9_flag_1": _text(line, 160, 160),
            "section9_flag_2": _text(line, 161, 161),
            "co2_landlord_percent": _text(line, 162, 164),
            "heat_connection_after_2023_flag": _text(line, 165, 165),
        },
    )


def _names(line: str, start: int) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        _text(line, start, start + 34),
        _text(line, start + 35, start + 69),
        _text(line, start + 70, start + 104),
        _text(line, start + 105, start + 139),
    )


def _parse_m(line: str) -> MRecord:
    return MRecord(
        header=_header(line, "M"),
        client_ref=_text(line, 32, 51),
        address_flag=_int(line, 52, 52),
        user_names=_names(line, 53),
        user_street=_text(line, 193, 227),
        user_country=_text(line, 228, 230),
        user_postal_code=_text(line, 231, 240),
        user_city=_text(line, 241, 275),
        owner_names=_names(line, 276),
        owner_street=_text(line, 416, 450),
        owner_country=_text(line, 451, 453),
        owner_postal_code=_text(line, 454, 463),
        owner_city=_text(line, 464, 498),
        occupancy_from=_date6(line, 499),
        occupancy_to=_date6(line, 505),
        vat_flag=_int(line, 511, 511),
        risk_allocation_flag=_int(line, 512, 512),
        heating_shares=_number(line, 513, 522, decimals=2),
        heating_prepayment_gross=_number(line, 523, 532, decimals=2),
        heating_prepayment_net=_number(line, 533, 542, decimals=2),
        hot_water_shares=_number(line, 543, 552, decimals=2),
        hot_water_prepayment_gross=_number(line, 553, 562, decimals=2),
        hot_water_prepayment_net=_number(line, 563, 572, decimals=2),
        cold_water_shares=_number(line, 573, 582, decimals=2),
        cold_water_prepayment_gross=_number(line, 583, 592, decimals=2),
        cold_water_prepayment_net=_number(line, 593, 602, decimals=2),
        allocations=(
            (_int(line, 603, 605), _number(line, 606, 615, decimals=2)),
            (_int(line, 616, 618), _number(line, 619, 628, decimals=2)),
            (_int(line, 629, 631), _number(line, 632, 641, decimals=2)),
        ),
        vacancy_flag=_int(line, 1167, 1167),
        change_fee_flag=_int(line, 1168, 1168),
        heating_shares_key=_int(line, 1169, 1171),
        hot_water_shares_key=_int(line, 1172, 1174),
        extra={
            "service_provider_name_1": _text(line, 642, 676),
            "service_provider_tax_flag": _text(line, 865, 865),
            "tax_rate_flag": _text(line, 882, 882),
            "invoice_number_flag": _text(line, 883, 883),
            "invoice_number": _text(line, 884, 908),
            "payment_kind_flag": _text(line, 943, 943),
            "service_recipient_name_1": _text(line, 944, 978),
        },
    )


def _parse_d(line: str) -> DRecord:
    return DRecord(
        header=_header(line, "D"),
        client_ref=_text(line, 32, 51),
        usage_period_end=_date6(line, 52),
        total_gross=_number(line, 58, 67, decimals=2),
        total_net=_number(line, 68, 77, decimals=2),
        prepayment_gross=_number(line, 78, 87, decimals=2),
        prepayment_net=_number(line, 88, 97, decimals=2),
        new_monthly_prepayment_gross=_number(line, 98, 107, decimals=2),
        new_monthly_prepayment_net=_number(line, 108, 117, decimals=2),
        risk_allocation_gross=_number(line, 118, 127, decimals=2),
        balance_gross=_number(line, 128, 137, decimals=2),
        balance_net=_number(line, 138, 147, decimals=2),
        cost_type_key=_text(line, 148, 150),
        consumption_shares=_number(line, 151, 159, decimals=3),
        consumption_unit_key=_text(line, 160, 162),
        reading_flag=_text(line, 163, 165),
        name=_text(line, 166, 200),
        currency=_text(line, 201, 203),
        co2_allocated_gross=_number(line, 204, 213, decimals=2),
        co2_allocated_net=_number(line, 214, 223, decimals=2),
        co2_not_allocated_gross=_number(line, 224, 233, decimals=2),
        co2_not_allocated_net=_number(line, 234, 243, decimals=2),
        co2_tenant_share_gross=_number(line, 244, 253, decimals=2),
        co2_tenant_share_net=_number(line, 254, 263, decimals=2),
    )


def _parse_e898(line: str) -> E898Record:
    return E898Record(
        sequence=_int(line, 5, 11),
        provider_key=_text(line, 12, 13),
        provider_ref=_text(line, 14, 31),
        client_ref=_text(line, 32, 51),
        billing_sequence=_text(line, 52, 52),
        image_path=_text(line, 53, 108),
        page=_int(line, 109, 111),
        usage_period_end=_date6(line, 112),
        document_kind=_text(line, 118, 120),
    )


def _record_type(line: str) -> str:
    if line.startswith("E898"):
        return "E898"
    return line[:1]


def _check_frame(line: str, record_type: str, expected_end: str | None) -> None:
    length = RECORD_LENGTHS[record_type]
    if len(line) != length:
        raise ValueError(f"Satzart {record_type} erwartet {length} Zeichen, gefunden {len(line)}")
    if expected_end is not None and line[-1] != expected_end:
        raise ValueError(f"Satzende '{expected_end}' fehlt an Position {length}")


# File parsing ----------------------------------------------------------------------------


def detect_file_kind(filename: str | None) -> str | None:
    """File name prefix per the standard (``DTD310_JJJJMMTThhmmssSSS.DAT``), else ``None``."""
    if not filename:
        return None
    upper = filename.rsplit("/", 1)[-1].upper()
    for prefix in FILE_KINDS:
        if upper.startswith(prefix):
            return prefix
    return None


def _lines(raw: bytes) -> Iterator[str]:
    text = raw.decode(ENCODING)
    for line in text.split("\r\n"):
        yield line.rstrip("\n")


def parse_file(raw: bytes, *, filename: str | None = None) -> HeiwakoFile:
    """Parse one exchange file. Faulty lines are reported in ``errors`` with their line number
    and skipped; the good lines are returned. The file name only checks the record types
    against the announced content, it never selects the parser (the record type is the first
    character of every line)."""
    kind = detect_file_kind(filename)
    allowed = FILE_KINDS.get(kind) if kind else None
    result = HeiwakoFile(kind=kind)
    parsers: dict[str, Callable[[str], Record]] = {
        "A": _parse_a,
        "L": _parse_l,
        "M": _parse_m,
        "D": _parse_d,
        "E898": _parse_e898,
    }
    ends = {"A": "A", "L": "L", "M": "M", "D": "D", "E898": None}
    for number, line in enumerate(_lines(raw), start=1):
        if number > MAX_LINES:
            result.errors.append(f"Zeile {number}: Datei überschreitet {MAX_LINES} Zeilen.")
            break
        if not line.strip():
            continue  # trailing empty line after the last CR LF
        record_type = _record_type(line)
        parser = parsers.get(record_type)
        if parser is None:
            result.errors.append(
                f"Zeile {number}: Satzart '{record_type}' wird nicht verarbeitet "
                "(nur A, L, M, D, E898)."
            )
            continue
        if allowed is not None and record_type not in allowed:
            result.errors.append(
                f"Zeile {number}: Satzart '{record_type}' passt nicht zum Dateinamen {kind}."
            )
            continue
        try:
            _check_frame(line, record_type, ends[record_type])
            record: Record = parser(line)
        except ValueError as exc:
            result.errors.append(f"Zeile {number}: {exc}")
            continue
        result.records.append(ParsedLine(number, record_type, record))
    return result


# Mapping to billing results --------------------------------------------------------------


def billing_results_from_d(
    d_records: Sequence[DRecord],
    *,
    periods: Mapping[str, tuple[date, date]] | None = None,
    period_from: date | None = None,
    default_currency: str = "EUR",
) -> tuple[list[BillingResultRecord], list[str]]:
    """One ``BillingResultRecord`` per D line (user and cost type). The D record carries only
    the last day of the usage period (field 7); the billing period start comes from the L
    record of the same property (``periods`` keyed by the 9 digit property number, from a
    DTM310 file) or from an explicit ``period_from``. Lines without a determinable start are
    reported, never guessed. The amount is the gross total of the cost type (field 8, as the
    bved billing result uses ``totalcosts``); balance and prepayments stay in the payload."""
    results: list[BillingResultRecord] = []
    problems: list[str] = []
    for index, rec in enumerate(d_records, start=1):
        prop = rec.header.provider_property_number
        if prop is None or rec.usage_period_end is None:
            problems.append(f"D-Satz {index}: Ordnungsbegriff oder Nutzungsende fehlt.")
            continue
        start: date | None = period_from
        end = rec.usage_period_end
        if periods and prop in periods:
            start, l_end = periods[prop]
            end = rec.usage_period_end if rec.usage_period_end <= l_end else l_end
        if start is None:
            problems.append(
                f"D-Satz {index} ({prop}): Beginn des Abrechnungszeitraums nicht bestimmbar "
                "(kein L-Satz und kein Zeitraum angegeben)."
            )
            continue
        if rec.total_gross is None:
            problems.append(f"D-Satz {index} ({prop}): Gesamtkosten (Brutto) nicht belegt.")
            continue
        unit = rec.header.provider_unit_number
        cost = rec.cost_type_key or "-"
        results.append(
            BillingResultRecord(
                external_billing_unit=prop,
                external_unit_number=unit,
                period_from=start,
                period_to=end,
                amount=rec.total_gross,
                currency=rec.currency or default_currency,
                external_document_ref=(
                    f"D/{prop}/{rec.usage_period_end.isoformat()}/{unit or '-'}/{cost}"
                ),
                payload={
                    "record_type": "D",
                    "version": rec.header.version,
                    "provider_key": rec.header.provider_key,
                    "customer_number": rec.header.customer_number,
                    "client_ref": rec.client_ref,
                    "cost_type_key": rec.cost_type_key,
                    "usage_period_end": rec.usage_period_end.isoformat(),
                    "total_gross": _str(rec.total_gross),
                    "total_net": _str(rec.total_net),
                    "prepayment_gross": _str(rec.prepayment_gross),
                    "prepayment_net": _str(rec.prepayment_net),
                    "balance_gross": _str(rec.balance_gross),
                    "balance_net": _str(rec.balance_net),
                    "new_monthly_prepayment_gross": _str(rec.new_monthly_prepayment_gross),
                    "new_monthly_prepayment_net": _str(rec.new_monthly_prepayment_net),
                    "risk_allocation_gross": _str(rec.risk_allocation_gross),
                    "consumption_shares": _str(rec.consumption_shares),
                    "consumption_unit_key": rec.consumption_unit_key,
                    "reading_flag": rec.reading_flag,
                    "co2_allocated_gross": _str(rec.co2_allocated_gross),
                    "co2_not_allocated_gross": _str(rec.co2_not_allocated_gross),
                    "co2_tenant_share_gross": _str(rec.co2_tenant_share_gross),
                    "name": rec.name,
                },
            )
        )
    return results, problems


def _str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


# Writer for the order reference record A (GA09-01) -----------------------------------------


def _put_field(
    buf: list[str], start: int, end: int, value: str | None, *, numeric: bool = False
) -> None:
    width = end - start + 1
    text = value or ""
    if len(text) > width:
        raise ValueError(f"Wert '{text}' passt nicht in Feld {start}-{end}")
    buf[start - 1 : end] = list(text.rjust(width, "0") if numeric and text else text.ljust(width))


def write_a_records(
    records: Sequence[ARecord], *, version: str = "03.10", encoding: str = ENCODING
) -> bytes:
    """Serialise ``A`` records (PDF page 14, 128 bytes, last byte ``A``, CR LF) for the file
    ``DTA310_*.DAT``. Only fields documented in this module are written: version (2 to 6),
    customer number (7 to 16, zero padded), provider key (17 to 18), provider reference
    (19 to 31: 9 digit property plus 4 digit unit) and the client reference (32 to 51). All
    other positions stay blank. Whether a provider expects this master data export is open
    (docs/OPEN_QUESTIONS.md AA16-01); the writer is not wired into any transmission."""
    lines: list[str] = []
    for record in records:
        buf = [" "] * RECORD_LENGTHS["A"]

        header = record.header
        _put_field(buf, 1, 1, "A")
        _put_field(buf, 2, 6, version)
        _put_field(buf, 7, 16, header.customer_number, numeric=True)
        _put_field(buf, 17, 18, header.provider_key)
        if header.provider_property_number is not None:
            unit = header.provider_unit_number or "0000"
            _put_field(
                buf, 19, 31, header.provider_property_number.rjust(9, "0") + unit.rjust(4, "0")
            )
        _put_field(buf, 32, 51, record.client_ref)
        buf[-1] = "A"
        lines.append("".join(buf))
    return "".join(f"{line}\r\n" for line in lines).encode(encoding)


# Writers for the property record L and the user record M (GA09-01) -------------------------


def _put_num(
    buf: list[str], start: int, end: int, value: Decimal | int | None, *, decimals: int = 0
) -> None:
    """Right aligned, zero filled, minus sign first; ``None`` stays blank (never zero)."""
    if value is None:
        return
    width = end - start + 1
    scaled = int((Decimal(value) * (Decimal(10) ** decimals)).to_integral_exact())
    digits = str(abs(scaled))
    text = "-" + digits.rjust(width - 1, "0") if scaled < 0 else digits.rjust(width, "0")
    if len(text) > width:
        raise ValueError(f"Wert {value} passt nicht in Feld {start}-{end}")
    buf[start - 1 : end] = list(text)


def _put_date(buf: list[str], start: int, value: date | None) -> None:
    if value is None:
        return
    if not 1970 <= value.year <= 2069:
        raise ValueError(f"Jahr {value.year} ist mit zweistelligem Jahr nicht darstellbar")
    buf[start - 1 : start + 5] = list(value.strftime("%d%m%y"))


def _put_names(buf: list[str], start: int, names: Sequence[str | None]) -> None:
    for offset, name in zip((0, 35, 70, 105), names, strict=False):
        _put_field(buf, start + offset, start + offset + 34, name)


def _put_header(buf: list[str], header: _Header, record_type: str, version: str) -> None:
    _put_field(buf, 1, 1, record_type)
    _put_field(buf, 2, 6, version)
    _put_field(buf, 7, 16, header.customer_number, numeric=True)
    _put_field(buf, 17, 18, header.provider_key)
    if header.provider_property_number is not None:
        unit = header.provider_unit_number or "0000"
        _put_field(buf, 19, 31, header.provider_property_number.rjust(9, "0") + unit.rjust(4, "0"))


def _finish(lines: list[str], encoding: str) -> bytes:
    return "".join(f"{line}\r\n" for line in lines).encode(encoding)


def write_l_records(
    records: Sequence[LRecord], *, version: str = "03.10", encoding: str = ENCODING
) -> bytes:
    """Serialise ``L`` records (2048 bytes, last byte ``L``, CR LF) for ``DTM310_*.DAT``.
    Written are exactly the positions the reader ``_parse_l`` evaluates (fields 1 to 18 and the
    five flags kept in ``extra``). Not written because not documented in this repository:
    the CO2 fields beyond position 165 and everything after it (AA16-01). Not wired into any
    transmission."""
    lines: list[str] = []
    for rec in records:
        buf = [" "] * RECORD_LENGTHS["L"]
        _put_header(buf, rec.header, "L", version)
        _put_num(buf, 32, 32, rec.vat_flag)
        _put_field(buf, 33, 67, rec.street)
        _put_field(buf, 68, 70, rec.country)
        _put_field(buf, 71, 80, rec.postal_code)
        _put_field(buf, 81, 115, rec.city)
        _put_date(buf, 116, rec.period_from)
        _put_date(buf, 122, rec.period_to)
        _put_field(buf, 128, 142, rec.object_number)
        _put_num(buf, 143, 143, rec.risk_allocation_flag)
        _put_num(buf, 144, 146, rec.risk_allocation_percent, decimals=2)
        _put_num(buf, 147, 147, rec.wage_share_flag)
        _put_field(buf, 148, 150, rec.currency)
        _put_num(buf, 151, 151, rec.weg_flag)
        _put_num(buf, 152, 158, rec.total_area, decimals=2)
        for key, (start, end) in _L_EXTRA.items():
            _put_field(buf, start, end, rec.extra.get(key))
        buf[-1] = "L"
        lines.append("".join(buf))
    return _finish(lines, encoding)


_L_EXTRA = {
    "non_residential_flag": (159, 159),
    "section9_flag_1": (160, 160),
    "section9_flag_2": (161, 161),
    "co2_landlord_percent": (162, 164),
    "heat_connection_after_2023_flag": (165, 165),
}


def write_m_records(
    records: Sequence[MRecord], *, version: str = "03.10", encoding: str = ENCODING
) -> bytes:
    """Serialise ``M`` records (2048 bytes, last byte ``M``, CR LF) for ``DTM310_*.DAT``.
    Written are the positions the reader ``_parse_m`` evaluates as typed fields (user, owner,
    occupancy, shares, prepayments, allocations 1 to 3, flags 67 to 70). The provider and
    recipient blocks kept in ``extra`` (account data of the provider) are deliberately not
    written. Further allocation lines (fields 36 to 41 beyond three keys) and all positions
    not documented here stay blank (AA16-01). Not wired into any transmission."""
    lines: list[str] = []
    for rec in records:
        buf = [" "] * RECORD_LENGTHS["M"]
        _put_header(buf, rec.header, "M", version)
        _put_field(buf, 32, 51, rec.client_ref)
        _put_num(buf, 52, 52, rec.address_flag)
        _put_names(buf, 53, rec.user_names)
        _put_field(buf, 193, 227, rec.user_street)
        _put_field(buf, 228, 230, rec.user_country)
        _put_field(buf, 231, 240, rec.user_postal_code)
        _put_field(buf, 241, 275, rec.user_city)
        _put_names(buf, 276, rec.owner_names)
        _put_field(buf, 416, 450, rec.owner_street)
        _put_field(buf, 451, 453, rec.owner_country)
        _put_field(buf, 454, 463, rec.owner_postal_code)
        _put_field(buf, 464, 498, rec.owner_city)
        _put_date(buf, 499, rec.occupancy_from)
        _put_date(buf, 505, rec.occupancy_to)
        _put_num(buf, 511, 511, rec.vat_flag)
        _put_num(buf, 512, 512, rec.risk_allocation_flag)
        amounts = (
            rec.heating_shares,
            rec.heating_prepayment_gross,
            rec.heating_prepayment_net,
            rec.hot_water_shares,
            rec.hot_water_prepayment_gross,
            rec.hot_water_prepayment_net,
            rec.cold_water_shares,
            rec.cold_water_prepayment_gross,
            rec.cold_water_prepayment_net,
        )
        for index, amount in enumerate(amounts):
            start = 513 + 10 * index
            _put_num(buf, start, start + 9, amount, decimals=2)
        for index, (key, share) in enumerate(rec.allocations[:3]):
            start = 603 + 13 * index
            _put_num(buf, start, start + 2, key)
            _put_num(buf, start + 3, start + 12, share, decimals=2)
        _put_num(buf, 1167, 1167, rec.vacancy_flag)
        _put_num(buf, 1168, 1168, rec.change_fee_flag)
        _put_num(buf, 1169, 1171, rec.heating_shares_key)
        _put_num(buf, 1172, 1174, rec.hot_water_shares_key)
        buf[-1] = "M"
        lines.append("".join(buf))
    return _finish(lines, encoding)
