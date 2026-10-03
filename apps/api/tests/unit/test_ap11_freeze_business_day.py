"""AP11 (GAM-611): the time fixture fixes the business day for importers by name and leaves
other clocks alone."""

from datetime import UTC, date, datetime

from mhvp.core.clock import local_today
from mhvp.workspace.services import local_today as workspace_local_today


def test_freeze_business_day_applies_to_all_importers(freeze_business_day) -> None:  # type: ignore[no-untyped-def]
    assert freeze_business_day("2026-12-31") == date(2026, 12, 31)
    assert local_today() == date(2026, 12, 31)
    assert workspace_local_today() == date(2026, 12, 31)


def test_freeze_business_day_does_not_touch_the_global_datetime(freeze_business_day) -> None:  # type: ignore[no-untyped-def]
    freeze_business_day()
    assert local_today() == date(2026, 3, 16)
    assert datetime.now(UTC).year >= 2026


def test_without_fixture_the_real_day_applies() -> None:
    assert abs((local_today() - datetime.now(UTC).date()).days) <= 1
