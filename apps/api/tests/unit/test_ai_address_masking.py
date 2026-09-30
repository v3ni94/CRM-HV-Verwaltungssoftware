"""M7-10: address masking before provider calls (rule AI-MASK-02)."""

import pytest

from mhvp.ai.masking import mask_addresses, mask_personal_data


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Musterstraße 12a, 10115 Berlin", "[Straße], [PLZ Ort]"),
        ("Herr Meier, Am Panke Park 3", "Herr Meier, [Straße]"),
        ("Bahnhofstr. 5", "[Straße]"),
        ("Betrag 12345 Euro offen", "Betrag 12345 Euro offen"),
        ("Rechnung vom 01.02.2026 Nr 12", "Rechnung vom 01.02.2026 Nr 12"),
    ],
)
def test_mask_addresses(raw: str, expected: str) -> None:
    assert mask_addresses(raw) == expected


def test_names_kept_and_identifiers_masked() -> None:
    out = mask_personal_data("Frau Schulz, Lindenallee 7, schulz@example.org")
    assert "Frau Schulz" in out
    assert "Lindenallee" not in out
    assert "schulz@example.org" not in out


def test_empty_inputs() -> None:
    assert mask_addresses(None) == ""
    assert mask_personal_data("") == ""
