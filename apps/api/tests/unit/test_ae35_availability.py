"""AE35 (GB16-02, AD10-02): own availability measurement without network and database.

Expected values by hand (March 2025 has 31 days = 44.640 minute checks):
* 340 failed checks, 240 of them inside an announced window: gross = 1 - 340/44.640 = 2215/2232
  = 99,2383512544... percent, rounded down to eight places 99,23835125 (target 99,5 missed);
  net = 44.300 / (44.640 - 240) = 443/444 = 99,7747747747... percent -> 99,77477477 (met).
* 223,2 minutes are the most the target allows in 44.640 minutes (0,5 percent)."""

from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from mhvp.platform import availability_probe as ap
from mhvp.worker import create_celery
from tests.conftest import make_settings

PROBE_TASK = "mhvp.platform.availability_probe"


def test_percent_rounds_down_and_never_overstates() -> None:
    assert ap.percent(44_300, 44_640) == Decimal("99.23835125")
    assert ap.percent(44_300, 44_400) == Decimal("99.77477477")
    # 2/3 rounds down, not up
    assert ap.percent(2, 3) == Decimal("66.66666666")
    assert ap.percent(0, 5) == Decimal("0E-8")
    assert ap.percent(5, 5) == Decimal("100")
    assert ap.percent(1, 0) is None


def test_month_figures_gross_and_net() -> None:
    figures = ap.month_figures(
        total=44_640, ok=44_300, maintenance=240, ok_maintenance=0, expected=44_640
    )
    assert figures.uptime_gross == Decimal("99.23835125")
    assert figures.uptime_net == Decimal("99.77477477")
    # Every check inside a window: nothing left for the net figure.
    only_window = ap.month_figures(
        total=240, ok=0, maintenance=240, ok_maintenance=0, expected=44_640
    )
    assert only_window.uptime_net is None
    with pytest.raises(ValueError, match="at least one check"):
        ap.month_figures(total=0, ok=0, maintenance=0, ok_maintenance=0, expected=10)


def test_switch_selects_the_rated_figure() -> None:
    gross, net = Decimal("99.23835125"), Decimal("99.77477477")
    coverage = Decimal("100")
    # Default (switch off): windows do not count, the net figure is rated.
    assert ap.counted_percent(gross, net, counts_maintenance=False) == net
    assert ap.rated(ap.counted_percent(gross, net, False), coverage) is True
    # Switch on: windows count as downtime, the gross figure is rated.
    assert ap.counted_percent(gross, net, counts_maintenance=True) == gross
    assert ap.rated(ap.counted_percent(gross, net, True), coverage) is False
    # Exactly the target is met, one hundred millionth below is not.
    assert ap.rated(Decimal("99.5"), coverage) is True
    assert ap.rated(Decimal("99.49999999"), coverage) is False
    # No figure or too little coverage: no rating.
    assert ap.rated(None, coverage) is None
    assert ap.rated(Decimal("100"), Decimal("94.999")) is None
    assert ap.rated(Decimal("100"), Decimal("95")) is True


def test_coverage_is_capped_and_rounded_down() -> None:
    assert ap.coverage_percent(44_640, 44_640) == Decimal("100.000")
    assert ap.coverage_percent(50_000, 44_640) == Decimal("100.000")
    assert ap.coverage_percent(10_000, 43_200) == Decimal("23.148")
    assert ap.coverage_percent(5, 0) == Decimal("0.000")


def test_month_bounds_utc() -> None:
    from datetime import UTC, date, datetime

    start, end = ap.month_bounds(date(2025, 2, 1))
    assert (end - start).total_seconds() == 2_419_200
    assert start == datetime(2025, 2, 1, tzinfo=UTC)
    assert ap.slot_of(datetime(2025, 3, 1, 10, 7, 42, 999, tzinfo=UTC)) == datetime(
        2025, 3, 1, 10, 7, tzinfo=UTC
    )


def test_url_settings_validated_and_blank_means_off() -> None:
    off = make_settings(availability_api_url="  ", availability_crm_url="")
    assert off.availability_api_url is None
    assert off.availability_probe_urls == {}
    on = make_settings(
        availability_api_url="https://api.example.test/api/v1/health/ready",
        availability_portal_url=" http://portal:3001/api/health ",
    )
    assert on.availability_probe_urls == {
        "api": "https://api.example.test/api/v1/health/ready",
        "portal": "http://portal:3001/api/health",
    }
    for bad in ("ftp://x/y", "api.example.test/health", "https://a b/health"):
        with pytest.raises(ValidationError):
            make_settings(availability_crm_url=bad)
    with pytest.raises(ValidationError):
        make_settings(availability_retention_days=10)
    with pytest.raises(ValidationError):
        make_settings(availability_timeout_seconds=0)


def test_url_host_hides_path_and_credentials() -> None:
    assert ap.url_host("https://user:secret@api.example.test:8443/x?token=abc") == (
        "api.example.test:8443"
    )
    assert ap.url_host("http://web-crm:3000/api/health") == "web-crm:3000"
    assert ap.url_host(None) is None
    assert ap.url_host("not a url") is None


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


@pytest.mark.asyncio
async def test_check_url_classifies_results_without_network() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path == "/ok":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/not-ready":
            return httpx.Response(503, json={"status": "fail"})
        if path == "/moved":
            return httpx.Response(301, headers={"location": "https://other.example.test/"})
        if path == "/slow":
            raise httpx.ReadTimeout("secret detail", request=request)
        if path == "/down":
            raise httpx.ConnectError("secret detail", request=request)
        if path == "/proto":
            raise httpx.RemoteProtocolError("secret detail", request=request)
        raise RuntimeError("secret detail")

    async with _client(httpx.MockTransport(respond)) as client:
        results = {
            name: await ap.check_url(client, "api", f"https://h.example.test/{name}", 5.0)
            for name in ("ok", "not-ready", "moved", "slow", "down", "proto", "boom")
        }
    assert (results["ok"].ok, results["ok"].status_code, results["ok"].error_class) == (
        True,
        200,
        None,
    )
    assert results["not-ready"].ok is False
    assert results["not-ready"].error_class == "http_status"
    assert results["not-ready"].status_code == 503
    # A redirect is not an answer of the health endpoint and is not followed.
    assert (results["moved"].ok, results["moved"].error_class) == (False, "http_status")
    assert results["slow"].error_class == "timeout"
    assert results["down"].error_class == "connect_error"
    assert results["proto"].error_class == "http_error"
    assert results["boom"].error_class == "error"
    for name in ("slow", "down", "proto", "boom"):
        assert results[name].ok is False
        assert results[name].status_code is None
        assert results[name].latency_ms is None
    # Neither the URL nor the exception text ends up in the stored failure class.
    for result in results.values():
        assert "secret" not in (result.error_class or "")
        assert "h.example.test" not in (result.error_class or "")
    # Every request went to the mock transport, none to a real host.
    assert len(seen) == 7


@pytest.mark.asyncio
async def test_run_probes_without_urls_does_nothing() -> None:
    called: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        return httpx.Response(200)

    async with _client(httpx.MockTransport(respond)) as client:
        assert await ap.run_probes_once(make_settings(), client=client) == {}
    assert called == []


def test_beat_plan_minute_check_only_with_urls() -> None:
    off = create_celery(make_settings(), set_as_current=False)
    assert "platform-availability-probe" not in off.conf.beat_schedule
    # Evaluation and retention purge run either way (no network, old points need handling).
    assert off.conf.beat_schedule["platform-availability-evaluate"]["task"] == (
        "mhvp.platform.availability_evaluate"
    )
    assert off.conf.beat_schedule["platform-availability-purge"]["task"] == (
        "mhvp.platform.availability_purge"
    )

    on = create_celery(
        make_settings(availability_portal_url="http://web-portal:3001/api/health"),
        set_as_current=False,
    )
    entry = on.conf.beat_schedule["platform-availability-probe"]
    assert entry["task"] == PROBE_TASK
    assert entry["schedule"] == 60.0
    assert entry["options"]["queue"] == "io"
    assert entry["options"]["expires"] < 60
    on.loader.import_default_modules()
    for name in (
        PROBE_TASK,
        "mhvp.platform.availability_evaluate",
        "mhvp.platform.availability_purge",
    ):
        assert name in on.tasks
