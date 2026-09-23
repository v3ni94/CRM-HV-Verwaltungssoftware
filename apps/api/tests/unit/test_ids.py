import time
import uuid

from mhvp.core import ids
from mhvp.core.ids import uuid7, uuid7_timestamp_ms


def test_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_timestamp_is_current() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000
    assert before <= uuid7_timestamp_ms(value) <= after + 1


def test_strictly_increasing_and_unique() -> None:
    generated = [uuid7() for _ in range(10_000)]
    assert generated == sorted(generated)
    assert len(set(generated)) == len(generated)


def test_monotonic_when_clock_goes_backwards(monkeypatch: object) -> None:
    first = uuid7()
    ids._last_ms += 5_000  # simulate a wall clock that jumped back by five seconds
    second = uuid7()
    assert second > first


def test_counter_overflow_advances_timestamp() -> None:
    uuid7()
    ids._counter = 0xFFF
    last_ms = ids._last_ms
    value = uuid7()
    assert uuid7_timestamp_ms(value) == last_ms + 1


def test_timestamp_rejects_other_versions() -> None:
    import pytest

    with pytest.raises(ValueError, match="version 7"):
        uuid7_timestamp_ms(uuid.uuid4())
