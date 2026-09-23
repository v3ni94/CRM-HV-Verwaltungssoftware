"""FastAPI application factory.

``uvicorn mhvp.main:app`` resolves ``app`` lazily (module ``__getattr__``), so importing this
module has no side effects and tests build their own app with :func:`create_app`.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from mhvp.core import health
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_app_engine
from mhvp.core.health import ReadinessCheck
from mhvp.core.logging import configure_logging
from mhvp.core.middleware import CorrelationIdMiddleware
from mhvp.core.problems import install_problem_handlers
from mhvp.core.release_gates import ClosedReleaseGateResolver, ReleaseGateResolver
from mhvp.core.storage import create_s3_client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

API_PREFIX = "/api/v1"


@dataclass(slots=True)
class Resources:
    engine: AsyncEngine
    redis: Redis
    s3: "S3Client | None"


ReadinessChecksFactory = Callable[[Settings, Resources], dict[str, ReadinessCheck]]


def default_readiness_checks(settings: Settings, resources: Resources) -> dict[str, ReadinessCheck]:
    return {
        "database": health.database_check(resources.engine),
        "database_role": health.database_role_check(resources.engine),
        "migrations": health.migrations_check(resources.engine, settings.alembic_config),
        "redis": health.redis_check(resources.redis),
        "object_storage": health.object_storage_check(settings, resources.s3),
    }


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks_factory: ReadinessChecksFactory | None = None,
    release_gate_resolver: ReleaseGateResolver | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    checks_factory = readiness_checks_factory or default_readiness_checks

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        timeout = settings.health_check_timeout_seconds
        resources = Resources(
            engine=create_app_engine(settings),
            redis=Redis.from_url(
                settings.redis_url.get_secret_value(),
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            ),
            s3=create_s3_client(settings) if settings.s3_configured else None,
        )
        app.state.resources = resources
        app.state.readiness_checks = checks_factory(settings, resources)
        try:
            yield
        finally:
            await resources.redis.aclose()
            await resources.engine.dispose()

    app = FastAPI(
        title="MH Verwaltungsplattform API",
        version=settings.app_version,
        description=(
            "Offene REST-API der MH Verwaltungsplattform. Fachbegriffe deutsch, Feldnamen "
            "englisch. Fehler als RFC 9457 Problem Details (application/problem+json)."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.release_gate_resolver = release_gate_resolver or ClosedReleaseGateResolver()
    install_problem_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.add_middleware(CorrelationIdMiddleware)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return create_app()
    raise AttributeError(name)
