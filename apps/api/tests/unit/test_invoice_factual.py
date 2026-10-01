"""M14-02: pure helpers of the factual invoice review (tolerance, rhythm, line arithmetic).

Expected values by hand: 1.190,00 against 1.000,00 deviates 190,00; 20 % allows 200,00,
19 % allows 190,00 (still within), 18 % allows 180,00 (outside). 3 x 300,00 = 900,00.
"""

from datetime import date
from decimal import Decimal

from mhvp.accounting.invoice_factual import (
    FactualResult,
    Tolerances,
    line_findings,
    months_between,
    within,
)
from mhvp.accounting.models import InvoiceLine


def test_within_tolerance() -> None:
    assert not within(Decimal("1190.00"), Decimal("1000.00"), Decimal("0"))
    assert within(Decimal("1000.00"), Decimal("1000.00"), Decimal("0"))
    assert within(Decimal("1190.00"), Decimal("1000.00"), Decimal("19"))
    assert not within(Decimal("1190.00"), Decimal("1000.00"), Decimal("18"))


def test_months_between() -> None:
    assert months_between(date(2026, 2, 1), date(2026, 4, 1)) == 2
    assert months_between(date(2025, 12, 31), date(2026, 1, 1)) == 1


def test_line_findings() -> None:
    out = FactualResult()
    lines = [
        InvoiceLine(net=Decimal("1000.00"), quantity=Decimal("3"), unit_price=Decimal("300")),
        InvoiceLine(net=Decimal("1000.00"), quantity=Decimal("4"), unit_price=Decimal("250")),
        InvoiceLine(net=Decimal("10.00"), quantity=Decimal("1"), unit_price=None),
        InvoiceLine(net=Decimal("10.00")),
    ]
    line_findings(lines, Tolerances(), out)
    assert [f["code"] for f in out.findings] == ["line_mismatch", "line_incomplete"]
    assert "900,00 EUR" in out.findings[0]["message"]
    tolerant = FactualResult()
    line_findings(lines[:1], Tolerances(quantity_percent=Decimal("12")), tolerant)
    assert tolerant.findings == []
