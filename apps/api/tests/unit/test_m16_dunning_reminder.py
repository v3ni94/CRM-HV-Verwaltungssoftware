"""M16-14 and M16-12: the Zahlungserinnerung (level 1) never carries a fee or interest, and
the preset ladder carries the default payment deadlines 14, 10 and 7 days. Expected values
are fixed here, not derived from the implementation."""

import asyncio
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import Request

from mhvp.accounting import dunning
from mhvp.accounting.routers import (
    DunningSettingsIn,
    _check_levels,
    put_dunning_settings,
)
from mhvp.core.problems import ProblemError

REMINDER_TEXT = "Zahlungserinnerung (Stufe 1) ist immer ohne Gebühr und ohne Zinsen"


def _put(body: DunningSettingsIn) -> None:
    # The fee rule is checked before any database access, so no request or session is needed.
    asyncio.run(put_dunning_settings(body, cast(Request, None), cast(Any, None)))


def test_fee_from_level_one_is_rejected_with_german_message() -> None:
    body = DunningSettingsIn(
        levels=[{"level": 1, "min_days_overdue": 7, "text": "Zahlungserinnerung"}],
        fee_from_level=1,
    )
    with pytest.raises(ProblemError) as exc:
        _put(body)
    assert REMINDER_TEXT in str(exc.value.detail)


def test_fee_from_level_one_is_rejected_for_object_override() -> None:
    body = DunningSettingsIn(
        property_id=uuid.UUID("0190a000-0000-7000-8000-000000000001"), fee_from_level=1
    )
    with pytest.raises(ProblemError) as exc:
        _put(body)
    assert REMINDER_TEXT in str(exc.value.detail)


@pytest.mark.parametrize("fee", ["2.50", "0.01", 5])
def test_level_one_fee_amount_is_rejected(fee: object) -> None:
    levels = [{"level": 1, "min_days_overdue": 7, "text": "Zahlungserinnerung", "fee_amount": fee}]
    with pytest.raises(ProblemError) as exc:
        _check_levels(levels, override=False)
    assert REMINDER_TEXT in str(exc.value.detail)


@pytest.mark.parametrize("fee", [None, "0", "0.00", 0])
def test_level_one_without_fee_is_accepted(fee: object) -> None:
    levels = [
        {"level": 1, "min_days_overdue": 7, "text": "Zahlungserinnerung", "fee_amount": fee},
        {"level": 2, "min_days_overdue": 14, "text": "1. Mahnung", "fee_amount": "5.00"},
    ]
    _check_levels(levels, override=False)


def test_override_level_one_fee_is_rejected() -> None:
    with pytest.raises(ProblemError):
        _check_levels([{"level": 1, "min_days_overdue": 7, "fee_amount": "1.00"}], override=True)


def test_guard_resets_fee_and_interest_on_level_one_with_note() -> None:
    fee, interest, note = dunning.reminder_guard(1, Decimal("5.00"), Decimal("1.23"))
    assert fee == Decimal("0.00")
    assert interest == Decimal("0.00")
    assert note is not None
    assert "5.00 EUR" in note
    assert "1.23 EUR" in note
    assert "0,00 EUR" in note


def test_guard_leaves_clean_level_one_untouched() -> None:
    assert dunning.reminder_guard(1, Decimal("0.00"), Decimal("0.00")) == (
        Decimal("0.00"),
        Decimal("0.00"),
        None,
    )


def test_guard_leaves_higher_levels_untouched() -> None:
    assert dunning.reminder_guard(2, Decimal("5.00"), Decimal("1.23")) == (
        Decimal("5.00"),
        Decimal("1.23"),
        None,
    )


def test_level_one_fee_is_zero_even_if_stored_config_says_otherwise() -> None:
    # A legacy row stored before the validation existed: fee_from_level 1 and a level 1 fee.
    eff = dunning.EffectiveSettings(
        property_id=None,
        levels=[{"level": 1, "min_days_overdue": 7, "text": "Erinnerung", "fee_amount": "4.00"}],
        fee_from_level=1,
    )
    raw = dunning.fee_amount_for(eff, 1) or Decimal("0.00")
    assert raw == Decimal("4.00")
    fee, _, note = dunning.reminder_guard(1, raw, Decimal("0.00"))
    assert fee == Decimal("0.00")
    assert note is not None


def test_preset_payment_days_defaults() -> None:
    days = {lv["level"]: lv["payment_days"] for lv in dunning.preset_levels()}
    assert days == {1: 14, 2: 10, 3: 7, 4: None}
    assert all(lv["fee_amount"] is None for lv in dunning.preset_levels())


def test_preset_levels_pass_validation() -> None:
    _check_levels(dunning.preset_levels(), override=False)
