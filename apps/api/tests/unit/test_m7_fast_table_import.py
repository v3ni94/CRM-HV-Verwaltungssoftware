"""M7-06 fast table import: deterministic column mapping and row processing (unit, no DB, no
provider). Synthetic data only, no real names from uploads."""

import io

from openpyxl import Workbook

from mhvp.ai import table_mapper


def test_parse_name_person_with_salutation_and_title() -> None:
    parsed = table_mapper.parse_name("Herr Dr. Hans Müller")
    assert parsed is not None
    assert parsed.kind == "person"
    assert parsed.salutation == "Herr"
    assert parsed.title == "Dr."
    assert parsed.first_name == "Hans"
    assert parsed.last_name == "Müller"


def test_parse_name_company() -> None:
    parsed = table_mapper.parse_name("Müller GmbH")
    assert parsed is not None
    assert parsed.kind == "company"
    assert parsed.company_name == "Müller GmbH"


def test_parse_name_two_persons_is_residual() -> None:
    assert table_mapper.parse_name("Hans und Erika Müller") is None


def test_parse_name_empty_is_residual() -> None:
    assert table_mapper.parse_name("") is None
    assert table_mapper.parse_name("Herr") is None  # salutation only, no actual name


def test_parse_name_last_name_only() -> None:
    parsed = table_mapper.parse_name("Müller")
    assert parsed is not None
    assert parsed.first_name is None
    assert parsed.last_name == "Müller"


def test_split_street_with_house_number_and_letter_suffix() -> None:
    assert table_mapper.split_street("Hauptstr. 12a") == ("Hauptstr.", "12a")
    assert table_mapper.split_street("Musterallee") == ("Musterallee", None)


def test_split_postal_city() -> None:
    assert table_mapper.split_postal_city("40789 Monheim am Rhein") == (
        "40789",
        "Monheim am Rhein",
    )
    assert table_mapper.split_postal_city("Monheim am Rhein") == (None, "Monheim am Rhein")


def test_split_list_phones_and_emails() -> None:
    assert table_mapper.split_list("0171 111; 0171 222") == ["0171 111", "0171 222"]
    assert table_mapper.split_list("a@example.org, b@example.org") == [
        "a@example.org",
        "b@example.org",
    ]


def _csv(rows: list[list[str]]) -> bytes:
    return "\n".join(";".join(r) for r in rows).encode("cp1252")


def test_load_csv_decodes_cp1252_umlauts() -> None:
    data = _csv(
        [
            ["Name", "Straße", "Ort"],
            ["Müller", "Königsallee 1", "Düsseldorf"],
        ]
    )
    header, rows, raw_chars = table_mapper.load_csv(data)
    assert header == ["Name", "Straße", "Ort"]
    assert rows == [["Müller", "Königsallee 1", "Düsseldorf"]]
    assert raw_chars > 0


def test_load_csv_skips_empty_rows_and_pads_short_rows() -> None:
    data = _csv(
        [
            ["Name", "Straße", "Ort"],
            ["Müller", "Hauptstr. 1", "Köln"],
            [],
            ["Schmidt", "X 1"],
        ]
    )
    header, rows, _ = table_mapper.load_csv(data)
    assert header == ["Name", "Straße", "Ort"]
    assert rows == [["Müller", "Hauptstr. 1", "Köln"], ["Schmidt", "X 1", ""]]


def _xlsx(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_load_xlsx_reads_header_and_rows() -> None:
    data = _xlsx([["Name", "Vorname"], ["Müller", "Hans"], [None, None]])
    header, rows, _ = table_mapper.load_xlsx(data)
    assert header == ["Name", "Vorname"]
    assert rows == [["Müller", "Hans"]]


def test_apply_mapping_splits_and_flags_empty_cells_as_incomplete_not_residual() -> None:
    table = table_mapper.TableData(
        filename="kontakte.csv",
        header=["Name", "Vorname", "Adresse", "PLZ Ort", "Telefon", "E-Mail"],
        rows=[["Muster", "Max", "Hauptstr. 12a", "40789 Monheim am Rhein", "0171 1", "a@x.org"]],
        raw_chars=100,
    )
    mapping = {
        "Name": "last_name",
        "Vorname": "first_name",
        "Adresse": "address_full",
        "PLZ Ort": "postal_city",
        "Telefon": "phone",
        "E-Mail": "email",
    }
    mapped = table_mapper.apply_mapping(table, mapping, default_role="owner")
    assert mapped.residual == []
    assert len(mapped.contacts) == 1
    contact = mapped.contacts[0]
    assert contact["last_name"] == "Muster"
    assert contact["first_name"] == "Max"
    assert contact["street"] == "Hauptstr."
    assert contact["house_number"] == "12a"
    assert contact["postal_code"] == "40789"
    assert contact["city"] == "Monheim am Rhein"
    assert contact["phones"] == ["0171 1"]
    assert contact["emails"] == ["a@x.org"]
    assert contact["role"] == "owner"
    assert contact["source_row"] == 2


def test_apply_mapping_sends_ambiguous_and_missing_name_rows_to_residual() -> None:
    table = table_mapper.TableData(
        filename="kontakte.csv",
        header=["Name"],
        rows=[["Hans und Erika Müller"], [""], ["Schmidt GmbH"]],
        raw_chars=10,
    )
    mapped = table_mapper.apply_mapping(table, {"Name": "name_full"}, default_role=None)
    assert len(mapped.residual) == 2  # ambiguous + missing name
    assert [r["row"] for r in mapped.residual] == [2, 3]
    assert len(mapped.contacts) == 1
    assert mapped.contacts[0]["kind"] == "company"
    assert mapped.contacts[0]["company_name"] == "Schmidt GmbH"


def test_residual_table_text_keeps_header_and_row_numbers() -> None:
    table = table_mapper.TableData(
        filename="kontakte.csv", header=["Name", "Ort"], rows=[], raw_chars=0
    )
    residual = [{"row": 5, "cells": {"Name": "Hans und Erika Müller", "Ort": "Köln"}}]
    text = table_mapper.residual_table_text(table, residual)
    assert text.splitlines() == [
        "Zeile 1: Name | Ort",
        "Zeile 5: Hans und Erika Müller | Köln",
    ]
