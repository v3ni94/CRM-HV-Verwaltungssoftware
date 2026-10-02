"""AJ09: business calendar day (GAI-102/103) and guard against UTC day in business code."""

import re
from datetime import UTC, date, datetime
from pathlib import Path

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
