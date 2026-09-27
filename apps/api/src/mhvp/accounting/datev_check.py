"""Formal self check of a DATEV "Buchungsstapel" file and the test batch for the tax advisor.

Scope (M18-01, DATEV import test, gate G1): the check reads the CSV text that
``reports.datev_csv`` wrote (or any pasted file) and reports every finding with a rule id, the
line, a severity and the source status of the rule. Only rules that the public DATEV material
documents are marked ``belegt``; everything that is common practice but could not be verified
against the DATEV-Schnittstellenbeschreibung during this task is marked ``zu_pruefen`` and
never claimed as a DATEV requirement (rule 0.1.3). A green report is a formal pre-check only;
the binding proof is the import test at the tax advisor (docs/handbuch/datev-importtest.md).

The check is deterministic and pure: no database, no network.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]
SourceStatus = Literal["belegt", "zu_pruefen"]

# Header positions (1 based) of the EXTF first line as written by ``reports.datev_csv``.
H_FLAG, H_VERSION, H_CATEGORY, H_FORMAT_NAME, H_FORMAT_VERSION = 1, 2, 3, 4, 5
H_CREATED, H_CONSULTANT, H_CLIENT, H_FY_START, H_ACCOUNT_LENGTH = 6, 11, 12, 13, 14
H_DATE_FROM, H_DATE_TO, H_CHART = 15, 16, 20

# Booking columns as written by this system (the first seven DATEV columns are fixed; the
# BU-Schlüssel column is optional here and checked only when present and filled).
COL_AMOUNT = "Umsatz (ohne Soll/Haben-Kz)"
COL_SH = "Soll/Haben-Kennzeichen"
COL_ACCOUNT = "Konto"
COL_CONTRA = "Gegenkonto (ohne BU-Schlüssel)"
COL_BU = "BU-Schlüssel"
COL_DATE = "Belegdatum"
COL_TEXT = "Buchungstext"
COL_REF = "Belegfeld 1"

EXPECTED_HEADER_FIELDS = 31  # zu prüfen (common practice, not verified in this task)
TEXT_MAX = 60  # zu prüfen
REF_MAX = 36  # zu prüfen
ACCOUNT_LENGTH_RANGE = (4, 8)  # zu prüfen

RULES: dict[str, dict[str, str]] = {
    "DC-01": {
        "title": "Kopfzeile beginnt mit dem Kennzeichen EXTF",
        "source": "belegt",
        "reference": (
            "DATEV-Format, Kopfzeile Feld 1 (öffentliche Beispiele: EXTF;700;21;Buchungsstapel;7)"
        ),
    },
    "DC-02": {
        "title": "Versionsnummer des Formats (Feld 2) ist 700",
        "source": "belegt",
        "reference": "DATEV-Format, Kopfzeile Feld 2",
    },
    "DC-03": {
        "title": "Datenkategorie (Feld 3) ist 21 und Formatname (Feld 4) ist Buchungsstapel",
        "source": "belegt",
        "reference": "DATEV-Format, Kopfzeile Felder 3 und 4",
    },
    "DC-04": {
        "title": "Formatversion (Feld 5) ist eine ganze Zahl",
        "source": "belegt",
        "reference": "DATEV-Format, Kopfzeile Feld 5 (Beispielwert 7)",
    },
    "DC-05": {
        "title": "Anzahl der Kopfzeilenfelder",
        "source": "zu_pruefen",
        "reference": (
            "Gängige Praxis: 31 Felder; Vorgabe der Schnittstellenbeschreibung nicht abgerufen"
        ),
    },
    "DC-06": {
        "title": "Beraternummer und Mandantennummer sind numerisch und gefüllt",
        "source": "zu_pruefen",
        "reference": (
            "Kopfzeile Felder 11 und 12; Längenvorgabe (Berater 4 bis 7, Mandant 1 "
            "bis 5 Stellen) zu prüfen"
        ),
    },
    "DC-07": {
        "title": "Wirtschaftsjahresbeginn, Datum von und Datum bis im Format JJJJMMTT, von vor bis",
        "source": "zu_pruefen",
        "reference": "Kopfzeile Felder 13, 15, 16",
    },
    "DC-08": {
        "title": "Sachkontenlänge zwischen 4 und 8",
        "source": "zu_pruefen",
        "reference": "Kopfzeile Feld 14",
    },
    "DC-09": {
        "title": "Kontenrahmen (Feld 20) gesetzt",
        "source": "zu_pruefen",
        "reference": (
            "Kopfzeile Feld 20; ob 03 oder SKR03 erwartet wird, ist im Importtest zu klären"
        ),
    },
    "DC-10": {
        "title": "Spaltenüberschriften Umsatz, Soll/Haben, Konto, Gegenkonto, Belegdatum vorhanden",
        "source": "belegt",
        "reference": "DATEV-Format, Buchungssatz Felder 1 bis 10",
    },
    "DC-11": {
        "title": "Jede Buchungszeile hat so viele Felder wie die Spaltenüberschrift",
        "source": "belegt",
        "reference": "CSV-Struktur, Trennzeichen Semikolon",
    },
    "DC-12": {
        "title": "Umsatz ist ein positiver Betrag mit Komma und höchstens zwei Nachkommastellen",
        "source": "belegt",
        "reference": "DATEV-Format: Umsatz immer positiv; Dezimalkomma zu prüfen",
    },
    "DC-13": {
        "title": "Soll/Haben-Kennzeichen ist S oder H",
        "source": "belegt",
        "reference": "DATEV-Format, Buchungssatz Feld 2",
    },
    "DC-14": {
        "title": "Konto und Gegenkonto sind gefüllt und numerisch",
        "source": "belegt",
        "reference": "DATEV-Format: Konto und Gegenkonto sind Sach- oder Personenkonten",
    },
    "DC-15": {
        "title": "Kontonummernlänge passt zur Sachkontenlänge der Kopfzeile",
        "source": "zu_pruefen",
        "reference": (
            "Sachkonto = Sachkontenlänge, Personenkonto = Sachkontenlänge + 1 (gängige Praxis)"
        ),
    },
    "DC-16": {
        "title": "Belegdatum im Format TTMM mit gültigem Tag und Monat",
        "source": "belegt",
        "reference": "DATEV-Format, Buchungssatz Feld Belegdatum (TTMM)",
    },
    "DC-17": {
        "title": "Belegdatum liegt im Zeitraum Datum von bis Datum bis der Kopfzeile",
        "source": "zu_pruefen",
        "reference": "Kopfzeile Felder 15 und 16",
    },
    "DC-18": {
        "title": "Buchungstext höchstens 60 Zeichen, Belegfeld 1 höchstens 36 Zeichen",
        "source": "zu_pruefen",
        "reference": "Feldlängen der Schnittstellenbeschreibung nicht abgerufen",
    },
    "DC-19": {
        "title": "BU-Schlüssel, falls gesetzt, numerisch mit höchstens vier Stellen",
        "source": "zu_pruefen",
        "reference": "Nur geprüft, wenn die Spalte vorhanden und das Feld gefüllt ist",
    },
    "DC-20": {
        "title": "Zeichensatz: alle Zeichen in Windows-1252 darstellbar",
        "source": "zu_pruefen",
        "reference": (
            "DATEV erwartet nach gängiger Praxis ANSI (Windows-1252); Datei wird "
            "als UTF-8 geschrieben"
        ),
    },
    "DC-21": {
        "title": "Zeilenende CRLF",
        "source": "zu_pruefen",
        "reference": "Gängige Praxis",
    },
    "DC-22": {
        "title": "Mindestens eine Buchungszeile vorhanden",
        "source": "belegt",
        "reference": "Ein leerer Stapel kann nicht importiert werden",
    },
}


@dataclass
class Finding:
    rule: str
    severity: Severity
    message: str
    line: int | None = None
    field_name: str | None = None
    value: str | None = None

    @property
    def source(self) -> str:
        return RULES[self.rule]["source"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "title": RULES[self.rule]["title"],
            "source": self.source,
            "severity": self.severity,
            "line": self.line,
            "field": self.field_name,
            "value": self.value,
            "message": self.message,
        }


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)
    booking_rows: int = 0
    header_fields: int = 0
    columns: list[str] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def status(self) -> str:
        if self.errors:
            return "fehlerhaft"
        if self.warnings:
            return "mit_hinweisen"
        return "formal_ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": sum(1 for f in self.findings if f.severity == "info"),
            "booking_rows": self.booking_rows,
            "header_fields": self.header_fields,
            "columns": self.columns,
            "rules": [
                {"id": rule_id, **RULES[rule_id], "checked": rule_id in self.checked_rules}
                for rule_id in RULES
            ],
            "findings": [f.as_dict() for f in self.findings],
            "disclaimer": (
                "Formale Selbstprüfung nach den belegten Regeln des DATEV-Formats. Regeln mit "
                "Quellenstatus zu_pruefen sind gängige Praxis und keine bestätigte DATEV-Vorgabe. "
                "Verbindlich ist der Importtest beim Steuerberater."
            ),
        }


_STATUS_TEXT = {
    "formal_ok": "Formal ohne Befund",
    "mit_hinweisen": "Formal ohne Fehler, mit Hinweisen",
    "fehlerhaft": "Fehlerhaft, Datei so nicht für den Import geeignet",
}


def report_text(report: CheckReport) -> str:
    """Human readable report in German (for the CRM and the tax advisor)."""
    lines = [
        "Prüfbericht DATEV-Buchungsstapel (formale Selbstprüfung)",
        f"Ergebnis: {_STATUS_TEXT[report.status]}",
        f"Buchungszeilen: {report.booking_rows}, Kopfzeilenfelder: {report.header_fields}, "
        f"Fehler: {report.errors}, Hinweise: {report.warnings}",
        "",
    ]
    if not report.findings:
        lines.append("Keine Befunde.")
    else:
        lines.append("Befunde:")
        for f in report.findings:
            where = f"Zeile {f.line}" if f.line else "Datei"
            severity = {"error": "Fehler", "warning": "Hinweis", "info": "Info"}[f.severity]
            source = "belegt" if f.source == "belegt" else "zu prüfen"
            lines.append(f"- [{f.rule}] {severity} ({source}), {where}: {f.message}")
    lines += [
        "",
        "Geprüfte Regeln:",
        *[
            f"- {rid}: {RULES[rid]['title']} (Quelle: {RULES[rid]['source']})"
            for rid in report.checked_rules
        ],
        "",
        "Hinweis: Regeln mit Quellenstatus zu prüfen sind gängige Praxis und keine bestätigte "
        "DATEV-Vorgabe. Verbindlich ist der Importtest beim Steuerberater.",
    ]
    return "\n".join(lines)


_DATE8 = re.compile(r"^\d{8}$")
_DIGITS = re.compile(r"^\d+$")
_AMOUNT = re.compile(r"^\d+(,\d{1,2})?$")


def _yyyymmdd(value: str) -> date | None:
    if not _DATE8.match(value):
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def check_batch(content: str) -> CheckReport:
    """Run every rule on the CSV text and return the report with all findings."""
    report = CheckReport()
    add = report.findings.append
    checked = report.checked_rules

    def use(rule: str) -> None:
        if rule not in checked:
            checked.append(rule)

    # Encoding and line endings ------------------------------------------------------------
    use("DC-20")
    try:
        content.encode("cp1252")
    except UnicodeEncodeError as exc:
        add(
            Finding(
                "DC-20",
                "warning",
                f"Zeichen {content[exc.start : exc.end]!r} ist in Windows-1252 nicht darstellbar.",
            )
        )
    use("DC-21")
    if "\n" in content and "\r\n" not in content:
        add(Finding("DC-21", "warning", "Zeilen enden mit LF statt CRLF."))

    reader = csv.reader(io.StringIO(content), delimiter=";")
    try:
        rows = list(reader)
    except csv.Error as exc:
        add(Finding("DC-11", "error", f"CSV nicht lesbar: {exc}"))
        use("DC-11")
        return report
    while rows and rows[-1] == []:
        rows.pop()

    # Header line --------------------------------------------------------------------------
    header = rows[0] if rows else []
    report.header_fields = len(header)

    def h(pos: int) -> str:
        return header[pos - 1].strip() if len(header) >= pos else ""

    use("DC-01")
    if h(H_FLAG) != "EXTF":
        add(Finding("DC-01", "error", "Kopfzeile beginnt nicht mit EXTF.", 1, "Kennzeichen", h(1)))
    use("DC-02")
    if h(H_VERSION) != "700":
        add(Finding("DC-02", "error", "Versionsnummer ist nicht 700.", 1, "Versionsnummer", h(2)))
    use("DC-03")
    if h(H_CATEGORY) != "21":
        add(Finding("DC-03", "error", "Datenkategorie ist nicht 21.", 1, "Datenkategorie", h(3)))
    if h(H_FORMAT_NAME) != "Buchungsstapel":
        add(
            Finding("DC-03", "error", "Formatname ist nicht Buchungsstapel.", 1, "Formatname", h(4))
        )
    use("DC-04")
    if not _DIGITS.match(h(H_FORMAT_VERSION)):
        add(Finding("DC-04", "error", "Formatversion ist keine Zahl.", 1, "Formatversion", h(5)))
    use("DC-05")
    if len(header) != EXPECTED_HEADER_FIELDS:
        add(
            Finding(
                "DC-05",
                "warning",
                f"Kopfzeile hat {len(header)} Felder, gängige Praxis sind "
                f"{EXPECTED_HEADER_FIELDS}. Im Importtest zu klären.",
                1,
            )
        )
    use("DC-06")
    for pos, name, lo, hi in (
        (H_CONSULTANT, "Beraternummer", 4, 7),
        (H_CLIENT, "Mandantennummer", 1, 5),
    ):
        value = h(pos)
        if not _DIGITS.match(value):
            add(
                Finding(
                    "DC-06", "warning", f"{name} fehlt oder ist nicht numerisch.", 1, name, value
                )
            )
        elif not lo <= len(value) <= hi:
            add(
                Finding(
                    "DC-06",
                    "warning",
                    f"{name} hat {len(value)} Stellen, erwartet werden {lo} bis {hi}.",
                    1,
                    name,
                    value,
                )
            )
    use("DC-07")
    dates: dict[str, date | None] = {}
    for pos, name in (
        (H_FY_START, "Wirtschaftsjahresbeginn"),
        (H_DATE_FROM, "Datum von"),
        (H_DATE_TO, "Datum bis"),
    ):
        value = h(pos)
        parsed = _yyyymmdd(value)
        dates[name] = parsed
        if parsed is None:
            add(
                Finding(
                    "DC-07",
                    "warning",
                    f"{name} ist kein Datum im Format JJJJMMTT.",
                    1,
                    name,
                    value,
                )
            )
    date_from, date_to = dates["Datum von"], dates["Datum bis"]
    if date_from and date_to and date_from > date_to:
        add(Finding("DC-07", "warning", "Datum von liegt nach Datum bis.", 1, "Datum von"))
    if (
        dates["Wirtschaftsjahresbeginn"]
        and date_from
        and dates["Wirtschaftsjahresbeginn"] > date_from
    ):
        add(
            Finding(
                "DC-07",
                "warning",
                "Wirtschaftsjahresbeginn liegt nach Datum von.",
                1,
                "Wirtschaftsjahresbeginn",
            )
        )
    use("DC-08")
    account_length: int | None = None
    value = h(H_ACCOUNT_LENGTH)
    if _DIGITS.match(value) and ACCOUNT_LENGTH_RANGE[0] <= int(value) <= ACCOUNT_LENGTH_RANGE[1]:
        account_length = int(value)
    else:
        add(
            Finding(
                "DC-08",
                "warning",
                "Sachkontenlänge fehlt oder liegt nicht zwischen 4 und 8.",
                1,
                "Sachkontenlänge",
                value,
            )
        )
    use("DC-09")
    if not h(H_CHART):
        add(Finding("DC-09", "warning", "Kontenrahmen ist nicht gesetzt.", 1, "Kontenrahmen"))

    # Column header ------------------------------------------------------------------------
    columns = [c.strip() for c in rows[1]] if len(rows) > 1 else []
    report.columns = columns
    use("DC-10")
    required = [COL_AMOUNT, COL_SH, COL_ACCOUNT, COL_CONTRA, COL_DATE]
    missing = [c for c in required if c not in columns]
    if missing:
        add(
            Finding(
                "DC-10",
                "error",
                "Spaltenüberschriften fehlen: " + ", ".join(missing),
                2 if columns else None,
            )
        )
        return report
    index = {name: columns.index(name) for name in columns}
    bu_index = index.get(COL_BU)

    body = rows[2:]
    report.booking_rows = len(body)
    use("DC-22")
    if not body:
        add(Finding("DC-22", "error", "Der Stapel enthält keine Buchungszeile."))
        return report

    for rule in ("DC-11", "DC-12", "DC-13", "DC-14", "DC-15", "DC-16", "DC-17", "DC-18"):
        use(rule)
    if bu_index is not None:
        use("DC-19")

    def cell(row: list[str], name: str) -> str:
        pos = index[name]
        return row[pos].strip() if pos < len(row) else ""

    for offset, row in enumerate(body, start=3):
        if len(row) != len(columns):
            add(
                Finding(
                    "DC-11",
                    "error",
                    f"Zeile hat {len(row)} Felder, die Spaltenüberschrift {len(columns)}.",
                    offset,
                )
            )
            continue
        amount = cell(row, COL_AMOUNT)
        if not _AMOUNT.match(amount):
            add(
                Finding(
                    "DC-12",
                    "error",
                    "Umsatz ist kein positiver Betrag mit Dezimalkomma.",
                    offset,
                    COL_AMOUNT,
                    amount,
                )
            )
        else:
            try:
                if Decimal(amount.replace(",", ".")) <= 0:
                    add(
                        Finding(
                            "DC-12",
                            "error",
                            "Umsatz ist nicht positiv.",
                            offset,
                            COL_AMOUNT,
                            amount,
                        )
                    )
            except InvalidOperation:  # pragma: no cover - regex already excludes this
                add(Finding("DC-12", "error", "Umsatz nicht lesbar.", offset, COL_AMOUNT, amount))
        sh = cell(row, COL_SH)
        if sh not in {"S", "H"}:
            add(
                Finding(
                    "DC-13",
                    "error",
                    "Soll/Haben-Kennzeichen ist nicht S oder H.",
                    offset,
                    COL_SH,
                    sh,
                )
            )
        for name in (COL_ACCOUNT, COL_CONTRA):
            number = cell(row, name)
            if not number:
                add(Finding("DC-14", "error", f"{name} ist leer.", offset, name, number))
            elif not _DIGITS.match(number):
                add(Finding("DC-14", "error", f"{name} ist nicht numerisch.", offset, name, number))
            elif account_length is not None and len(number) not in (
                account_length,
                account_length + 1,
            ):
                add(
                    Finding(
                        "DC-15",
                        "warning",
                        f"{name} hat {len(number)} Stellen, Sachkontenlänge ist "
                        f"{account_length} (Personenkonto {account_length + 1}).",
                        offset,
                        name,
                        number,
                    )
                )
        booking_date = cell(row, COL_DATE)
        if not re.match(r"^\d{4}$", booking_date):
            add(
                Finding(
                    "DC-16",
                    "error",
                    "Belegdatum ist nicht im Format TTMM.",
                    offset,
                    COL_DATE,
                    booking_date,
                )
            )
        else:
            day, month = int(booking_date[:2]), int(booking_date[2:])
            if not (1 <= day <= 31 and 1 <= month <= 12):
                add(
                    Finding(
                        "DC-16",
                        "error",
                        "Belegdatum hat keinen gültigen Tag oder Monat.",
                        offset,
                        COL_DATE,
                        booking_date,
                    )
                )
            elif date_from and date_to:
                candidates = {date_from.year, date_to.year}
                inside = False
                for year in candidates:
                    try:
                        inside = inside or date_from <= date(year, month, day) <= date_to
                    except ValueError:
                        continue
                if not inside:
                    add(
                        Finding(
                            "DC-17",
                            "warning",
                            "Belegdatum liegt nicht im Zeitraum der Kopfzeile.",
                            offset,
                            COL_DATE,
                            booking_date,
                        )
                    )
        if COL_TEXT in index and len(cell(row, COL_TEXT)) > TEXT_MAX:
            add(
                Finding(
                    "DC-18",
                    "warning",
                    f"Buchungstext länger als {TEXT_MAX} Zeichen.",
                    offset,
                    COL_TEXT,
                )
            )
        if COL_REF in index and len(cell(row, COL_REF)) > REF_MAX:
            add(
                Finding(
                    "DC-18",
                    "warning",
                    f"Belegfeld 1 länger als {REF_MAX} Zeichen.",
                    offset,
                    COL_REF,
                )
            )
        if bu_index is not None:
            bu = cell(row, COL_BU)
            if bu and not re.match(r"^\d{1,4}$", bu):
                add(
                    Finding(
                        "DC-19",
                        "warning",
                        "BU-Schlüssel ist nicht numerisch (1 bis 4 Stellen).",
                        offset,
                        COL_BU,
                        bu,
                    )
                )
    return report


# Test batch for the tax advisor ---------------------------------------------------------------

SAMPLE_POSTINGS: list[tuple[str, str, str, str, str, str, str]] = [
    # amount, S/H, account, contra account, TTMM, text, reference (all fictional)
    ("250,00", "S", "1200", "8400", "0501", "Hausgeld Einheit 1 Testbuchung", "TB-0001"),
    ("250,00", "S", "1200", "8400", "0501", "Hausgeld Einheit 2 Testbuchung", "TB-0002"),
    ("310,50", "S", "1200", "8400", "0601", "Hausgeld Einheit 3 Testbuchung", "TB-0003"),
    ("89,90", "H", "1200", "4200", "0701", "Gebäudeversicherung Testbuchung", "TB-0004"),
    ("120,00", "H", "1200", "4210", "0801", "Hausstrom Testbuchung", "TB-0005"),
    ("45,00", "H", "1200", "4250", "1001", "Gartenpflege Testbuchung", "TB-0006"),
    ("1000,00", "H", "1200", "0950", "1501", "Zuführung Rücklage Testbuchung", "TB-0007"),
    ("12,50", "H", "1200", "4970", "3101", "Kontoführung Testbuchung", "TB-0008"),
    ("250,00", "S", "1200", "8400", "0102", "Hausgeld Einheit 1 Testbuchung", "TB-0009"),
    ("250,00", "S", "1200", "8400", "0102", "Hausgeld Einheit 2 Testbuchung", "TB-0010"),
    ("310,50", "S", "1200", "8400", "0302", "Hausgeld Einheit 3 Testbuchung", "TB-0011"),
    ("199,00", "H", "1200", "4240", "0502", "Heizungswartung Testbuchung", "TB-0012"),
    ("75,00", "H", "1200", "4260", "1002", "Treppenhausreinigung Testbuchung", "TB-0013"),
    ("30,00", "H", "1200", "4230", "1202", "Müllabfuhr Testbuchung", "TB-0014"),
    ("600,00", "H", "1200", "4300", "1502", "Verwaltervergütung Testbuchung", "TB-0015"),
    ("250,00", "S", "1200", "8400", "0103", "Hausgeld Einheit 1 Testbuchung", "TB-0016"),
    ("250,00", "S", "1200", "8400", "0103", "Hausgeld Einheit 2 Testbuchung", "TB-0017"),
    ("310,50", "S", "1200", "8400", "0303", "Hausgeld Einheit 3 Testbuchung", "TB-0018"),
    ("58,20", "H", "1200", "4220", "1003", "Wasser und Abwasser Testbuchung", "TB-0019"),
    ("12,50", "H", "1200", "4970", "3103", "Kontoführung Testbuchung", "TB-0020"),
]


def sample_batch(
    *,
    consultant_number: str,
    client_number: str,
    chart_of_accounts: str,
    account_length: int,
    fiscal_year_start: date,
    date_from: date,
    date_to: date,
    generated: str,
) -> str:
    """The test batch handed to the tax advisor: 20 fictional bookings on four digit SKR
    accounts, same header layout as the productive export (``reports.datev_csv``). Account
    numbers are examples for the import test only, no chart of accounts is asserted."""
    header = [
        "EXTF",
        "700",
        "21",
        "Buchungsstapel",
        "7",
        generated,
        "",
        "RE",
        "",
        "",
        consultant_number,
        client_number,
        f"{fiscal_year_start:%Y%m%d}",
        str(account_length),
        f"{date_from:%Y%m%d}",
        f"{date_to:%Y%m%d}",
        "",
        "",
        "1",
        chart_of_accounts,
        "0",
    ]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(header)
    writer.writerow([COL_AMOUNT, COL_SH, COL_ACCOUNT, COL_CONTRA, COL_DATE, COL_TEXT, COL_REF])
    for amount, sh, account, contra, ttmm, text, ref in SAMPLE_POSTINGS:
        writer.writerow([amount, sh, account, contra, ttmm, text, ref])
    return out.getvalue()
