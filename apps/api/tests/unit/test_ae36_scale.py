"""AE36 (AC09-01, ADR 0021, AA15-01): scale monitoring and demo data, pure parts.

Expected values by hand:

* P95 by the nearest rank method: 20 samples 1 to 20 give rank ceil(0,95 * 20) = 19, so 19;
  100 samples 1 to 100 give rank 95, so 95; 19 samples give no figure (basis too small).
* Size threshold 50 GB is 50 * 1024^3 = 53.687.091.200 bytes; rows threshold 20.000.000.
* P95 trigger: three measurements in a row above 300 ms (deep access 1.000 ms).
"""

import asyncio
from typing import Any

import pytest

from mhvp.platform import demo_seed
from mhvp.platform.scale_models import (
    DEFAULT_P95_DEEP_MS_THRESHOLD,
    DEFAULT_P95_MS_THRESHOLD,
    DEFAULT_P95_WEEKS,
    DEFAULT_RESTORE_SECONDS_THRESHOLD,
    DEFAULT_ROWS_THRESHOLD,
    DEFAULT_SIZE_GB_THRESHOLD,
    DEFAULT_TENANTS_REVIEW_THRESHOLD,
)
from mhvp.workspace import scale

NOW = 1_800_000_000.0


def thresholds(**override: int) -> scale.Thresholds:
    values = {
        "rows": DEFAULT_ROWS_THRESHOLD,
        "size_gb": DEFAULT_SIZE_GB_THRESHOLD,
        "p95_ms": DEFAULT_P95_MS_THRESHOLD,
        "p95_deep_ms": DEFAULT_P95_DEEP_MS_THRESHOLD,
        "p95_weeks": DEFAULT_P95_WEEKS,
        "restore_seconds": DEFAULT_RESTORE_SECONDS_THRESHOLD,
        "tenants_review": DEFAULT_TENANTS_REVIEW_THRESHOLD,
    }
    values.update(override)
    return scale.Thresholds(**values)


def tables(rows: int = 0, size: int = 0) -> dict[str, dict[str, Any]]:
    return {
        name: {"rows": rows, "bytes": size, "exact": True}
        for name in ("journal_entry", "journal_line", "bank_transaction")
    }


def latency(**p95: float | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {
        key: {"samples": 50, "p95_ms": None} for key in scale.LATENCY_KEYS
    }
    for key, value in p95.items():
        out[key] = {"samples": 50, "p95_ms": value}
    return out


def measurement(**kw: Any) -> scale.Measurement:
    base: dict[str, Any] = {
        "tables": tables(),
        "latency": latency(),
        "restore_seconds": None,
        "tenants_productive": 2,
        "tenants_demo": 1,
    }
    base.update(kw)
    return scale.Measurement(**base)


def point(week: str, **p95: float | None) -> scale.HistoryPoint:
    return scale.HistoryPoint(iso_week=week, latency=latency(**p95))


def keys(triggers: list[scale.Trigger]) -> set[str]:
    return {t.key for t in triggers}


# Defaults = proposals of ADR 0021 -----------------------------------------------------------


def test_defaults_are_the_adr_proposals() -> None:
    assert DEFAULT_ROWS_THRESHOLD == 20_000_000
    assert DEFAULT_SIZE_GB_THRESHOLD == 50
    assert DEFAULT_P95_MS_THRESHOLD == 300
    assert DEFAULT_P95_DEEP_MS_THRESHOLD == 1000
    assert DEFAULT_P95_WEEKS == 3
    assert DEFAULT_RESTORE_SECONDS_THRESHOLD == 14_400  # RTO 4 hours
    assert DEFAULT_TENANTS_REVIEW_THRESHOLD == 20


# P95 -----------------------------------------------------------------------------------------


def test_percentile95_nearest_rank() -> None:
    assert scale.percentile95(range(1, 21)) == 19  # rank ceil(19) = 19
    assert scale.percentile95([float(n) for n in range(100, 0, -1)]) == 95  # unsorted input
    assert scale.percentile95(range(1, 20)) is None  # 19 samples: no basis
    assert scale.percentile95([]) is None
    assert scale.percentile95([250.0] * 20) == 250.0


def test_parse_samples_keeps_the_window_and_skips_garbage() -> None:
    fresh = f"{int(NOW) - 3600}:120.5"
    stale = f"{int(NOW) - 8 * 86400}:9999.0"  # outside the seven day window
    raw: list[bytes | str] = [fresh, stale.encode(), b"garbage", "x:y", f"{int(NOW)}:80".encode()]
    assert sorted(scale.parse_samples(raw, NOW)) == [80.0, 120.5]


def test_classify_paths_and_deep_access() -> None:
    journal = "/api/v1/accounting/ledgers/0b9c7e9a-0000-4000-8000-000000000001/entries"
    assert scale.classify(journal, b"") == "journal_list"
    assert scale.classify(journal, b"page=2&page_size=100") == "journal_list"  # offset 100
    assert scale.classify(journal, b"page=101&page_size=100") == "journal_list_deep"  # 10.000
    assert scale.classify(journal, b"page=100&page_size=100") == "journal_list"  # 9.900
    assert scale.classify(journal, b"offset=10000") == "journal_list_deep"
    assert scale.classify("/api/v1/banking/transactions", b"limit=200") == "bank_list"
    assert scale.classify("/api/v1/banking/transactions", b"offset=9999") == "bank_list"
    assert scale.classify("/api/v1/banking/transactions", b"offset=10000") == "bank_list_deep"
    assert scale.classify("/api/v1/banking/transactions", b"offset=abc") == "bank_list"
    # everything else is not measured
    assert scale.classify("/api/v1/contacts", b"") is None
    assert scale.classify(journal + "/x", b"") is None
    assert scale.classify("/api/v1/accounting/ledgers/entries", b"") is None
    assert scale.classify("/api/v1/banking/transactions/abc", b"") is None


# Triggers of ADR 0021 --------------------------------------------------------------------------


def test_rows_and_size_trigger_at_the_threshold() -> None:
    below = measurement(tables=tables(rows=19_999_999, size=50 * 1024**3 - 1))
    assert scale.evaluate(thresholds(), below, []) == []
    at = measurement(tables=tables(rows=20_000_000, size=50 * 1024**3))
    found = keys(scale.evaluate(thresholds(), at, []))
    assert found == {
        f"{kind}:{name}"
        for kind in ("rows", "size")
        for name in ("journal_entry", "journal_line", "bank_transaction")
    }
    kinds = {t.kind for t in scale.evaluate(thresholds(), at, [])}
    assert kinds == {scale.KIND_PARTITION_REVIEW}


def test_p95_trigger_needs_three_measurements_in_a_row() -> None:
    now = measurement(latency=latency(journal_list=420.0))
    history = [point("2026-W39", journal_list=350.0), point("2026-W38", journal_list=310.0)]
    assert keys(scale.evaluate(thresholds(), now, history)) == {"p95:journal_list"}
    # only two measurements so far
    assert scale.evaluate(thresholds(), now, history[:1]) == []
    # one week under the threshold breaks the row
    broken = [point("2026-W39", journal_list=299.9), point("2026-W38", journal_list=500.0)]
    assert scale.evaluate(thresholds(), now, broken) == []
    # a week without figure (too few samples) is no measurement above the threshold
    missing = [point("2026-W39", journal_list=None), point("2026-W38", journal_list=500.0)]
    assert scale.evaluate(thresholds(), now, missing) == []
    # exactly at the threshold is not above it
    equal = measurement(latency=latency(journal_list=300.0))
    assert scale.evaluate(thresholds(), equal, history) == []


def test_deep_access_uses_its_own_threshold() -> None:
    history = [point("2026-W39", bank_list_deep=1200.0), point("2026-W38", bank_list_deep=1100.0)]
    now = measurement(latency=latency(bank_list_deep=1001.0))
    assert keys(scale.evaluate(thresholds(), now, history)) == {"p95:bank_list_deep"}
    # 900 ms is above 300 but not above the deep threshold of 1.000 ms
    lower = measurement(latency=latency(bank_list_deep=900.0))
    assert scale.evaluate(thresholds(), lower, history) == []


def test_number_of_weeks_is_configurable() -> None:
    now = measurement(latency=latency(bank_list=400.0))
    assert keys(scale.evaluate(thresholds(p95_weeks=1), now, [])) == {"p95:bank_list"}
    assert scale.evaluate(thresholds(p95_weeks=2), now, []) == []


def test_restore_trigger_above_the_rto() -> None:
    assert scale.evaluate(thresholds(), measurement(restore_seconds=14_400), []) == []
    found = scale.evaluate(thresholds(), measurement(restore_seconds=14_401), [])
    assert keys(found) == {"restore:duration"}
    assert scale.evaluate(thresholds(), measurement(restore_seconds=None), []) == []


def test_tenant_mark_asks_for_a_new_measurement_not_for_a_rebuild() -> None:
    twenty = measurement(tenants_productive=20, tenants_demo=5)
    found = scale.evaluate(thresholds(), twenty, [])
    assert keys(found) == {"tenants:productive"}
    assert found[0].kind == scale.KIND_MEASURE_AGAIN
    assert scale.evaluate(thresholds(), measurement(tenants_productive=19), []) == []


# Latency middleware ------------------------------------------------------------------------------


class FakePipeline:
    def __init__(self, store: dict[str, list[str]]) -> None:
        self.store = store
        self.ops: list[tuple[str, Any]] = []

    def lpush(self, name: str, value: str) -> None:
        self.ops.append(("lpush", (name, value)))

    def ltrim(self, name: str, start: int, end: int) -> None:
        self.ops.append(("ltrim", (name, start, end)))

    def expire(self, name: str, seconds: int) -> None:
        self.ops.append(("expire", (name, seconds)))

    async def execute(self) -> None:
        for op, args in self.ops:
            if op == "lpush":
                self.store.setdefault(args[0], []).insert(0, args[1])
            elif op == "ltrim":
                self.store[args[0]] = self.store[args[0]][args[1] : args[2] + 1]


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, list[str]] = {}
        self.fail = fail

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        if self.fail:
            raise ConnectionError("redis down")
        return FakePipeline(self.store)


class _Resources:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis


class _State:
    def __init__(self, redis: FakeRedis) -> None:
        self.resources = _Resources(redis)


class _App:
    def __init__(self, redis: FakeRedis) -> None:
        self.state = _State(redis)


async def _call(
    redis: FakeRedis, path: str, *, method: str = "GET", status: int = 200, query: bytes = b""
) -> list[Any]:
    sent: list[Any] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"[]"})

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: Any) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "app": _App(redis),
    }
    await scale.ListLatencyMiddleware(inner)(scope, receive, send)
    return sent


def test_middleware_records_only_successful_list_gets() -> None:
    redis = FakeRedis()
    bank = "/api/v1/banking/transactions"
    asyncio.run(_call(redis, bank))
    asyncio.run(_call(redis, bank, query=b"offset=20000"))
    asyncio.run(_call(redis, bank, status=500))  # failed request: no sample
    asyncio.run(_call(redis, bank, method="POST"))  # not a list read
    asyncio.run(_call(redis, "/api/v1/contacts"))  # not measured
    assert sorted(redis.store) == [
        scale.LATENCY_PREFIX + "bank_list",
        scale.LATENCY_PREFIX + "bank_list_deep",
    ]
    stamp, _, millis = redis.store[scale.LATENCY_PREFIX + "bank_list"][0].partition(":")
    assert int(stamp) > 1_700_000_000
    assert float(millis) >= 0
    # no tenant, user or query value is stored with the sample
    assert all(v.count(":") == 1 for samples in redis.store.values() for v in samples)


def test_middleware_survives_a_redis_error_and_keeps_the_response() -> None:
    sent = asyncio.run(_call(FakeRedis(fail=True), "/api/v1/banking/transactions"))
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
    assert sent[0]["status"] == 200


def test_sample_list_is_capped() -> None:
    redis = FakeRedis()
    for n in range(scale.SAMPLE_CAP + 25):
        asyncio.run(scale.record_latency(redis, "bank_list", float(n)))  # type: ignore[arg-type]
    assert len(redis.store[scale.LATENCY_PREFIX + "bank_list"]) == scale.SAMPLE_CAP


# Demo data ---------------------------------------------------------------------------------------


def valid_iban(iban: str) -> bool:
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def test_demo_ibans_are_synthetic_and_valid() -> None:
    own = demo_seed.own_ibans()
    assert len(own) == 3
    assert len(set(own)) == 3
    counterparties = [demo_seed.synthetic_iban(n) for n in range(1, 201)]
    for iban in (*own, *counterparties):
        assert iban.startswith("DE")
        assert len(iban) == 22
        assert iban[4:12] == "00000000"
        assert valid_iban(iban)
    demo_seed.assert_synthetic_ibans([*own, *counterparties])


@pytest.mark.parametrize(
    "iban",
    [
        "DE02120300000000202051",  # documented example IBAN of a real bank
        "DE91100000000123456789",  # bank code of a real institute
        "DE89000000009000000000",  # wrong check digits
        "AT611904300234573201",  # not German
        "DE8900000000900000000",  # wrong length
    ],
)
def test_real_or_malformed_ibans_are_refused(iban: str) -> None:
    with pytest.raises(ValueError, match="synthetische"):
        demo_seed.assert_synthetic_ibans([iban])


def test_demo_statement_data_holds_only_synthetic_ibans_and_invented_names() -> None:
    from datetime import date

    parsed = demo_seed.build_statements(list(demo_seed.own_ibans()), date(2026, 10, 1))
    transactions = [t for s in parsed.statements for t in s.transactions]
    assert len(transactions) == 200
    demo_seed.assert_synthetic_ibans(
        [t.counterpart_iban for t in transactions if t.counterpart_iban]
        + [s.iban for s in parsed.statements]
    )
    names = {t.counterpart_name for t in transactions}
    assert all(n.startswith(("Max Beispiel", "Muster")) for n in names)
