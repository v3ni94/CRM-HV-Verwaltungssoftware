"""M35 Stufe 4 Listengenerierung: CSV shape of the Anforderungsliste and Dokumentenübersicht
(semicolon, CRLF, UTF-8 BOM, quoting of separators in values), without a database."""

from typing import Any

from mhvp.objektakte import lists


def test_missing_documents_csv_one_row_per_missing_class() -> None:
    entries: list[dict[str, Any]] = [
        {
            "property_number": "801",
            "property_name": "Haus; Listenweg",
            "management_type": "hoa",
            "missing": [{"code": "prot", "name": "Protokoll"}, {"code": "wp", "name": "Plan"}],
        },
        {
            "property_number": "802",
            "property_name": "Voll",
            "management_type": "hoa",
            "missing": [],
        },
    ]
    text = lists.missing_documents_csv(entries)
    assert text.startswith("﻿")
    lines = text.lstrip("﻿").split("\r\n")
    assert lines[0] == "Objektnummer;Objekt;Verwaltungsart;Kategorie;Fehlende Unterlage"
    assert lines[1] == '801;"Haus; Listenweg";hoa;prot;Protokoll'
    assert lines[2] == '801;"Haus; Listenweg";hoa;wp;Plan'
    assert lines[3] == ""  # complete property yields no row


def test_documents_csv_flags_duplicates_and_uncategorised() -> None:
    overview = {
        "property_number": "801",
        "property_name": "Haus",
        "groups": [
            {
                "code": "wp",
                "name": "Wirtschaftsplan",
                "documents": [
                    {
                        "title": "WP 2027",
                        "filename": "wp.pdf",
                        "mime_type": "application/pdf",
                        "created_at": "2026-09-26T10:00:00+00:00",
                        "source_system": "objektakte",
                        "duplicate": True,
                    }
                ],
            },
            {
                "code": lists.UNCATEGORISED_CODE,
                "name": lists.UNCATEGORISED_NAME,
                "documents": [
                    {
                        "title": "Unklar",
                        "filename": "u.pdf",
                        "mime_type": "application/pdf",
                        "created_at": "2026-09-26T11:00:00+00:00",
                        "source_system": None,
                        "duplicate": False,
                    }
                ],
            },
        ],
    }
    lines = lists.documents_csv(overview).lstrip("﻿").split("\r\n")
    assert lines[0] == ";".join(lists.DOCUMENTS_HEADER)
    assert lines[1] == (
        "801;Haus;wp;Wirtschaftsplan;WP 2027;wp.pdf;application/pdf;"
        "2026-09-26T10:00:00+00:00;objektakte;ja"
    )
    assert lines[2] == (
        "801;Haus;;Ohne Kategorie;Unklar;u.pdf;application/pdf;2026-09-26T11:00:00+00:00;;nein"
    )


def test_csv_neutralises_formula_prefixes() -> None:
    """Sicherheitsreview 26.09.2026, Befund 6: titles starting like a formula are exported as
    text (leading apostrophe), numbers and ordinary titles stay as they are."""
    rows_in = [(1, "=1+1", 2), (2, "@SUM(A1)", -3), (3, "Plan", 0)]
    text = lists.to_csv(("Nr", "Titel", "Anzahl"), rows_in)
    rows = text.lstrip("\ufeff").split("\r\n")
    assert rows[1] == "1;'=1+1;2"
    assert rows[2] == "2;'@SUM(A1);-3"
    assert rows[3] == "3;Plan;0"
