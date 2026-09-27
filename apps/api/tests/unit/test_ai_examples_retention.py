"""Retention cut-off of the learning examples (ADR 0010 addendum 27.09.2026): calendar months,
day clamped to the target month."""

from datetime import UTC, datetime

from mhvp.ai.examples import DEFAULT_RETENTION_MONTHS, retention_cutoff
from mhvp.worker import create_celery


def test_cutoff_in_calendar_months() -> None:
    now = datetime(2026, 9, 27, 3, 45, tzinfo=UTC)
    assert retention_cutoff(now, 24) == datetime(2024, 9, 27, 3, 45, tzinfo=UTC)
    assert retention_cutoff(now, 9) == datetime(2025, 12, 27, 3, 45, tzinfo=UTC)
    assert retention_cutoff(now, 1) == datetime(2026, 8, 27, 3, 45, tzinfo=UTC)


def test_cutoff_clamps_the_day() -> None:
    assert retention_cutoff(datetime(2026, 5, 31, tzinfo=UTC), 3) == datetime(
        2026, 2, 28, tzinfo=UTC
    )
    assert retention_cutoff(datetime(2028, 5, 31, tzinfo=UTC), 3) == datetime(
        2028, 2, 29, tzinfo=UTC
    )


def test_default_and_beat_entry(settings: object) -> None:
    assert DEFAULT_RETENTION_MONTHS == 24
    entry = create_celery(settings).conf.beat_schedule["ai-examples-retention"]  # type: ignore[arg-type]
    assert entry["task"] == "mhvp.ai.examples_retention"
