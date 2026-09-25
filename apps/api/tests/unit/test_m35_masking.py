"""M35 Stufe 3 part 2 (AI stage): masking before an external provider call."""

from mhvp.objektakte.masking import contains_iban, mask_text


def test_masks_iban() -> None:
    text = "IBAN: DE89 3704 0044 0532 0130 00, bitte vormerken."
    out = mask_text(text)
    assert "DE89" not in out
    assert "[IBAN]" in out
    assert not contains_iban(out)


def test_masks_email() -> None:
    out = mask_text("Rückfragen an erika.musterfrau@example.org bitte.")
    assert "erika.musterfrau@example.org" not in out
    assert "[E-MAIL]" in out


def test_masks_german_phone_numbers() -> None:
    for number in ["+49 211 1234567", "0211-1234567", "0170 1234567"]:
        out = mask_text(f"Telefon {number} erreichbar.")
        assert number not in out
        assert "[TELEFON]" in out


def test_masks_probable_person_names() -> None:
    out = mask_text("Herr Max Mustermann hat unterschrieben.")
    assert "Max Mustermann" not in out
    assert "[NAME]" in out


def test_empty_and_none_input_never_raises() -> None:
    assert mask_text(None) == ""
    assert mask_text("") == ""


def test_plain_text_without_pii_is_left_readable() -> None:
    out = mask_text("Betreff: Wirtschaftsplan 2027, Kategorie 03.")
    assert "Wirtschaftsplan 2027" in out


def test_contains_iban_detects_unmasked_iban() -> None:
    assert contains_iban("Konto DE02120300000000202051")
    assert not contains_iban("kein Konto hier")
