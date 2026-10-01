"""Optional OpenTelemetry tracing (M9-02, section 16).

Off by default. Setting ``MHVP_OTEL_ENDPOINT`` (OTLP/HTTP, e.g. ``http://otel-collector:4318``)
enables spans for FastAPI, SQLAlchemy, Celery and outgoing httpx calls. W3C ``traceparent`` is
propagated to outgoing httpx requests and returned in the response header. Request bodies,
query strings and SQL parameters are not recorded as attributes (``enable_commenter`` and
statement parameters stay off), so personal data does not reach the collector.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span
from sqlalchemy.ext.asyncio import AsyncEngine

from mhvp.core.config import Settings

_PROBE_PATHS = "/api/v1/health/live,/api/v1/health/ready"


def tracing_enabled(settings: Settings) -> bool:
    return bool(settings.otel_endpoint)


def setup_tracing(
    settings: Settings, *, span_processor: SpanProcessor | None = None
) -> TracerProvider | None:
    """Build a tracer provider, or ``None`` when tracing is off.

    ``span_processor`` is for tests (in-memory exporter); it replaces the OTLP exporter.
    """
    if span_processor is None and not tracing_enabled(settings):
        return None
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": settings.otel_service_name, "service.version": settings.app_version}
        )
    )
    if span_processor is None:
        endpoint = (settings.otel_endpoint or "").rstrip("/")
        span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    provider.add_span_processor(span_processor)
    return provider


_URL_ATTRIBUTES = ("http.url", "http.target", "url.full", "url.query")


def _strip_query(span: Span, scope: dict[str, object]) -> None:
    """Query strings may carry personal data (section 16): record the path only."""
    if not span.is_recording():
        return
    path = str(scope.get("path", ""))
    server = scope.get("server")
    host = f"{server[0]}" if isinstance(server, tuple) else "localhost"
    attrs = getattr(span, "attributes", None) or {}
    for name in _URL_ATTRIBUTES:
        if name in attrs:
            span.set_attribute(name, path if name != "http.url" else f"http://{host}{path}")


def instrument_app(app: FastAPI, provider: TracerProvider | None) -> None:
    if provider is None:
        return
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=_PROBE_PATHS,
        server_request_hook=_strip_query,
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)


def instrument_engine(engine: AsyncEngine, provider: TracerProvider | None) -> None:
    if provider is None:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)


def instrument_celery(settings: Settings) -> TracerProvider | None:
    """Trace Celery tasks (producer and worker) and their httpx calls and SQL statements."""
    provider = setup_tracing(
        settings.model_copy(update={"otel_service_name": "mhvp-worker"})
        if settings.otel_service_name == "mhvp-api"
        else settings
    )
    if provider is None:
        return None
    CeleryInstrumentor().instrument(tracer_provider=provider)  # type: ignore[no-untyped-call]
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(tracer_provider=provider)
    return provider


def uninstrument_all() -> None:
    """Remove all instrumentation (tests)."""
    for instrumentor in (CeleryInstrumentor, HTTPXClientInstrumentor, SQLAlchemyInstrumentor):
        instrumentor().uninstrument()


def current_traceparent() -> str | None:
    """W3C ``traceparent`` of the active span, ``None`` when there is none."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    flags = format(int(ctx.trace_flags), "02x")
    return f"00-{format(ctx.trace_id, '032x')}-{format(ctx.span_id, '016x')}-{flags}"
