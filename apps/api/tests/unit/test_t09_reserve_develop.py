"""M24-01: closing = opening + contribution - withdrawals - taxes - fees + interest."""

from decimal import Decimal

from mhvp.hoa.reserves import develop


def test_develop_by_hand() -> None:
    fig = {
        "contributions": Decimal("2400.00"),
        "withdrawals": Decimal("1500.00"),
        "taxes": Decimal("5.28"),
        "fees": Decimal("12.00"),
        "interest": Decimal("21.10"),
    }
    # 10.000,00 + 2.400,00 - 1.500,00 - 5,28 - 12,00 + 21,10 = 10.903,82
    assert develop(Decimal("10000.00"), fig) == Decimal("10903.82")
