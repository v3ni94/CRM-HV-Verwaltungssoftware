"""Tolerant reading of Immoware24 CSV exports (objektdaten, kontakte).

Real exports differ in encoding (UTF-8 with or without BOM, Windows-1252), delimiter
(semicolon, comma, tab), quoting (embedded delimiters and line breaks), spacing, empty lines,
repeated header rows, column order and extra columns. ``decode_csv`` and ``read_table`` absorb
those variants and report what they did as German notes; the importers then look columns up by
a normalised name (case, spacing, hyphens and umlaut spelling do not matter) so that missing
required columns are reported by name instead of failing on a bad index.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
DELIMITERS = (";", ",", "\t")


def column_key(name: str) -> str:
    """Comparison key of a column name: ``"E-Mail"``, ``"email"`` and ``"E Mail "`` match."""
    return _NOT_ALNUM.sub("", name.strip().casefold().translate(_UMLAUTS))


def decode_csv(data: bytes) -> tuple[str, str | None]:
    """Text of an export and a note when the file was not plain UTF-8.

    UTF-8 (with or without BOM) is tried first; a file that is not valid UTF-8 is read as
    Windows-1252 (the usual Excel export), falling back to Latin-1 for the five bytes that
    Windows-1252 leaves undefined."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "Datei als UTF-16 gelesen"
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252"), "Datei als Windows-1252 (ANSI) gelesen, nicht als UTF-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "Datei als Latin-1 gelesen, nicht als UTF-8"


def detect_delimiter(text: str) -> str:
    """Delimiter with the most occurrences outside quotes in the first non empty line."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = dict.fromkeys(DELIMITERS, 0)
    quoted = False
    for ch in first:
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch in counts:
            counts[ch] += 1
    best = max(counts.values())
    if best == 0:
        return ";"
    return next(d for d in DELIMITERS if counts[d] == best)


@dataclass
class Row:
    line: int
    cells: list[str]


@dataclass
class Table:
    headers: list[str]
    rows: list[Row]
    delimiter: str
    notes: list[str] = field(default_factory=list)

    def columns(self, *names: str) -> list[int]:
        """All column indexes whose key matches one of ``names`` (a header may repeat)."""
        keys = {column_key(n) for n in names}
        return [i for i, h in enumerate(self.headers) if column_key(h) in keys]

    def column(self, *names: str) -> int | None:
        found = self.columns(*names)
        return found[0] if found else None

    def require(self, required: dict[str, tuple[str, ...]], source: str | None = None) -> None:
        """Raise a German ``ValueError`` naming every missing required column.

        ``required`` maps the label shown to the operator to the accepted header spellings."""
        missing = [label for label, names in required.items() if self.column(*names) is None]
        if not missing:
            return
        prefix = f"{source}: " if source else ""
        found = ", ".join(h for h in self.headers if h) or "keine"
        plural = "Spalten fehlen" if len(missing) > 1 else "Spalte fehlt"
        raise ValueError(
            f"{prefix}{plural}: {', '.join(missing)}. Gefundene Spalten: {found}. "
            "Bitte die Kopfzeile des Exports prüfen."
        )

    def cell(self, row: Row, index: int | None) -> str | None:
        if index is None or index >= len(row.cells):
            return None
        return row.cells[index].strip() or None


def read_table(text: str, source: str | None = None) -> Table:
    """Parse a CSV export: delimiter detection, stripped cells, empty rows and repeated header
    rows skipped (both counted in ``notes``), line numbers of the physical file kept."""
    text = text.lstrip("﻿")
    delimiter = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, quotechar='"')
    headers: list[str] | None = None
    header_keys: list[str] = []
    rows: list[Row] = []
    empty = 0
    repeated = 0
    previous = 0
    for cells in reader:
        start = previous + 1
        previous = reader.line_num
        stripped = [c.strip() for c in cells]
        if not any(stripped):
            if headers is not None:
                empty += 1
            continue
        if headers is None:
            headers = stripped
            header_keys = [column_key(h) for h in headers]
            continue
        if [column_key(c) for c in stripped] == header_keys:
            repeated += 1
            continue
        rows.append(Row(line=start, cells=stripped))
    if headers is None:
        prefix = f"{source}: " if source else ""
        raise ValueError(f"{prefix}Die Datei enthält keine Kopfzeile.")
    notes: list[str] = []
    label = {";": "Semikolon", ",": "Komma", "\t": "Tabulator"}[delimiter]
    if delimiter != ";":
        notes.append(f"Trennzeichen {label} erkannt")
    if repeated:
        notes.append(f"{repeated} wiederholte Kopfzeile(n) übersprungen")
    if empty:
        notes.append(f"{empty} leere Zeile(n) übersprungen")
    return Table(headers=headers, rows=rows, delimiter=delimiter, notes=notes)
