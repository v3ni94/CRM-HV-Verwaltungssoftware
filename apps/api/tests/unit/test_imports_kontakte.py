"""Kontakte import against real Immoware24 export variants (encoding, delimiter, quoting,
spacing, empty and repeated header rows, column order, extra and missing columns, duplicate
ids, phone and e-mail spellings, name forms, legal forms, house number additions, IBAN only as
a proposal). The rows are invented for the tests."""

from __future__ import annotations

import pytest

from mhvp.contacts.models import ContactKind, ContactRoleCode
from mhvp.imports.csvtext import decode_csv, detect_delimiter
from mhvp.imports.kontakte import (
    compose_phone,
    is_company,
    legal_form,
    parse_kontakte,
    prepare,
    prepare_row,
    split_address,
    split_emails,
    split_person_name,
    split_title,
)

HEADERS = [
    "id",
    "Name",
    "Briefanrede",
    "Benutzername",
    "Adresse",
    "Stadt",
    "PLZ",
    "Staat",
    "Land",
    "Landesvorwahl",
    "Vorwahl",
    "Telefonnummer",
    "E-Mail",
]
ROWS = [
    [
        "4711",
        "Müller, Jörg",
        "Sehr geehrter Herr Müller",
        "",
        "Musterstraße 2a",
        "Köln",
        "50667",
        "NRW",
        "Deutschland",
        "0049",
        "0221",
        "1234567",
        "joerg@example.org",
    ],
    [
        "4712",
        "Erika Mieter",
        "Sehr geehrte Frau Mieter",
        "",
        "Am Markt 3-5",
        "Düsseldorf",
        "40213",
        "",
        "Deutschland",
        "",
        "0211",
        "7654321",
        "erika@example.org",
    ],
    [
        "3",
        "Sparkasse Köln Bonn",
        "",
        "",
        "Hahnenstraße 57",
        "Köln",
        "50667",
        "",
        "Deutschland",
        "",
        "",
        "",
        "",
    ],
]
MIETER = ContactRoleCode.MIETER


def _csv(headers: list[str], rows: list[list[str]], sep: str = ";", quote_all: bool = False) -> str:
    def cell(value: str) -> str:
        if quote_all or sep in value or '"' in value or "\n" in value:
            return '"' + value.replace('"', '""') + '"'
        return value

    lines = [sep.join(cell(h) for h in headers)] + [sep.join(cell(c) for c in row) for row in rows]
    return "\n".join(lines) + "\n"


REFERENCE = _csv(HEADERS, ROWS)


def _snapshot(text: str) -> list[dict[str, object]]:
    out = []
    for item in prepare(parse_kontakte(text, MIETER, "mieter.csv")):
        assert item.data is not None, item.problems
        out.append(item.data.model_dump(mode="json"))
    return out


EXPECTED = _snapshot(REFERENCE)


def test_reference_is_sane() -> None:
    assert [e["external_ids"] for e in EXPECTED] == [
        {"immoware24": "4711", "immoware24_name": "Müller, Jörg"},
        {"immoware24": "4712", "immoware24_name": "Erika Mieter"},
        {"immoware24": "3", "immoware24_name": "Sparkasse Köln Bonn"},
    ]
    first = EXPECTED[0]
    assert (first["first_name"], first["last_name"], first["salutation"]) == (
        "Jörg",
        "Müller",
        "Herr",
    )
    assert first["addresses"][0]["street"] == "Musterstraße"  # type: ignore[index]
    assert first["addresses"][0]["house_number"] == "2a"  # type: ignore[index]
    assert first["phones"][0]["number"] == "+492211234567"  # type: ignore[index]
    assert EXPECTED[2]["kind"] == "company"


# --- encodings, delimiters, quoting, spacing --------------------------------------------------


@pytest.mark.parametrize(
    ("encoding", "bom"),
    [("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"), ("cp1252", b""), ("latin-1", b"")],
)
def test_encodings(encoding: str, bom: bytes) -> None:
    text, _ = decode_csv(bom + REFERENCE.encode(encoding))
    assert _snapshot(text) == EXPECTED
    assert parse_kontakte(text, MIETER, "m.csv").rows[0].name == "Müller, Jörg"


@pytest.mark.parametrize("sep", [";", ",", "\t"])
@pytest.mark.parametrize("quote_all", [False, True])
def test_delimiters_and_quoting(sep: str, quote_all: bool) -> None:
    text = _csv(HEADERS, ROWS, sep, quote_all)
    assert detect_delimiter(text) == sep
    assert _snapshot(text) == EXPECTED


def test_embedded_delimiter_and_line_break_in_quoted_cell() -> None:
    rows = [list(r) for r in ROWS]
    rows[2][1] = 'Sparkasse "Köln/Bonn"; Filiale\nSüd'
    parsed = parse_kontakte(_csv(HEADERS, rows), ContactRoleCode.BANK, "bank.csv")
    assert parsed.rows[2].name == 'Sparkasse "Köln/Bonn"; Filiale\nSüd'
    assert parsed.rows[2].line == 4
    item = prepare_row(parsed.rows[2])
    assert item.data is not None
    assert item.data.company_name == 'Sparkasse "Köln/Bonn"; Filiale Süd'


def test_whitespace_empty_lines_and_repeated_headers() -> None:
    padded = [[f" {c} " for c in row] for row in ROWS]
    text = (
        "\n"
        + _csv([f" {h} " for h in HEADERS], padded[:1])
        + ";;;;;;;;;;;;\n"
        + _csv(HEADERS, padded[1:])
        + "\n"
    )
    parsed = parse_kontakte(text, MIETER, "mieter.csv")
    assert _snapshot(text) == EXPECTED
    assert "mieter.csv: 1 wiederholte Kopfzeile(n) übersprungen" in parsed.notes
    assert any("leere Zeile" in n for n in parsed.notes)
    assert [r.line for r in parsed.rows] == [3, 6, 7]


# --- columns ---------------------------------------------------------------------------------


def test_columns_in_other_order_with_extra_and_alias_headers() -> None:
    order = [12, 0, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    headers = [HEADERS[i] for i in order] + ["Kundennummer", "Notiz"]
    headers[headers.index("E-Mail")] = "Email"
    headers[headers.index("Stadt")] = "Ort"
    headers[headers.index("Telefonnummer")] = "Telefon"
    headers[headers.index("id")] = "ID"
    rows = [[row[i] for i in order] + ["K1", "x"] for row in ROWS]
    assert _snapshot(_csv(headers, rows)) == EXPECTED


def test_missing_required_columns_are_named() -> None:
    with pytest.raises(ValueError, match="Spalte fehlt") as exc:
        parse_kontakte("Nr;Wert;Ort\n1;x;y\n", MIETER, "mieter.csv")
    assert str(exc.value).startswith(
        "mieter.csv: Spalte fehlt: Name. Gefundene Spalten: Nr, Wert, Ort."
    )
    with pytest.raises(ValueError, match="Spalten fehlen: id, Name"):
        parse_kontakte("Wert;Ort\n1;x\n", MIETER, "x.csv")


def test_rows_without_id_or_name_are_skipped_with_note() -> None:
    rows = [ROWS[0], ["", "Ohne Id", *ROWS[0][2:]], ["9", "", *ROWS[0][2:]]]
    parsed = parse_kontakte(_csv(HEADERS, rows), MIETER, "mieter.csv")
    assert [r.external_id for r in parsed.rows] == ["4711"]
    assert "mieter.csv Zeile 3: id fehlt, übersprungen" in parsed.notes
    assert "mieter.csv Zeile 4: Name fehlt, übersprungen" in parsed.notes


def test_minimal_file_with_only_id_and_name() -> None:
    items = prepare(parse_kontakte("Name;id\nMuster, Max;1\n", MIETER, "m.csv"))
    assert items[0].data is not None
    assert items[0].data.completeness.value == "incomplete"
    assert items[0].data.last_name == "Max" or items[0].data.last_name == "Muster"


# --- duplicates ------------------------------------------------------------------------------


def test_duplicate_ids_within_a_file_are_marked_not_created_twice() -> None:
    rows = [ROWS[0], ROWS[1], ROWS[0]]
    items = prepare(parse_kontakte(_csv(HEADERS, rows), MIETER, "mieter.csv"))
    assert [i.duplicate_of for i in items] == [None, None, 2]
    assert items[2].data is None
    assert items[2].problems == []
    assert items[2].notes == ["id 4711 bereits in Zeile 2, nicht erneut angelegt"]


def test_same_id_in_two_files_is_not_a_duplicate() -> None:
    a = parse_kontakte(_csv(HEADERS, ROWS[:1]), ContactRoleCode.EIGENTUEMER, "eigentuemer.csv")
    b = parse_kontakte(_csv(HEADERS, ROWS[:1]), MIETER, "mieter.csv")
    a.extend(b)
    assert [i.duplicate_of for i in prepare(a)] == [None, None]


# --- phones ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cc", "area", "number", "expected"),
    [
        ("0049", "0157", "54296195", "+4915754296195"),
        ("+49", "157", "54296195", "+4915754296195"),
        ("49", "0157", "5429 6195", "+4915754296195"),
        ("", "0157", "54296195", "015754296195"),
        ("", "", "0157 / 54 29 61 95", "015754296195"),
        ("", "", "0157-54296195", "015754296195"),
        ("", "", "+49 (0) 157 54296195", "+4915754296195"),
        ("", "", "0049 157 54296195", "+4915754296195"),
        ("0049", "", "015754296195", "+4915754296195"),
        ("030", "4391", "7008", "03043917008"),
        ("", "02431", "9550300", "024319550300"),
        ("", "", "", None),
        ("0049", "", "", None),
    ],
)
def test_phone_spellings(cc: str, area: str, number: str, expected: str | None) -> None:
    assert compose_phone(cc, area, number) == expected


def test_phone_spellings_validate_to_the_same_e164() -> None:
    numbers = set()
    for cc, area, number in [
        ("0049", "0221", "1234567"),
        ("", "", "0221/1234567"),
        ("", "", "+49 221 123 45 67"),
        ("", "0221", "123 45 67"),
        ("+49", "(0)221", "1234567"),
    ]:
        row = _row(country_code=cc, area_code=area, phone=number)
        item = prepare_row(row)
        assert item.data is not None
        numbers.add(item.data.phones[0].number)
    assert numbers == {"+492211234567"}


def test_invalid_phone_becomes_note_only() -> None:
    item = prepare_row(_row(phone="12"))
    assert item.data is not None
    assert item.data.phones == []
    assert item.notes == ["Telefon '012' ungültig, nur als Notiz übernommen"]
    assert item.data.notes == "Telefon laut Altsystem: 012"


# --- e-mails ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("max@example.org", ["max@example.org"]),
        ("  Max@Example.ORG ", ["max@example.org"]),
        ("mailto:max@example.org", ["max@example.org"]),
        ("Max Muster <max@example.org>", ["max@example.org"]),
        ("max@example.org; erika@example.org", ["max@example.org", "erika@example.org"]),
        ("max@example.org, max@example.org", ["max@example.org"]),
        ("max@example.org.", ["max@example.org"]),
        ("keine", []),
        ("", []),
        (None, []),
    ],
)
def test_email_spellings(raw: str | None, expected: list[str]) -> None:
    assert split_emails(raw) == expected


def test_emails_in_prepared_contact() -> None:
    item = prepare_row(_row(email="Max Muster <Max@Example.org>; zweite@example.org"))
    assert item.data is not None
    assert [(e.email, e.is_primary) for e in item.data.emails] == [
        ("max@example.org", True),
        ("zweite@example.org", False),
    ]
    assert item.notes == ["2 E-Mail-Adressen übernommen, die erste als Hauptadresse"]
    bad = prepare_row(_row(email="keine mail"))
    assert bad.data is not None
    assert bad.data.emails == []
    assert bad.notes == ["E-Mail 'keine mail' ungültig, nur als Notiz übernommen"]
    assert bad.data.notes == "E-Mail laut Altsystem: keine mail"


# --- names -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "salutation_line", "first", "last", "guessed"),
    [
        ("Müller, Jörg", None, "Jörg", "Müller", False),
        ("Müller,Jörg", None, "Jörg", "Müller", False),
        (" Müller , Jörg ", None, "Jörg", "Müller", False),
        ("Müller, Jörg,", None, "Jörg", "Müller", False),
        ("Jörg Müller", "Sehr geehrter Herr Müller", "Jörg", "Müller", False),
        ("Jörg Müller", "Sehr geehrter Herr Jörg Müller,", "Jörg", "Müller", False),
        ("Jörg Müller", None, "Jörg", "Müller", True),
        ("Anna Maria von Berg", None, "Anna Maria von", "Berg", True),
        (
            "Joachims Christina Maria",
            "Sehr geehrte Frau Joachims",
            "Christina Maria",
            "Joachims",
            False,
        ),
        ("Müller", None, None, "Müller", False),
        ("Müller, Dr. Jörg", None, "Jörg", "Müller", False),
    ],
)
def test_person_name_forms(
    name: str, salutation_line: str | None, first: str | None, last: str, guessed: bool
) -> None:
    got_first, got_last, note = split_person_name(name, salutation_line)
    assert (got_first, got_last) == (first, last)
    assert (note is not None) is guessed


def test_titles_are_split_off() -> None:
    assert split_title("Dr. Jörg Müller") == ("Dr.", "Jörg Müller")
    assert split_title("Prof. Dr. med. Ute Kern") == ("Prof. Dr. med.", "Ute Kern")
    assert split_title("Dipl.-Ing. Hans Berg") == ("Dipl.-Ing.", "Hans Berg")
    assert split_title("Drusilla Berg") == (None, "Drusilla Berg")
    item = prepare_row(_row(name="Dr. Müller, Jörg"))
    assert item.data is not None
    # A title in front of "Nachname, Vorname" is kept in the title field, not the name.
    assert (item.data.title, item.data.first_name, item.data.last_name) == ("Dr.", "Jörg", "Müller")


@pytest.mark.parametrize(
    ("name", "form"),
    [
        ("Lotta Center GmbH", "GmbH"),
        ("Bau und Wohnen GmbH & Co. KG", "GmbH & Co. KG"),
        ("Müller Holding AG", "AG"),
        ("Startup UG (haftungsbeschränkt)", "UG (haftungsbeschränkt)"),
        ("Musikschule Nord e.V.", "e.V."),
        ("Handel Schmitz e. K.", "e. K."),
        ("Wohnungsgenossenschaft eG", "eG"),
        ("Berg und Tal GbR", "GbR"),
        ("Sparkasse Köln Bonn", None),
    ],
)
def test_company_names_with_legal_form(name: str, form: str | None) -> None:
    assert is_company(name, ContactRoleCode.SONSTIGES)
    assert legal_form(name) == form
    item = prepare_row(_row(name=name))
    assert item.data is not None
    assert item.data.kind is ContactKind.COMPANY
    assert item.data.company_name == name
    assert item.data.legal_form == form


def test_person_is_not_company() -> None:
    for name in ("Jörg Müller", "Müller, Jörg", "Anna Maria von Berg", "Dr. Ute Kern"):
        assert not is_company(name, MIETER)


# --- addresses -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("Musterstraße 2", ("Musterstraße", "2", None)),
        ("Musterstraße 2a", ("Musterstraße", "2a", None)),
        ("Musterstraße 2 a", ("Musterstraße", "2 a", None)),
        ("Musterstraße 2A", ("Musterstraße", "2A", None)),
        ("Am Markt 3-5", ("Am Markt", "3-5", None)),
        ("Am Markt 3 - 5", ("Am Markt", "3 - 5", None)),
        ("Am Markt 1/2", ("Am Markt", "1/2", None)),
        ("Hauptstr. 12a-14", ("Hauptstr.", "12a-14", None)),
        ("Straße des 17. Juni 5", ("Straße des 17. Juni", "5", None)),
        ("Musterstraße 2a, Whg. 3", ("Musterstraße", "2a", "Whg. 3")),
        ("Musterstraße  2   a", ("Musterstraße", "2 a", None)),
        ("Marktplatz", ("Marktplatz", None, None)),
        (
            "Venner Straße 16 / Annakirchenstraße 24",
            ("Venner Straße 16 / Annakirchenstraße 24", None, None),
        ),
        ("", (None, None, None)),
        (None, (None, None, None)),
    ],
)
def test_addresses_with_house_number_additions(
    address: str | None, expected: tuple[str | None, str | None, str | None]
) -> None:
    assert split_address(address) == expected


def test_separate_house_number_column_is_used() -> None:
    text = "id;Name;Straße;Hausnummer;PLZ;Ort\n1;Muster, Max;Musterstraße;2 a;50667;Köln\n"
    item = prepare(parse_kontakte(text, MIETER, "m.csv"))[0]
    assert item.data is not None
    address = item.data.addresses[0]
    assert (address.street, address.house_number, address.postal_code, address.city) == (
        "Musterstraße",
        "2 a",
        "50667",
        "Köln",
    )


def test_country_codes_and_names() -> None:
    assert prepare_row(_row(country="Niederlande")).data.addresses[0].country == "NL"  # type: ignore[union-attr]
    assert prepare_row(_row(country="nl")).data.addresses[0].country == "NL"  # type: ignore[union-attr]
    item = prepare_row(_row(country="Atlantis"))
    assert item.data is not None
    assert item.data.addresses[0].country == "DE"
    assert item.notes == ["Land 'Atlantis' nicht zugeordnet, DE angenommen"]


# --- IBAN: proposal only ---------------------------------------------------------------------


def test_iban_column_is_reported_masked_and_never_stored() -> None:
    text = _csv([*HEADERS, "IBAN"], [[*ROWS[0], "DE02 1203 0000 0000 2020 51"]])
    item = prepare(parse_kontakte(text, MIETER, "mieter.csv"))[0]
    assert item.data is not None
    assert item.data.bank_accounts is None
    assert item.notes == [
        "IBAN laut Altsystem DE02 **** **** 2051: nur Vorschlag, nicht übernommen. "
        "Bankverbindung manuell erfassen und im Vier-Augen-Verfahren freigeben."
    ]
    assert item.data.notes is not None
    assert "DE02 **** **** 2051" in item.data.notes
    assert "120300000000202051" not in item.data.notes
    assert "DE02120300000000202051" not in item.data.model_dump_json()


def test_invalid_iban_is_reported_without_value() -> None:
    text = _csv([*HEADERS, "IBAN"], [[*ROWS[0], "DE00 1234"]])
    item = prepare(parse_kontakte(text, MIETER, "mieter.csv"))[0]
    assert item.data is not None
    assert item.data.bank_accounts is None
    assert item.notes == [
        "IBAN laut Altsystem ungültig (IBAN hat kein gültiges Format.), nicht übernommen"
    ]
    assert "DE00" not in item.data.model_dump_json()


# --- helpers ---------------------------------------------------------------------------------


def _row(**overrides: str | None):  # type: ignore[no-untyped-def]
    from mhvp.imports.kontakte import ContactRow

    base: dict[str, object] = {
        "external_id": "1",
        "name": "Muster, Max",
        "salutation_line": None,
        "username": None,
        "address": "Musterstraße 2",
        "house_number": None,
        "city": "Köln",
        "postal_code": "50667",
        "state": None,
        "country": None,
        "country_code": None,
        "area_code": None,
        "phone": None,
        "email": None,
        "role": MIETER,
        "source_file": "mieter.csv",
        "line": 2,
    }
    base.update(overrides)
    return ContactRow(**base)  # type: ignore[arg-type]
