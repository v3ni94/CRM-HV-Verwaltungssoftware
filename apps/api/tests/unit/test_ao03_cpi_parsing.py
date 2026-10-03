"""AO03 (GAK-203): CSV parsing of index values and the proposal helpers (values by hand)."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.letting import increase_proposals as ip


def test_parse_csv_formats_and_header() -> None:
    rows = ip.parse_cpi_csv("Monat;Wert\n2026-07;1.234,5\n08/2026;119,8\n\n2026-09-01;120\n")
    assert rows == [
        (date(2026, 7, 1), Decimal("1234.5")),
        (date(2026, 8, 1), Decimal("119.8")),
        (date(2026, 9, 1), Decimal("120")),
    ]
    assert ip.parse_cpi_csv("2026-01,117.3") == [(date(2026, 1, 1), Decimal("117.3"))]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "Monat;Wert\n",
        "2026-13;100",
        "2026-01;0",
        "2026-01;-1",
        "2026-01;1;2",
        "2026-01;100\n2026-01;101",
        "2026-01;1,123456789",
        "2026-01;100\nfoo;1",
    ],
)
def test_parse_csv_refuses(content: str) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        ip.parse_cpi_csv(content)


def test_index_adjustment_rounds_half_up() -> None:
    # 600,00 * 110,5 / 100 = 663,00; 333,33 * 105,5 / 100 = 351,663... -> 351,66
    p = ip.index_adjustment(Decimal("600.00"), Decimal("100"), Decimal("110.5"), date(2026, 11, 1))
    assert p is not None
    assert p.target_rent == Decimal("663.00")
    q = ip.index_adjustment(Decimal("333.33"), Decimal("100"), Decimal("105.5"), date(2026, 11, 1))
    assert q is not None
    assert q.target_rent == Decimal("351.66")
    assert (
        ip.index_adjustment(Decimal("600"), Decimal("100"), Decimal("99"), date(2026, 11, 1))
        is None
    )


def test_first_of_next_month() -> None:
    assert ip.first_of_next_month(date(2026, 12, 15)) == date(2027, 1, 1)
    assert ip.first_of_next_month(date(2026, 10, 3)) == date(2026, 11, 1)
