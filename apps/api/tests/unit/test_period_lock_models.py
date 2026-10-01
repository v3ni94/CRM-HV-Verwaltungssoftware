"""AE20: validation of the period lock schemas (P06-02)."""

from datetime import date

import pytest
from pydantic import ValidationError

from mhvp.accounting.period_lock import PeriodLockIn, PeriodLockSettingIn, setting_out


def test_period_order_and_defaults() -> None:
    import uuid

    ok = PeriodLockIn(
        ledger_id=uuid.uuid4(),
        property_id=uuid.uuid4(),
        period_from=date(2026, 1, 1),
        period_to=date(2026, 1, 1),
        reason="Abschluss",
    )
    assert ok.period_from == ok.period_to
    with pytest.raises(ValidationError):
        PeriodLockIn(
            ledger_id=uuid.uuid4(),
            property_id=uuid.uuid4(),
            period_from=date(2026, 2, 1),
            period_to=date(2026, 1, 1),
            reason="Abschluss",
        )
    with pytest.raises(ValidationError):
        PeriodLockSettingIn(lock_mode="all")
    out = setting_out(None)
    assert (out.lock_mode, out.auto_lock_on_close, out.reopen_enabled) == (
        "ledger_only",
        False,
        False,
    )
