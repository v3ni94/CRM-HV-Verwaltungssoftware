"""P13 (SA-03): form builder with 14 element types, delivery check, chat pre-qualification
rules. Pure helpers, no database."""

import pytest

from mhvp.core.problems import ProblemError
from mhvp.portal import forms
from mhvp.portal.chat import prequalify_text


def _fields() -> list[dict[str, object]]:
    return [
        {"key": "h", "label": "Kopf", "type": "heading"},
        {"key": "i", "label": "Hinweis", "type": "info", "help": "Bitte lesen"},
        {"key": "t", "label": "Text", "type": "text", "required": True},
        {"key": "ta", "label": "Langtext", "type": "textarea"},
        {"key": "n", "label": "Zahl", "type": "number"},
        {"key": "d", "label": "Datum", "type": "date"},
        {"key": "z", "label": "Uhrzeit", "type": "time"},
        {"key": "s", "label": "Auswahl", "type": "select", "options": ["a", "b"]},
        {"key": "r", "label": "Radio", "type": "radio", "options": ["x", "y"]},
        {"key": "m", "label": "Mehrfach", "type": "multiselect", "options": ["p", "q", "r"]},
        {"key": "c", "label": "Zustimmung", "type": "checkbox", "required": True},
        {"key": "e", "label": "E-Mail", "type": "email"},
        {"key": "p", "label": "Telefon", "type": "phone"},
        {"key": "f", "label": "Anhang", "type": "file"},
    ]


def test_at_least_twelve_types() -> None:
    assert len(forms.FIELD_TYPES) >= 12


def test_all_types_normalise_and_validate() -> None:
    fields = forms.normalise_fields(_fields())
    assert len(fields) == 14
    assert fields[0]["required"] is False
    values = forms.validate_values(
        fields,
        {
            "t": "Hallo",
            "n": "3,5",
            "d": "2026-09-30",
            "z": "08:15",
            "s": "a",
            "r": "y",
            "m": ["p", "r", "p"],
            "c": True,
            "e": "a@example.org",
            "p": "+49 2103 123456",
        },
    )
    assert values["m"] == ["p", "r"]
    assert values["c"] == "true"
    assert "h" not in values


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("z", "25:00"),
        ("e", "kein-mail"),
        ("p", "abc"),
        ("m", ["zzz"]),
        ("r", "nicht da"),
        ("c", "vielleicht"),
    ],
)
def test_invalid_values_are_refused(key: str, value: object) -> None:
    fields = forms.normalise_fields(_fields())
    with pytest.raises(ProblemError):
        forms.validate_values(fields, {"t": "x", "c": True, key: value})


def test_required_checkbox_must_be_checked() -> None:
    fields = forms.normalise_fields(_fields())
    with pytest.raises(ProblemError):
        forms.validate_values(fields, {"t": "x", "c": False})


def test_choice_types_need_options_and_unknown_type_fails() -> None:
    with pytest.raises(ProblemError):
        forms.normalise_fields([{"key": "a", "label": "A", "type": "radio"}])
    with pytest.raises(ProblemError):
        forms.normalise_fields([{"key": "a", "label": "A", "type": "signature"}])


def test_delivery_rules() -> None:
    assert forms.normalise_delivery("ticket", "x@example.org") == ("ticket", None)
    assert forms.normalise_delivery("email", " Info@Example.org ") == ("email", "Info@Example.org")
    with pytest.raises(ProblemError):
        forms.normalise_delivery("email", None)
    with pytest.raises(ProblemError):
        forms.normalise_delivery("post", None)


def test_prequalification_rules_are_deterministic() -> None:
    out = prequalify_text("Die Heizung ist ausgefallen und es gab einen Rohrbruch im Keller")
    assert "Heizung" in out["topics"]
    assert out["urgent_hint"] is True
    assert out["emergency_note"]
    calm = prequalify_text("Bitte um Rückruf wegen der Nebenkosten")
    assert calm["topics"] == []
    assert calm["urgent_hint"] is False
    assert calm["emergency_note"] is None
