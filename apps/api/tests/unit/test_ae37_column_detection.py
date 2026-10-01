"""AE37 (Q08-01, M8): header heuristic and validation report on invented headers.

The headers are invented for the test and make no statement about real Immoware24 exports
(13.1). Expected values by hand (rule 0.1.8):

* "Objekt-Nr." becomes "objektnummer" (abbreviation "nr"), equal to the label "Objektnummer":
  95 percent, basis label. "Einheit" is part of "Einheitennummer": 70 percent (check). "MEA"
  equals the field name ``mea``: 90 percent (the general term would give 85). "Bemerkung"
  matches nothing.
* Header row: title line and empty line are skipped (fewer than two cells); the header row
  scores 0.35 + 0.25 + 0.10 + 0.20 + 0.10 = 100; the first data row (one number of four cells,
  no term) 0.2625 + 0.25 + 0.10 + 0.10 = 71; the last row without data below 61.
"""

from mhvp.imports import column_detection as cd
from mhvp.imports.models import ReportType

UNIT_HEADERS = ["Objekt-Nr.", "Einheit", "Art", "Wohnfläche m²", "MEA", "Bemerkung"]
UNIT_ROWS = [
    {
        "Objekt-Nr.": "001",
        "Einheit": "01",
        "Art": "Wohnung",
        "Wohnfläche m²": "71,35",
        "MEA": "125",
    },
    {
        "Objekt-Nr.": "001",
        "Einheit": "02",
        "Art": "Wohnung",
        "Wohnfläche m²": "64,10",
        "MEA": "110",
    },
]


def _field(result: dict, name: str) -> dict:
    return next(f for f in result["fields"] if f["name"] == name)


def test_keys_normalise_spelling_and_abbreviations() -> None:
    assert cd.compare_key("Objekt-Nr.") == "objektnummer"
    assert cd.compare_key("Wohnfläche m²") == "wohnflaechem2"
    assert cd.compare_key("Straße") == "strasse"
    assert cd.header_key(" E-Mail ") == "email"


def test_proposal_by_label_part_and_term() -> None:
    result = cd.propose_columns(ReportType.UNITS, UNIT_HEADERS, UNIT_ROWS)
    assert result["columns"] == {
        "property_number": "Objekt-Nr.",
        "number": "Einheit",
        "unit_type": "Art",
        "living_area_sqm": "Wohnfläche m²",
        "mea": "MEA",
    }
    prop = _field(result, "property_number")
    assert (prop["score"], prop["basis"], prop["status"]) == (95, "label", "sure")
    number = _field(result, "number")
    assert (number["score"], number["basis"], number["status"]) == (70, "part", "check")
    assert number["alternatives"] == [{"header": "Objekt-Nr.", "score": 70, "basis": "part"}]
    mea = _field(result, "mea")
    assert (mea["score"], mea["basis"], mea["status"]) == (90, "name", "sure")
    assert _field(result, "building")["status"] == "none"
    assert result["unassigned_headers"] == ["Bemerkung"]
    assert result["missing_required"] == []
    assert result["stored_used"] == 0


def test_stored_assignment_wins_and_ignored_header() -> None:
    headers = ["VE", "Objekt-Nr.", "Art", "Bemerkung"]
    stored = {"ve": "number", "bemerkung": None}
    result = cd.propose_columns(ReportType.UNITS, headers, [], stored)
    number = _field(result, "number")
    assert (number["header"], number["score"], number["status"]) == ("VE", 100, "stored")
    assert result["ignored_headers"] == ["Bemerkung"]
    assert "Bemerkung" not in result["unassigned_headers"]
    assert result["stored_used"] == 1


def test_stored_assignment_of_unknown_field_is_ignored() -> None:
    result = cd.propose_columns(ReportType.UNITS, ["Art"], [], {"art": "no_such_field"})
    assert _field(result, "unit_type")["status"] == "sure"


def test_type_check_halves_score_of_unreadable_samples() -> None:
    rows = [{"Wohnfläche": "groß"}, {"Wohnfläche": "klein"}]
    result = cd.propose_columns(ReportType.UNITS, ["Wohnfläche"], rows)
    living = _field(result, "living_area_sqm")
    assert living["status"] == "none"
    assert living["alternatives"] == [{"header": "Wohnfläche", "score": 42, "basis": "term"}]
    readable = cd.propose_columns(ReportType.UNITS, ["Wohnfläche"], [{"Wohnfläche": "71,35"}])
    assert _field(readable, "living_area_sqm")["score"] == 85


def test_each_header_is_used_once() -> None:
    result = cd.propose_columns(ReportType.UNITS, ["Objekt-Nr."], [])
    assert result["columns"] == {"property_number": "Objekt-Nr."}
    assert result["missing_required"] == ["number", "unit_type"]


def test_header_row_detection_skips_title_lines() -> None:
    rows = [
        ["Objektliste Stand 30.09.2026", None, None, None],
        [None, None, None, None],
        ["Objektnummer", "Bezeichnung", "Verwaltungsart", "Ort"],
        ["001", "Haus A", "WEG", "Bernau"],
        ["002", "Haus B", "Miete", "Berlin"],
    ]
    candidates = cd.detect_header_row(rows, ReportType.PROPERTIES)
    assert [(c.row, c.score) for c in candidates] == [(3, 100), (4, 71), (5, 61)]
    assert candidates[0].matched_terms == ["Objektnummer", "Bezeichnung", "Verwaltungsart", "Ort"]
    assert "Datenzeile darunter" in candidates[0].reason


def test_header_row_detection_reports_duplicates_and_stored_terms() -> None:
    rows = [["VE", "VE", "Kennung"], ["01", "02", "x"]]
    candidates = cd.detect_header_row(rows, ReportType.UNITS, {"kennung": "number"})
    assert candidates[0].duplicates == ["VE"]
    assert candidates[0].matched_terms == ["Kennung"]
    assert cd.detect_header_row([["nur eine Zelle"]], ReportType.UNITS) == []


PROPERTY_ROWS = [
    (2, {"Nr": "001", "Name": "Haus A", "Art": "WEG"}),
    (3, {"Nr": "12", "Name": "", "Art": "Miete"}),
]


def test_check_report_counts_required_columns_and_samples() -> None:
    columns = {"number": "Nr", "name": "Name", "management_type": "Art"}
    report = cd.check_report(
        ReportType.PROPERTIES,
        ["Nr", "Name", "Art", "Ort"],
        PROPERTY_ROWS,
        columns,
        {"management_type": {"WEG": "hoa"}},
        sample_size=1,
    )
    assert (report["rows"], report["valid"], report["invalid"]) == (2, 1, 1)
    status = {r["name"]: r["status"] for r in report["required"]}
    assert status == {"number": "ok", "name": "partly_empty", "management_type": "ok"}
    stats = {f["name"]: (f["filled"], f["empty"], f["errors"]) for f in report["fields"]}
    assert stats == {"number": (2, 0, 0), "name": (1, 1, 1), "management_type": (2, 0, 1)}
    assert report["unassigned_headers"] == ["Ort"]
    assert report["sample_rows"][0]["values"] == {
        "number": "001",
        "name": "Haus A",
        "management_type": "hoa",
    }
    assert report["error_rows"][0]["row_number"] == 3
    assert "Bezeichnung: fehlt" in report["error_rows"][0]["errors"]
    assert report["ready"] is True


def test_check_report_blocks_missing_and_foreign_columns() -> None:
    report = cd.check_report(
        ReportType.PROPERTIES,
        ["Nr", "Name", "Art"],
        PROPERTY_ROWS,
        {"number": "Nr", "management_type": "Art", "city": "Stadt"},
        {},
    )
    status = {r["name"]: r["status"] for r in report["required"]}
    assert status["name"] == "missing"
    assert report["not_in_file"] == ["Stadt"]
    assert report["ready"] is False


def test_check_report_empty_required_column_blocks() -> None:
    rows = [(2, {"Nr": "001", "Name": "", "Art": "hoa"})]
    report = cd.check_report(
        ReportType.PROPERTIES,
        ["Nr", "Name", "Art"],
        rows,
        {"number": "Nr", "name": "Name", "management_type": "Art", "street": "Name"},
        {},
    )
    status = {r["name"]: r["status"] for r in report["required"]}
    assert status["name"] == "empty"
    assert report["assigned_twice"] == ["Name"]
    assert report["ready"] is False


def test_staged_only_report_has_no_fields() -> None:
    report = cd.check_report(ReportType.JOURNAL, ["Konto"], [(2, {"Konto": "1000"})], {}, {})
    assert report["staged_only"] is True
    assert report["ready"] is True
    assert report["required"] == []
