"""AE30 (AA14-01): form builder with 20 element types, final. One check rule per type (valid and
invalid examples), type register, preview dry run. Pure helpers, no database."""

import pytest

from mhvp.core.problems import ProblemError
from mhvp.portal import forms
from mhvp.portal.provider_info import average_rating

EXPECTED_TYPES = {
    "text",
    "textarea",
    "number",
    "date",
    "time",
    "select",
    "radio",
    "multiselect",
    "checkbox",
    "email",
    "phone",
    "file",
    "address",
    "location",
    "signature",
    "consent",
    "amount",
    "heading",
    "info",
    "divider",
}
OPTIONS = ["a", "b"]
FILE_ID = "0192f0d0-0000-7000-8000-000000000001"

# type: (valid value, normalised value, invalid values)
CASES: dict[str, tuple[object, object, list[object]]] = {
    "text": ("Heizung im Flur", "Heizung im Flur", ["zwei\nZeilen", "x" * 501]),
    "textarea": ("Zeile 1\nZeile 2", "Zeile 1\nZeile 2", ["x" * 4001]),
    "number": ("3,5", "3,5", ["abc", "1,23456", "1" * 13]),
    "date": ("2026-10-01", "2026-10-01", ["01.10.2026", "2026-02-30"]),
    "time": ("08:15", "08:15", ["25:00", "8:5"]),
    "select": ("a", "a", ["c"]),
    "radio": ("b", "b", ["zzz"]),
    "multiselect": (["a", "b", "a"], ["a", "b"], [["c"], "a"]),
    "checkbox": (True, "true", ["vielleicht"]),
    "email": ("a@example.org", "a@example.org", ["kein-mail", "a@b"]),
    "phone": ("+49 2103 123456", "+49 2103 123456", ["abc", "12"]),
    "file": ([FILE_ID], [FILE_ID], ["nicht-als-liste", ["keine-uuid"], [FILE_ID] * 11]),
    "address": (
        "Weg 1\n12345 Ort",
        "Weg 1\n12345 Ort",
        ["Weg 1", "Weg\nOrt", "a\nb\nc\nd\ne\nf 1"],
    ),
    "location": ("Keller", "Keller", ["K", "Keller\nTür", "x" * 301]),
    "signature": ("  Max   Muster ", "Max Muster", ["M", "12", "x" * 121]),
    "consent": ("true", "true", ["vielleicht"]),
    "amount": ("1234,5", "1234.5", ["12,345", "-5", "abc"]),
}


def _field(ftype: str, **extra: object) -> dict[str, object]:
    options = OPTIONS if ftype in forms.CHOICE_TYPES else None
    return {"key": "f", "label": "Feld", "type": ftype, "options": options, **extra}


def test_register_matches_the_twenty_types() -> None:
    assert set(forms.FIELD_TYPES) == EXPECTED_TYPES
    assert len(forms.FIELD_TYPES) == 20
    assert [s.type for s in forms.ELEMENT_SPECS] == list(forms.FIELD_TYPES)
    assert len(forms.ELEMENT_SPECS) == 20
    assert set(forms.SPECS_BY_TYPE) == EXPECTED_TYPES
    kinds = {s.type: s.kind for s in forms.ELEMENT_SPECS}
    assert {t for t, k in kinds.items() if k == "display"} == set(forms.DISPLAY_TYPES)
    assert all(s.value_format and s.rule for s in forms.ELEMENT_SPECS)
    assert {s.type for s in forms.ELEMENT_SPECS if s.options} == set(forms.CHOICE_TYPES)


def test_element_types_listing_carries_source_status() -> None:
    rows = forms.element_types()
    assert len(rows) == 20
    assert all("AA14-01" in r["source_status"] for r in rows)
    display = [r for r in rows if r["kind"] == "display"]
    assert len(display) == 3
    assert all(r["required_allowed"] is False for r in display)


@pytest.mark.parametrize("ftype", sorted(CASES))
def test_each_input_type_accepts_its_valid_value(ftype: str) -> None:
    valid, normalised, _ = CASES[ftype]
    fields = forms.normalise_fields([_field(ftype, required=True)])
    out = forms.validate_values(fields, {"f": valid})
    assert out["f"] == normalised


@pytest.mark.parametrize(
    ("ftype", "bad"),
    [(t, b) for t, (_, _, bads) in sorted(CASES.items()) for b in bads],
)
def test_each_input_type_refuses_invalid_values(ftype: str, bad: object) -> None:
    fields = forms.normalise_fields([_field(ftype)])
    with pytest.raises(ProblemError) as err:
        forms.validate_values(fields, {"f": bad})
    assert err.value.errors is not None
    assert err.value.errors[0].field == "values.f"


@pytest.mark.parametrize("ftype", sorted(CASES))
def test_required_input_types_refuse_missing_and_blank(ftype: str) -> None:
    fields = forms.normalise_fields([_field(ftype, required=True)])
    for missing in ({}, {"f": ""}, {"f": "   "}) if ftype not in ("file", "multiselect") else ({},):
        with pytest.raises(ProblemError):
            forms.validate_values(
                fields, {**missing, **({"f": "false"} if ftype in forms.CHECK_TYPES else {})}
            )


@pytest.mark.parametrize("ftype", sorted(forms.DISPLAY_TYPES))
def test_display_types_carry_no_value(ftype: str) -> None:
    fields = forms.normalise_fields([_field(ftype, required=True)])
    assert fields[0]["required"] is False
    assert forms.validate_values(fields, {}) == {}
    with pytest.raises(ProblemError):
        forms.validate_values(fields, {"f": "x"})


def test_address_single_line_with_commas_is_normalised_to_lines() -> None:
    fields = forms.normalise_fields([_field("address")])
    out = forms.validate_values(fields, {"f": "Musterweg 1, 40822 Mettmann"})
    assert out["f"] == "Musterweg 1\n40822 Mettmann"
    tpl = forms.PortalFormTemplate(name="T", fields=fields)
    assert "Feld: Musterweg 1, 40822 Mettmann" in forms.render_values(tpl, out, {})


def test_options_are_limited_and_deduplicated() -> None:
    cleaned = forms.normalise_fields(
        [{"key": "a", "label": "A", "type": "select", "options": [" x ", "x", "y", ""]}]
    )
    assert cleaned[0]["options"] == ["x", "y"]
    too_many = [str(i) for i in range(forms.MAX_OPTIONS + 1)]
    with pytest.raises(ProblemError):
        forms.normalise_fields([{"key": "a", "label": "A", "type": "radio", "options": too_many}])
    with pytest.raises(ProblemError):
        forms.normalise_fields(
            [{"key": "a", "label": "A", "type": "radio", "options": ["x" * 201]}]
        )
    with pytest.raises(ProblemError):
        forms.normalise_fields([{"key": "a", "label": "A", "type": "radio", "options": [" ", ""]}])
    text = forms.normalise_fields([{"key": "a", "label": "A", "type": "text", "options": ["z"]}])
    assert text[0]["options"] is None


def test_preview_is_a_dry_run_with_errors_and_rendered_text() -> None:
    raw = [
        {"key": "h", "label": "Kopf", "type": "heading"},
        {"key": "u", "label": "Unterschrift", "type": "signature", "required": True},
        {"key": "b", "label": "Betrag", "type": "amount"},
        {"key": "f", "label": "Anhang", "type": "file", "required": True},
    ]
    bad = forms.preview("Antrag", raw, {"u": "M", "b": "1.234,5"})
    assert bad["valid"] is False
    assert {e["field"] for e in bad["errors"]} == {"values.u", "values.b"}
    assert bad["rendered"] is None
    ok = forms.preview("Antrag", raw, {"u": "Max Muster", "b": "1234,5"})
    assert ok["valid"] is True
    assert ok["errors"] == []
    assert "Formular: Antrag" in ok["rendered"]
    assert "Betrag: 1.234,50 EUR" in ok["rendered"]
    assert "Anhang: keine Angabe" in ok["rendered"]  # files are not checked in a preview
    with pytest.raises(ProblemError):
        forms.preview("Antrag", [{"key": "x", "label": "X", "type": "select"}], {})


def test_average_rating_rounds_half_up_to_one_decimal() -> None:
    assert average_rating({}) is None
    assert average_rating({5: 1}) == "5.0"
    assert average_rating({4: 1, 5: 1}) == "4.5"
    assert average_rating({1: 1, 2: 1, 5: 1}) == "2.7"  # 8 / 3 = 2,666...
    assert average_rating({3: 2, 4: 1}) == "3.3"  # 10 / 3 = 3,333...
    assert average_rating({1: 1, 2: 1}) == "1.5"
    assert average_rating({2: 1, 3: 1}) == "2.5"
