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


# A84: heuristic names of a sole trader neither in the contacts nor in an XML issuer -------

from mhvp.receipts.masking import header_person_names, numbered_placeholder  # noqa: E402

SOLE_TRADER = """Max Mustermann, Malermeister
Hauptstraße 1
40789 Monheim am Rhein
Telefon 02173 123456

Rechnung Nr. 2026-0815
An: Hausverwaltung Müller GmbH
Leistung: Malerarbeiten Treppenhaus, Objekt Rheinpromenade 13
Kontoinhaber: MUSTERMANN, MAX
IBAN DE02 1203 0000 0000 2020 51

Mit freundlichen Grüßen
Erika Musterfrau
Bürokauffrau"""


def test_header_name_before_address_is_found_and_masked_with_stable_placeholder() -> None:
    names = header_person_names(SOLE_TRADER)
    assert names == ["Max Mustermann", "Erika Musterfrau"]
    out = mask_text(SOLE_TRADER, header_names=names)
    assert out.startswith(f"{numbered_placeholder(1)}, Malermeister")
    assert f"Kontoinhaber: {numbered_placeholder(1)}" in out  # second spelling, same number
    assert f"Mit freundlichen Grüßen\n{numbered_placeholder(2)}" in out
    assert "Mustermann" not in out
    assert "Musterfrau" not in out
    assert "Hausverwaltung Müller GmbH" in out
    assert "Rheinpromenade 13" in out
    assert "[IBAN]" in out
    assert "[TELEFON]" in out


def test_header_names_are_deterministic_and_never_raise() -> None:
    assert header_person_names(SOLE_TRADER) == header_person_names(SOLE_TRADER)
    assert header_person_names(None) == []
    assert header_person_names("") == []
    assert mask_text(SOLE_TRADER, header_names=[]) == mask_text(SOLE_TRADER)
    assert mask_text("x", header_names=["", "  "]) == "x"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # positive: profession before or after the name, academic title, hyphenated name
        ("Malermeister Max Mustermann\nHauptstr. 1\n40789 Monheim", ["Max Mustermann"]),
        (
            "Elektromeister Hans-Peter Meier-Lüdenscheid\nAm Markt 3\n40789 Monheim",
            ["Hans-Peter Meier-Lüdenscheid"],
        ),
        ("Dipl.-Ing. Anna Maria Schmidt\nRingstraße 12\n50667 Köln", ["Anna Maria Schmidt"]),
        ("Max Mustermann | Malerbetrieb\nHauptstraße 1\n40789 Monheim", ["Max Mustermann"]),
        # positive: OCR blanks inside the line and between name and profession
        (
            "Max   Mustermann   ,   Malermeister\nHauptstraße   1\n40789   Monheim",
            ["Max Mustermann"],
        ),
        # positive: signature block only
        (
            "Rechnung Nr. 1\nBetrag 100,00 EUR\nMit freundlichen Grüßen\nErika Musterfrau",
            ["Erika Musterfrau"],
        ),
        ("Rechnung\nHochachtungsvoll\n\nErika Musterfrau\nInhaberin", ["Erika Musterfrau"]),
        # negative: company names and legal forms stay
        ("Elektro Müller GmbH\nHauptstraße 1\n40789 Monheim", []),
        ("Max Mustermann e.K.\nHauptstraße 1\n40789 Monheim", []),
        ("Müller & Söhne KG\nHauptstraße 1\n40789 Monheim", []),
        ("Stadtwerke Monheim AG\nRheinallee 5\n40789 Monheim", []),
        ("Verband Deutscher Grundstücksnutzer\nPostfach 1\n40789 Monheim", []),
        ("Malerbetrieb Mustermann\nHauptstraße 1\n40789 Monheim", []),  # surname alone
        # negative: document words, digits, single word, lower case, recipient block
        ("Rechnung Nr. 2026-0815\nRechnungsdatum 01.09.2026", []),
        ("Objekt Rheinpromenade\nMalerarbeiten Treppenhaus", []),
        ("Mustermann\nHauptstraße 1\n40789 Monheim", []),
        ("max mustermann\nHauptstraße 1\n40789 Monheim", []),
        ("Sehr geehrte Damen und Herren\nvielen Dank für Ihren Auftrag", []),
        # doubtful: header name without address, kept only when it occurs twice
        ("Max Mustermann\nRechnung Nr. 1\nBetrag 100,00 EUR", []),
        ("Max Mustermann\nRechnung Nr. 1\nKontoinhaber: Mustermann, Max", ["Max Mustermann"]),
        # name deep in the text without greeting or header position is not guessed
        (
            "Rechnung Nr. 1\nPos 1\nPos 2\nPos 3\nPos 4\nPos 5\nPos 6\nPos 7\nPos 8\n"
            "Max Mustermann\nHauptstraße 1\n40789 Monheim",
            [],
        ),
    ],
)
def test_header_person_names(text: str, expected: list[str]) -> None:
    assert header_person_names(text) == expected


def test_two_header_names_get_two_stable_placeholders() -> None:
    text = "Max Mustermann und Erika Musterfrau, Max Mustermann"
    out = mask_text(text, header_names=["Max Mustermann", "Erika Musterfrau"])
    assert (
        out == f"{numbered_placeholder(1)} und {numbered_placeholder(2)}, {numbered_placeholder(1)}"
    )


def test_known_name_takes_precedence_over_header_placeholder() -> None:
    out = mask_text("Max Mustermann", ["Max Mustermann"], header_names=["Max Mustermann"])
    assert out == NAME_PLACEHOLDER
