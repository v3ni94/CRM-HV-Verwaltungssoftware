"""AJ04: GAI-604 statement chain findings in checks(), GAI-606 day count in
interest_amount_for. Expected values by hand (rule 0.1.8):

* statement S2 opens with 105,00 after S1 closed with 100,00 -> break 5,00;
  S2 100 + 10 movements != 120 closing -> difference 10,00; gap 11.01. to 14.01.
* 1.000,00 at 10 % for 366 days from 01.01.2024: act_365_fixed 1.000 * 0,1 * 366/365 =
  100,27; act_act 1.000 * 0,1 * 366/366 = 100,00; without start always days/365 = 100,27.
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.accounting import dunning, services


class _Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def scalars(self, _stmt: Any) -> _Scalars:
        return _Scalars(self._rows)


class _Ledger:
    id = uuid.uuid4()


def test_chain_findings(monkeypatch: Any) -> None:
    bank = uuid.uuid4()

    async def fake_reconcile(_s: Any, bank_id: uuid.UUID) -> list[dict[str, Any]]:
        assert bank_id == bank
        return [
            {
                "statement_ref": "S1",
                "chain_status": "first",
                "chain_difference": None,
                "statement_difference": Decimal("0"),
                "period_status": "first",
                "gap_from": None,
                "gap_to": None,
            },
            {
                "statement_ref": "S2",
                "chain_status": "break",
                "chain_difference": Decimal("5.00"),
                "statement_difference": Decimal("10.00"),
                "period_status": "gap",
                "gap_from": date(2026, 1, 11),
                "gap_to": date(2026, 1, 14),
            },
        ]

    import mhvp.banking.services as bs

    monkeypatch.setattr(bs, "reconcile", fake_reconcile)
    out = asyncio.run(
        services.bank_statement_chain_findings(_Session([bank]), _Ledger())  # type: ignore[arg-type]
    )
    assert len(out) == 3
    assert "S2" in out[0]
    assert "5.00" in out[0]
    assert "10.00" in out[1]
    assert "2026-01-11 bis 2026-01-14" in out[2]


def test_chain_findings_none_without_bank_accounts() -> None:
    out = asyncio.run(services.bank_statement_chain_findings(_Session([]), _Ledger()))  # type: ignore[arg-type]
    assert out == []


def _settings(day_count: str) -> dunning.EffectiveSettings:
    s = dunning.EffectiveSettings(property_id=None)
    s.interest_enabled = True
    s.interest_base_rate = Decimal("10")
    s.interest_spread = Decimal("0")
    s.interest_day_count = day_count
    return s


def test_interest_amount_for_day_count() -> None:
    total = Decimal("1000.00")
    fixed = _settings(dunning.DAY_COUNT_FIXED)
    actual = _settings(dunning.DAY_COUNT_ACTUAL)
    start = date(2024, 1, 1)
    assert dunning.interest_amount_for(fixed, total, 366, start) == Decimal("100.27")
    assert dunning.interest_amount_for(actual, total, 366, start) == Decimal("100.00")
    assert dunning.interest_amount_for(actual, total, 366) == Decimal("100.27")
