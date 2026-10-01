"""OpenTelemetry tracing (M9-02): off by default, spans and traceparent without network."""

import json
import re

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mhvp.core.logging import add_trace_context
from mhvp.core.middleware import CorrelationIdMiddleware
from mhvp.core.telemetry import (
    current_traceparent,
    instrument_app,
    setup_tracing,
    tracing_enabled,
    uninstrument_all,
)
from tests.conftest import make_settings

TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def _traced_app(exporter: InMemorySpanExporter) -> FastAPI:
    provider = setup_tracing(make_settings(), span_processor=SimpleSpanProcessor(exporter))
    assert provider is not None
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str | None]:
        ctx = trace.get_current_span().get_span_context()
        event = add_trace_context(None, "info", {})
        return {"trace_id": format(ctx.trace_id, "032x"), "log_trace_id": event.get("trace_id")}

    app.add_middleware(CorrelationIdMiddleware)
    instrument_app(app, provider)
    return app


def test_tracing_off_by_default() -> None:
    settings = make_settings()
    assert not tracing_enabled(settings)
    assert setup_tracing(settings) is None
    assert current_traceparent() is None
    assert add_trace_context(None, "info", {"event": "x"}) == {"event": "x"}


def test_endpoint_enables_tracing_provider() -> None:
    settings = make_settings(otel_endpoint="http://collector.invalid:4318")
    provider = setup_tracing(settings)
    assert provider is not None
    provider.shutdown()


@pytest.mark.anyio
async def test_request_creates_span_with_header_and_log_context() -> None:
    exporter = InMemorySpanExporter()
    app = _traced_app(exporter)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping?secret=1")
    body = response.json()
    header = response.headers["traceparent"]
    assert TRACEPARENT.match(header)
    assert header.split("-")[1] == body["trace_id"] == body["log_trace_id"]
    spans = exporter.get_finished_spans()
    assert any(format(s.context.trace_id, "032x") == body["trace_id"] for s in spans)
    assert "x-correlation-id" in response.headers
    assert "secret" not in json.dumps([dict(s.attributes or {}) for s in spans])


@pytest.mark.anyio
async def test_httpx_client_propagates_traceparent() -> None:
    exporter = InMemorySpanExporter()
    provider = setup_tracing(make_settings(), span_processor=SimpleSpanProcessor(exporter))
    assert provider is not None
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    HTTPXClientInstrumentor.instrument_client(client, tracer_provider=provider)
    with provider.get_tracer("t").start_as_current_span("outer") as outer:
        await client.get("http://upstream.invalid/x")
    await client.aclose()
    assert TRACEPARENT.match(seen["traceparent"])
    assert seen["traceparent"].split("-")[1] == format(outer.get_span_context().trace_id, "032x")
    uninstrument_all()
