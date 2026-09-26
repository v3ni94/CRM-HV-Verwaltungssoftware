"""Objektdaten import against real Immoware24 export variants (encoding, delimiter, quoting,
spacing, empty and repeated header rows, column order, extra and missing columns, duplicates,
object numbers with leading zeros and the number map). Every variant must yield the same
prepared result as the reference file; the rows are invented for the tests."""

from __future__ import annotations

import pytest

from mhvp.imports import objektdaten
from mhvp.imports.csvtext import column_key, decode_csv, detect_delimiter, read_table
from mhvp.imports.objektdaten import (
    normalise_number,
    parse_objektdaten,
    prepare,
)

HEADERS = [
    "Objekt-Nummer",
    "Objekt",
    "Verwaltungsart",
    "Gebäude",
    "VE-Nummer",
    "VE-Beschreibung",
    "VE-Lage",
    "aktueller Eigentümer",
    "vereinbarter Zahlbetrag",
    "aktueller Mieter",
    "vereinbarter Zahlbetrag",
]
ROWS = [
    [
        "81",
        "Musterstraße 2",
        "WEG-Verwaltung",
        "Haus A",
        "1",
        "WE 1",
        "EG links",
        "Müller, Jörg",
        "250,00",
        "",
        "",
    ],
    [
        "81",
        "Musterstraße 2",
        "WEG-Verwaltung",
        "Haus A",
        "2",
        "TG 1",
        "",
        "Müller, Jörg",
        "30,00",
        "",
        "",
    ],
    [
        "216",
        "Haagstraße 32",
        "Mietverwaltung",
        "Haagstraße 32",
        "14",
        "WE 14",
        "DG",
        "",
        "",
        "Roggen, Anna",
        "620,00",
    ],
]


def _csv(headers: list[str], rows: list[list[str]], sep: str = ";", quote_all: bool = False) -> str:
    def cell(value: str) -> str:
        if quote_all or sep in value or '"' in value or "\n" in value:
            return '"' + value.replace('"', '""') + '"'
        return value

    lines = [sep.join(cell(h) for h in headers)] + [sep.join(cell(c) for c in row) for row in rows]
    return "\n".join(lines) + "\n"


REFERENCE = _csv(HEADERS, ROWS)
DASHES = ("\u2013", "\u2014")  # German messages use no dashes as punctuation


def _snapshot(text: str) -> list[tuple[str | None, str, str | None, list[tuple[str | None, ...]]]]:
    """Comparable view of the prepared result of a file (numbers, names, types, units)."""
    out = []
    for item in prepare(parse_objektdaten(text), {}):
        out.append(
            (
                item.number,
                item.name,
                item.management_type,
                [u.content() for u in item.row.units],
            )
        )
    return out


EXPECTED = _snapshot(REFERENCE)


def test_reference_is_sane() -> None:
    assert [e[0] for e in EXPECTED] == ["081", "216"]
    assert EXPECTED[0][3][0][7] is None  # no tenant amount for the owner row
    assert EXPECTED[0][3][0][5] == "250,00"
    assert EXPECTED[1][3][0][6] == "Roggen, Anna"
    assert EXPECTED[1][3][0][7] == "620,00"


# --- encodings -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("encoding", "bom", "note_part"),
    [
        ("utf-8", b"", None),
        ("utf-8", b"\xef\xbb\xbf", None),
        ("cp1252", b"", "Windows-1252"),
        ("latin-1", b"", "Windows-1252"),  # identical bytes for German umlauts
        ("utf-16", b"", "UTF-16"),
    ],
)
def test_encodings(encoding: str, bom: bytes, note_part: str | None) -> None:
    data = bom + REFERENCE.encode(encoding)
    text, note = decode_csv(data)
    assert (note_part is None and note is None) or (note_part or "") in (note or "")
    assert _snapshot(text) == EXPECTED
    parsed = parse_objektdaten(text)
    assert parsed.rows[0].units[0].owner == "Müller, Jörg"
    assert parsed.rows[0].units[1].label == "TG 1"


def test_latin1_fallback_for_bytes_undefined_in_cp1252() -> None:
    text, note = decode_csv("a;b\n1;\x81\n".encode("latin-1"))
    assert note is not None
    assert "Latin-1" in note
    assert text.endswith("\x81\n")


# --- delimiters and quoting ------------------------------------------------------------------


@pytest.mark.parametrize("sep", [";", ",", "\t"])
@pytest.mark.parametrize("quote_all", [False, True])
def test_delimiters_and_quoting(sep: str, quote_all: bool) -> None:
    text = _csv(HEADERS, ROWS, sep, quote_all)
    assert detect_delimiter(text) == sep
    parsed = parse_objektdaten(text)
    assert _snapshot(text) == EXPECTED
    if sep != ";":
        assert any("Trennzeichen" in n for n in parsed.notes)
    else:
        assert parsed.notes == []


def test_comma_delimiter_with_comma_in_quoted_names() -> None:
    """The German amounts and "Nachname, Vorname" contain commas; the delimiter is still
    detected from the header line and quoted cells stay whole."""
    text = _csv(HEADERS, ROWS, ",")
    assert '"Müller, Jörg"' in text
    assert '"250,00"' in text
    assert _snapshot(text) == EXPECTED


def test_embedded_line_breaks_in_quoted_cells() -> None:
    rows = [list(r) for r in ROWS]
    rows[0][6] = "EG links\nHinterhaus"
    text = _csv(HEADERS, rows)
    parsed = parse_objektdaten(text)
    unit = parsed.rows[0].units[0]
    assert unit.location == "EG links\nHinterhaus"
    # Physical line numbers stay correct after a multi line cell.
    assert [u.line for u in parsed.rows[0].units] == [2, 4]
    assert parsed.rows[1].units[0].line == 5


# --- spacing, empty lines, repeated headers --------------------------------------------------


def test_whitespace_empty_lines_and_repeated_headers() -> None:
    padded_headers = [f"  {h} " for h in HEADERS]
    padded_rows = [[f" {c}  " if c else "   " for c in row] for row in ROWS]
    text = (
        "\n"
        + _csv(padded_headers, padded_rows[:1])
        + "\n;;;;;;;;;;\n"
        + _csv(HEADERS, [])  # repeated header row in the middle of the file
        + _csv([], padded_rows[1:]).lstrip("\n")
        + "\n\n"
    )
    parsed = parse_objektdaten(text)
    assert _snapshot(text) == EXPECTED
    assert any("wiederholte Kopfzeile" in n for n in parsed.notes)
    assert any("leere Zeile" in n for n in parsed.notes)


def test_crlf_line_endings() -> None:
    text = REFERENCE.replace("\n", "\r\n")
    assert _snapshot(text) == EXPECTED


# --- columns ---------------------------------------------------------------------------------


def test_columns_in_other_order_and_unknown_extra_columns() -> None:
    order = [4, 10, 9, 0, 2, 1, 7, 8, 3, 6, 5]
    headers = [HEADERS[i] for i in order] + ["Bemerkung", "Exportdatum"]
    rows = [[row[i] for i in order] + ["frei", "26.09.2026"] for row in ROWS]
    text = _csv(headers, rows)
    assert _snapshot(text) == EXPECTED


def test_header_spelling_variants_are_matched() -> None:
    assert (
        column_key("Objekt-Nummer") == column_key(" objektnummer ") == column_key("OBJEKT NUMMER")
    )
    assert column_key("Gebäude") == column_key("Gebaeude")
    headers = [
        "objektnummer",
        "OBJEKT",
        "verwaltungsart",
        "Gebaeude",
        "VE Nr",
        "VE-Beschreibung",
        "VE-Lage",
        "Eigentuemer",
        "Zahlbetrag",
        "Mieter",
        "Zahlbetrag",
    ]
    text = _csv(headers, ROWS)
    assert _snapshot(text) == EXPECTED


def test_missing_required_columns_are_named() -> None:
    headers = [h for h in HEADERS if h not in ("Verwaltungsart", "VE-Nummer")]
    rows = [
        [c for i, c in enumerate(row) if HEADERS[i] not in ("Verwaltungsart", "VE-Nummer")]
        for row in ROWS
    ]
    with pytest.raises(ValueError, match="Spalten fehlen") as exc:
        parse_objektdaten(_csv(headers, rows), "objektdaten.csv")
    message = str(exc.value)
    assert message.startswith("objektdaten.csv: Spalten fehlen: Verwaltungsart, VE-Nummer.")
    assert "Gefundene Spalten: Objekt-Nummer, Objekt, Gebäude" in message
    assert not any(dash in message for dash in DASHES)
    with pytest.raises(ValueError, match="Spalte fehlt: Objekt-Nummer"):
        parse_objektdaten(_csv(HEADERS[1:], [r[1:] for r in ROWS]))
    with pytest.raises(ValueError, match="keine Kopfzeile"):
        parse_objektdaten("\n\n")


def test_optional_columns_may_be_absent() -> None:
    headers = HEADERS[:5]
    text = _csv(headers, [r[:5] for r in ROWS])
    parsed = parse_objektdaten(text)
    unit = parsed.rows[0].units[0]
    assert (unit.label, unit.location, unit.owner, unit.owner_amount) == (None, None, None, None)
    assert [p.number for p in prepare(parsed, {})] == ["081", "216"]


def test_rows_without_numbers_are_skipped_not_fatal() -> None:
    rows = [list(r) for r in ROWS] + [
        ["", "Ohne Nummer", "WEG-Verwaltung", "", "1", "", "", "", "", "", ""]
    ]
    rows.append(["300", "Ohne VE", "WEG-Verwaltung", "", "", "", "", "", "", "", ""])
    parsed = parse_objektdaten(_csv(HEADERS, rows))
    assert [r.source_number for r in parsed.rows] == ["81", "216"]
    assert "Zeile 5: Objekt-Nummer fehlt, Zeile übersprungen" in parsed.notes
    assert "Zeile 6: VE-Nummer fehlt, Zeile übersprungen" in parsed.notes
    assert "2 Zeile(n) ohne Objekt-Nummer oder VE-Nummer übersprungen" in parsed.notes


# --- duplicates ------------------------------------------------------------------------------


def test_exact_duplicate_rows_are_taken_once_with_note() -> None:
    rows = [ROWS[0], ROWS[0], ROWS[1], ROWS[2], ROWS[2]]
    parsed = parse_objektdaten(_csv(HEADERS, rows))
    assert _snapshot(_csv(HEADERS, rows)) == EXPECTED
    assert parsed.rows[0].notes == ["Zeile 3: VE 1 ist ein Duplikat von Zeile 2, einmal übernommen"]
    assert "2 doppelte Zeile(n) nur einmal übernommen" in parsed.notes
    prepared = prepare(parsed, {})
    assert prepared[0].problems == []
    assert any("Duplikat" in n for n in prepared[0].notes)


def test_same_unit_number_with_different_content_is_a_problem() -> None:
    rows = [ROWS[0], [*ROWS[0][:5], "WE 1a", *ROWS[0][6:]]]
    prepared = prepare(parse_objektdaten(_csv(HEADERS, rows)), {})
    assert prepared[0].problems == ["VE-Nummer 1 kommt 2 mal mit abweichenden Angaben vor"]


# --- object numbers and the number map -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "number_map", "number", "note_part"),
    [
        ("359", {}, "359", None),
        ("081", {}, "081", None),
        ("81", {}, "081", "führenden Nullen als 081"),
        ("8", {}, "008", "führenden Nullen als 008"),
        ("0081", {}, "081", "überzählige führende Nullen als 081"),
        ("00081", {}, "081", "überzählige führende Nullen als 081"),
        (" 81 ", {}, "081", "führenden Nullen"),
        ("10012", {}, None, "nicht dreistellig; bitte mit --number-map 10012=NNN"),
        ("2911", {}, None, "nicht dreistellig"),
        ("999999", {}, None, "nicht dreistellig"),
        ("10012", {"10012": "012"}, "012", "laut Zuordnung als 012"),
        ("10012", {"10012": "12"}, "012", "laut Zuordnung 10012=12 als 012"),
        ("10012", {"10012": "1234"}, None, "nicht dreistellig"),
        ("10012", {"10012": "abc"}, None, "nicht dreistellig"),
        ("010012", {"10012": "012"}, "012", "laut Zuordnung"),
        ("999999", {"999999": "999"}, "999", "laut Zuordnung als 999"),
        ("A12", {}, None, "nicht dreistellig"),
    ],
)
def test_number_normalisation(
    raw: str, number_map: dict[str, str], number: str | None, note_part: str | None
) -> None:
    got, note = normalise_number(raw, number_map)
    assert got == number
    if note_part is None:
        assert note is None
    else:
        assert note_part in (note or "")
        assert not any(dash in (note or "") for dash in DASHES)


def test_number_map_parsing_accepts_operator_spellings() -> None:
    mapping = objektdaten._parse_number_map(["10012=012, 10013 = 13", "999999=999", "", " "])
    assert mapping == {"10012": "012", "10013": "13", "999999": "999"}
    with pytest.raises(Exception, match="erwartet ALT=NEU"):
        objektdaten._parse_number_map(["10012"])


def test_management_type_spellings() -> None:
    for raw in ("WEG-Verwaltung", "weg verwaltung", " WEG-VERWALTUNG ", "WEG"):
        assert objektdaten.management_type_for(raw) == "hoa"
    for raw in ("Mietverwaltung", "MIETVERWALTUNG", "Miete"):
        assert objektdaten.management_type_for(raw) == "rental"
    for raw in ("WEG mit SE-Verwaltung", "WEG mit SEV", "Sondereigentumsverwaltung", "SEV"):
        assert objektdaten.management_type_for(raw) == "hoa_with_sev"
    assert objektdaten.management_type_for("Sonstiges") is None
    prepared = prepare(
        parse_objektdaten(_csv(HEADERS, [[*ROWS[0][:2], "Sonstiges", *ROWS[0][3:]]])), {}
    )
    assert prepared[0].problems == ["Verwaltungsart 'Sonstiges' ist nicht zugeordnet"]


def test_read_table_line_numbers_and_cells() -> None:
    table = read_table('a;b\n\n1;"x;y"\n2; z \n')
    assert table.headers == ["a", "b"]
    assert [(r.line, r.cells) for r in table.rows] == [(3, ["1", "x;y"]), (4, ["2", "z"])]
    assert table.cell(table.rows[0], 1) == "x;y"
    assert table.cell(table.rows[0], 5) is None
    assert table.cell(table.rows[0], None) is None
