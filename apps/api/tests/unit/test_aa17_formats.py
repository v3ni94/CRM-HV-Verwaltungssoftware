"""AA17: expected values follow from the documented formats (no database)."""

from datetime import date

import pytest

from mhvp.core.number_format import NumberFormat, effective_formats, format_number, preview
from mhvp.documents.folder_scheme import render_folder_path, validate_folder_scheme


def test_defaults_match_hard_coded_formats() -> None:
    f = effective_formats(None)
    assert format_number(f["contract"], 123) == "000123"
    assert format_number(f["property"], 7) == "007"
    assert format_number(f["ticket"], 42) == "42"
    assert format_number(f["invoice"], 5, date(2026, 3, 1)) == "MR-2026-000005"


def test_configured_format_and_preview() -> None:
    fmt = NumberFormat(prefix="OBJ", digits=4, start=10, year_based=True)
    assert preview(fmt, date(2026, 1, 1)) == ["OBJ-2026-0010", "OBJ-2026-0011", "OBJ-2026-0012"]
    assert effective_formats({"number_formats": {"ticket": {"prefix": "T", "digits": 3}}})[
        "ticket"
    ] == NumberFormat(prefix="T", digits=3)


@pytest.mark.parametrize("prefix", ["a", "A B", "A-B", "X" * 11])
def test_prefix_validation(prefix: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        NumberFormat(prefix=prefix)


def test_folder_scheme_default_and_custom() -> None:
    assert render_folder_path(None, objekt="001 Musterstr", jahr=2026) == ["001 Musterstr", "2026"]
    assert render_folder_path(
        "{objekt}/{kategorie}/{jahr}", objekt="O", jahr=2025, kategorie="Rechnungen"
    ) == ["O", "Rechnungen", "2025"]
    assert validate_folder_scheme(" /{objekt}/{jahr}/ ") == "{objekt}/{jahr}"


@pytest.mark.parametrize(
    "scheme",
    [
        "",
        "{jahr}",
        "{objekt}//{jahr}",
        "{objekt}/{foo}",
        "../{objekt}",
        "{objekt}/a:b",
        "{objekt}/{",
        "a/b/c/d/e/{objekt}",
    ],
)
def test_folder_scheme_invalid(scheme: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        validate_folder_scheme(scheme)
