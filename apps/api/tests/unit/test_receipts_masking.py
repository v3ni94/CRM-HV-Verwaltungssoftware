"""A65: deterministic masking of person names without a title before the provider call in
the receipt intake (`mhvp.receipts.masking`). Company names survive, known person names from
the tenant's contacts and a person-like issuer are hidden, IBAN and contact data stay hidden."""

import pytest

from mhvp.receipts.masking import (
    NAME_PLACEHOLDER,
    compile_names,
    issuer_person_name,
    mask_text,
    name_variants,
)

INVOICE = """Rechnung Nr. 2026-0815
Max Mustermann, Malermeister
Hauptstraße 1, 40789 Monheim am Rhein
An: Hausverwaltung Müller GmbH
Leistung: Malerarbeiten Treppenhaus, Objekt Rheinpromenade 13
Ansprechpartner: Erika Musterfrau (Telefon 0171 1234567)
Kontoinhaber: MUSTERMANN, MAX
IBAN DE02 1203 0000 0000 2020 51
Bitte überweisen an Elektro Müller GmbH, nicht an Frau Müller."""

NAMES = ["Max Mustermann", "Mustermann, Max", "Erika Musterfrau", "Musterfrau, Erika"]


def test_known_names_are_masked_in_both_spellings_and_any_case() -> None:
    out = mask_text(INVOICE, NAMES)
    assert "Max Mustermann" not in out
    assert "MUSTERMANN, MAX" not in out
    assert "Erika Musterfrau" not in out
    assert f"{NAME_PLACEHOLDER}, Malermeister" in out
    assert f"Kontoinhaber: {NAME_PLACEHOLDER}" in out
    assert out.count(NAME_PLACEHOLDER) == 4  # Max, Erika, MUSTERMANN, MAX, Frau Müller


def test_company_names_and_lone_surnames_survive() -> None:
    out = mask_text(INVOICE, NAMES)
    assert "Hausverwaltung Müller GmbH" in out
    assert "Elektro Müller GmbH" in out
    assert "Malermeister" in out
    assert "Rheinpromenade 13" in out


def test_titled_name_still_masked_without_known_names() -> None:
    out = mask_text(INVOICE)
    assert "Frau Müller" not in out
    assert "Max Mustermann" in out  # the gap A65 closes only with known names


def test_earlier_placeholders_are_not_re_exposed() -> None:
    out = mask_text(INVOICE, NAMES)
    assert "[IBAN]" in out
    assert "DE02" not in out
    assert "[TELEFON]" in out
    assert "1234567" not in out


def test_masking_is_deterministic_and_never_raises() -> None:
    assert mask_text(INVOICE, NAMES) == mask_text(INVOICE, reversed(NAMES))
    assert mask_text(None, NAMES) == ""
    assert mask_text("", NAMES) == ""
    assert mask_text("x", ["", "  ", "A B"]) == "x"


def test_ocr_whitespace_between_name_parts_is_tolerated() -> None:
    assert mask_text("Max   Mustermann\tGmbH-frei", ["Max Mustermann"]).startswith(NAME_PLACEHOLDER)


def test_partial_words_are_not_masked() -> None:
    out = mask_text("Maximilian Mustermannsche Werke, Max Mustermann", ["Max Mustermann"])
    assert out == f"Maximilian Mustermannsche Werke, {NAME_PLACEHOLDER}"


def test_longer_name_wins_over_contained_name() -> None:
    out = mask_text("Anna Maria Schmidt", ["Anna Maria Schmidt", "Maria Schmidt"])
    assert out == NAME_PLACEHOLDER


def test_name_variants_require_both_parts() -> None:
    assert name_variants("Erika", "Musterfrau") == ["Erika Musterfrau", "Musterfrau, Erika"]
    assert name_variants(" Erika ", " Muster  frau ") == [
        "Erika Muster frau",
        "Muster frau, Erika",
    ]
    assert name_variants(None, "Musterfrau") == []
    assert name_variants("Erika", "") == []


def test_compile_names_ignores_short_or_empty_entries() -> None:
    assert compile_names([]) is None
    assert compile_names(["", "Li"]) is None
    assert compile_names(["Li Wu"]) is not None


@pytest.mark.parametrize(
    ("issuer", "expected"),
    [
        ("Max Mustermann", "Max Mustermann"),
        ("Dr. Anna Maria Schmidt", "Anna Maria Schmidt"),
        ("Mustermann, Max", "Mustermann Max"),
        ("Hans-Peter Meier-Lüdenscheid", "Hans-Peter Meier-Lüdenscheid"),
        ("Elektro Müller GmbH", None),
        ("Müller & Söhne", None),
        ("Max Mustermann e.K.", None),
        ("Mustermann", None),
        ("Malerbetrieb Max Mustermann", "Max Mustermann"),
        ("Max Mustermann Malermeister", "Max Mustermann"),
        ("MAX MUSTERMANN", None),
        ("Stadt Monheim am Rhein", None),
        ("", None),
        (None, None),
    ],
)
def test_issuer_person_name(issuer: str | None, expected: str | None) -> None:
    assert issuer_person_name(issuer) == expected


def test_issuer_person_name_is_masked_in_text() -> None:
    issuer = issuer_person_name("Max Mustermann")
    assert issuer
    out = mask_text("Rechnungssteller: Max Mustermann, Hauptstraße 1", [issuer])
    assert out == f"Rechnungssteller: {NAME_PLACEHOLDER}, Hauptstraße 1"
