"""AF24 (GAE-33): availability check against a real HTTP server on 127.0.0.1 (uvicorn in a
thread) instead of only a mock transport, plus the warning for missing deploy variables.
Only loopback addresses are contacted; the test refuses any other host."""

import asyncio
import logging
import socket
import threading
import time
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import SecretStr

from mhvp.core.config import Environment, Settings
from mhvp.platform import availability_probe as ap

pytestmark = pytest.mark.integration

LOOPBACK = "127.0.0.1"


def _only_loopback(url: str) -> str:
    assert urlsplit(url).hostname == LOOPBACK, f"AF24 test must only call {LOOPBACK}: {url}"
    return url


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOOPBACK, 0))
        return int(sock.getsockname()[1])


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/down")
    def down() -> JSONResponse:
        return JSONResponse({"status": "down"}, status_code=503)

    @app.get("/moved")
    def moved() -> RedirectResponse:
        return RedirectResponse("/ok")

    @app.get("/slow")
    def slow() -> dict[str, str]:
        time.sleep(1.5)
        return {"status": "late"}

    return app


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(_app(), host=LOOPBACK, port=port, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"
    try:
        yield f"http://{LOOPBACK}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_check_url_over_real_http(base_url: str) -> None:
    async def run() -> dict[str, ap.ProbeResult]:
        async with httpx.AsyncClient() as client:
            return {
                name: await ap.check_url(client, name, _only_loopback(base_url + path), 0.5)
                for name, path in (
                    ("ok", "/ok"),
                    ("down", "/down"),
                    ("moved", "/moved"),
                    ("slow", "/slow"),
                )
            }

    results = asyncio.run(run())
    assert results["ok"].ok
    assert results["ok"].status_code == 200
    assert results["ok"].latency_ms is not None
    assert not results["down"].ok
    assert results["down"].error_class == "http_status"
    assert results["down"].status_code == 503
    # a redirect does not count as available
    assert not results["moved"].ok
    assert results["moved"].status_code in (302, 307)
    assert not results["slow"].ok
    assert results["slow"].error_class == "timeout"


def test_check_url_closed_port_is_connect_error() -> None:
    url = _only_loopback(f"http://{LOOPBACK}:{_free_port()}/ok")

    async def run() -> ap.ProbeResult:
        async with httpx.AsyncClient() as client:
            return await ap.check_url(client, "api", url, 1.0)

    result = asyncio.run(run())
    assert not result.ok
    assert result.error_class == "connect_error"
    assert result.status_code is None
    assert result.latency_ms is None


def _settings(**urls: str | None) -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://x:y@127.0.0.1:5432/none"),
        redis_url=SecretStr("redis://127.0.0.1:6380/9"),
        **urls,  # type: ignore[arg-type]
    )


def test_missing_deploy_variables_are_reported(caplog: pytest.LogCaptureFixture) -> None:
    settings = _settings(availability_api_url="http://127.0.0.1:1/health")
    assert ap.missing_probe_urls(settings) == ["crm", "portal"]
    staging = settings.model_copy(update={"env": Environment.STAGING})
    ap._warned_missing = False
    with caplog.at_level(logging.INFO, logger=ap.log.name):
        ap.warn_missing_probe_urls(staging)
        ap.warn_missing_probe_urls(staging)  # second call stays silent (once per process)
    records = [r for r in caplog.records if "deploy variable" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "MHVP_AVAILABILITY_CRM_URL" in records[0].getMessage()
    assert "MHVP_AVAILABILITY_API_URL" not in records[0].getMessage()
    assert (
        ap.warn_missing_probe_urls(
            _settings(
                availability_api_url="http://127.0.0.1:1/a",
                availability_crm_url="http://127.0.0.1:1/b",
                availability_portal_url="http://127.0.0.1:1/c",
            )
        )
        == []
    )
    ap._warned_missing = False
