"""Full import assistant (M8-01, M8-02, V9): pre-check of every export type, duplicate and
missing field detection, checksum, synthetic dataset shape and PDF draft rendering."""

from __future__ import annotations

import hashlib

import pytest

from mhvp.core.problems import ProblemError
from mhvp.imports import vollimport
from mhvp.imports.objektdaten import parse_objektdaten
from mhvp.imports.vollimport import EXPORT_KINDS, Upload, precheck
from tests.synthetic_immoware import KONTAKTE_HEADER, OBJEKTDATEN_HEADER, generate


def _up(kind: str, text: str, name: str = "export.csv", encoding: str = "utf-8") -> Upload:
    return Upload(name, kind, text.encode(encoding))


def test_export_kinds_cover_every_repo_export() -> None:
    assert set(EXPORT_KINDS) == {
        "objektdaten",
        "eigentuemer",
        "mieter",
        "sonstige",
        "bank",
        "dienstleister",
        "adressen",
        "bankumsaetze",
        "salden",
        "mietvertraege",
        "eigentuemervertraege",
    }
    assert EXPORT_KINDS["mietvertraege"].required == (
        "Objektnummer",
        "Einheitennummer",
        "Kontakt-ID Mieter",
        "Mietbeginn",
    )
    assert EXPORT_KINDS["eigentuemervertraege"].key_columns == (
        "Objektnummer",
        "Einheitennummer",
        "Beginn",
    )
    assert EXPORT_KINDS["objektdaten"].required == (
        "Objekt-Nummer",
        "Objekt",
        "Verwaltungsart",
        "VE-Nummer",
    )
    assert EXPORT_KINDS["mieter"].required == ("id", "Name")


def test_precheck_objektdaten_ok_with_checksum_and_counts() -> None:
    text = (
        OBJEKTDATEN_HEADER
        + '\n359;"Brunnenstraße 145";WEG-Verwaltung;Haus;10001;01;EG;"Sakwa, Agata";230,00;;\n'
    )
    check = precheck(_up("objektdaten", text))
    assert check.ok is True
    assert check.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert check.encoding == "UTF-8"
    assert check.delimiter == "Semikolon"
    assert check.row_count == 1
    assert check.missing_required == []
    assert check.unknown_headers == []
    assert check.duplicate_keys == []
    assert check.as_dict()["zeilen"] == 1


def test_precheck_reports_encoding_delimiter_and_unknown_columns() -> None:
    text = "id,Name,Extra\n1,Müller,x\n"
    check = precheck(_up("mieter", text, encoding="cp1252"))
    assert check.ok is True
    assert check.encoding == "Windows-1252"
    assert check.delimiter == "Komma"
    assert check.unknown_headers == ["Extra"]
    assert "Briefanrede" in check.missing_optional


def test_precheck_finds_missing_required_column_and_field_and_duplicates() -> None:
    text = "id;Briefanrede\n1;x\n"
    check = precheck(_up("eigentuemer", text))
    assert check.ok is False
    assert check.missing_required == ["Name"]
    text = "id;Name\n1;A\n;B\n1;C\n"
    check = precheck(_up("eigentuemer", text))
    assert check.ok is False
    assert check.missing_fields == [{"zeile": 3, "feld": "id"}]
    assert check.duplicate_keys == [{"schluessel": "1", "zeilen": [2, 4]}]


def test_precheck_objektdaten_duplicate_only_when_content_differs() -> None:
    same = OBJEKTDATEN_HEADER + "\n1;A;WEG;H;01;WE 1;EG;X;1,00;;\n1;A;WEG;H;01;WE 1;EG;X;1,00;;\n"
    assert precheck(_up("objektdaten", same)).duplicate_keys == []
    differs = (
        OBJEKTDATEN_HEADER + "\n1;A;WEG;H;01;WE 1;EG;X;1,00;;\n1;A;WEG;H;01;WE 2;OG;X;1,00;;\n"
    )
    check = precheck(_up("objektdaten", differs))
    assert check.duplicate_keys == [{"schluessel": "1 / 01", "zeilen": [2, 3]}]
    assert check.ok is False


def test_precheck_empty_unknown_kind_and_no_rows() -> None:
    assert precheck(_up("salden", "")).ok is False
    assert precheck(_up("bankumsaetze", "Objekt;IBAN;Betrag\n")).ok is False
    with pytest.raises(ProblemError) as info:
        precheck(_up("unbekannt", "a;b\n1;2\n"))
    assert "unbekannt" in (info.value.detail or "")


def test_precheck_adressen_needs_an_address_column() -> None:
    assert precheck(_up("adressen", "Objektnummer;Sonstiges\n081;x\n")).ok is False
    assert (
        precheck(_up("adressen", "Objektnummer;Straße;PLZ;Ort\n081;Weg 1;12345;Ort\n")).ok is True
    )


def test_precheck_bank_and_salden_headers() -> None:
    assert precheck(
        _up("bankumsaetze", "Objekt;IBAN;Datum;Betrag;Saldo\n081;DE1;01.01.2026;1,00;2,00\n")
    ).ok
    assert precheck(_up("salden", "Objekt-Nummer;VE-Nummer;Name;Saldo\n081;01;A;12,50\n")).ok


def test_synthetic_dataset_has_67_objects_and_869_units() -> None:
    data = generate()
    parsed = parse_objektdaten(data.objektdaten)
    assert len(parsed.rows) == 67
    assert sum(len(r.units) for r in parsed.rows) == 869
    assert parsed.notes == []
    for kind, text in (
        ("objektdaten", data.objektdaten),
        ("eigentuemer", data.eigentuemer),
        ("mieter", data.mieter),
        ("adressen", data.adressen),
        ("salden", data.salden),
        ("bankumsaetze", data.bankumsaetze),
        ("mietvertraege", data.mietvertraege),
        ("eigentuemervertraege", data.eigentuemervertraege),
    ):
        check = precheck(_up(kind, text))
        assert check.ok, (kind, check.as_dict())
    assert precheck(_up("mietvertraege", data.mietvertraege)).row_count == data.tenancy_rows
    assert data.ownership_rows == len(data.owner_ids) == 605
    assert data.landlord_rows == 22
    assert data.tenancy_rows == 571
    assert data.balance_rows == data.tenancy_rows + data.ownership_rows - data.landlord_rows
    assert precheck(_up("objektdaten", data.objektdaten)).row_count == 869
    assert precheck(_up("eigentuemer", data.eigentuemer)).row_count == len(data.owner_ids)
    assert data.eigentuemer.startswith(KONTAKTE_HEADER)


def test_pdf_draft_renders() -> None:
    run = {
        "mode": "apply",
        "stichtag": "2026-12-31",
        "differenzen": 1,
        "dateien": [
            {"datei": "o.csv", "art": "objektdaten", "sha256": "ab" * 32, "bytes": 10, "zeilen": 2}
        ],
        "abgleich": [
            {
                "entitaet": "objekte",
                "soll": 2,
                "ist": 1,
                "uebereinstimmend": 1,
                "fehlend": [{"schluessel": "101", "grund": "nicht angelegt"}],
                "doppelt": [],
                "abweichend": [
                    {"schluessel": "100", "felder": [{"feld": "name", "soll": "A", "ist": "B"}]}
                ],
                "zusaetzlich": [],
                "hinweise": [],
            },
        ],
        "eroeffnungssalden": {"summe": "1234.50", "anzahl": {"vorschlag": 1}},
    }
    pdf = vollimport.report_pdf(run, "Mandant <Test>")
    assert pdf.startswith(b"%PDF")


def test_parse_contract_rows_reports_unreadable_values() -> None:
    from mhvp.contracts.models import ContractKind
    from mhvp.imports.csvtext import read_table
    from mhvp.imports.vollimport_vertraege import parse_contracts

    text = (
        "Vertragsnummer;Objektnummer;Einheitennummer;Kontakt-ID Mieter;Mietbeginn;Mietende;Miete\n"
        "MV-1;081;01;4711;01.01.2025;;650,00\n"
        ";081;02;4712;31.02.2025;;abc\n"
        "MV-3;081;03;4713;01.06.2025;01.01.2025;-5,00\n"
    )
    parsed = parse_contracts(read_table(text, "m.csv"), ContractKind.TENANCY)
    ok, bad_date, bad_order = parsed.rows
    assert (ok.contract_no, ok.unit_key, ok.contact_id, str(ok.amount)) == (
        "MV-1",
        "081/01",
        "4711",
        "650.00",
    )
    assert ok.start is not None
    assert ok.start.isoformat() == "2025-01-01"
    assert ok.problems == []
    assert bad_date.contract_no is None
    assert any("Mietbeginn" in p for p in bad_date.problems)
    assert any(p == "Miete 'abc' nicht lesbar" for p in bad_date.problems)
    assert "Ende liegt vor dem Beginn" in bad_order.problems
    assert any("negativ" in p for p in bad_order.problems)
    eig = parse_contracts(
        read_table(
            "Objektnummer;Einheitennummer;Kontakt-ID Eigentümer;Beginn;Hausgeld;SEV\n"
            "081;01;4711;01.01.2020;250,00;ja\n",
            "e.csv",
        ),
        ContractKind.OWNERSHIP,
    )
    assert eig.rows[0].sev is True
    assert eig.rows[0].title_transfer is None
    assert "Eigentumsübergang" in eig.notes[0]


def test_precheck_contract_lists_need_contact_and_start() -> None:
    check = precheck(
        _up("mietvertraege", "Objektnummer;Einheitennummer;Mietbeginn\n081;01;01.01.2025\n")
    )
    assert check.missing_required == ["Kontakt-ID Mieter"]
    check = precheck(
        _up(
            "eigentuemervertraege",
            "Objektnummer;Einheitennummer;Kontakt-ID Eigentümer;Beginn\n"
            "081;01;1;01.01.2020\n081;01;2;01.01.2020\n",
        )
    )
    assert check.duplicate_keys == [{"schluessel": "081 / 01 / 01.01.2020", "zeilen": [2, 3]}]
