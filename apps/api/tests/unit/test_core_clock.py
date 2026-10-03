"""AJ09: business calendar day (GAI-102/103) and guard against UTC day in business code."""

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from mhvp.core.clock import local_date, local_today

SRC = Path(__file__).resolve().parents[2] / "src" / "mhvp"
FORBIDDEN = re.compile(r"now\((tz=)?UTC\)\.date\(\)|datetime\.now\(\)\.date|date\.today\(\)")


def test_midnight_boundary_summer() -> None:
    # 22:30 UTC on 30.06. is 00:30 on 01.07. in Berlin (CEST, UTC+2)
    assert local_today(datetime(2026, 6, 30, 22, 30, tzinfo=UTC)) == date(2026, 7, 1)
    assert local_today(datetime(2026, 6, 30, 21, 59, tzinfo=UTC)) == date(2026, 6, 30)


def test_midnight_boundary_winter() -> None:
    # 23:30 UTC on 31.12. is 00:30 on 01.01. in Berlin (CET, UTC+1)
    assert local_today(datetime(2026, 12, 31, 23, 30, tzinfo=UTC)) == date(2027, 1, 1)
    assert local_today(datetime(2026, 12, 31, 22, 59, tzinfo=UTC)) == date(2026, 12, 31)


def test_dst_switch_days() -> None:
    assert local_date(datetime(2026, 3, 28, 23, 30, tzinfo=UTC)) == date(2026, 3, 29)
    assert local_date(datetime(2026, 10, 24, 22, 30, tzinfo=UTC)) == date(2026, 10, 25)


def test_no_utc_day_in_business_code() -> None:
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if FORBIDDEN.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_ak19_naive_timestamp_is_read_as_utc_regardless_of_host_tz(
    monkeypatch: "pytest.MonkeyPatch",
) -> None:
    """AK19-01: a naive value counts as UTC; 22:30 UTC in summer is the next Berlin day."""
    import os
    import time

    monkeypatch.setenv("TZ", "America/New_York")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        assert local_date(datetime(2026, 10, 2, 22, 30)) == date(2026, 10, 3)  # noqa: DTZ001
        assert local_today(datetime(2026, 12, 31, 23, 30)) == date(2027, 1, 1)  # noqa: DTZ001
        # DST end 25.10.2026: 22:30 UTC on 24.10. is 00:30 CEST on 25.10.
        assert local_date(datetime(2026, 10, 24, 22, 30)) == date(2026, 10, 25)  # noqa: DTZ001
        # 23:30 UTC on 25.10. (after the switch, CET) is 00:30 on 26.10.
        assert local_date(datetime(2026, 10, 25, 23, 30)) == date(2026, 10, 26)  # noqa: DTZ001
    finally:
        os.environ.pop("TZ", None)
        if hasattr(time, "tzset"):
            time.tzset()
